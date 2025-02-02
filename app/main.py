# ruff: noqa: F403, F405, E402, E501, E722, F401

import datetime as dt
from contextlib import asynccontextmanager
from datetime import timedelta
from functools import lru_cache

import httpx
import requests
import urllib3
from aiomqtt.client import Message
from ccdexplorer_fundamentals.enums import NET
from ccdexplorer_fundamentals.mongodb import MongoDB, MongoMotor
from fastapi import FastAPI, HTTPException, Response, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse
from fastapi.security.api_key import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi_restful.tasks import repeat_every
from prometheus_fastapi_instrumentator import Instrumentator
from rich import print

from app.state_getters import *

urllib3.disable_warnings()

from ccdexplorer_fundamentals.GRPCClient import GRPCClient
from ccdexplorer_fundamentals.tooter import Tooter

from app.ENV import *
from app.models import rate_limit_rules
from app.routers.account import account
from app.routers.auth import auth
from app.routers.home import home
from app.routers.plans import plans

# # V2
from app.routers.v2 import (
    account_v2,
    accounts_v2,
    block_v2,
    blocks_v2,
    contract_v2,
    markets_v2,
    misc_v2,
    module_v2,
    modules_v2,
    site_user_v2,
    smart_wallet_v2,
    smart_wallets_v2,
    token_v2,
    tokens_v2,
    transaction_v2,
    transactions_v2,
)

grpcclient = GRPCClient()
tooter = Tooter()

mongodb = MongoDB(tooter, nearest=True)
motormongo = MongoMotor(tooter)

# ratelimit
from typing import Tuple

import paho.mqtt.client as mqtt
import sentry_sdk
from ratelimit import RateLimitMiddleware, Rule
from ratelimit.auths import EmptyInformation
from ratelimit.auths.session import from_session
from ratelimit.backends.redis import RedisBackend
from ratelimit.backends.simple import MemoryBackend
from ratelimit.backends.slidingredis import SlidingRedisBackend
from ratelimit.types import ASGIApp, Receive, Scope, Send
from redis.asyncio import StrictRedis

from app.ratelimiting import AUTH_FUNCTION, handle_429, handle_auth_error

if environment["SITE_URL"] != "http://127.0.0.1:8000":
    sentry_sdk.init(
        dsn=environment["SENTRY_DSN"],
        traces_sample_rate=1.0,
        _experiments={"continuous_profiling_auto_start": True},
    )


# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, reason_code, properties):
    print(f"MQTT connected with result code: {reason_code}")


def on_subscribe(client, userdata, mid, reason_code_list, properties):
    if reason_code_list[0].is_failure:
        print(f"Broker rejected you subscription: {reason_code_list[0]}")
    else:
        print(f"Broker granted the following QoS: {reason_code_list[0].value}")


def on_message(client, userdata, message: Message):
    if "info" in message.topic:
        grpcclient.connection_info(f"API on {RUN_ON_NET}", tooter, ADMIN_CHAT_ID)
    if "keys" in message.topic:
        save_api_keys_for_topic(mongodb=mongodb, app=app, for_="MQTT topic")


mqttc = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2,
    f"mqtt-{RUN_ON_NET}-{API_URL}-ccdexplorer-api",
)

mqttc.on_connect = on_connect
mqttc.on_subscribe = on_subscribe
mqttc.on_message = on_message

mqttc.username_pw_set(MQTT_USER, MQTT_PASSWORD)
mqttc.connect(MQTT_SERVER, 1883, 10)
mqttc.subscribe("ccdexplorer/services/api/#", qos=MQTT_QOS)
mqttc.loop_start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.templates = Jinja2Templates(directory="app/templates")
    app.grpcclient = grpcclient
    app.redis = StrictRedis.from_url(REDIS_URL)
    app.api_url = environment["API_URL"]
    app.httpx_client = httpx.AsyncClient(
        timeout=None, headers={"x-ccdexplorer-key": environment["CCDEXPLORER_API_KEY"]}
    )
    app.tooter = tooter
    app.mongodb = mongodb
    app.motormongo = motormongo
    app.mqtt = mqttc
    init_time = dt.datetime.now().astimezone(dt.timezone.utc) - timedelta(seconds=10)
    app.users_last_requested = init_time
    app.exchange_rates_last_requested = init_time
    app.blocks_per_day_last_requested = init_time
    app.api_keys_last_requested = init_time
    app.api_keys = await get_api_keys(motormongo=motormongo, app=app, for_="lifespan")
    app.exchange_rates = None
    app.blocks_per_day = None

    yield
    pass


tags_metadata = [
    {
        "name": "Transaction",
        "description": "Routes to retrieve information from a transaction.",
    },
    # {
    #     "name": "Token",
    #     "description": "Routes to retrieve information from a token.",
    # },
    {
        "name": "Account",
        "description": "Routes to retrieve information from an account.",
        "externalDocs": {
            "description": "GRPC Models",
            "url": "https://github.com/ccdexplorer/ccdexplorer-fundamentals/blob/main/docs/grpc_types_docs.md",
        },
    },
]


app = FastAPI(
    lifespan=lifespan,
    # docs_url=None,
    swagger_ui_parameters={"syntaxHighlight.theme": "obsidian"},
    openapi_tags=tags_metadata,
    separate_input_output_schemas=False,
    title="CCDExplorer.io API",
    summary="The API service for CCDExplorer.io.",
    version="1.0.0",
    contact={
        "name": "explorer.ccd on Telegram",
    },
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    },
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/node", StaticFiles(directory="node_modules"), name="node_modules")

origins = [
    "http://127.0.0.1:7000",
    "https://127.0.0.1:7000",
    "http://api.ccdexplorer.io",
    "https://api.ccdexplorer.io",
    "http://dev-api.ccdexplorer.io",
    "https://dev-api.ccdexplorer.io",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.add_middleware(
    RateLimitMiddleware,
    authenticate=AUTH_FUNCTION,
    # if ever the plan to go to a sliding window technique, use this.
    # backend=SlidingRedisBackend(StrictRedis.from_url(REDIS_URL)),
    backend=RedisBackend(StrictRedis.from_url(REDIS_URL)),
    on_auth_error=handle_auth_error,
    on_blocked=handle_429,
    config={r"^/v2": rate_limit_rules},
)

instrumentator = Instrumentator().instrument(app)
instrumentator.expose(app)

# # V2
app.include_router(account_v2.router)
app.include_router(accounts_v2.router)
app.include_router(transaction_v2.router)
app.include_router(transactions_v2.router)
app.include_router(token_v2.router)
app.include_router(tokens_v2.router)
app.include_router(block_v2.router)
app.include_router(blocks_v2.router)
app.include_router(markets_v2.router)
app.include_router(contract_v2.router)
app.include_router(misc_v2.router)
app.include_router(module_v2.router)
app.include_router(modules_v2.router)
app.include_router(smart_wallet_v2.router)
app.include_router(smart_wallets_v2.router)

# auth, content, key management
app.include_router(auth.router)
app.include_router(home.router)
app.include_router(account.router)
app.include_router(plans.router)

# site user
app.include_router(site_user_v2.router)

# @app.get("/docs", include_in_schema=False)
# async def custom_swagger_ui_html_cdn():
#     return get_swagger_ui_html(
#         openapi_url=app.openapi_url,
#         title=f"{app.title} - Swagger UI",
#         # swagger_ui_dark.css CDN link
#         swagger_css_url="https://cdn.jsdelivr.net/gh/Itz-fork/Fastapi-Swagger-UI-Dark/assets/swagger_ui_dark.min.css",
#     )
