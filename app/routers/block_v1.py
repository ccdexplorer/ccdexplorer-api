from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from pymongo import ASCENDING
from ccdexplorer_fundamentals.tooter import Tooter, TooterType, TooterChannel  # noqa
from ccdexplorer_fundamentals.mongodb import (
    MongoDB,
    Collections,
)
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import CCD_BlockInfo
from app.state.state import get_mongo_db


router = APIRouter(tags=["Block"], prefix="/v1")


@router.get("/{net}/block/{block_hash_or_height}", response_class=JSONResponse)
async def get_block_at_height(
    request: Request,
    net: str,
    block_hash_or_height: str | int,
    mongodb: MongoDB = Depends(get_mongo_db),
) -> CCD_BlockInfo:
    """
    Endpoint to get blockInfo as stored in MongoDB collection `blocks`.


    """
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    try:
        block_height = int(block_hash_or_height)
        block_hash = None
    except ValueError:
        block_height = None
        block_hash = block_hash_or_height

    if block_height:
        result = db_to_use[Collections.blocks].find_one({"height": block_height})
    else:
        result = db_to_use[Collections.blocks].find_one(block_hash)

    if result:
        result = CCD_BlockInfo(**result)
        return result
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested block at {block_hash_or_height} not found on {net}",
        )


@router.get("/{net}/block/height/finalized", response_class=JSONResponse)
async def get_last_finalized_block(
    request: Request,
    net: str,
    mongodb: MongoDB = Depends(get_mongo_db),
) -> CCD_BlockInfo:
    """
    Endpoint to get the last block as stored in MongoDB collection `blocks`.


    """
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    result = db_to_use[Collections.blocks].find().sort({"height": -1}).limit(1)

    if result:
        result = list(result)
        result = CCD_BlockInfo(**result[0])
        return result
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Can't find latest block at in collection for {net}",
        )
