from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from app.ENV import environment
from app.jinja2_helpers import templates
from app.models import User, APIKey
from app.state import get_user_details
from uuid import uuid4
from pymongo import ReplaceOne

router = APIRouter(include_in_schema=False)


@router.get("/management")
async def key_management_home(request: Request):

    context = {"request": request, "env": environment}
    return templates.TemplateResponse("management/home.html", context)


@router.get("/management/keys")
async def key_management(request: Request):
    user: User = get_user_details(request)
    if not user:
        response = RedirectResponse(url="/auth/login", status_code=303)
        return response

    result = (
        await request.app.motormongo.utilities_db["api_api_keys"]
        .find({"api_account_id": user.api_account_id})
        .to_list(length=None)
    )

    user_api_keys = []
    if len(result) > 0:
        user_api_keys = [{"key": x["_id"], "tier": x["api_group"]} for x in result]
    context = {
        "request": request,
        "env": environment,
        "user": user,
        "user_api_keys": user_api_keys,
    }
    return templates.TemplateResponse("management/keys.html", context)


@router.post(
    "/management/new-key",
    # response_class=Response,
)
async def management_new_key(
    request: Request,
):
    tier = "free"
    body = await request.body()
    if body:
        tier = body.decode("utf-8").split("=")[1]

    user: User = get_user_details(request)
    key_id = str(uuid4())
    key_to_add = APIKey(api_account_id=user.api_account_id, api_group=tier, id=key_id)

    request.app.motormongo.utilities_db["api_api_keys"].bulk_write(
        [
            ReplaceOne(
                {"_id": key_id},
                key_to_add.model_dump(),
                upsert=True,
            )
        ]
    )
    response = RedirectResponse(url="/management/keys", status_code=303)
    return response
