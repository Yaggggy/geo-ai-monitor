import os
import requests
from dotenv import load_dotenv

load_dotenv()

print("🛰️ Sentinel Hub Test Start\n")

client_id = os.getenv("SENTINEL_HUB_OAUTH_CLIENT_ID")
client_secret = os.getenv("SENTINEL_HUB_OAUTH_CLIENT_SECRET")

if not client_id or not client_secret:
    print("❌ Missing environment variables. Check .env file.")
    exit()

print("🔍 Environment Check:")
print(f"  CLIENT_ID:")
print(f"  CLIENT_SECRET:\n")

# Get token
print("🔑 Getting OAuth token for Sentinel Hub...")
token_url = "https://services.sentinel-hub.com/oauth/token"
data = {
    "grant_type": "client_credentials",
    "client_id": client_id,
    "client_secret": client_secret
}
res = requests.post(token_url, data=data)
access_token = res.json().get("access_token")

if not access_token:
    print("Failed to retrieve token.")
    exit()

print("Token acquired.\n")

# Request image
print("🌍 Fetching Sentinel image for 2024-07-10")

url = "https://services.sentinel-hub.com/api/v1/process"
headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json"
}

payload = {
    "input": {
        "bounds": {
            "bbox": [13.3777, 52.5163, 13.4077, 52.5463],  # Berlin
            "properties": {
                "crs": "http://www.opengis.net/def/crs/EPSG/0/4326"
            }
        },
        "data": [{
            "type": "sentinel-2-l2a", 
            "dataFilter": {
                "timeRange": {
                    "from": "2024-07-10T00:00:00Z",
                    "to": "2024-07-10T23:59:59Z"
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
    "evalscript": """
        // Brightened True Color Visualization
        function setup() {
            return {
                input: ["B04", "B03", "B02"],
                output: { bands: 3 }
            };
        }

        function evaluatePixel(sample) {
            return [
                sample.B04 * 2.5, // Red
                sample.B03 * 2.5, // Green
                sample.B02 * 2.5  // Blue
            ];
        }
    """
}

response = requests.post(url, headers=headers, json=payload)

if response.status_code == 200:
    with open("berlin_image.jpg", "wb") as f:
        f.write(response.content)
    print("Image fetched and saved as 'berlin_image.jpg'")
else:
    print(f"Error: {response.status_code} - {response.text}")

print("\nSentinel Hub Test Complete ✅")
