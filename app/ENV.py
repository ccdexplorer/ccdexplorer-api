import os
from fastapi.security.api_key import APIKeyHeader
from dotenv import load_dotenv

load_dotenv()


BRANCH = os.environ.get("BRANCH", "dev")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "prod")
MONGO_URI = os.environ.get("MONGO_URI")
SITE_URL = os.environ.get("SITE_URL")
API_KEY_HEADER = APIKeyHeader(name="x-ccdexplorer-key")
LOGIN_SECRET = os.environ.get("LOGIN_SECRET")
CCDEXPLORER_API_KEY = os.environ.get("CCDEXPLORER_API_KEY")
API_URL = os.environ.get("API_URL")
REDIS_URL = os.environ.get("REDIS_URL")
API_ACCOUNT_TESTNET = "4NkwL9zPsZF6Y8VDztVtBv38fmgoY8GneDsGZ6zRpTZJgyX29E"
API_ACCOUNT_MAINNET = "3GjqwYXv5sGY1QZdhx3uBdNz1LWUofQAn4tyV6wQu8cg9592Ur"
# set this to have the api look out for payments on the chosen net.
API_NET = os.environ.get("API_NET", "mainnet")

environment = {
    "SITE_URL": SITE_URL,
    "CCDEXPLORER_API_KEY": CCDEXPLORER_API_KEY,
    "API_ACCOUNT_TESTNET": API_ACCOUNT_TESTNET,
    "API_ACCOUNT_MAINNET": API_ACCOUNT_MAINNET,
    "API_NET": API_NET,
    "API_URL": API_URL,
    "REDIS_URL": REDIS_URL,
}
