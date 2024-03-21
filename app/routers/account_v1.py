from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from ccdexplorer_fundamentals.tooter import Tooter, TooterType, TooterChannel  # noqa
from ccdexplorer_fundamentals.mongodb import (
    MongoDB,
    Collections,
)
from pydantic import BaseModel
from app.state.state import get_mongo_db


class TokenHolding(BaseModel):
    token_address: str
    contract: str
    token_id: str
    token_amount: str


router = APIRouter(tags=["Account"], prefix="/v1")


@router.get("/{net}/account/{account_address}/tokens", response_class=JSONResponse)
async def get_account_tokens(
    request: Request,
    net: str,
    account_address: str,
    mongodb: MongoDB = Depends(get_mongo_db),
) -> list[TokenHolding]:
    """
    Endpoint to get all tokens for a given account, as stored in MongoDB collection `tokens_links_v2`.


    """
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    result_list = list(
        db_to_use[Collections.tokens_links_v2].find(
            {"account_address_canonical": account_address[:29]}
        )
    )
    tokens = [TokenHolding(**x["token_holding"]) for x in result_list]

    if len(tokens) > 0:

        return tokens
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested account({account_address}) has no tokens on {net}",
        )
