from fastapi import APIRouter, Request, Depends, HTTPException, Security
from app.ENV import API_KEY_HEADER, API_NET, API_URL

from fastapi.responses import JSONResponse
from ccdexplorer_fundamentals.mongodb import (
    MongoMotor,
    Collections,
    CollectionsUtilities,
)
from pymongo import ReplaceOne
from app.state_getters import get_mongo_motor
from fastapi.encoders import jsonable_encoder
import httpx
import datetime as dt
from ccdexplorer_fundamentals.user_v2 import (
    UserV2,
    AccountForUser,
    ContractForUser,
    NotificationPreferences,
    NotificationService,
    AccountNotificationPreferences,
    ContractNotificationPreferences,
    ValidatorNotificationPreferences,
    OtherNotificationPreferences,
)

router = APIRouter(tags=["Site User"], prefix="/v2", include_in_schema=False)


@router.get("/site_user/explanations", response_class=JSONResponse)
async def get_site_user_explanations(
    request: Request,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """
    Endpoint to get explanations for options for site users.

    """
    db_to_use = mongomotor.utilities
    try:
        result = (
            await db_to_use[CollectionsUtilities.preferences_explanations]
            .find({})
            .to_list(length=None)
        )
    except Exception as _:
        result = None

    return {x["_id"]: x for x in result}


@router.get("/site_user/{token}", response_class=JSONResponse)
async def get_site_user_from_token(
    request: Request,
    token: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> UserV2 | None:
    """
    Endpoint to get site user from token.

    """
    db_to_use = mongomotor.utilities
    try:
        result = await db_to_use[CollectionsUtilities.users_v2_prod].find_one(
            {"token": token}
        )
        if result:
            return UserV2(**result)
    except Exception as _:
        result = None

    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"No user found for {token}.",
        )


async def get_user(token: str, httpx_client: httpx.AsyncClient):
    response = await httpx_client.get(f"{API_URL}/v2/site_user/{token}")
    if response.status_code == 200:
        return UserV2(**response.json())
    else:
        return None


@router.put("/site_user/{user_token}/save/email-address", response_class=JSONResponse)
async def post_user_email_address(
    request: Request,
    user_token: str,
    response_form: dict,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> bool:
    """
    Endpoint to update and save user email address.

    """
    user: UserV2 | None = await get_user(user_token, request.app.httpx_client)
    response_as_dict = jsonable_encoder(response_form)
    user.email_address = response_as_dict["email_address"]
    user.last_modified = dt.datetime.now().astimezone(tz=dt.timezone.utc)
    await mongomotor.utilities[CollectionsUtilities.users_v2_prod].bulk_write(
        [
            ReplaceOne(
                {"token": str(user.token)},
                user.model_dump(exclude_none=True),
                upsert=True,
            )
        ]
    )

    return True


@router.put("/site_user/{user_token}/save/user", response_class=JSONResponse)
async def post_user(
    request: Request,
    user_token: str,
    response_form: dict,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> bool:
    """
    Endpoint to update and save user.

    """
    user: UserV2 | None = await get_user(user_token, request.app.httpx_client)
    if user:
        response_as_dict = jsonable_encoder(response_form)
        user = UserV2(**response_as_dict["user"])
        user.last_modified = dt.datetime.now().astimezone(tz=dt.timezone.utc)
        await mongomotor.utilities[CollectionsUtilities.users_v2_prod].bulk_write(
            [
                ReplaceOne(
                    {"token": str(user.token)},
                    user.model_dump(exclude_none=True),
                    upsert=True,
                )
            ]
        )

        return True
    else:
        return False
