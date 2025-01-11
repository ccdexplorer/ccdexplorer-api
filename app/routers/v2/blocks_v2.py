from fastapi import APIRouter, Request, Depends, HTTPException, Security
from app.ENV import API_KEY_HEADER
from fastapi.responses import JSONResponse
from ccdexplorer_fundamentals.tooter import Tooter, TooterType, TooterChannel  # noqa
from ccdexplorer_fundamentals.mongodb import (
    MongoMotor,
    Collections,
)
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import CCD_BlockInfo
from app.state_getters import get_mongo_motor


router = APIRouter(tags=["Blocks"], prefix="/v2")


@router.get("/{net}/blocks/last/{count}", response_class=JSONResponse)
async def get_last_blocks(
    request: Request,
    net: str,
    count: int,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> list[CCD_BlockInfo]:
    """
    Endpoint to get the last X blocks as stored in MongoDB collection `blocks`. Maxes out at 50.

    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    count = min(50, max(count, 1))
    error = None
    try:
        result = (
            await db_to_use[Collections.blocks]
            .find({})
            .sort({"height": -1})
            .to_list(count)
        )

    except Exception as error:
        print(error)
        result = None

    if result:
        return result
    else:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving last {count} blocks on {net}, {error}.",
        )
