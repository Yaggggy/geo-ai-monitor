# backend/geospatial.py

import os
import numpy as np
from sentinelhub import (
    SentinelHubRequest, DataCollection, MimeType, CRS, BBox, SHConfig
)
import base64
from io import BytesIO
from PIL import Image

class NoDataAvailableException(Exception):
    pass

# --- Dictionary of Evalscripts ---
EVALSCRIPTS = {
    "ndvi": """
        //VERSION=3
        function setup() {
            return { input: ["B04", "B08", "SCL"], output: { bands: 1, sampleType: "FLOAT32" }};
        }
        function evaluatePixel(sample) {
            if ([8, 9, 10].includes(sample.SCL)) { return [NaN]; } // Cloud mask
            if (sample.B08 + sample.B04 === 0) { return [NaN]; }
            return [(sample.B08 - sample.B04) / (sample.B08 + sample.B04)];
        }
    """,
    "ndwi": """
        //VERSION=3
        function setup() {
            return { input: ["B03", "B08", "SCL"], output: { bands: 1, sampleType: "FLOAT32" }};
        }
        function evaluatePixel(sample) {
            if ([8, 9, 10].includes(sample.SCL)) { return [NaN]; } // Cloud mask
            if (sample.B08 + sample.B03 === 0) { return [NaN]; }
            return [(sample.B03 - sample.B08) / (sample.B03 + sample.B08)];
        }
    """
}

def encode_image(image_array):
    nan_mask = np.isnan(image_array)
    image_array[nan_mask] = -1 # Represent no-data areas as black
    img_scaled = (np.clip(image_array, -1, 1) * 127.5 + 127.5).astype(np.uint8)
    img = Image.fromarray(img_scaled, 'L')
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffered.getvalue()).decode()

def get_analysis(bbox_coords: list, from_date: str, to_date: str, analysis_type: str = "ndvi"):
    config = SHConfig()
    config.sh_client_id = os.environ.get('SH_CLIENT_ID')
    config.sh_client_secret = os.environ.get('SH_CLIENT_SECRET')
    bbox = BBox(bbox=bbox_coords, crs=CRS.WGS84)

    evalscript = EVALSCRIPTS.get(analysis_type)
    if not evalscript:
        raise ValueError("Invalid analysis type specified.")

    request_from = SentinelHubRequest(
        evalscript=evalscript,
        input_data=[SentinelHubRequest.input_data(data_collection=DataCollection.SENTINEL2_L1C, time_interval=(from_date, from_date))],
        responses=[SentinelHubRequest.output_response("default", MimeType.TIFF)],
        bbox=bbox, size=(512, 512), config=config
    )
    request_to = SentinelHubRequest(
        evalscript=evalscript,
        input_data=[SentinelHubRequest.input_data(data_collection=DataCollection.SENTINEL2_L1C, time_interval=(to_date, to_date))],
        responses=[SentinelHubRequest.output_response("default", MimeType.TIFF)],
        bbox=bbox, size=(512, 512), config=config
    )

    image_from = request_from.get_data()[0]
    image_to = request_to.get_data()[0]

    mean_from = np.nanmean(image_from)
    mean_to = np.nanmean(image_to)

    if np.isnan(mean_from) or np.isnan(mean_to):
        raise NoDataAvailableException("No satellite data found for one or both dates, likely due to cloud cover.")

    change = 0.0
    if abs(mean_from) > 1e-6:
        change = ((mean_to - mean_from) / abs(mean_from)) * 100

    result = {
        "from_date_str": from_date,
        "to_date_str": to_date,
        f"mean_{analysis_type}_from": round(float(mean_from), 4),
        f"mean_{analysis_type}_to": round(float(mean_to), 4),
        "change_percentage": round(float(change), 2),
        "image_from": encode_image(np.copy(image_from)),
        "image_to": encode_image(np.copy(image_to)),
        "analysis_type": analysis_type.upper()
    }
    return result