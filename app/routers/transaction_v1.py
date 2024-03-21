from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from pymongo import ASCENDING
from ccdexplorer_fundamentals.tooter import Tooter, TooterType, TooterChannel  # noqa
from ccdexplorer_fundamentals.mongodb import (
    MongoDB,
    Collections,
)
from ccdexplorer_fundamentals.cis import MongoTypeLoggedEvent
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import CCD_BlockItemSummary
from app.state.state import get_mongo_db


router = APIRouter(tags=["Transaction"], prefix="/v1")


@router.get("/{net}/transaction/{tx_hash}/logged_events", response_class=JSONResponse)
async def get_transaction_logged_events(
    request: Request,
    net: str,
    tx_hash: str,
    mongodb: MongoDB = Depends(get_mongo_db),
) -> list[MongoTypeLoggedEvent]:
    """
    Endpoint to get logged events for a transaction as stored in MongoDB collection `tokens_logged_events`. Note that only
    logged events are stored that are relevant for token accounting, so `mint`, `transfer`, `burn` and `metadata`.
    See http://proposals.concordium.software/CIS/cis-2.html for further details on these events.


    """
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    pipeline = [
        {"$match": {"tx_hash": tx_hash}},
        {
            "$sort": {
                "ordering": ASCENDING,
            }
        },
    ]
    result = list(db_to_use[Collections.tokens_logged_events].aggregate(pipeline))

    if len(result) > 0:
        result = [MongoTypeLoggedEvent(**x) for x in result]

        return result
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested transaction hash ({tx_hash}) not found on {net}",
        )


@router.get("/{net}/transaction/{tx_hash}", response_class=JSONResponse)
async def get_transaction(
    request: Request,
    net: str,
    tx_hash: str,
    mongodb: MongoDB = Depends(get_mongo_db),
) -> CCD_BlockItemSummary:
    """
    Endpoint to get a transaction as stored in MongoDB collection `transactions`.


    """
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    result = db_to_use[Collections.transactions].find_one(tx_hash)
    if result:
        result = CCD_BlockItemSummary(**result)
        return result  # .model_dump_json(exclude="_id", exclude_none=True)
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested transaction hash ({tx_hash}) not found on {net}",
        )
