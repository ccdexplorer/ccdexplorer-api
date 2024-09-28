from typing import Optional
from uuid import uuid4

from ccdexplorer_fundamentals.mongodb import MongoMotor
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_login.exceptions import InvalidCredentialsException
from pymongo import ReplaceOne

from app.models import User
from app.ENV import environment
from app.jinja2_helpers import templates
from app.security import hash_password, manager, verify_password
from app.state import get_mongo_motor, get_user_details

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

    if not verify_password(form_data.password, user.password):
        error = "Can't find user and/or password is wrong. "

    if error:
        context = {"request": request, "env": environment, "error": error}
        return templates.TemplateResponse("auth/error.html", context)
    response = RedirectResponse(url="/", status_code=303)
    manager.set_cookie(response, user.token)
    return response


@router.post("/register", status_code=201)
async def register(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: MongoMotor = Depends(get_mongo_motor),
):
    """
    Registers a new user
    """
    user = await get_user_by_email(form_data.username, db)
    if user is None:
        user = User(
            api_account_id=str(uuid4()),
            token=str(uuid4()),
            email=form_data.username,
            password=hash_password(form_data.password),
            is_admin=False,
        )
        db.utilities_db["api_users"].bulk_write(
            [
                ReplaceOne(
                    {"_id": user.email},
                    user.model_dump(exclude_none=True),
                    upsert=True,
                )
            ]
        )

    else:
        pass


@router.get("/logout")
async def logout(request: Request, response: Response):
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("api.ccdexplorer.io")
    request.app.user = None
    return response
