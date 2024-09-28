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


environment = {
    "SITE_URL": SITE_URL,
}
