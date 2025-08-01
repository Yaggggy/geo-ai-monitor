# To Check the API is working by downloading a true color image of Paris using Sentinel Hub
import os
from sentinelhub import SHConfig, BBox, CRS, MimeType, SentinelHubRequest, DataCollection, bbox_to_dimensions
from dotenv import load_dotenv
from PIL import Image
from io import BytesIO

load_dotenv()

config = SHConfig()
config.sh_client_id = os.getenv("SH_CLIENT_ID")
config.sh_client_secret = os.getenv("SH_CLIENT_SECRET")
config.instance_id = os.getenv("INSTANCE_ID")


if not config.instance_id:
    raise ValueError("Missing INSTANCE_ID. Check your .env file.")
if not config.sh_client_id or not config.sh_client_secret:
    raise ValueError("Missing CLIENT_ID or CLIENT_SECRET. Check your .env file.")


paris_bbox = BBox(bbox=[2.252, 48.816, 2.422, 48.902], crs=CRS.WGS84)
resolution = 10  
size = bbox_to_dimensions(paris_bbox, resolution=resolution)


request = SentinelHubRequest(
    data_folder=".",
    evalscript="""
    // Simple True Color script
    // Bands: B04 (Red), B03 (Green), B02 (Blue)
    // All bands are scaled from 0 to 1
    // Max value (default 255) controls brightness

    //VERSION=3
    function setup() {
        return {
            input: ["B04", "B03", "B02"],
            output: {
                bands: 3
            }
        };
    }

    function evaluatePixel(sample) {
        return [sample.B04, sample.B03, sample.B02];
    }
    """,
    input_data=[
        SentinelHubRequest.input_data(
            data_collection=DataCollection.SENTINEL2_L1C,
            time_interval=("2024-06-01", "2024-06-15"), 
            mosaicking_order="leastCC"
        )
    ],
    responses=[
        SentinelHubRequest.output_response("default", MimeType.PNG)
    ],
    bbox=paris_bbox,
    size=size,
    config=config
)

image_data = request.get_data()[0]
image = Image.fromarray(image_data)
image.save("paris_true_color.png")
print("Image saved: paris_true_color.png")
