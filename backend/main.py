# backend/main.py

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import os
import httpx
import json
from dotenv import load_dotenv
from typing import List, Optional
import redis.asyncio as redis
import datetime
import base64

# Load environment variables from .env file
load_dotenv()

# --- DEBUGGING PRINTS FOR ENV VARIABLES ---
print("\n--- Environment Variable Check ---")
print(f"GOOGLE_API_KEY: {'SET' if os.getenv('GOOGLE_API_KEY') else 'NOT SET'}")
print(f"SENTINEL_HUB_OAUTH_CLIENT_ID: {'SET' if os.getenv('SENTINEL_HUB_OAUTH_CLIENT_ID') else 'NOT SET'}")
print(f"SENTINEL_HUB_OAUTH_CLIENT_SECRET: {'SET' if os.getenv('SENTINEL_HUB_OAUTH_CLIENT_SECRET') else 'NOT SET'}")
print(f"SENTINEL_HUB_CONFIG_ID: {'SET' if os.getenv('SENTINEL_HUB_CONFIG_ID') else 'NOT SET'}") # Still used for WMS if needed, but not directly in Process API
print(f"REDIS_URL: {'SET' if os.getenv('REDIS_URL') else 'NOT SET'}")
print("--- End Environment Variable Check ---\n")
# --- END DEBUGGING PRINTS ---


# Initialize FastAPI app
app = FastAPI(
    title="Geo AI Vision Explorer Backend",
    description="Backend for Geo AI Explorer, handling Sentinel Hub image fetching, Redis caching, and Gemini AI interactions.",
    version="1.0.0"
)

# --- CORS Configuration ---
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    # IMPORTANT FOR DEPLOYMENT: Add your frontend's production URL here when deploying
    # e.g., "https://your-geo-ai-frontend.vercel.app"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Environment Variables ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

SENTINEL_HUB_OAUTH_CLIENT_ID = os.getenv("SENTINEL_HUB_OAUTH_CLIENT_ID")
SENTINEL_HUB_OAUTH_CLIENT_SECRET = os.getenv("SENTINEL_HUB_OAUTH_CLIENT_SECRET")
SENTINEL_HUB_CONFIG_ID = os.getenv("SENTINEL_HUB_CONFIG_ID") # Kept for consistency and potential future use

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Sentinel Hub OAuth token and expiration
SENTINEL_HUB_TOKEN = None
TOKEN_EXPIRY = None

# Redis client initialization (will connect on startup)
redis_client: Optional[redis.Redis] = None

# --- Lifespan Events for Redis Connection ---
@app.on_event("startup")
async def startup_event():
    global redis_client
    try:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        await redis_client.ping()
        print("Connected to Redis successfully!")
    except Exception as e:
        print(f"Could not connect to Redis: {e}")
        redis_client = None

@app.on_event("shutdown")
async def shutdown_event():
    if redis_client:
        await redis_client.close()
        print("Redis connection closed.")

# --- Pydantic Models ---
class BoundingBox(BaseModel):
    north: float
    south: float
    east: float
    west: float

class GeoAnalysisRequest(BaseModel):
    bbox: BoundingBox
    start_date: str # YYYY-MM-DD
    end_date: str   # YYYY-MM-DD

class GeoAnalysisResponse(BaseModel):
    ai_response: str
    image_url_1: Optional[str] = None
    image_url_2: Optional[str] = None
    cached: bool = False

# --- Sentinel Hub Authentication ---
async def get_sentinel_hub_token():
    global SENTINEL_HUB_TOKEN, TOKEN_EXPIRY
    if SENTINEL_HUB_TOKEN and TOKEN_EXPIRY and TOKEN_EXPIRY > datetime.datetime.now() + datetime.timedelta(minutes=5):
        return SENTINEL_HUB_TOKEN

    if not SENTINEL_HUB_OAUTH_CLIENT_ID or not SENTINEL_HUB_OAUTH_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Sentinel Hub OAuth Client ID or Secret not configured.")

    token_url = "https://services.sentinel-hub.com/oauth/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "client_credentials",
        "client_id": SENTINEL_HUB_OAUTH_CLIENT_ID,
        "client_secret": SENTINEL_HUB_OAUTH_CLIENT_SECRET
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(token_url, headers=headers, data=data, timeout=10.0)
            response.raise_for_status()
            token_data = response.json()
            SENTINEL_HUB_TOKEN = token_data["access_token"]
            TOKEN_EXPIRY = datetime.datetime.now() + datetime.timedelta(seconds=token_data["expires_in"] - 60)
            return SENTINEL_HUB_TOKEN
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"Network error fetching Sentinel Hub token: {exc}")
    except httpx.HTTPStatusError as exc:
        print(f"Sentinel Hub Token Error: {exc.response.text}")
        raise HTTPException(status_code=exc.response.status_code, detail=f"Sentinel Hub authentication error: {exc.response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error fetching Sentinel Hub token: {e}")

# --- Sentinel Hub Image Fetching (Using Process API) ---
async def get_sentinel_image_data(bbox: BoundingBox, date: str, token: str) -> tuple[str, str]:
    process_url = "https://services.sentinel-hub.com/api/v1/process"
    
    # Evalscript for True Color (B04, B03, B02) with improved scaling and clamping
    # Increased factor for brighter images, added more robust clamping
    evalscript = """
        //VERSION=3
        function setup() {
            return {
                input: ["B04", "B03", "B02"],
                output: { bands: 3, sampleType: "UINT8" } // Output as 8-bit unsigned integer
            };
        }

        function evaluatePixel(sample) {
            // Factor for brightness adjustment. Try values from 2.5 to 3.5 or even higher.
            const factor = 3.0; // Increased from 2.5 for potentially brighter images

            // Clamp values between 0 and 1 before final scaling to prevent over/underflow
            let red = Math.min(Math.max(sample.B04 / 10000 * factor, 0), 1);
            let green = Math.min(Math.max(sample.B03 / 10000 * factor, 0), 1);
            let blue = Math.min(Math.max(sample.B02 / 10000 * factor, 0), 1);

            return [
                red * 255,
                green * 255,
                blue * 255
            ];
        }
    """

    # Calculate a wider time range (e.g., +/- 6 months around the target date)
    # This significantly increases the chance of finding a cloud-free image.
    try:
        target_date_obj = datetime.datetime.strptime(date, "%Y-%m-%d").date()
        # Search for images within the entire year of the target date
        time_range_from = f"{target_date_obj.year}-01-01T00:00:00Z"
        time_range_to = f"{target_date_obj.year}-12-31T23:59:59Z"
    except ValueError:
        # Fallback if date parsing fails, use a very wide default range
        time_range_from = "2015-01-01T00:00:00Z" # Start of Sentinel-2 data
        time_range_to = datetime.date.today().isoformat() + "T23:59:59Z" # Today
        print(f"Warning: Date parsing failed for {date}. Using very wide default range.")


    # Define the payload for the Process API request
    payload = {
        "input": {
            "bounds": {
                "bbox": [bbox.west, bbox.south, bbox.east, bbox.north],
                "properties": {
                    "crs": "http://www.opengis.net/def/crs/EPSG/0/4326"
                }
            },
            "data": [{
                "type": "sentinel-2-l2a", # Sentinel-2 Level 2A data
                "dataFilter": {
                    "timeRange": {
                        "from": time_range_from,
                        "to": time_range_to
                    },
                    "mosaickingOrder": "leastCC", # Get the least cloudy image within the time range
                    "maxcc": 30 # Max Cloud Coverage: Increased to 30% to allow more data, adjust as needed (e.g., 50, 80)
                }
            }]
        },
        "output": {
            "width": 512,
            "height": 512,
            "responses": [{
                "identifier": "default",
                "format": {"type": "image/jpeg"}
            }]
        },
        "evalscript": evalscript
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # --- DEBUGGING PRINT FOR SENTINEL HUB PROCESS API REQUEST ---
    print(f"\n--- Sentinel Hub Process API Request ---")
    print(f"URL: {process_url}")
    print(f"Headers: {headers}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    print(f"--- End Sentinel Hub Process API Request ---\n")
    # --- END DEBUGGING PRINT ---

    try:
        async with httpx.AsyncClient() as client:
            image_response = await client.post(process_url, headers=headers, json=payload, timeout=60.0) # Increased timeout
            image_response.raise_for_status()

            base64_encoded_image = base64.b64encode(image_response.content).decode('utf-8')
            display_url = f"data:image/jpeg;base64,{base64_encoded_image}"
            print(f"Successfully fetched image for {date} via Process API. Size: {len(base64_encoded_image)} bytes (Base64).")
            return base64_encoded_image, display_url
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"Network error fetching Sentinel Hub image from Process API: {exc}")
    except httpx.HTTPStatusError as exc:
        print(f"Sentinel Hub Process API Error (HTTP {exc.response.status_code}): {exc.response.text}")
        # If the error is 400 and indicates no data, provide a more specific message
        if exc.response.status_code == 400 and "No data available" in exc.response.text:
             raise HTTPException(status_code=400, detail=f"No cloud-free Sentinel-2 L2A data available for the selected area and time range (maxcc={payload['input']['data'][0]['dataFilter']['maxcc']}%). Try a different date or a larger maxcc.")
        raise HTTPException(status_code=exc.response.status_code, detail=f"Sentinel Hub Process API error: {exc.response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error fetching Sentinel Hub image: {e}")


# --- Main AI Analysis Endpoint ---
@app.post("/generate-ai-response/", response_model=GeoAnalysisResponse)
async def generate_ai_response(request: GeoAnalysisRequest):
    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Google API Key not configured.")
    if not SENTINEL_HUB_OAUTH_CLIENT_ID or not SENTINEL_HUB_OAUTH_CLIENT_SECRET: # CONFIG_ID not directly needed for Process API auth
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Sentinel Hub OAuth Client ID/Secret not fully configured.")

    gemini_fixed_prompt = (
        "Analyze the provided satellite image(s) of this geographical area. "
        "If two images are provided, compare them and describe any significant changes related to "
        "urban development, deforestation, agricultural expansion, water body changes, "
        "or other notable human activities or natural shifts. Provide a concise summary of your observations."
    )

    cache_key_parts = [
        str(request.bbox.north), str(request.bbox.south),
        str(request.bbox.east), str(request.bbox.west),
        request.start_date, request.end_date,
        str(hash(gemini_fixed_prompt))
    ]
    cache_key = "geo_ai_response:" + "_".join(cache_key_parts)

    if redis_client:
        try:
            cached_response = await redis_client.get(cache_key)
            if cached_response:
                print(f"Cache hit for key: {cache_key}")
                response_data = json.loads(cached_response)
                return GeoAnalysisResponse(**response_data, cached=True)
        except Exception as e:
            print(f"Redis cache read error: {e}")

    base64_image_1 = None
    base64_image_2 = None
    original_image_url_1 = None
    original_image_url_2 = None

    try:
        sh_token = await get_sentinel_hub_token()
        
        base64_image_1, original_image_url_1 = await get_sentinel_image_data(request.bbox, request.start_date, sh_token)

        if request.start_date != request.end_date:
            base64_image_2, original_image_url_2 = await get_sentinel_image_data(request.bbox, request.end_date, sh_token)

    except HTTPException as e:
        print(f"Sentinel Hub image fetching failed ({e.detail}).")
        raise HTTPException(status_code=e.status_code, detail=f"Failed to fetch satellite images: {e.detail}")


    contents_parts = []
    gemini_model = "gemini-1.5-flash-latest"

    contents_parts.append({"text": gemini_fixed_prompt})

    if base64_image_1:
        contents_parts.append({"inlineData": {"mimeType": "image/jpeg", "data": base64_image_1}})
        if base64_image_2:
            contents_parts.append({"inlineData": {"mimeType": "image/jpeg", "data": base64_image_2}})
    else:
        contents_parts.insert(0, {"text": f"Regarding the area defined by BBOX: {request.bbox.west},{request.bbox.south},{request.bbox.east},{request.bbox.north} and dates {request.start_date} to {request.end_date}:"})


    payload = {"contents": [{"parts": contents_parts}]}
    gemini_api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={GOOGLE_API_KEY}"

    print(f"\n--- Gemini API Request Details ---")
    print(f"Model: {gemini_model}")
    print(f"API URL: {gemini_api_url}")
    debug_payload_contents = []
    for part in payload['contents'][0]['parts']:
        if 'inlineData' in part and 'data' in part['inlineData']:
            debug_payload_contents.append({
                "inlineData": {
                    "mimeType": part['inlineData']['mimeType'],
                    "data_snippet": part['inlineData']['data'][:50] + "..."
                }
            })
        else:
            debug_payload_contents.append(part)
    print(f"Payload (contents): {json.dumps([{'parts': debug_payload_contents}], indent=2)}")
    print(f"--- End Request Details ---\n")

    try:
        async with httpx.AsyncClient() as client:
            gemini_response = await client.post(
                gemini_api_url,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=120.0
            )
            gemini_response.raise_for_status()
            gemini_result = gemini_response.json()

            ai_text = ""
            if gemini_result.get("candidates") and len(gemini_result["candidates"]) > 0 and \
               gemini_result["candidates"][0].get("content") and \
               gemini_result["candidates"][0]["content"].get("parts") and \
               len(gemini_result["candidates"][0]["content"]["parts"]) > 0:
                ai_text = gemini_result["candidates"][0]["content"]["parts"][0].get("text", "")
            else:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="AI response content is empty or malformed.")

            final_response = GeoAnalysisResponse(
                ai_response=ai_text,
                image_url_1=original_image_url_1,
                image_url_2=original_image_url_2,
                cached=False
            )

            if redis_client:
                try:
                    await redis_client.set(cache_key, final_response.model_dump_json(), ex=3600)
                    print(f"Cache set for key: {cache_key}")
                except Exception as e:
                    print(f"Redis cache write error: {e}")

            return final_response

    except httpx.RequestError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Network error communicating with Gemini API: {exc}. Ensure image URLs are publicly accessible.")
    except httpx.HTTPStatusError as exc:
        print(f"Error response from Gemini API: {exc.response.text}")
        raise HTTPException(status_code=exc.response.status_code, detail=f"Gemini API error: {exc.response.text}. Check API key permissions or image content.")
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to decode JSON response from Gemini API.")
    except Exception as e:
        print(f"An unexpected error occurred during AI analysis: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {e}. Check server logs.")

