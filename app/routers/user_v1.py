from ccdexplorer_fundamentals.mongodb import (
    CollectionsUtilities,
    MongoMotor,
)
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
import json
from app.state.state import get_mongo_motor

router = APIRouter(tags=["User"], prefix="/v1", include_in_schema=False)


@router.get(
    "/user/{token}",
    response_class=JSONResponse,
)
async def get_user(
    request: Request,
    token: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
) -> JSONResponse:
    """
    Endpoint to get user information.
    """

    db_to_use = mongomotor.utilities
    result = await db_to_use[CollectionsUtilities.users_v2_prod].find_one(
        {"token": token}
    )
    if result:
        return result
    else:
        raise HTTPException(
            status_code=404,
            detail=f"User with token {token} is not found.",
        )
