import os

from dotenv import load_dotenv

load_dotenv()


BRANCH = os.environ.get("BRANCH", "dev")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "prod")
MONGO_URI = os.environ.get("MONGO_URI")
SITE_URL = os.environ.get("SITE_URL")
