from ccdexplorer_fundamentals.mongodb import (
    CollectionsUtilities,
    MongoMotor,
)
from fastapi import APIRouter, Depends, HTTPException, Request, Security
from app.ENV import API_KEY_HEADER, environment
from fastapi.responses import JSONResponse, HTMLResponse
from app.models import User, plans_for_display

from fastapi.security import OAuth2PasswordRequestForm

from fastapi_login.exceptions import InvalidCredentialsException

from app.state_getters import get_mongo_motor, get_user_details
from app.jinja2_helpers import templates
from app.security import manager

router = APIRouter(include_in_schema=False)


@router.get("/")
async def home_route(
    request: Request,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
):
    user: User = get_user_details(request)
    faqs = [
        x
        for x in await mongomotor.utilities_db["api_faq"].find({}).to_list(length=None)
    ]
    context = {
        "request": request,
        "env": environment,
        "user": user,
        "faqs": faqs,
        "plans_for_display": plans_for_display,
    }
    return templates.TemplateResponse("plans/home.html", context)
