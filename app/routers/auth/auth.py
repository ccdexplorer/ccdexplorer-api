from typing import Optional
from uuid import uuid4

from ccdexplorer_fundamentals.mongodb import MongoMotor
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm

from pymongo import ReplaceOne

from app.models import User
from app.ENV import environment, API_NET, API_URL
from app.jinja2_helpers import templates
from app.security import hash_password, manager, verify_password
from app.state_getters import get_mongo_motor, get_user_details
import datetime as dt

motormongo = MongoMotor(None)


router = APIRouter(prefix="/auth", include_in_schema=False)


def get_session() -> MongoMotor:
    return motormongo


async def get_user_by_email(email: str, session) -> Optional[User]:
    """ """
    if isinstance(session, MongoMotor):
        motormongo = session
    else:
        motormongo = session()
    db = motormongo.utilities_db
    result = await db["api_users"].find({"email": email}).to_list(length=1)
    if result:
        return User(**result[0])
    else:
        return None


async def get_user_by_reset_password_token(
    reset_password_token: str, session
) -> Optional[User]:
    """ """
    if isinstance(session, MongoMotor):
        motormongo = session
    else:
        motormongo = session()
    db = motormongo.utilities_db
    result = (
        await db["api_users"]
        .find({"reset_password_token": reset_password_token})
        .to_list(length=1)
    )
    if result:
        return User(**result[0])
    else:
        return None


@manager.user_loader(session=get_session)
async def get_user(name: str, session):
    return await get_user_by_email(name, session)


@router.get("/login", response_class=HTMLResponse)
def login_get(request: Request):
    user = get_user_details(request)
    context = {"request": request, "env": environment, "user": user}
    return templates.TemplateResponse("auth/login.html", context)


@router.get("/register", response_class=HTMLResponse)
def register_get(request: Request):
    context = {
        "request": request,
        "env": environment,
    }
    return templates.TemplateResponse("auth/register.html", context)


@router.post("/login")
async def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: MongoMotor = Depends(get_mongo_motor),
) -> RedirectResponse:
    """
    Logs in the user provided by form_data.username and form_data.password
    """
    user = await get_user_by_email(form_data.username, db)
    error = None
    if user is None:
        error = "Can't find user and/or password is wrong. "

    if user:
        if not verify_password(form_data.password, user.password):
            error = "Can't find user and/or password is wrong. "

    if error:
        context = {"request": request, "env": environment, "errors": [error]}

        return templates.TemplateResponse("auth/login.html", context)
    response = RedirectResponse(url="/account", status_code=303)
    manager.set_cookie(response, user.token)
    return response


@router.get("/forgot-password")
async def forgot_password(
    request: Request,
    response: Response,
    db: MongoMotor = Depends(get_mongo_motor),
) -> HTMLResponse:
    """
    The user has forgotten its password. Ask for email and send a reset email.
    """

    context = {
        "request": request,
        "env": environment,
    }
    return templates.TemplateResponse("auth/forgot_password.html", context)


@router.get("/reset-password-action/{reset_password_token}")
async def reset_password_action(
    request: Request,
    reset_password_token: str,
    response: Response,
    db: MongoMotor = Depends(get_mongo_motor),
) -> HTMLResponse:
    """
    The user has forgotten its password and clicked on the link in the email.
    """
    user = await get_user_by_reset_password_token(reset_password_token, db)
    if not user:
        response = RedirectResponse(url="/auth/login", status_code=303)
        return response

    context = {
        "request": request,
        "env": environment,
        "reset_password_token": reset_password_token,
    }
    return templates.TemplateResponse("auth/reset_password.html", context)


@router.post("/reset-password")
async def forgot_password_action(
    request: Request,
    response: Response,
    db: MongoMotor = Depends(get_mongo_motor),
) -> HTMLResponse:
    """
    The user has forgotten its password. Ask for email and send a reset email.
    """
    username = None
    body = await request.body()
    if body:
        username = body.decode("utf-8").split("=")[1].replace("%40", "@")
    user = await get_user_by_email(username, db)

    if user:
        user.reset_password_token = str(uuid4())
        db.utilities_db["api_users"].bulk_write(
            [
                ReplaceOne(
                    {"_id": user.api_account_id},
                    user.model_dump(exclude_none=True),
                    upsert=True,
                )
            ]
        )
        request.app.tooter.email_api(
            title="CCDExplorer.io API - Forgot password",
            body=f"""Someone has clicked the 'Reset Password' link on {API_URL} for your account. If this was you and you need to reset your password, please click <a href='{API_URL}/auth/reset-password-action/{user.reset_password_token}'>Reset Password</a>.
            If this wasn't you, please ignore this email.""",
            email_address=user.email,
        )

    context = {
        "request": request,
        "env": environment,
    }
    return templates.TemplateResponse("auth/forgot_password_action.html", context)


@router.post("/set-password")
async def set_new_password_after_forgot(
    request: Request,
    response: Response,
    db: MongoMotor = Depends(get_mongo_motor),
) -> HTMLResponse:
    """
    The user has forgotten its password. Asks for email and clicked on the link. Now sets new password.
    """
    password = None
    reset_password_token = None
    body = await request.body()
    if body:
        components = body.decode("utf-8").split("&")

        password = components[0].split("=")[1]
        reset_password_token = components[1].split("=")[1]
    user = await get_user_by_reset_password_token(reset_password_token, db)

    if user:
        user.password = hash_password(password)
        user.reset_password_token = None
        db.utilities_db["api_users"].bulk_write(
            [
                ReplaceOne(
                    {"_id": user.api_account_id},
                    user.model_dump(exclude_none=True),
                    upsert=True,
                )
            ]
        )
        request.app.tooter.email_api(
            title="CCDExplorer.io API - Reset password",
            body=f"""The password on your account on {API_URL} was just reset. If this wasn't you, please contact me on Telegram (explorer.ccd) at once.""",
            email_address=user.email,
        )

    response = RedirectResponse(url="/auth/login", status_code=303)
    return response


async def get_next_alias_id_and_account_id(db: MongoMotor):
    pipeline = [
        # accounts should be valid on all scopes
        # {"$match": {"scope": API_URL}},
        {"$sort": {"alias_id": -1}},
        {"$limit": 1},
    ]
    result = await db.utilities_db["api_users"].aggregate(pipeline).to_list(length=1)
    if len(result) > 0:
        max_alias_id = result[0]["alias_id"]
    else:
        # no users found, so start at 0
        max_alias_id = -1
    next_alias_id = int(max_alias_id) + 1
    pipeline = [
        {"$match": {"net": API_NET}},
        {"$match": {"alias_id": next_alias_id}},
    ]
    result = await db.utilities_db["api_aliases"].aggregate(pipeline).to_list(length=1)
    alias_account_id = result[0]["alias"]
    return next_alias_id, alias_account_id


@router.post("/register", status_code=201)
async def register(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: MongoMotor = Depends(get_mongo_motor),
):
    """
    Registers a new user
    """
    user = await get_user_by_email(form_data.username, db)
    next_alias_id, alias_account_id = await get_next_alias_id_and_account_id(db)
    if user is None:
        user = User(
            scope=API_URL,
            api_account_id=str(uuid4()),
            alias_id=next_alias_id,
            alias_account_id=alias_account_id,
            token=str(uuid4()),
            email=form_data.username,
            password=hash_password(form_data.password),
            is_admin=False,
            plan_end_date=dt.datetime.now().astimezone(dt.UTC),
        )
        db.utilities_db["api_users"].bulk_write(
            [
                ReplaceOne(
                    {"_id": user.api_account_id},
                    user.model_dump(exclude_none=True),
                    upsert=True,
                )
            ]
        )
        response = RedirectResponse(url="/account", status_code=303)
        manager.set_cookie(response, user.token)
        return response

    else:
        context = {
            "request": request,
            "env": environment,
            "errors": ["email address already registered."],
        }
    return templates.TemplateResponse("auth/register.html", context)


@router.get("/logout")
async def logout(request: Request, response: Response):
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("api.ccdexplorer.io")
    request.app.user = None
    return response
