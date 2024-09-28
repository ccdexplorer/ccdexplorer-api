from pydantic import BaseModel
from typing import Optional


class User(BaseModel):
    token: str  # uuid
    api_account_id: str  # uuid
    email: str
    password: str  # hashed


class APIKey(BaseModel):
    id: str
    api_account_id: str  # uuid
    api_group: str  # this group/tier determines the limits
    active: Optional[bool] = True
