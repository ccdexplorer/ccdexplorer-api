import grpc
from ccdexplorer_fundamentals.enums import NET
from ccdexplorer_fundamentals.GRPCClient import GRPCClient
from ccdexplorer_fundamentals.mongodb import (
    Collections,
    MongoDB,
)
from ccdexplorer_fundamentals.tooter import Tooter, TooterChannel, TooterType  # noqa
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.state.state import get_grpcclient, get_mongo_db


class TokenHolding(BaseModel):
    token_address: str
    contract: str
    token_id: str
    token_amount: str


router = APIRouter(tags=["Account"], prefix="/v1")


@router.get("/{net}/account/{account_address}/tokens", response_class=JSONResponse)
async def get_account_tokens(
    request: Request,
    net: str,
    account_address: str,
    mongodb: MongoDB = Depends(get_mongo_db),
) -> list[TokenHolding]:
    """
    Endpoint to get all tokens for a given account, as stored in MongoDB collection `tokens_links_v2`.


    """
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    result_list = list(
        db_to_use[Collections.tokens_links_v2].find(
            {"account_address_canonical": account_address[:29]}
        )
    )
    tokens = [TokenHolding(**x["token_holding"]) for x in result_list]

    if len(tokens) > 0:

        return tokens
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested account ({account_address}) has no tokens on {net}",
        )


@router.get(
    "/{net}/account/{account_address}/balance/block/{block}",
    response_class=JSONResponse,
)
async def get_account_balance_at_block(
    request: Request,
    net: str,
    account_address: str,
    block: int,
    grpcclient: GRPCClient = Depends(get_grpcclient),
) -> int:
    """
    Endpoint to get all CCD balance in microCCD for a given account at the given block.


    """
    try:
        result = grpcclient.get_account_info(block, account_address, net=NET(net))
    except grpc._channel._InactiveRpcError:
        result = None

    if result:
        return result.amount
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested account {account_address} or block {block:,.0f} not found on {net}",
        )


@router.get("/{net}/account/{account_address}/balance", response_class=JSONResponse)
async def get_account_balance(
    request: Request,
    net: str,
    account_address: str,
    grpcclient: GRPCClient = Depends(get_grpcclient),
) -> int:
    """
    Endpoint to get all CCD balance in microCCD for a given account at the last final block.


    """
    try:
        result = grpcclient.get_account_info(
            "last_final", account_address, net=NET(net)
        )
    except grpc._channel._InactiveRpcError:
        result = None

    if result:
        return result.amount
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested account {account_address} not found on {net}",
        )
