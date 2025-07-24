# backend/config.py
import os
from sentinelhub import SHConfig

config = SHConfig()

# It's better to use environment variables for security
config.sh_client_id = os.environ.get('SH_CLIENT_ID', 'your_fallback_id')
config.sh_client_secret = os.environ.get('SH_CLIENT_SECRET', 'your_fallback_secret')

if not config.sh_client_id or not config.sh_client_secret:
    print("Warning: Sentinel Hub credentials not found.")