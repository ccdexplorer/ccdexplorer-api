from ccdexplorer_fundamentals.mongodb import (
    Collections,
    MongoMotor,
)
from fastapi import APIRouter, Depends, HTTPException, Request, Security
from fastapi.responses import JSONResponse
from app.ENV import API_KEY_HEADER
from app.state_getters import get_mongo_motor

router = APIRouter(tags=["Markets"], prefix="/v2")


@router.get(
    "/markets/info",
    response_class=JSONResponse,
)
async def get_markets_info(
    request: Request,
    api_key: str = Security(API_KEY_HEADER),
    mongomotor: MongoMotor = Depends(get_mongo_motor),
) -> dict:
    """
    Endpoint to get market information ffor CCD from CoinMarketCap.
    """
    db_to_use = mongomotor.mainnet
    try:
        result = await db_to_use[Collections.helpers].find_one(
            {"_id": "coinmarketcap_data"}
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
            detail="Error retrieving markets information for CCD.",
        )
