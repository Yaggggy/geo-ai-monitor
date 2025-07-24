import os
from sentinelhub import SHConfig
from dotenv import load_dotenv

load_dotenv()

config = SHConfig()
config.sh_client_id = os.getenv('SH_CLIENT_ID')
config.sh_client_secret = os.getenv('SH_CLIENT_SECRET')

if not config.sh_client_id or not config.sh_client_secret:
    print("Warning: Sentinel Hub credentials not found.")
