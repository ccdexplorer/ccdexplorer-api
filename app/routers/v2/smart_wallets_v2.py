from ccdexplorer_fundamentals.mongodb import (
    Collections,
    MongoDB,
)
from fastapi import APIRouter, Depends, Request, Security
from fastapi.responses import JSONResponse

from app.ENV import API_KEY_HEADER
from app.state_getters import get_mongo_db

router = APIRouter(tags=["Smart Wallets"], prefix="/v2")


@router.get("/{net}/smart-wallets/overview", response_class=JSONResponse)
async def get_all_smart_wallet_contracts(
    request: Request,
    net: str,
    mongodb: MongoDB = Depends(get_mongo_db),
    api_key: str = Security(API_KEY_HEADER),
) -> list[str]:
    """
    Fetches all unique smart wallet contract addresses from the specified MongoDB collection.

    Args:
        request (Request): The request object.
        net (str): The network type, either "testnet" or "mainnet".
        mongodb (MongoDB, optional): The MongoDB dependency, defaults to the result of get_mongo_db.
        api_key (str, optional): The API key for security, defaults to the result of API_KEY_HEADER.

    Returns:
        list[str]: A list of unique smart wallet contract addresses.
    """
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    result = list(
        db_to_use[Collections.cis5_public_keys_contracts].distinct(
            "wallet_contract_address"
        )
    )

    return result
