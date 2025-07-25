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
import asyncio # For running synchronous code in async context

# Import sentinelhub-py components
from sentinelhub import SHConfig, BBox, CRS, MimeType, SentinelHubRequest, DataCollection, bbox_to_dimensions
from PIL import Image # For image processing (converting to JPEG bytes)
from io import BytesIO # For handling image bytes in memory

# Load environment variables from .env file
load_dotenv()

# --- DEBUGGING PRINTS FOR ENV VARIABLES ---
# These prints will show you if your .env variables are being read correctly on startup
print("\n--- Environment Variable Check ---")
print(f"GOOGLE_API_KEY: {'SET' if os.getenv('GOOGLE_API_KEY') else 'NOT SET'}")
print(f"SH_CLIENT_ID: {'SET' if os.getenv('SH_CLIENT_ID') else 'NOT SET'}")
print(f"SH_CLIENT_SECRET: {'SET' if os.getenv('SH_CLIENT_SECRET') else 'NOT SET'}")
print(f"INSTANCE_ID: {'SET' if os.getenv('INSTANCE_ID') else 'NOT SET'}")
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

# --- Environment Variables (read again for direct use) ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
SH_CLIENT_ID = os.getenv("SH_CLIENT_ID")
SH_CLIENT_SECRET = os.getenv("SH_CLIENT_SECRET")
INSTANCE_ID = os.getenv("INSTANCE_ID") # Sentinel Hub Configuration ID

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# --- Sentinel Hub Configuration (for sentinelhub-py) ---
sh_config = SHConfig()
sh_config.sh_client_id = SH_CLIENT_ID
sh_config.sh_client_secret = SH_CLIENT_SECRET
sh_config.instance_id = INSTANCE_ID # Set the instance ID here (used by some sentinelhub-py functions)

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

# --- Sentinel Hub Image Fetching (Using sentinelhub-py Process API) ---
async def get_sentinel_image_data(bbox: BoundingBox, date: str) -> tuple[str, str]:
    # Validate sentinelhub-py config
    if not sh_config.sh_client_id or not sh_config.sh_client_secret:
        raise HTTPException(status_code=500, detail="Sentinel Hub OAuth Client ID/Secret not configured in backend.")

    # Convert Pydantic BBox to sentinelhub.BBox
    sh_bbox = BBox(bbox=[bbox.west, bbox.south, bbox.east, bbox.north], crs=CRS.WGS84)
    
    # Define image resolution (10m for Sentinel-2)
    resolution_meters = 10
    size = bbox_to_dimensions(sh_bbox, resolution=resolution_meters)

    # Evalscript for True Color (B04, B03, B02) with basic scaling for visual output
    # This evalscript is from the user's working code, adapted for general use.
    evalscript = """
        //VERSION=3
        function setup() {
            return {
                input: ["B04", "B03", "B02"],
                output: { bands: 3, sampleType: "UINT8" } // Output as 8-bit unsigned integer for JPEG
            };
        }

        function evaluatePixel(sample) {
            // Apply a simple scaling for visual brightness. Adjust 'factor' as needed (e.g., 2.5, 3.0, 3.5).
            const factor = 2.5; 
            return [
                sample.B04 * factor,
                sample.B03 * factor,
                sample.B02 * factor
            ];
        }
    """

    # Calculate a time range for the request (e.g., entire year of the target date)
    # This significantly increases the chance of finding a cloud-free image.
    try:
        target_year = datetime.datetime.strptime(date, "%Y-%m-%d").year
        time_interval_from = f"{target_year}-01-01T00:00:00Z"
        time_interval_to = f"{target_year}-12-31T23:59:59Z"
    except ValueError:
        # Fallback if date parsing fails, use a very wide default range
        time_interval_from = "2015-01-01T00:00:00Z" # Start of Sentinel-2 data
        time_interval_to = datetime.date.today().isoformat() + "T23:59:59Z" # Today
        print(f"Warning: Date parsing failed for {date}. Using very wide default range.")


    request = SentinelHubRequest(
        data_folder=".", # Data will be processed in memory, not saved to disk by default
        evalscript=evalscript,
        input_data=[
            SentinelHubRequest.input_data(
                data_collection=DataCollection.SENTINEL2_L1C, # Changed from L2A to L1C
                time_interval=(time_interval_from, time_interval_to),
                mosaicking_order="leastCC", # Get the least cloudy image within the time range
                maxcc=0.30 # Max Cloud Coverage: Changed to 0.30 (30%) as a float between 0 and 1
            )
        ],
        responses=[
            SentinelHubRequest.output_response("default", MimeType.JPG) # CRITICAL FIX: Changed from MimeType.JPEG to MimeType.JPG
        ],
        bbox=sh_bbox,
        size=size,
        config=sh_config # Pass the global SHConfig object
    )

    # --- DEBUGGING PRINT FOR SENTINEL HUB PROCESS API REQUEST ---
    print(f"\n--- Sentinel Hub Process API Request (via sentinelhub-py) ---")
    print(f"Data Collection: {DataCollection.SENTINEL2_L1C.name}") # Reflects the change
    print(f"Time Interval: {time_interval_from} to {time_interval_to}")
    print(f"BBOX: {str(sh_bbox)}") # FIX: Changed sh_bbox.wgs84_str() to str(sh_bbox)
    print(f"Evalscript (snippet): {evalscript[:200]}...")
    print(f"--- End Sentinel Hub Process API Request ---\n")
    # --- END DEBUGGING PRINT ---

    try:
        # Run the synchronous get_data() call in a separate thread
        image_data_list = await asyncio.to_thread(request.get_data)
        
        if not image_data_list or len(image_data_list) == 0:
            raise HTTPException(status_code=400, detail=f"No cloud-free Sentinel-2 L1C data available for the selected area and time range (maxcc={payload['input']['data'][0]['dataFilter']['maxcc']}%). Try a different date or a larger maxcc.")

        # The result is a NumPy array, convert to PIL Image then to bytes
        image_array = image_data_list[0] # Assuming one image response
        
        # Ensure image_array is 3D (height, width, channels)
        if image_array.ndim == 2: # Grayscale image
            image_array = Image.fromarray(image_array, mode='L')
        elif image_array.ndim == 3 and image_array.shape[2] == 3: # RGB image
             image_array = Image.fromarray(image_array, mode='RGB')
        else:
            raise ValueError("Unexpected image array dimensions from Sentinel Hub.")

        # Convert PIL Image to JPEG bytes in memory
        byte_io = BytesIO()
        image_array.save(byte_io, format='JPEG') # Save as JPEG format
        image_bytes = byte_io.getvalue()

        base64_encoded_image = base64.b64encode(image_bytes).decode('utf-8')
        # For frontend display, we generate a data URL (base64 encoded image directly in URL)
        display_url = f"data:image/jpeg;base64,{base64_encoded_image}"
        
        print(f"Successfully fetched image via sentinelhub-py. Size: {len(base64_encoded_image)} bytes (Base64).")
        return base64_encoded_image, display_url
    except HTTPException: # Re-raise our own HTTPExceptions
        raise
    except Exception as e:
        print(f"Error fetching image with sentinelhub-py: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch satellite image via Sentinel Hub Process API: {e}")


# --- Main AI Analysis Endpoint ---
@app.post("/generate-ai-response/", response_model=GeoAnalysisResponse)
async def generate_ai_response(request: GeoAnalysisRequest):
    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Google API Key not configured.")
    # Check sentinelhub-py config directly now
    if not sh_config.sh_client_id or not sh_config.sh_client_secret:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Sentinel Hub OAuth Client ID/Secret not fully configured in backend.")


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
    original_image_url_2 = None # FIX: Ensure original_image_url_2 is initialized

    try:
        # No need for get_sentinel_hub_token() explicitly here, sentinelhub-py handles it
        
        base64_image_1, original_image_url_1 = await get_sentinel_image_data(request.bbox, request.start_date)

        if request.start_date != request.end_date:
            base64_image_2, original_image_url_2 = await get_sentinel_image_data(request.bbox, request.end_date)

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

