from ccdexplorer_fundamentals.mongodb import (
    Collections,
    MongoMotor,
)
from fastapi import APIRouter, Depends, HTTPException, Request, Security
from app.ENV import API_KEY_HEADER
from fastapi.responses import JSONResponse

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
