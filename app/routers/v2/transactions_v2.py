from fastapi import APIRouter, Request, Depends, HTTPException, Security
from app.ENV import API_KEY_HEADER
from fastapi.responses import JSONResponse
from ccdexplorer_fundamentals.mongodb import (
    MongoMotor,
    Collections,
)
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import CCD_BlockItemSummary
from app.state_getters import get_mongo_motor


router = APIRouter(tags=["Transactions"], prefix="/v2")


@router.get("/{net}/transactions/last/{count}", response_class=JSONResponse)
async def get_last_transactions(
    request: Request,
    net: str,
    count: int,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> list[dict]:
    """
    Endpoint to get the last X transactions as stored in MongoDB collection `transactions`. Maxes out at 50.

    """
    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    count = min(50, max(count, 1))
    error = None
    try:
        result = (
            await db_to_use[Collections.transactions]
            .find({})
            .sort({"block_info.height": -1})
            .to_list(count)
        )

    except Exception as error:
        print(error)
        result = None

    if result:
        last_txs = [
            CCD_BlockItemSummary(**x).model_dump(exclude_none=True) for x in result
        ]
        return last_txs
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Error retrieving last {count} transactions on {net}, {error}.",
        )


@router.get("/{net}/transactions/info/tps", response_class=JSONResponse)
async def get_transactions_tps(
    request: Request,
    net: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
) -> dict:
    """
    Endpoint to get the transactions TPS as stored in MongoDB collection `pre_render`.

    """
    if net != "mainnet":
        raise HTTPException(
            status_code=404,
            detail="Transactions TPS information only available for mainnet.",
        )

    db_to_use = mongomotor.mainnet
    try:
        result = await db_to_use[Collections.pre_render].find_one({"_id": "tps_table"})
        error = None
    except Exception as error:
        print(error)
        result = None

    if result:
        return result
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Error retrieving last transactions tps, {error}.",
        )


@router.get("/{net}/transactions/info/count", response_class=JSONResponse)
async def get_transactions_count_estimate(
    request: Request,
    net: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
) -> int:
    """
    Endpoint to get the transactions estimated count.

    """

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    try:
        result = await db_to_use[Collections.transactions].estimated_document_count()
        error = None
    except Exception as error:
        print(error)
        result = None

    if result:
        return result
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Error retrieving transactions count on {net}, {error}.",
        )
