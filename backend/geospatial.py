# backend/geospatial.py
import os 
import numpy as np
from sentinelhub import (
    SentinelHubRequest,
    DataCollection,
    MimeType,
    CRS,
    BBox,
    SHConfig,
    Geometry
)
import base64
from io import BytesIO
from PIL import Image

# Function to encode numpy array image to base64 string
def encode_image(image_array):
    # Scale to 0-255 and convert to uint8
    img_scaled = (np.clip(image_array, -1, 1) * 127.5 + 127.5).astype(np.uint8)

    # For single-band NDVI, we can use a colormap. Here we just make it grayscale.
    if len(img_scaled.shape) == 2:
        img = Image.fromarray(img_scaled, 'L')
    else:
        img = Image.fromarray(img_scaled)

    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffered.getvalue()).decode()

def get_ndvi_change(bbox_coords: list, from_date: str, to_date: str):
    # --- 1. Setup Configuration & Bounding Box ---
    config = SHConfig()
    config.sh_client_id = os.environ.get('SH_CLIENT_ID')
    config.sh_client_secret = os.environ.get('SH_CLIENT_SECRET')

    # Sentinel Hub requires bounding box in a specific CRS
    bbox = BBox(bbox=bbox_coords, crs=CRS.WGS84)

    # --- 2. Define the NDVI Calculation Script ---
    # This script runs on Sentinel Hub's servers. B04 is Red, B08 is NIR.
    evalscript_ndvi = """
        //VERSION=3
        function setup() {
            return {
                input: ["B04", "B08"],
                output: { bands: 1, sampleType: "FLOAT32" }
            };
        }
        function evaluatePixel(sample) {
            let ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04);
            return [ndvi];
        }
    """

    # --- 3. Create Requests for Start and End Dates ---
    request_from = SentinelHubRequest(
        evalscript=evalscript_ndvi,
        input_data=[
            SentinelHubRequest.input_data(
                data_collection=DataCollection.SENTINEL2_L1C,
                time_interval=(from_date, from_date),
            )
        ],
        responses=[SentinelHubRequest.output_response("default", MimeType.TIFF)],
        bbox=bbox,
        size=(512, 512),
        config=config,
    )

    request_to = SentinelHubRequest(
        evalscript=evalscript_ndvi,
        input_data=[
            SentinelHubRequest.input_data(
                data_collection=DataCollection.SENTINEL2_L1C,
                time_interval=(to_date, to_date),
            )
        ],
        responses=[SentinelHubRequest.output_response("default", MimeType.TIFF)],
        bbox=bbox,
        size=(512, 512),
        config=config,
    )

    # --- 4. Fetch Data ---
    # .get_data() returns a list, we take the first image
    image_from = request_from.get_data()[0]
    image_to = request_to.get_data()[0]

    # --- 5. Perform Analysis ---
    mean_ndvi_from = np.mean(image_from)
    mean_ndvi_to = np.mean(image_to)

    change = 0
    if mean_ndvi_from != 0:
        change = ((mean_ndvi_to - mean_ndvi_from) / abs(mean_ndvi_from)) * 100

    # --- 6. Prepare Results ---
    result = {
        "from_date_str": from_date,
        "to_date_str": to_date,
        "mean_ndvi_from": round(mean_ndvi_from, 4),
        "mean_ndvi_to": round(mean_ndvi_to, 4),
        "change_percentage": round(change, 2),
        "image_from": encode_image(image_from),
        "image_to": encode_image(image_to),
    }
    return result