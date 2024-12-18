from fastapi import Request
from app.ENV import API_URL
import datetime as dt
from app.models import User
from ccdexplorer_fundamentals.mongodb import (
    CollectionsUtilities,
    Collections,
    MongoTypeBlockPerDay,
)


async def get_httpx_client(req: Request):
    return req.app.httpx_client


def get_and_save_user_from_collection(req: Request):
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
            < 10
        ) and (req.app.api_keys):
            req.app.api_keys

    else:
        now = dt.datetime.now().astimezone(dt.UTC)
        pipeline = [
            {"$match": {"scope": API_URL}},
            {"$match": {"api_key_end_date": {"$gte": now}}},
        ]

        db = motormongo.utilities_db if motormongo else req.app.motormongo.utilities_db

        keys = {
            x["_id"]: x
            for x in await db["api_api_keys"].aggregate(pipeline).to_list(length=None)
        }
        if motormongo:
            app.api_keys = keys
            app.api_keys_last_requested = now
        else:
            req.app.api_keys = keys
            req.app.api_keys_last_requested = now
    return keys


def get_exchange_rates(
    req: Request = None,
    motormongo=None,
    app=None,
):
    collection = req.app.mongodb.utilities if req else app.mongodb.utilities
    exchange_rates = req.app.exchange_rates if req else app.exchange_rates
    exchange_rates_last_requested = (
        req.app.exchange_rates_last_requested
        if req
        else app.exchange_rates_last_requested
    )
    if (
        (
            dt.datetime.now().astimezone(dt.timezone.utc)
            - exchange_rates_last_requested
        ).total_seconds()
        < 10
    ) and (exchange_rates):
        pass

    else:
        coll = collection[CollectionsUtilities.exchange_rates]

        exchange_rates = {x["token"]: x for x in coll.find({})}

        exchange_rates_last_requested = dt.datetime.now().astimezone(dt.timezone.utc)
        if req:
            req.app.exchange_rates = exchange_rates
            req.app.exchange_rates_last_requested = exchange_rates_last_requested
        else:
            app.exchange_rates = exchange_rates
            app.exchange_rates_last_requested = exchange_rates_last_requested
    return exchange_rates


def get_blocks_per_day(
    req: Request,
):
    if (
        (
            dt.datetime.now().astimezone(dt.timezone.utc)
            - req.app.blocks_per_day_last_requested
        ).total_seconds()
        < 60
    ) and (req.app.blocks_per_day):
        pass

    else:
        if "net" in req.path_params:
            db_to_use = (
                req.app.mongodb.testnet
                if req.path_params["net"] == "testnet"
                else req.app.mongodb.mainnet
            )
        else:
            db_to_use = req.app.mongodb.mainnet

        result = {
            x["_id"]: MongoTypeBlockPerDay(**x)
            for x in db_to_use[Collections.blocks_per_day].find({})
        }
        req.app.blocks_per_day = result
        req.app.blocks_per_day_last_requested = dt.datetime.now().astimezone(
            dt.timezone.utc
        )

    return req.app.blocks_per_day
