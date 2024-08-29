from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from ccdexplorer_fundamentals.tooter import Tooter, TooterType, TooterChannel  # noqa
from ccdexplorer_fundamentals.mongodb import (
    MongoDB,
    Collections,
)
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import CCD_BlockInfo
from app.state.state import get_mongo_motor


router = APIRouter(tags=["Blocks"], prefix="/v1")


@router.get("/{net}/blocks/last/{count}", response_class=JSONResponse)
async def get_last_blocks(
    request: Request,
    net: str,
    count: int,
    mongomotor: MongoDB = Depends(get_mongo_motor),
) -> list[CCD_BlockInfo]:
    """
    Endpoint to get the last X blocks as stored in MongoDB collection `blocks`. Maxes out at 50.

    """
    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    count = min(50, max(count, 1))
    try:
        result = (
            await db_to_use[Collections.blocks]
            .find({})
            .sort({"height": -1})
            .to_list(count)
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
            detail=f"Error retrieving last {count} blocks on {net}, {error}.",
        )
