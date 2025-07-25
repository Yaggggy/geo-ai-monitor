import os
import requests
from dotenv import load_dotenv

load_dotenv()

client_id = os.getenv("SENTINEL_HUB_OAUTH_CLIENT_ID")
client_secret = os.getenv("SENTINEL_HUB_OAUTH_CLIENT_SECRET")

# Get access token
token_response = requests.post(
    "https://services.sentinel-hub.com/oauth/token",
    data={
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret
    }
)
token_response.raise_for_status()
access_token = token_response.json()["access_token"]

headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json"
}

# Use Sentinel Hub official True Color Evalscript
evalscript_truecolor = """
//VERSION=3
function setup() {
  return {
    input: ["B02", "B03", "B04"],
    output: { bands: 3 }
  };
}

function evaluatePixel(sample) {
  return [sample.B04, sample.B03, sample.B02];
}
"""

payload = {
    "input": {
        "bounds": {
            "bbox": [9.17, 45.45, 9.23, 45.51],  # Milan, Italy
            "properties": {
                "crs": "http://www.opengis.net/def/crs/EPSG/0/4326"
            }
        },
        "data": [{
            "type": "sentinel-2-l2a",
            "dataFilter": {
                "timeRange": {
                    "from": "2024-07-01T00:00:00Z",
                    "to": "2024-07-01T23:59:59Z"
                },
                "mosaickingOrder": "leastCC"
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
    "evalscript": evalscript_truecolor
}

response = requests.post(
    "https://services.sentinel-hub.com/api/v1/process",
    headers=headers,
    json=payload
)

if response.status_code == 200:
    with open("true_color.jpg", "wb") as f:
        f.write(response.content)
    print("✅ Image saved as 'true_color.jpg'")
else:
    print(f"❌ Request failed: {response.status_code}\n{response.text}")
