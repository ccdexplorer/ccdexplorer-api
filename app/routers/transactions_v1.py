from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from ccdexplorer_fundamentals.tooter import Tooter, TooterType, TooterChannel  # noqa
from ccdexplorer_fundamentals.mongodb import (
    MongoDB,
    Collections,
)
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import CCD_BlockItemSummary
from app.state.state import get_mongo_motor


router = APIRouter(tags=["Transactions"], prefix="/v1")


@router.get("/{net}/transactions/last/{count}", response_class=JSONResponse)
async def get_last_transactions(
    request: Request,
    net: str,
    count: int,
    mongomotor: MongoDB = Depends(get_mongo_motor),
) -> list[dict]:
    """
    Endpoint to get the last X transactions as stored in MongoDB collection `transactions`. Maxes out at 50.

    """
    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    count = min(50, max(count, 1))
    try:
        result = (
            await db_to_use[Collections.transactions]
            .find({})
            .sort({"block_info.height": -1})
            .to_list(count)
        )
        error = None
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
