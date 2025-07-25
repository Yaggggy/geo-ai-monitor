# backend/test_gemini_vision.py
import os
import httpx
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

async def test_gemini_vision_api():
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

    if not GOOGLE_API_KEY:
        print("Error: GOOGLE_API_KEY not found in .env file.")
        return

    print(f"Using API Key: {GOOGLE_API_KEY[:5]}...{GOOGLE_API_KEY[-5:]}") # Print partial key for security
    gemini_api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro-vision:generateContent?key={GOOGLE_API_KEY}"

    # Use a publicly accessible image URL for testing
    # This is a placeholder image. You can replace it with any other publicly accessible image URL.
    test_image_url = "https://placehold.co/600x400/FF0000/FFFFFF?text=Test+Image"

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": "Describe this image in detail."},
                    {"image": {"source": {"imageUri": test_image_url}}}
                ]
            }
        ]
    }

    print(f"\n--- Direct Gemini API Request Details ---")
    print(f"Model: gemini-pro-vision")
    print(f"API URL: {gemini_api_url}")
    print(f"Payload (contents): {json.dumps(payload['contents'], indent=2)}")
    print(f"--- End Request Details ---\n")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                gemini_api_url,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=60.0 # Increased timeout
            )
            response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)

            result = response.json()
            print("\n--- Gemini API Response ---")
            print(json.dumps(result, indent=2))
            print("--- End Response ---\n")

            if result.get("candidates") and len(result["candidates"]) > 0 and \
               result["candidates"][0].get("content") and \
               result["candidates"][0]["content"].get("parts") and \
               len(result["candidates"][0]["content"]["parts"]) > 0:
                ai_text = result["candidates"][0]["content"]["parts"][0].get("text", "")
                print("\nAI Response (Extracted):")
                print(ai_text)
            else:
                print("\nError: AI response content is empty or malformed.")

    except httpx.RequestError as exc:
        print(f"\nNetwork error during API call: {exc}")
    except httpx.HTTPStatusError as exc:
        print(f"\nHTTP Error response from Gemini API: {exc.response.status_code}")
        print(f"Response text: {exc.response.text}")
    except json.JSONDecodeError:
        print("\nError: Failed to decode JSON response from Gemini API.")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_gemini_vision_api())