import os
import numpy as np
from datetime import datetime
from sentinelhub import (
    SHConfig,
    SentinelHubRequest,
    DataCollection,
    MimeType,
    CRS,
    BBox,
    bbox_to_dimensions,
    SentinelHubDownloadFailedException,
)

# Custom Exception
class NoDataAvailableException(Exception):
    pass

# Load SentinelHub configuration
def get_sh_config():
    config = SHConfig()
    config.sh_client_id = os.environ.get("SH_CLIENT_ID")
    config.sh_client_secret = os.environ.get("SH_CLIENT_SECRET")

    if not config.sh_client_id or not config.sh_client_secret:
        raise RuntimeError("Missing SentinelHub credentials in environment variables")
    
    return config

# Get evalscript for analysis type
def get_evalscript(analysis_type: str) -> str:
    if analysis_type.lower() == "ndvi":
        return """
        // NDVI = (B08 - B04) / (B08 + B04)
        // Band 8 = NIR, Band 4 = Red
        return [ (B08 - B04) / (B08 + B04) ]
        """
    elif analysis_type.lower() == "ndwi":
        return """
        // NDWI = (B03 - B08) / (B03 + B08)
        // Band 3 = Green, Band 8 = NIR
        return [ (B03 - B08) / (B03 + B08) ]
        """
    else:
        raise ValueError("Unsupported analysis type. Use 'ndvi' or 'ndwi'.")

# Main analysis function
def get_analysis(bbox_coords: list, from_date: str, to_date: str, analysis_type: str):
    config = get_sh_config()

    # Define bounding box and size
    bbox = BBox(bbox=bbox_coords, crs=CRS.WGS84)
    resolution = 10  # meters
    size = bbox_to_dimensions(bbox, resolution=resolution)

    # Get evalscript
    evalscript = get_evalscript(analysis_type)

    # Build request
    request = SentinelHubRequest(
        evalscript=evalscript,
        input_data=[
            SentinelHubRequest.input_data(
                data_collection=DataCollection.SENTINEL2_L2A,
                time_interval=(from_date, to_date),
                mosaicking_order='mostRecent'
            )
        ],
        responses=[SentinelHubRequest.output_response('default', MimeType.TIFF)],
        bbox=bbox,
        size=size,
        config=config
    )

    try:
        response = request.get_data()
        if not response or len(response[0].shape) == 0:
            raise NoDataAvailableException("No valid satellite data available for the specified region and time.")
        
        image_data = response[0].squeeze()
        mean_value = float(np.nanmean(image_data))
        
        return {
            "analysis_type": analysis_type,
            "bbox": bbox_coords,
            "from_date": from_date,
            "to_date": to_date,
            "mean_index_value": round(mean_value, 4)
        }

    except SentinelHubDownloadFailedException as e:
        raise NoDataAvailableException("Failed to download satellite data from SentinelHub.") from e
    except Exception as e:
        raise RuntimeError(f"Unexpected error during geospatial analysis: {e}")
