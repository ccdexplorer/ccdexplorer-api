from ccdexplorer_fundamentals.mongodb import (
    Collections,
    MongoMotor,
)
from fastapi import APIRouter, Depends, HTTPException, Request, Security
from app.ENV import API_KEY_HEADER
from fastapi.responses import JSONResponse
import json
from app.state_getters import get_mongo_motor

router = APIRouter(tags=["Accounts"], prefix="/v2")


@router.get("/{net}/accounts/info/count", response_class=JSONResponse)
async def get_accounts_count_estimate(
    request: Request,
    net: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> int:
    """
    Endpoint to get the accounts estimated count.

    """

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    try:
        result = (
            await db_to_use[Collections.all_account_addresses]
            .find({})
            .sort({"account_index": -1})
            .limit(1)
            .to_list(length=1)
        )
        error = None
    except Exception as error:
        print(error)
        result = None

    if result:
        return int(result[0]["account_index"]) + 1
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Error retrieving accounts count on {net}, {error}.",
        )


@router.post("/{net}/accounts/get-indexes", response_class=JSONResponse)
async def get_account_indexes(
    request: Request,
    net: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """
    Endpoint to get the the account_indexes for a list of canonical account_ids.

    """
    body = await request.body()
    if body:
        account_ids = json.loads(body.decode("utf-8"))

    else:
        account_ids = []
    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    try:
        result = (
            await db_to_use[Collections.all_account_addresses]
            .find({"_id": {"$in": account_ids}})
            .to_list(length=None)
        )
        error = None
    except Exception as error:
        print(error)
        result = None

    if result:
        return {x["_id"]: x["account_index"] for x in result}
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Error retrieving accounts list on {net}, {error}.",
        )


@router.post("/{net}/accounts/get-addresses", response_class=JSONResponse)
async def get_account_addresses(
    request: Request,
    net: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """
    Endpoint to get the the account_addresses for a list of account_indexes.

    """
    body = await request.body()
    if body:
        account_indexes = json.loads(body.decode("utf-8"))

    else:
        account_indexes = []
    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    try:
        result = (
            await db_to_use[Collections.all_account_addresses]
            .find({"account_index": {"$in": account_indexes}})
            .to_list(length=None)
        )
        error = None
    except Exception as error:
        print(error)
        result = None

    if result:
        return {x["account_index"]: x["_id"] for x in result}
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Error retrieving accounts list on {net}, {error}.",
        )


@router.get("/{net}/accounts/current-payday/info", response_class=JSONResponse)
async def get_current_payday_info(
    request: Request,
    net: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> list[dict]:
    """
    Endpoint to get the current payday info.

    """

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    try:
        result = (
            await db_to_use[Collections.paydays_current_payday]
            .find({})
            .to_list(length=None)
        )
        error = None
    except Exception as error:
        print(error)
        result = None

    if result:
        return result
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Error retrieving current payday info, {error}.",
        )
