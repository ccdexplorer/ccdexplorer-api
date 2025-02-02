from pydantic import BaseModel
from typing import Optional


class TokenHolding(BaseModel):
    token_address: str
    contract: str
    token_id: str
    token_amount: str
    decimals: Optional[int] = None
    token_symbol: Optional[str] = None
    token_value: Optional[float] = None
    token_value_USD: Optional[float] = None
    verified_information: Optional[dict] = None
    address_information: Optional[dict] = None
