from fastapi import APIRouter, Request, Depends, HTTPException, Security
from app.ENV import API_KEY_HEADER
from fastapi.responses import JSONResponse
from ccdexplorer_fundamentals.mongodb import (
    MongoDB,
    Collections,
)
from app.state import get_mongo_motor


router = APIRouter(tags=["Tokens"], prefix="/v2")


@router.get("/{net}/tokens/info/count", response_class=JSONResponse)
async def get_tokens_count_estimate(
    request: Request,
    net: str,
    mongomotor: MongoDB = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> int:
    """
    Endpoint to get the tokens estimated count.

    """

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    try:
        result = await db_to_use[
            Collections.tokens_token_addresses_v2
        ].estimated_document_count()
        error = None
    except Exception as error:
        print(error)
        result = None

    if result:
        return result
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Error retrieving tokens count on {net}, {error}.",
        )
