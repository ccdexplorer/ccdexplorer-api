from uuid import uuid4
import httpx
import math
from ccdexplorer_fundamentals.cis import MongoTypeLoggedEvent, transferEvent
from ccdexplorer_fundamentals.mongodb import (
    MongoMotor,
    Collections,
    CollectionsUtilities,
    MongoDB,
)
import io
import datetime as dt
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import CCD_BlockItemSummary
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from pymongo import ReplaceOne, DeleteOne
import dateutil
from app.ENV import environment, API_NET, API_URL
from app.jinja2_helpers import templates
from app.models import APIKey, User, APIPayment, APIPlans, plans
from app.state_getters import (
    get_mongo_motor,
    get_user_details,
    get_httpx_client,
    get_mongo_db,
    get_api_keys,
)

router = APIRouter(include_in_schema=False)


async def get_user_api_keys(user, mongomotor):
    pipeline = [
        {"$match": {"scope": API_URL}},
        {"$match": {"api_account_id": user.api_account_id}},
    ]
    result = (
        await mongomotor.utilities_db["api_api_keys"]
        .aggregate(pipeline)
        .to_list(length=None)
    )
    user_api_keys = [APIKey(**x) for x in result]
    return user_api_keys


async def get_payment_tx_and_update_payments(
    request: Request, user: User, db_to_use, euroe_tag: dict, token_address: str
):
    pipeline = [
        {"$match": {"result.to_address": user.alias_account_id}},
        {"$match": {"token_address": token_address}},
    ]
    result = (
        await db_to_use[Collections.tokens_logged_events]
        .aggregate(pipeline)
        .to_list(length=None)
    )
    events = [MongoTypeLoggedEvent(**x) for x in result]

    user.payments = {}
    if user.plan:
        for event in events:
            event_result = transferEvent(**event.result)
            amount_euroe = event_result.token_amount * (
                math.pow(10, -euroe_tag["decimals"])
            )
            if amount_euroe > 0:
                days = amount_euroe / plans[APIPlans[user.plan]].rate
            else:
                days = 0
            user.payments[event.tx_hash] = APIPayment(
                tx_hash=event.tx_hash,
                tx_date=event.date,
                amount_euroe=event_result.token_amount
                * (math.pow(10, -euroe_tag["decimals"])),
                paid_days_for_plan=days,
            )

        _ = await request.app.motormongo.utilities[
            CollectionsUtilities.api_users
        ].bulk_write(
            [
                ReplaceOne(
                    {"_id": user.api_account_id},
                    user.model_dump(exclude_none=True),
                    upsert=True,
                )
            ]
        )
        await set_end_date_for_plan(user, request.app.motormongo)


@router.get("/account")
async def account_home(
    request: Request,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
):
    user: User = get_user_details(request)
    if not user:
        response = RedirectResponse(url="/auth/login", status_code=303)
        return response

    request.app.api_keys = await get_api_keys(motormongo=mongomotor, app=request.app)
    # find transactions through logged events
    db_to_use = (
        request.app.motormongo.testnet
        if API_NET == "testnet"
        else request.app.motormongo.mainnet
    )
    token_address = "<7260,0>-" if API_NET == "testnet" else "<9390,>-"
    euroe_tag = await db_to_use[Collections.tokens_tags].find_one({"_id": "EUROe"})

    _ = await get_payment_tx_and_update_payments(
        request, user, db_to_use, euroe_tag, token_address
    )

    total_paid_amount = [payment.amount_euroe for payment in user.payments.values()]

    user_api_keys = await get_user_api_keys(user, request.app.motormongo)
    if len(user_api_keys) == 0:
        sample_key = "528e6511-d55a-49d3-a4f1-fcce5eef03cc"
    else:
        sample_key = user_api_keys[0].id

    # reload from collection
    user: User = get_user_details(request)
    context = {
        "request": request,
        "env": environment,
        "user": user,
        "user_api_keys": user_api_keys,
        "sample_key": sample_key,
        "total_paid_amount": total_paid_amount,
        "net": API_NET,
    }
    return templates.TemplateResponse("account/home.html", context)


@router.get("/account/keys")
async def account_keys(request: Request):
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
    return templates.TemplateResponse("account/keys.html", context)


@router.post(
    "/account/refresh",
)
async def account_home_refresh(
    request: Request,
):
    response = RedirectResponse(url="/account", status_code=200)
    response.headers["HX-Refresh"] = "true"
    return response


@router.post("/account/new-key")
async def account_new_key(
    request: Request,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
):
    user: User = get_user_details(request)

    # api keys for the free plan are always active, set to 365 days (but of course rate limited)
    if user.plan == "free":
        api_key_end_date = dt.datetime.now().astimezone(dt.UTC) + dt.timedelta(days=365)
    # api keys for paid plans are initially
    else:
        api_key_end_date = user.plan_end_date

    key_id = str(uuid4())
    key_to_add = APIKey(
        api_account_id=user.api_account_id,
        scope=API_URL,
        api_group=user.plan,
        # id=key_id,
        api_key_end_date=api_key_end_date,
    )

    request.app.motormongo.utilities_db["api_api_keys"].bulk_write(
        [
            ReplaceOne(
                {"_id": key_id},
                key_to_add.model_dump(),
                upsert=True,
            )
        ]
    )
    request.app.api_keys = await get_api_keys(motormongo=mongomotor, app=request.app)
    response = RedirectResponse(url="/account", status_code=200)
    response.headers["HX-Redirect"] = "/account"
    return response


@router.delete("/account/key/{key}")
async def account_delete_key(
    request: Request,
    key: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
):
    request.app.motormongo.utilities_db["api_api_keys"].bulk_write(
        [
            DeleteOne(
                {"_id": key},
            )
        ]
    )
    request.app.api_keys = await get_api_keys(motormongo=mongomotor, app=request.app)
    response = RedirectResponse(url="/account", status_code=200)
    response.headers["HX-Redirect"] = "/account"
    return response


async def set_end_date_for_plan(user: User, mongomotor: MongoMotor):
    # 1 get tx hashes from payments
    # 2 get
    if len(user.payments) == 0:
        user.active = False
        if user.plan == "free":
            end_date = dt.datetime.now().astimezone(dt.UTC) + dt.timedelta(days=365)
        else:
            end_date = dt.datetime.now().astimezone(dt.UTC) - dt.timedelta(days=1)
    else:
        sorted_txs = sorted(user.payments.items(), key=lambda x: x[1].tx_date)
        # set initial value
        start_date = dateutil.parser.parse(sorted_txs[0][1].tx_date)
        end_date = start_date

        for _, tx in sorted_txs:
            start_date = dateutil.parser.parse(tx.tx_date)
            if start_date < end_date:
                # calculate the overlap days
                days_overlap = (end_date - start_date).total_seconds() / (60 * 60 * 24)
                end_date = start_date + dt.timedelta(
                    days=tx.paid_days_for_plan + int(days_overlap)
                )
            else:
                # either there is just 1 payment,
                # or the user has a period between the previous payment ending
                # and the next payment
                end_date = start_date + dt.timedelta(days=tx.paid_days_for_plan)

    user.plan_end_date = dt.datetime.combine(end_date, dt.time.max)
    # write back to user
    _ = await mongomotor.utilities[CollectionsUtilities.api_users].bulk_write(
        [
            ReplaceOne(
                {"_id": user.api_account_id},
                user.model_dump(exclude_none=True),
                upsert=True,
            )
        ]
    )

    # await get_user_api_keys(user, mongomotor)


async def set_end_date_for_api_keys(user: User, mongomotor: MongoMotor):
    if len(user.payments) == 0:
        user.active = False

    await get_user_api_keys(user, mongomotor)
