# ruff: noqa: F403, F405, E402, E501, E722, F401

import datetime as dt
from datetime import timedelta
import gc
import logging
import uuid
from functools import lru_cache
import resource
import requests
import urllib3
from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi_restful.tasks import repeat_every
from rich import print
from ccdexplorer_fundamentals.mongodb import MongoDB, MongoMotor
from prometheus_fastapi_instrumentator import Instrumentator

# from app.__chain import *
from app.state.state import *

urllib3.disable_warnings()

from ccdexplorer_fundamentals.GRPCClient import GRPCClient

from app.console import console
from app.ENV import *
from app.routers import transaction_v1
from app.routers import transactions_v1
from app.routers import account_v1
from app.routers import token_v1
from app.routers import block_v1
from app.routers import blocks_v1

from ccdexplorer_fundamentals.tooter import Tooter

grpcclient = GRPCClient()
tooter = Tooter()

mongodb = MongoDB(tooter, nearest=True)
motormongo = MongoMotor(tooter)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the ML model
    app.grpcclient = grpcclient
    app.tooter = tooter
    app.mongodb = mongodb
    app.motormongo = motormongo
    yield
    # Any cleanup should happen here
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
    openapi_tags=tags_metadata,
    separate_input_output_schemas=False,
    title="CCDExplorer.io API",
    summary="The API service for CCDExplorer.io.",
    version="0.0.1",
    contact={
        "name": "explorer.ccd on Telegram",
    },
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    },
)
instrumentator = Instrumentator().instrument(app)

app.include_router(account_v1.router)
app.include_router(transaction_v1.router)
app.include_router(transactions_v1.router)
app.include_router(token_v1.router)
app.include_router(block_v1.router)
app.include_router(blocks_v1.router)
