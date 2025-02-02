import grpc
from pymongo.collection import Collection
from ccdexplorer_fundamentals.enums import NET
from ccdexplorer_fundamentals.cis import MongoTypeLoggedEvent
from ccdexplorer_fundamentals.GRPCClient import GRPCClient
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import (
    CCD_AccountInfo,
    CCD_PoolInfo,
    CCD_BlockItemSummary,
    CCD_ContractAddress,
)
import dateutil
from ccdexplorer_fundamentals.mongodb import (
    Collections,
    MongoMotor,
    MongoDB,
    MongoTypePayday,
    MongoTypeBlockPerDay,
    MongoImpactedAddress,
)
from fastapi import APIRouter, Depends, HTTPException, Request, Security
from app.ENV import API_KEY_HEADER
from fastapi.responses import JSONResponse
import datetime as dt
import math
from pymongo import DESCENDING, ASCENDING
from app.state_getters import (
    get_grpcclient,
    get_mongo_db,
    get_mongo_motor,
    get_exchange_rates,
    get_blocks_per_day,
)
from app.routers.v2.contract_v2 import (
    get_balance_of,
    GetBalanceOfRequest,
    get_module_name_from_contract_address,
)
from app.utils import TokenHolding


router = APIRouter(tags=["Account"], prefix="/v2")


async def convert_account_fungible_tokens_value_to_USD(
    tokens_dict: dict[str, TokenHolding], db_to_use: Collection, exchange_rates
):
    tokens_tags = {
        x["contracts"][0]: x
        for x in await db_to_use[Collections.tokens_tags]
        .find({"token_type": "fungible"})
        .to_list(length=None)
    }

    tokens_with_metadata: dict[str, TokenHolding] = {}
    for contract, d in tokens_dict.items():
        if contract in tokens_tags.keys():
            # it's a single use contract
            d.decimals = tokens_tags[contract]["decimals"]
            d.token_symbol = tokens_tags[contract]["get_price_from"]
            d.token_value = int(d.token_amount) * (math.pow(10, -d.decimals))

            if d.token_symbol in exchange_rates:
                d.token_value_USD = (
                    d.token_value * exchange_rates[d.token_symbol]["rate"]
                )

            else:
                d.token_value_USD = 0
            tokens_with_metadata[contract] = d

    tokens_value_USD = sum([x.token_value_USD for x in tokens_with_metadata.values()])
    return tokens_value_USD


@router.get(
    "/{net}/account/{account_address}/received-tokens/{contract_index}/{contract_subindex}",
    response_class=JSONResponse,
)
async def get_account_tokens_received(
    request: Request,
    net: str,
    account_address: str,
    contract_index: int,
    contract_subindex: int,
    mongodb: MongoDB = Depends(get_mongo_db),
    api_key: str = Security(API_KEY_HEADER),
) -> list[TokenHolding]:
    """
    Endpoint to get all received tokens for a given account, as stored in MongoDB collection `tokens_logged_events`.


    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    pipeline = [
        {"$match": {"contract": f"<{contract_index},{contract_subindex}>"}},
        {"$match": {"event_type": "transfer_event"}},
        {"$match": {"result.to_address": f"{account_address}"}},
    ]
    result_list = list(db_to_use[Collections.tokens_logged_events].aggregate(pipeline))

    logged_events = [MongoTypeLoggedEvent(**x) for x in result_list]

    if len(logged_events) > 0:

        return logged_events
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested account ({account_address}) has not received tokens from contract <{contract_index},{contract_subindex}> on {net}",
        )


@router.get(
    "/{net}/account/{account_address}/tokens-available", response_class=JSONResponse
)
async def get_account_tokens_available(
    request: Request,
    net: str,
    account_address: str,
    mongodb: MongoDB = Depends(get_mongo_db),
    api_key: str = Security(API_KEY_HEADER),
) -> bool:
    """
    Endpoint to determine if a given account holds tokens, as stored in MongoDB collection `tokens_links_v3`.


    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    result_list = list(
        db_to_use[Collections.tokens_links_v3]
        .find({"account_address_canonical": account_address[:29]})
        .limit(1)
    )
    tokens = [TokenHolding(**x["token_holding"]) for x in result_list]

    return len(tokens) > 0


@router.get(
    "/{net}/account/{account_address}/fungible-tokens/USD", response_class=JSONResponse
)
async def get_account_fungible_tokens_value_in_USD(
    request: Request,
    net: str,
    account_address: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    exchange_rates: dict = Depends(get_exchange_rates),
    api_key: str = Security(API_KEY_HEADER),
) -> float:
    """
    Endpoint to get sum of all fungible tokens in USD for a given account, as stored in MongoDB collection `tokens_links_v3`.


    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet

    # first get all contracts for fungible tokens
    fungible_contracts = {
        x["contracts"][0]: x
        for x in await db_to_use[Collections.tokens_tags]
        .find({"token_type": "fungible"}, {"_id": 1, "contracts": 1})
        .to_list(length=None)
    }
    pipeline = [
        {
            "$match": {
                "token_holding.contract": {"$in": list(fungible_contracts.keys())}
            }
        },
        {"$match": {"account_address_canonical": account_address[:29]}},
    ]
    result_list = (
        await db_to_use[Collections.tokens_links_v3]
        .aggregate(pipeline)
        .to_list(length=None)
    )

    tokens = [TokenHolding(**x["token_holding"]) for x in result_list]

    # use grpc balance_of method
    for token in tokens:
        result = await db_to_use[Collections.tokens_tags].find_one(
            {"related_token_address": token.token_address}
        )
        if result:
            if "module_name" not in result:
                module_name = await get_module_name_from_contract_address(
                    db_to_use, CCD_ContractAddress.from_str(token.contract)
                )

            else:
                module_name = result["module_name"]

            contract = result["contracts"][0]
            request = GetBalanceOfRequest(
                net=net,
                contract_address=CCD_ContractAddress.from_str(contract),
                token_id=(
                    ""
                    if result["related_token_address"].replace(contract, "") == "-"
                    else result["related_token_address"].replace(f"{contract}-", "")
                ),
                module_name=module_name,
                addresses=[account_address],
                grpcclient=grpcclient,
            )
            token_amount_from_state = await get_balance_of(request)
            token.token_amount = token_amount_from_state.get(account_address, 0)

    if len(tokens) > 0:
        tokens_value_USD = await convert_account_fungible_tokens_value_to_USD(
            {x.contract: x for x in tokens},
            db_to_use,
            exchange_rates,
        )
        return tokens_value_USD
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested account ({account_address}) has no tokens on {net}",
        )


@router.get(
    "/{net}/account/{account_address}/token-symbols-for-flow",
    response_class=JSONResponse,
)
async def get_account_token_symbols_for_flow(
    request: Request,
    net: str,
    account_address: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> list[str]:
    """
    Endpoint to get all fungible tokens for a given account, even if the current balance is zero.


    """
    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet

    # first get all contracts for fungible tokens
    fungible_contracts = {
        x["contracts"][0]: x
        for x in await db_to_use[Collections.tokens_tags]
        .find({"token_type": "fungible"}, {"_id": 1, "contracts": 1})
        .to_list(length=None)
    }

    pipeline = [
        {"$match": {"effect_type": {"$ne": "data_registered"}}},
        {"$match": {"contract": {"$exists": True}}},
        {
            "$match": {"impacted_address_canonical": {"$eq": account_address[:29]}},
        },
        {"$match": {"contract": {"$in": list(fungible_contracts.keys())}}},
        {
            "$match": {"event_type": {"$exists": True}},
        },
        {
            "$group": {
                "_id": "$contract",
            }
        },
        {
            "$project": {
                "_id": 0,
                "contract": "$_id",
            }
        },
    ]
    contracts = (
        await db_to_use[Collections.impacted_addresses]
        .aggregate(pipeline)
        .to_list(length=None)
    )

    if len(contracts) > 0:
        contracts_for_account = [x["contract"] for x in contracts]

        return sorted(
            [
                value["_id"]
                for key, value in fungible_contracts.items()
                if key in contracts_for_account
            ]
        )
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested account ({account_address}) has no tokens on {net}",
        )


@router.get(
    "/{net}/account/{account_address}/fungible-tokens/{skip}/{limit}/verified",
    response_class=JSONResponse,
)
async def get_account_fungible_tokens_verified(
    request: Request,
    net: str,
    account_address: str,
    skip: int,
    limit: int,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    exchange_rates: dict = Depends(get_exchange_rates),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """
    Endpoint to get verified fungible tokens for a given account, as stored in MongoDB collection `tokens_links_v3`.
    """

    # if net == "testnet":
    #     raise HTTPException(
    #         status_code=404,
    #         detail=f"Fungible verified tokens are not tracked on {net}",
    #     )

    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    if skip < 0:
        raise HTTPException(
            status_code=400,
            detail="Don't be silly. Skip must be greater than or equal to zero.",
        )

    if limit > 100:
        raise HTTPException(
            status_code=400,
            detail="Limit must be less than or equal to 100.",
        )

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    fungible_token_result = (
        await db_to_use[Collections.tokens_tags]
        .find({"token_type": "fungible"}, {"related_token_address": 1})
        .to_list(length=None)
    )

    fungible_token_addresses = [
        x["related_token_address"]
        for x in fungible_token_result
        if "related_token_address" in x
    ]

    pipeline = [
        {"$match": {"account_address_canonical": account_address[:29]}},
        {"$match": {"token_holding.token_address": {"$in": fungible_token_addresses}}},
        {
            "$facet": {
                "metadata": [{"$count": "total"}],
                "data": [{"$skip": skip}, {"$limit": limit}],
            }
        },
        {
            "$project": {
                "data": 1,
                "total": {"$arrayElemAt": ["$metadata.total", 0]},
            }
        },
    ]
    result = (
        await db_to_use[Collections.tokens_links_v3]
        .aggregate(pipeline)
        .to_list(length=None)
    )
    all_tokens = [x for x in result[0]["data"]]
    if "total" in result[0]:
        total_token_count = result[0]["total"]
    else:
        total_token_count = 0
    tokens = [TokenHolding(**x["token_holding"]) for x in all_tokens]

    # add verified information and metadata and USD value
    for index, token in enumerate(tokens):

        result = await db_to_use[Collections.tokens_tags].find_one(
            {"related_token_address": token.token_address}
        )
        token.verified_information = result
        if "module_name" not in result:
            module_name = await get_module_name_from_contract_address(
                db_to_use, CCD_ContractAddress.from_str(token.contract)
            )

        else:
            module_name = result["module_name"]

        contract = result["contracts"][0]
        request = GetBalanceOfRequest(
            net=net,
            contract_address=CCD_ContractAddress.from_str(contract),
            token_id=(
                ""
                if result["related_token_address"].replace(contract, "") == "-"
                else result["related_token_address"].replace(f"{contract}-", "")
            ),
            module_name=module_name,
            addresses=[all_tokens[index]["account_address"]],
            grpcclient=grpcclient,
        )
        token_amount_from_state = await get_balance_of(request)
        token.token_amount = token_amount_from_state.get(
            all_tokens[index]["account_address"], 0
        )

        token.token_symbol = token.verified_information["get_price_from"]
        token.decimals = token.verified_information["decimals"]
        token.token_value = int(token.token_amount) * (math.pow(10, -token.decimals))
        if token.token_symbol in exchange_rates:
            token.token_value_USD = (
                token.token_value * exchange_rates[token.token_symbol]["rate"]
            )
        else:
            token.token_value_USD = 0

        result = await db_to_use[Collections.tokens_token_addresses_v2].find_one(
            {"_id": token.token_address}
        )
        token.address_information = result

    if len(tokens) > 0:

        return {"tokens": tokens, "total_token_count": total_token_count}
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested account ({account_address}) has no fungible verified tokens on {net}",
        )


@router.get(
    "/{net}/account/{account_address}/non-fungible-tokens/{skip}/{limit}/verified",
    response_class=JSONResponse,
)
async def get_account_non_fungible_tokens_verified(
    request: Request,
    net: str,
    account_address: str,
    skip: int,
    limit: int,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    exchange_rates: dict = Depends(get_exchange_rates),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """
    Endpoint to get verified non fungible tokens for a given account, as stored in MongoDB collection `tokens_links_v3`.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    if skip < 0:
        raise HTTPException(
            status_code=400,
            detail="Don't be silly. Skip must be greater than or equal to zero.",
        )

    if limit > 100:
        raise HTTPException(
            status_code=400,
            detail="Limit must be less than or equal to 100.",
        )

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    non_fungible_token_contracts = [
        x["contracts"]
        for x in await db_to_use[Collections.tokens_tags]
        .find({"token_type": "non-fungible"}, {"contracts": 1})
        .to_list(length=None)
    ]
    non_fungible_token_contracts = [
        item for row in non_fungible_token_contracts for item in row
    ]
    pipeline = [
        {"$match": {"account_address_canonical": account_address[:29]}},
        {"$match": {"token_holding.contract": {"$in": non_fungible_token_contracts}}},
        {
            "$facet": {
                "metadata": [{"$count": "total"}],
                "data": [{"$skip": skip}, {"$limit": limit}],
            }
        },
        {
            "$project": {
                "data": 1,
                "total": {"$arrayElemAt": ["$metadata.total", 0]},
            }
        },
    ]
    result = (
        await db_to_use[Collections.tokens_links_v3]
        .aggregate(pipeline)
        .to_list(length=None)
    )
    all_tokens = [x for x in result[0]["data"]]
    if "total" in result[0]:
        total_token_count = result[0]["total"]
    else:
        total_token_count = 0
    tokens = [TokenHolding(**x["token_holding"]) for x in all_tokens]

    # add verified information and metadata
    for token in tokens:

        result = await db_to_use[Collections.tokens_tags].find_one(
            {"contracts": {"$in": [token.contract]}}
        )
        token.verified_information = result
        if "module_name" not in result:
            module_name = await get_module_name_from_contract_address(
                db_to_use, CCD_ContractAddress.from_str(token.contract)
            )

        else:
            module_name = result["module_name"]

        request = GetBalanceOfRequest(
            net=net,
            contract_address=CCD_ContractAddress.from_str(token.contract),
            token_id=token.token_id,
            module_name=module_name,
            addresses=[account_address],
            grpcclient=grpcclient,
        )
        token_amount_from_state = await get_balance_of(request)
        token.token_amount = token_amount_from_state.get(account_address, 0)
        result = await db_to_use[Collections.tokens_token_addresses_v2].find_one(
            {"_id": token.token_address}
        )
        token.address_information = result

    if len(tokens) > 0:

        return {"tokens": tokens, "total_token_count": total_token_count}
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested account ({account_address}) has no fungible verified tokens on {net}",
        )


@router.get(
    "/{net}/account/{account_address}/tokens/{skip}/{limit}/unverified",
    response_class=JSONResponse,
)
async def get_account_tokens_unverified(
    request: Request,
    net: str,
    account_address: str,
    skip: int,
    limit: int,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    exchange_rates: dict = Depends(get_exchange_rates),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """
    Endpoint to get unverified tokens for a given account, as stored in MongoDB collection `tokens_links_v3`.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    if skip < 0:
        raise HTTPException(
            status_code=400,
            detail="Don't be silly. Skip must be greater than or equal to zero.",
        )

    if limit > 100:
        raise HTTPException(
            status_code=400,
            detail="Limit must be less than or equal to 100.",
        )

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    verified_token_contracts = [
        x["contracts"]
        for x in await db_to_use[Collections.tokens_tags]
        .find({}, {"contracts": 1})
        .to_list(length=None)
    ]
    verified_token_contracts = [
        item for row in verified_token_contracts for item in row
    ]
    pipeline = [
        {"$match": {"account_address_canonical": account_address[:29]}},
        {"$match": {"token_holding.contract": {"$nin": verified_token_contracts}}},
        {
            "$facet": {
                "metadata": [{"$count": "total"}],
                "data": [{"$skip": skip}, {"$limit": limit}],
            }
        },
        {
            "$project": {
                "data": 1,
                "total": {"$arrayElemAt": ["$metadata.total", 0]},
            }
        },
    ]
    result = (
        await db_to_use[Collections.tokens_links_v3]
        .aggregate(pipeline)
        .to_list(length=None)
    )
    all_tokens = [x for x in result[0]["data"]]
    if "total" in result[0]:
        total_token_count = result[0]["total"]
    else:
        total_token_count = 0
    tokens = [TokenHolding(**x["token_holding"]) for x in all_tokens]

    # add metadata
    for token in tokens:
        result = await db_to_use[Collections.tokens_token_addresses_v2].find_one(
            {"_id": token.token_address}
        )
        token.address_information = result

        module_name = await get_module_name_from_contract_address(
            db_to_use, CCD_ContractAddress.from_str(token.contract)
        )

        request = GetBalanceOfRequest(
            net=net,
            contract_address=CCD_ContractAddress.from_str(token.contract),
            token_id=token.token_id,
            module_name=module_name,
            addresses=[account_address],
            grpcclient=grpcclient,
        )
        token_amount_from_state = await get_balance_of(request)
        if token_amount_from_state != []:
            token.token_amount = token_amount_from_state.get(account_address, 0)
    if len(tokens) > 0:

        return {"tokens": tokens, "total_token_count": total_token_count}
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested account ({account_address}) has no fungible verified tokens on {net}",
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
    api_key: str = Security(API_KEY_HEADER),
) -> int:
    """
    Endpoint to get all CCD balance in microCCD for a given account at the given block.


    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

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


@router.get("/{net}/account/{account_address}/balance/USD", response_class=JSONResponse)
async def get_account_balance_in_USD(
    request: Request,
    net: str,
    account_address: str,
    grpcclient: GRPCClient = Depends(get_grpcclient),
    exchange_rates: dict = Depends(get_exchange_rates),
    api_key: str = Security(API_KEY_HEADER),
) -> float:
    """
    Endpoint to get all CCD balance in microCCD converted to USD for a given account at the last final block.


    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    try:
        result = grpcclient.get_account_info(
            "last_final", account_address, net=NET(net)
        )
    except grpc._channel._InactiveRpcError:
        result = None

    if result:
        return (result.amount / 1_000_000) * exchange_rates["CCD"]["rate"]
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested account {account_address} not found on {net}",
        )


@router.get("/{net}/account/{account_address}/balance", response_class=JSONResponse)
async def get_account_balance(
    request: Request,
    net: str,
    account_address: str,
    grpcclient: GRPCClient = Depends(get_grpcclient),
    api_key: str = Security(API_KEY_HEADER),
) -> int:
    """
    Endpoint to get all CCD balance in microCCD for a given account at the last final block.


    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

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
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> CCD_AccountInfo:
    """
    Endpoint to get all account info for a given account at the last final block.


    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

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
            if len(index_or_hash) == 29:
                try:
                    db_to_use = (
                        mongomotor.testnet if net == "testnet" else mongomotor.mainnet
                    )
                    result = await db_to_use[
                        Collections.all_account_addresses
                    ].find_one({"_id": index_or_hash})
                    if result:
                        index_or_hash = result["account_address"]
                except Exception:
                    index_or_hash = ""

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
    api_key: str = Security(API_KEY_HEADER),
) -> dt.datetime:
    """
    Endpoint to get earliest win time for an account that is an active validator.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

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


def expectation(value, blocks_validated):
    if round(value, 0) == 1:
        plural = ""
    else:
        plural = "s"
    if value < 5:
        expectation_string = f"{blocks_validated:,.0f} / {value:,.2f} block{plural}"
    else:
        expectation_string = f"{blocks_validated:,.0f} / {value:,.0f} block{plural}"
    return expectation_string


@router.get("/{net}/account/{index}/current-payday-stats", response_class=JSONResponse)
async def get_validator_current_payday_stats(
    request: Request,
    net: str,
    index: int,
    grpcclient: GRPCClient = Depends(get_grpcclient),
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> str:
    """
    Endpoint to get current payday stats for an account that is an active validator.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    pipeline = [{"$sort": {"date": -1}}, {"$limit": 1}]
    mongo_result = (
        await mongomotor.mainnet[Collections.paydays]
        .aggregate(pipeline)
        .to_list(length=1)
    )
    if mongo_result:
        mongo_result = MongoTypePayday(**mongo_result[0])
        paydays_last_blocks_validated = (
            mongo_result.height_for_last_block - mongo_result.height_for_first_block + 1
        )

        try:
            pool = grpcclient.get_pool_info_for_pool(index, "last_final", net=NET(net))
            stats = expectation(
                pool.current_payday_info.lottery_power * paydays_last_blocks_validated,
                pool.current_payday_info.blocks_baked,
            )
        except grpc._channel._InactiveRpcError:
            raise HTTPException(
                status_code=404,
                detail=f"Can't get earliest win time for account {index} on {net}",
            )

        if stats:
            return stats
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
    api_key: str = Security(API_KEY_HEADER),
) -> CCD_PoolInfo:
    """
    Endpoint to get the current pool info for an account that is an active validator.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

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
    "/{net}/account/{account_id}/staking-rewards-bucketed", response_class=JSONResponse
)
async def get_staking_rewards_bucketed(
    request: Request,
    net: str,
    account_id: int | str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> list:
    """
    Endpoint to get staking rewards info for a given account for graphing.


    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    db_to_use = mongomotor.mainnet
    pp = [
        {"$match": {"account_id": account_id}},
    ]
    try:
        result_pp = (
            await db_to_use[Collections.paydays_rewards]
            .aggregate(pp)
            .to_list(length=None)
        )
        return result_pp
    except Exception as error:
        raise HTTPException(
            status_code=404,
            detail=f"Can't retrieve staking rewards for account at {account_id} on {net} with error {error}.",
        )


@router.get("/{net}/account/{index}/validator-performance", response_class=JSONResponse)
async def get_validator_performance(
    request: Request,
    net: str,
    index: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> list:
    """
    Endpoint to get validator performance for a given validator.


    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    db_to_use = mongomotor.mainnet
    try:
        result = (
            await db_to_use[Collections.paydays_performance]
            .find({"baker_id": index})
            .sort("date", ASCENDING)
            .to_list(length=None)
        )
        return result
    except Exception as error:
        raise HTTPException(
            status_code=404,
            detail=f"Can't retrieve validator performance for validator {index} on {net} with error {error}.",
        )


@router.get(
    "/{net}/account/{account_id}/rewards-available", response_class=JSONResponse
)
async def get_bool_account_rewards_available(
    request: Request,
    net: str,
    account_id: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> bool:
    """
    Endpoint to get determine if payday rewards are available for an account.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    db_to_use = mongomotor.mainnet
    try:
        result = await db_to_use[Collections.paydays_rewards].find_one(
            {"account_id": account_id}
        )

        return result is not None

    except Exception as error:
        raise HTTPException(
            status_code=404,
            detail=f"Can't determine whether account {account_id} on {net}  has rewards with error {error}.",
        )


@router.get(
    "/{net}/account/{index}/validator-tally/{skip}/{limit}", response_class=JSONResponse
)
async def get_validator_tally(
    request: Request,
    net: str,
    index: int,
    skip: int,
    limit: int,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """
    Endpoint to get validator tally data.


    """

    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    if skip < 0:
        raise HTTPException(
            status_code=400,
            detail="Don't be silly. Skip must be greater than or equal to zero.",
        )

    if limit > 100:
        raise HTTPException(
            status_code=400,
            detail="Limit must be less than or equal to 100.",
        )

    # limit = limit if limit <= 50 else 50
    db_to_use = mongomotor.mainnet
    try:
        account_info = grpcclient.get_account_info(
            block_hash="last_final", account_index=index, net=NET(net)
        )

        if account_info.stake:
            if account_info.stake.baker:
                validator_id = account_info.stake.baker.baker_info.baker_id
            else:
                validator_id = None
        else:
            validator_id = None

        data = None
        if validator_id:
            pipeline = [
                {
                    "$match": {"baker_id": str(validator_id)},
                },
                {"$sort": {"date": DESCENDING}},
                {
                    "$facet": {
                        "metadata": [{"$count": "total"}],
                        "data": [{"$skip": skip}, {"$limit": limit}],
                    }
                },
                {
                    "$project": {
                        "data": 1,
                        "total": {"$arrayElemAt": ["$metadata.total", 0]},
                    }
                },
            ]
            result = (
                await db_to_use[Collections.paydays_performance]
                .aggregate(pipeline)
                .to_list(length=limit)
            )

            data = {
                v["date"]: {
                    "actuals": v["pool_status"]["current_payday_info"]["blocks_baked"],
                    "lp": v["pool_status"]["current_payday_info"]["lottery_power"],
                    "expectation": v["expectation"],
                }
                for v in result[0]["data"]
            }
            return {"data": data, "total_row_count": result[0]["total"]}
    except Exception as error:
        raise HTTPException(
            status_code=404,
            detail=f"Can't retrieve validator tally with error {error}.",
        )


@router.get(
    "/{net}/account/{index}/pool/delegators/{skip}/{limit}", response_class=JSONResponse
)
async def get_account_pool_delegators(
    request: Request,
    net: str,
    index: int,
    skip: int,
    limit: int,
    grpcclient: GRPCClient = Depends(get_grpcclient),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """
    Endpoint to get all delegators to pool.


    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    if skip < 0:
        raise HTTPException(
            status_code=400,
            detail="Don't be silly. Skip must be greater than or equal to zero.",
        )

    if limit > 100:
        raise HTTPException(
            status_code=400,
            detail="Limit must be less than or equal to 100.",
        )

    try:
        account_info = grpcclient.get_account_info(
            block_hash="last_final", account_index=index, net=NET(net)
        )
        validator = account_info.stake.baker
        if validator:
            try:
                delegators_current_payday = [
                    x
                    for x in grpcclient.get_delegators_for_pool_in_reward_period(
                        pool_id=validator.baker_info.baker_id,
                        block_hash="last_final",
                        net=NET(net),
                    )
                ]
            except:  # noqa: E722
                delegators_current_payday = []

            try:
                delegators_in_block = [
                    x
                    for x in grpcclient.get_delegators_for_pool(
                        pool_id=validator.baker_info.baker_id,
                        block_hash="last_final",
                        net=NET(net),
                    )
                ]
            except:  # noqa: E722
                delegators_in_block = []

            delegators_current_payday_list = set(
                [x.account for x in delegators_current_payday]
            )
            delegators_in_block_list = set([x.account for x in delegators_in_block])

            new_delegators = delegators_in_block_list - delegators_current_payday_list

            delegators = sorted(
                delegators_current_payday, key=lambda x: x.stake, reverse=True
            )
            return {
                "delegators": delegators[skip : (skip + limit)],
                "delegators_in_block": delegators_in_block,
                "delegators_current_payday": delegators_current_payday,
                "new_delegators": new_delegators,
                "total_delegators": len(delegators_current_payday),
            }
    except Exception as error:
        raise HTTPException(
            status_code=404,
            detail=f"Can't retrieve delegators with error {error}.",
        )


@router.get("/{net}/account/{index_or_hash}/apy-data", response_class=JSONResponse)
async def get_account_apy_data(
    request: Request,
    net: str,
    index_or_hash: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """
    Endpoint to get account APY data.


    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    db_to_use = mongomotor.mainnet
    try:
        result = await db_to_use[Collections.paydays_apy_intermediate].find_one(
            {"_id": {"$eq": str(index_or_hash)}}
        )
        return result
    except Exception as error:
        raise HTTPException(
            status_code=404,
            detail=f"Can't retrieve account APY data with error {error}.",
        )


@router.get("/{net}/account/{index}/node", response_class=JSONResponse)
async def get_account_validator_node(
    request: Request,
    net: str,
    index: int,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """
    Endpoint to get account validator node.


    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    db_to_use = mongomotor.mainnet

    result = await db_to_use[Collections.dashboard_nodes].find_one(
        {"consensusBakerId": str(index)}
    )

    if result:
        return result
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Can't find node for validator {index} on {net}.",
        )


@router.get(
    "/{net}/account/{index_or_hash}/staking-rewards-object", response_class=JSONResponse
)
async def get_staking_rewards_object(
    request: Request,
    net: str,
    index_or_hash: int | str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """
    Endpoint to get all account info for a given account at the last final block.


    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

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


@router.get(
    "/{net}/account/{account_id}/transactions/{skip}/{limit}",
    response_class=JSONResponse,
)
async def get_account_txs(
    request: Request,
    net: str,
    account_id: str,
    skip: int,
    limit: int,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """
    Endpoint to get all account transactions.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    if skip < 0:
        raise HTTPException(
            status_code=400,
            detail="Don't be silly. Skip must be greater than or equal to zero.",
        )

    if limit > 100:
        raise HTTPException(
            status_code=400,
            detail="Limit must be less than or equal to 100.",
        )

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet

    try:
        top_list_member = await db_to_use[
            Collections.impacted_addresses_all_top_list
        ].find_one({"_id": account_id[:29]})

        if not top_list_member:
            pipeline = [
                {
                    "$match": {"impacted_address_canonical": {"$eq": account_id[:29]}},
                },
                {  # this filters out account rewards, as they are special events
                    "$match": {"tx_hash": {"$exists": True}},
                },
                {"$sort": {"block_height": DESCENDING}},
                {"$project": {"_id": 0, "tx_hash": 1}},
                {
                    "$facet": {
                        "metadata": [{"$count": "total"}],
                        "data": [{"$skip": skip}, {"$limit": limit}],
                    }
                },
                {
                    "$project": {
                        "data": 1,
                        "total": {"$arrayElemAt": ["$metadata.total", 0]},
                    }
                },
            ]
            result = (
                await db_to_use[Collections.impacted_addresses]
                .aggregate(pipeline)
                .to_list(limit)
            )
            all_txs_hashes = [x["tx_hash"] for x in result[0]["data"]]
            if "total" in result[0]:
                total_tx_count = result[0]["total"]
            else:
                total_tx_count = 0

        else:
            #### This is a TOP_TX_COUNT account
            pipeline = [
                {
                    "$match": {"impacted_address_canonical": {"$eq": account_id[:29]}},
                },
                {  # this filters out account rewards, as they are special events
                    "$match": {"tx_hash": {"$exists": True}},
                },
                {"$sort": {"block_height": DESCENDING}},
                {"$skip": skip},
                {"$limit": limit},
                {"$project": {"tx_hash": 1}},
            ]
            result = (
                await db_to_use[Collections.impacted_addresses]
                .aggregate(pipeline)
                .to_list(limit)
            )
            all_txs_hashes = [x["tx_hash"] for x in result]
            total_tx_count = top_list_member["count"]

        int_result = (
            await db_to_use[Collections.transactions]
            .find({"_id": {"$in": all_txs_hashes}})
            .sort("block_info.height", DESCENDING)
            .to_list(limit)
        )
        tx_result = [CCD_BlockItemSummary(**x) for x in int_result]
        return {"transactions": tx_result, "total_tx_count": total_tx_count}
    except Exception as error:
        raise HTTPException(
            status_code=404,
            detail=f"Can't retrieve transactions for account at {account_id} on {net} with error {error}.",
        )


@router.get(
    "/{net}/account/{account_id}/validator-transactions/{skip}/{limit}",
    response_class=JSONResponse,
)
async def get_account_validator_txs(
    request: Request,
    net: str,
    account_id: str,
    skip: int,
    limit: int,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """
    Endpoint to get all account validator transactions.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    if skip < 0:
        raise HTTPException(
            status_code=400,
            detail="Don't be silly. Skip must be greater than or equal to zero.",
        )

    if limit > 100:
        raise HTTPException(
            status_code=400,
            detail="Limit must be less than or equal to 100.",
        )

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet

    try:
        pipeline = [
            {
                "$match": {"impacted_address_canonical": {"$eq": account_id[:29]}},
            },
            {  # this filters out account rewards, as they are special events
                "$match": {
                    "$or": [
                        {"effect_type": "baker_added"},
                        {"effect_type": "baker_removed"},
                        {"effect_type": "baker_stake_updated"},
                        {"effect_type": "baker_restake_earnings_updated"},
                        # {"effect_type": "baker_keys_updated"},
                        {"effect_type": "baker_configured"},
                    ]
                },
            },
            {"$sort": {"block_height": DESCENDING}},
            {"$project": {"_id": 0, "tx_hash": 1}},
            {
                "$facet": {
                    "metadata": [{"$count": "total"}],
                    "data": [{"$skip": skip}, {"$limit": limit}],
                }
            },
            {
                "$project": {
                    "data": 1,
                    "total": {"$arrayElemAt": ["$metadata.total", 0]},
                }
            },
        ]
        result = (
            await db_to_use[Collections.impacted_addresses]
            .aggregate(pipeline)
            .to_list(limit)
        )
        all_txs_hashes = [x["tx_hash"] for x in result[0]["data"]]
        if "total" in result[0]:
            total_tx_count = result[0]["total"]
        else:
            total_tx_count = 0

        int_result = (
            await db_to_use[Collections.transactions]
            .find({"_id": {"$in": all_txs_hashes}})
            .sort("block_info.height", DESCENDING)
            .to_list(limit)
        )
        tx_result = [CCD_BlockItemSummary(**x) for x in int_result]
        return {"transactions": tx_result, "total_tx_count": total_tx_count}
    except Exception as error:
        raise HTTPException(
            status_code=404,
            detail=f"Can't retrieve validator transactions for account at {account_id} on {net} with error {error}.",
        )


@router.get(
    "/{net}/account/{account_id}/transactions-for-flow/{gte}/{start_date}/{end_date}",
    response_class=JSONResponse,
)
async def get_account_transactions_for_flow_graph(
    request: Request,
    net: str,
    account_id: str,
    gte: str,
    start_date: str,
    end_date: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    blocks_per_day: dict[str, MongoTypeBlockPerDay] = Depends(get_blocks_per_day),
    api_key: str = Security(API_KEY_HEADER),
) -> list[MongoImpactedAddress]:
    """
    Endpoint to get all txs for a given account that should be included in the flow graph for CCD.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    amended_start_date = (
        f"{(dateutil.parser.parse(start_date)-dt.timedelta(days=1)):%Y-%m-%d}"
    )
    start_block = blocks_per_day.get(amended_start_date)
    if start_block:
        start_block = start_block.height_for_first_block
    else:
        start_block = 0

    end_block = blocks_per_day.get(end_date)
    if end_block:
        end_block = end_block.height_for_last_block
    else:
        end_block = 1_000_000_000

    try:
        gte = int(gte.replace(",", "").replace(".", ""))
    except:  # noqa: E722
        error = True

    db_to_use = mongomotor.mainnet
    try:
        pipeline = [
            {
                "$match": {"included_in_flow": True},
            },
            {"$match": {"block_height": {"$gt": start_block, "$lte": end_block}}},
            {
                "$match": {"impacted_address_canonical": {"$eq": account_id[:29]}},
            },
        ]
        txs_for_account = (
            await db_to_use[Collections.impacted_addresses]
            .aggregate(pipeline)
            .to_list(length=None)
        )
        return txs_for_account

    except Exception as error:
        raise HTTPException(
            status_code=404,
            detail=f"Can't determine whether account {account_id} on {net}  has rewards with error {error}.",
        )


@router.get(
    "/{net}/account/{account_id}/token-transactions-for-flow/{token_id}/{gte}/{start_date}/{end_date}",
    response_class=JSONResponse,
)
async def get_account_token_transactions_for_flow_graph(
    request: Request,
    net: str,
    account_id: str,
    token_id: str,
    gte: str,
    start_date: str,
    end_date: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    blocks_per_day: dict[str, MongoTypeBlockPerDay] = Depends(get_blocks_per_day),
    api_key: str = Security(API_KEY_HEADER),
) -> list[MongoTypeLoggedEvent]:
    """
    Endpoint to get all token txs for a given account that should be included in the flow graph for a token.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    amended_start_date = (
        f"{(dateutil.parser.parse(start_date)-dt.timedelta(days=1)):%Y-%m-%d}"
    )
    start_block = blocks_per_day.get(amended_start_date)
    if start_block:
        start_block = start_block.height_for_first_block
    else:
        start_block = 0

    end_block = blocks_per_day.get(end_date)
    if end_block:
        end_block = end_block.height_for_last_block
    else:
        end_block = 1_000_000_000

    try:
        gte = int(gte.replace(",", "").replace(".", ""))
    except:  # noqa: E722
        error = True

    db_to_use = mongomotor.mainnet
    try:
        pipeline = [
            {
                "$match": {
                    "$or": [
                        {"to_address_canonical": account_id[:29]},
                        {"from_address_canonical": account_id[:29]},
                    ]
                }
            },
            {"$match": {"block_height": {"$gt": start_block, "$lte": end_block}}},
            {"$match": {"token_address": token_id}},
        ]
        txs_for_account = [
            MongoTypeLoggedEvent(**x)
            for x in await db_to_use[Collections.tokens_logged_events]
            .aggregate(pipeline)
            .to_list(length=None)
        ]
        return txs_for_account

    except Exception as error:
        raise HTTPException(
            status_code=404,
            detail=f"Can't determine whether account {account_id} on {net}  has token txs with error {error}.",
        )


@router.get(
    "/{net}/account/{account_id}/rewards-for-flow/{start_date}/{end_date}",
    response_class=JSONResponse,
)
async def get_account_rewards_for_flow_graph(
    request: Request,
    net: str,
    account_id: str,
    start_date: str,
    end_date: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    blocks_per_day: dict[str, MongoTypeBlockPerDay] = Depends(get_blocks_per_day),
    api_key: str = Security(API_KEY_HEADER),
) -> int:
    """
    Endpoint to get all rewards for a given account that should be included in the flow graph for CCD.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    amended_start_date = (
        f"{(dateutil.parser.parse(start_date)-dt.timedelta(days=1)):%Y-%m-%d}"
    )
    start_block = blocks_per_day.get(amended_start_date)
    if start_block:
        start_block = start_block.height_for_first_block
    else:
        start_block = 0

    end_block = blocks_per_day.get(end_date)
    if end_block:
        end_block = end_block.height_for_last_block
    else:
        end_block = 1_000_000_000

    db_to_use = mongomotor.mainnet
    try:
        pipeline = [
            {
                "$match": {"impacted_address_canonical": {"$eq": account_id[:29]}},
            },
            {"$match": {"block_height": {"$gte": start_block, "$lte": end_block}}},
            {"$match": {"effect_type": "Account Reward"}},
            {
                "$group": {
                    "_id": "$impacted_address",
                    "sum_finalization_reward": {
                        "$sum": "$balance_movement.finalization_reward",
                    },
                    "sum_baker_reward": {
                        "$sum": "$balance_movement.baker_reward",
                    },
                    "sum_transaction_fee_reward": {
                        "$sum": "$balance_movement.transaction_fee_reward",
                    },
                },
            },
        ]
        rewards_for_account = (
            await db_to_use[Collections.impacted_addresses]
            .aggregate(pipeline)
            .to_list(length=None)
        )
        if len(rewards_for_account) > 0:
            rewards_for_account = rewards_for_account[0]
        else:
            rewards_for_account = {
                "sum_transaction_fee_reward": 0,
                "sum_baker_reward": 0,
                "sum_finalization_reward": 0,
            }

        account_rewards_pre_payday = await db_to_use[
            Collections.impacted_addresses_pre_payday
        ].find_one({"impacted_address_canonical": {"$eq": account_id[:29]}})
        if account_rewards_pre_payday:
            account_rewards_total = account_rewards_pre_payday[
                "sum_transaction_fee_reward"
            ]
            +account_rewards_pre_payday["sum_baker_reward"]
            +account_rewards_pre_payday["sum_finalization_reward"]
            rewards_for_account["sum_transaction_fee_reward"]
            +rewards_for_account["sum_baker_reward"]
            +rewards_for_account["sum_finalization_reward"]

        else:
            if len(rewards_for_account) > 0:
                account_rewards_total = (
                    rewards_for_account["sum_transaction_fee_reward"]
                    + rewards_for_account["sum_baker_reward"]
                    + rewards_for_account["sum_finalization_reward"]
                )
            else:
                account_rewards_total = 0

        return account_rewards_total

    except Exception as error:
        raise HTTPException(
            status_code=404,
            detail=f"Can't determine whether account {account_id} on {net}  has rewards with error {error}.",
        )


@router.get(
    "/{net}/account/{account_id}/deployed",
    response_class=JSONResponse,
)
async def get_account_deployment_tx(
    request: Request,
    net: str,
    account_id: str,
    mongodb: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> CCD_BlockItemSummary | None:
    """
    Endpoint to get tx in which the account was deployed.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    pipeline = [
        {"$match": {"account_creation": {"$exists": True}}},
        {"$match": {"account_creation.address": account_id}},
    ]
    result = (
        await db_to_use[Collections.transactions].aggregate(pipeline).to_list(length=1)
    )

    if len(result) > 0:
        result = CCD_BlockItemSummary(**result[0])
        return result
    else:
        # account existed in genesis block
        return None


@router.get(
    "/{net}/account/{account_address}/aliases-in-use",
    response_class=JSONResponse,
)
async def get_aliases_in_use_for_account(
    request: Request,
    net: str,
    account_address: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> list[dict]:
    """
    Endpoint to get all aliases that are in use for a specific account address.


    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    pipeline = [
        {
            "$match": {"effect_type": {"$ne": "data_registered"}},
        },
        {
            "$match": {"impacted_address_canonical": {"$eq": account_address[:29]}},
        },
        {
            "$group": {
                "_id": "$impacted_address",
            }
        },
        {
            "$project": {
                "_id": 1,
            }
        },
    ]
    result = (
        await db_to_use[Collections.impacted_addresses]
        .aggregate(pipeline)
        .to_list(length=None)
    )

    aliases = [x for x in result if x["_id"] != account_address]
    return aliases
