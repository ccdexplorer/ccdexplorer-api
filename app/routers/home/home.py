from ccdexplorer_fundamentals.mongodb import (
    CollectionsUtilities,
    MongoMotor,
)
from fastapi import APIRouter, Depends, HTTPException, Request, Security
from app.ENV import API_KEY_HEADER, environment
from fastapi.responses import JSONResponse, HTMLResponse
from app.models import User

from fastapi.security import OAuth2PasswordRequestForm

from fastapi_login.exceptions import InvalidCredentialsException

from app.state_getters import get_mongo_motor, get_user_details
from app.jinja2_helpers import templates
from app.security import manager

router = APIRouter(include_in_schema=False)


@router.get("/")
async def home_route(request: Request):
    user: User = get_user_details(request)
    # if user:
    #     if not isinstance(user, User):
    #         user = User(**user)
    context = {"request": request, "env": environment, "user": user}
    return templates.TemplateResponse("plans/home.html", context)
