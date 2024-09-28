from fastapi import Request

import datetime as dt
from app.models import User

# from ccdexplorer_fundamentals.mongodb import MongoMotor


def get_and_save_user_from_collection(req: Request):
    if (
        dt.datetime.now().astimezone(dt.timezone.utc) - req.app.users_last_requested
    ).total_seconds() > 5:

        result = req.app.mongodb.utilities_db["api_users"].find({})
        req.app.users_from_collection = {x["token"]: User(**x) for x in list(result)}
        req.app.users_last_requested = dt.datetime.now().astimezone(dt.timezone.utc)


def get_user_details(req: Request, token: str = None) -> User | None:
    get_and_save_user_from_collection(req=req)
    if not token:
        token = req.cookies.get("api.ccdexplorer.io")

    try:
        users_from_collection = req.app.users_from_collection
        user = users_from_collection.get(token)
        if user:
            if type(user) is not User:
                user = User(**user)
    except AttributeError:
        user = None

    return user


async def get_mongo_db(req: Request):
    return req.app.mongodb


async def get_mongo_motor(req: Request):
    return req.app.motormongo


async def get_grpcclient(req: Request):
    return req.app.grpcclient


async def get_tooter(req: Request):
    return req.app.tooter


async def get_api_keys(req: Request = None, motormongo=None, app=None):
    if not motormongo:
        if (
            (
                dt.datetime.now().astimezone(dt.timezone.utc)
                - req.app.api_keys_last_requested
            ).total_seconds()
            < 60
        ) and (req.app.api_keys):
            pass

    else:
        if motormongo:
            db = motormongo.utilities_db
            app.api_keys = {
                x["_id"]: x
                for x in await db["api_api_keys"].find({}).to_list(length=None)
            }
        else:
            db = req.app.motormongo.utilities_db
            req.app.api_keys = {
                x["_id"]: x
                for x in await db["api_api_keys"].find({}).to_list(length=None)
            }
            req.app.api_keys_last_requested = dt.datetime.now().astimezone(
                dt.timezone.utc
            )
