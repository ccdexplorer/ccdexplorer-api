import grpc
from ccdexplorer_fundamentals.enums import NET
from ccdexplorer_fundamentals.GRPCClient import GRPCClient
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import CCD_AccountInfo, CCD_PoolInfo
from ccdexplorer_fundamentals.mongodb import Collections, MongoMotor, MongoDB
from ccdexplorer_fundamentals.tooter import Tooter, TooterChannel, TooterType  # noqa
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import datetime as dt
from app.state.state import get_grpcclient, get_mongo_db, get_mongo_motor


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


@router.get("/{net}/account/{index_or_hash}/info", response_class=JSONResponse)
async def get_account_info(
    request: Request,
    net: str,
    index_or_hash: int | str,
    grpcclient: GRPCClient = Depends(get_grpcclient),
) -> CCD_AccountInfo:
    """
    Endpoint to get all account info for a given account at the last final block.


    """

    try:
        # if this doesn't fail, it's type int.
        index_or_hash = int(index_or_hash)
    except ValueError:
        pass
    try:
        if isinstance(index_or_hash, int):
            try:
                result = grpcclient.get_account_info(
                    "last_final", account_index=index_or_hash, net=NET(net)
                )
            except grpc._channel._InactiveRpcError:
                result = None
        else:
            try:
                result = grpcclient.get_account_info(
                    "last_final", hex_address=index_or_hash, net=NET(net)
                )
            except grpc._channel._InactiveRpcError:
                result = None
    except:  # noqa: E722
        raise HTTPException(
            status_code=404,
            detail=f"Requested account {index_or_hash} not found on {net}",
        )

    if result:
        return result
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested account {index_or_hash} not found on {net}",
        )


@router.get("/{net}/account/{index}/earliest-win-time", response_class=JSONResponse)
async def get_validator_earliest_win_time(
    request: Request,
    net: str,
    index: int,
    grpcclient: GRPCClient = Depends(get_grpcclient),
) -> dt.datetime:
    """
    Endpoint to get earliest win time for an account that is an active validator.
    """

    try:
        result = grpcclient.get_baker_earliest_win_time(baker_id=index, net=NET(net))
    except grpc._channel._InactiveRpcError:
        result = None

    if result:
        return result
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Can't get earliest win time for account {index} on {net}",
        )


@router.get("/{net}/account/{index}/pool-info", response_class=JSONResponse)
async def get_validator_pool_info(
    request: Request,
    net: str,
    index: int,
    grpcclient: GRPCClient = Depends(get_grpcclient),
) -> CCD_PoolInfo:
    """
    Endpoint to get the current pool info for an account that is an active validator.
    """

    try:
        result = grpcclient.get_pool_info_for_pool(
            pool_id=index, block_hash="last_final", net=NET(net)
        )
    except grpc._channel._InactiveRpcError:
        result = None

    if result:
        return result
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Can't get pool info for account {index} on {net}",
        )


@router.get(
    "/{net}/account/{index_or_hash}/staking-rewards-object", response_class=JSONResponse
)
async def get_staking_rewards_object(
    request: Request,
    net: str,
    index_or_hash: int | str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
) -> dict:
    """
    Endpoint to get all account info for a given account at the last final block.


    """
    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    raw_apy_object = await db_to_use[Collections.paydays_apy_intermediate].find_one(
        {"_id": index_or_hash}
    )

    lookup_apy_object = {
        "d30": {"sum_of_rewards": 0, "apy": 0},
        "d90": {"sum_of_rewards": 0, "apy": 0},
        "d180": {"sum_of_rewards": 0, "apy": 0},
    }
    if raw_apy_object:
        if "d30_apy_dict" in raw_apy_object:
            if raw_apy_object["d30_apy_dict"] is not None:
                d30_day = list(raw_apy_object["d30_apy_dict"].keys())[-1]
                lookup_apy_object["d30"] = raw_apy_object["d30_apy_dict"][d30_day]

        if "d90_apy_dict" in raw_apy_object:
            if raw_apy_object["d90_apy_dict"] is not None:
                d90_day = list(raw_apy_object["d90_apy_dict"].keys())[-1]
                lookup_apy_object["d90"] = raw_apy_object["d90_apy_dict"][d90_day]

        if "d180_apy_dict" in raw_apy_object:
            if raw_apy_object["d180_apy_dict"] is not None:
                d180_day = list(raw_apy_object["d180_apy_dict"].keys())[-1]
                lookup_apy_object["d180"] = raw_apy_object["d180_apy_dict"][d180_day]

    return lookup_apy_object
