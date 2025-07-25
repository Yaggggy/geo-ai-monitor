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
SENTINEL_HUB_CLIENT_ID = os.getenv("SENTINEL_HUB_CLIENT_ID") # This should be your Configuration ID
SENTINEL_HUB_CLIENT_SECRET = os.getenv("SENTINEL_HUB_CLIENT_SECRET") # This is for OAuth, not directly in WMS URL
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379") # Default to local Redis

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
        redis_client = None # Set to None if connection fails

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
    start_date: str # YYYY-MM-DD (will be YYYY-01-01 from frontend)
    end_date: str   # YYYY-MM-DD (will be YYYY-01-01 from frontend)

class GeoAnalysisResponse(BaseModel):
    ai_response: str
    image_url_1: Optional[str] = None # Still return URLs for frontend display
    image_url_2: Optional[str] = None
    cached: bool = False # Indicate if response was from cache

# --- Sentinel Hub Authentication ---
async def get_sentinel_hub_token():
    global SENTINEL_HUB_TOKEN, TOKEN_EXPIRY
    if SENTINEL_HUB_TOKEN and TOKEN_EXPIRY and TOKEN_EXPIRY > datetime.datetime.now() + datetime.timedelta(minutes=5):
        return SENTINEL_HUB_TOKEN

    if not SENTINEL_HUB_CLIENT_ID or not SENTINEL_HUB_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Sentinel Hub Client ID or Secret not configured.")

    token_url = "https://services.sentinel-hub.com/oauth/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "client_credentials",
        "client_id": SENTINEL_HUB_CLIENT_ID, # This is the OAuth Client ID
        "client_secret": SENTINEL_HUB_CLIENT_SECRET
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(token_url, headers=headers, data=data, timeout=10.0)
            response.raise_for_status()
            token_data = response.json()
            SENTINEL_HUB_TOKEN = token_data["access_token"]
            # Set expiry a bit before actual expiry to refresh proactively
            TOKEN_EXPIRY = datetime.datetime.now() + datetime.timedelta(seconds=token_data["expires_in"] - 60)
            return SENTINEL_HUB_TOKEN
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"Network error fetching Sentinel Hub token: {exc}")
    except httpx.HTTPStatusError as exc:
        print(f"Sentinel Hub Token Error: {exc.response.text}")
        raise HTTPException(status_code=exc.response.status_code, detail=f"Sentinel Hub authentication error: {exc.response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error fetching Sentinel Hub token: {e}")

# --- Sentinel Hub Image Fetching ---
async def get_sentinel_image_data(bbox: BoundingBox, date: str, token: str) -> tuple[str, str]:
    # This uses Sentinel Hub's WMS service to get a direct image URL.
    # We'll request a true color (B04, B03, B02) image.

    # Define the bounding box string in WMS order (minx, miny, maxx, maxy)
    bbox_str = f"{bbox.west},{bbox.south},{bbox.east},{bbox.north}"

    # Sentinel-2 L2A (Level-2A) True Color (B4,B3,B2)
    layer_id = "TRUE_COLOR"

    width = 512
    height = 512
    image_format = "image/jpeg"

    # IMPORTANT: The SENTINEL_HUB_CLIENT_ID used here for WMS is actually the CONFIGURATION ID (Instance ID)
    # from your Sentinel Hub Dashboard -> Configurations.
    request_url = (
        f"https://services.sentinel-hub.com/ogc/wms/{SENTINEL_HUB_CLIENT_ID}?"
        f"REQUEST=GetMap&SERVICE=WMS&VERSION=1.3.0&LAYERS={layer_id}&FORMAT={image_format}&CRS=EPSG:4326&WIDTH={width}&HEIGHT={height}&BBOX={bbox_str}&TIME={date}/{date}"
    )

    # --- DEBUGGING PRINT FOR SENTINEL HUB URL ---
    print(f"\n--- Sentinel Hub Request URL ---")
    print(f"Using Sentinel Hub Configuration ID: {SENTINEL_HUB_CLIENT_ID}")
    print(f"Full WMS URL: {request_url}")
    print(f"--- End Sentinel Hub Request URL ---\n")
    # --- END DEBUGGING PRINT ---

    try:
        async with httpx.AsyncClient() as client:
            # Fetch the actual image data
            image_response = await client.get(request_url, timeout=30.0)
            image_response.raise_for_status() # Raise an error for bad responses

            # Encode image data to Base64
            base64_encoded_image = base64.b64encode(image_response.content).decode('utf-8')
            return base64_encoded_image, request_url # Return base64 and the original URL for display
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"Network error fetching Sentinel Hub image from {request_url}: {exc}")
    except httpx.HTTPStatusError as exc:
        print(f"Sentinel Hub Image Fetch Error (HTTP {exc.response.status_code}): {exc.response.text}") # Print full response text
        raise HTTPException(status_code=exc.response.status_code, detail=f"Sentinel Hub image error from {request_url}: {exc.response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error fetching Sentinel Hub image: {e}")


# --- Main AI Analysis Endpoint ---
@app.post("/generate-ai-response/", response_model=GeoAnalysisResponse)
async def generate_ai_response(request: GeoAnalysisRequest):
    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Google API Key not configured.")
    if not SENTINEL_HUB_CLIENT_ID or not SENTINEL_HUB_CLIENT_SECRET:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Sentinel Hub Client ID or Secret not configured.")

    # Define the hardcoded prompt for Gemini
    gemini_fixed_prompt = (
        "Analyze the provided satellite image(s) of this geographical area. "
        "If two images are provided, compare them and describe any significant changes related to "
        "urban development, deforestation, agricultural expansion, water body changes, "
        "or other notable human activities or natural shifts. Provide a concise summary of your observations."
    )

    # Generate a cache key based on request parameters (excluding prompt_text)
    cache_key_parts = [
        str(request.bbox.north), str(request.bbox.south),
        str(request.bbox.east), str(request.bbox.west),
        request.start_date, request.end_date,
        str(hash(gemini_fixed_prompt)) # Include hash of fixed prompt for cache uniqueness
    ]
    cache_key = "geo_ai_response:" + "_".join(cache_key_parts)

    # --- 1. Check Redis Cache ---
    if redis_client:
        try:
            cached_response = await redis_client.get(cache_key)
            if cached_response:
                print(f"Cache hit for key: {cache_key}")
                response_data = json.loads(cached_response)
                return GeoAnalysisResponse(**response_data, cached=True)
        except Exception as e:
            print(f"Redis cache read error: {e}")
            # Continue without cache if there's an error

    # Variables to store base64 encoded images and their original URLs
    base64_image_1 = None
    base64_image_2 = None
    original_image_url_1 = None
    original_image_url_2 = None

    # --- 2. Fetch Sentinel Hub Images (Base64) ---
    try:
        sh_token = await get_sentinel_hub_token() # This uses the OAuth Client ID/Secret
        
        # Fetch image for start_date using the Configuration ID
        base64_image_1, original_image_url_1 = await get_sentinel_image_data(request.bbox, request.start_date, sh_token)

        # If end_date is different from start_date, fetch a second image for comparison
        if request.start_date != request.end_date:
            base64_image_2, original_image_url_2 = await get_sentinel_image_data(request.bbox, request.end_date, sh_token)

    except HTTPException as e:
        print(f"Sentinel Hub image fetching failed ({e.detail}).")
        raise HTTPException(status_code=e.status_code, detail=f"Failed to fetch satellite images: {e.detail}")


    # --- 3. Prepare Gemini API Request ---
    contents_parts = []
    gemini_model = "gemini-pro" # Default to text model

    # Add the hardcoded prompt as the first part
    contents_parts.append({"text": gemini_fixed_prompt})

    # Add image parts using inlineData (Base64)
    if base64_image_1:
        gemini_model = "gemini-pro-vision"
        contents_parts.append({"inlineData": {"mimeType": "image/jpeg", "data": base64_image_1}})
        if base64_image_2:
            contents_parts.append({"inlineData": {"mimeType": "image/jpeg", "data": base64_image_2}})
    else:
        # This fallback should ideally not be hit if images are mandatory
        contents_parts.insert(0, {"text": f"Regarding the area defined by BBOX: {request.bbox.west},{request.bbox.south},{request.bbox.east},{request.bbox.north} and dates {request.start_date} to {request.end_date}:"})


    payload = {"contents": [{"parts": contents_parts}]}
    gemini_api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={GOOGLE_API_KEY}"

    # --- DEBUGGING PRINTS ---
    print(f"\n--- Gemini API Request Details ---")
    print(f"Model: {gemini_model}")
    print(f"API URL: {gemini_api_url}")
    # Print only a snippet of base64 data to avoid flooding console
    debug_payload_contents = []
    for part in payload['contents'][0]['parts']:
        if 'inlineData' in part and 'data' in part['inlineData']:
            debug_payload_contents.append({
                "inlineData": {
                    "mimeType": part['inlineData']['mimeType'],
                    "data_snippet": part['inlineData']['data'][:50] + "..." # Show only first 50 chars
                }
            })
        else:
            debug_payload_contents.append(part)
    print(f"Payload (contents): {json.dumps([{'parts': debug_payload_contents}], indent=2)}")
    print(f"--- End Request Details ---\n")
    # --- END DEBUGGING PRINTS ---

    # --- 4. Call Gemini API ---
    try:
        async with httpx.AsyncClient() as client:
            gemini_response = await client.post(
                gemini_api_url,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=120.0 # Increased timeout for Base64 image transfer
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
                image_url_1=original_image_url_1, # Return original URLs for frontend display
                image_url_2=original_image_url_2,
                cached=False
            )

            # --- 5. Store in Redis Cache ---
            if redis_client:
                try:
                    await redis_client.set(cache_key, final_response.model_dump_json(), ex=3600) # Cache for 1 hour
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

