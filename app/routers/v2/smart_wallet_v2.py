import math

from ccdexplorer_fundamentals.cis import CIS
from ccdexplorer_fundamentals.enums import NET
from ccdexplorer_fundamentals.GRPCClient import GRPCClient
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import (
    CCD_BlockItemSummary,
    CCD_ContractAddress,
)
from ccdexplorer_fundamentals.mongodb import (
    Collections,
    MongoDB,
    MongoMotor,
    MongoTypeInstance,
)

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Security
from fastapi.responses import JSONResponse
from pymongo import ASCENDING, DESCENDING
from pydantic import BaseModel, Field
from app.ENV import API_KEY_HEADER
from app.state_getters import (
    get_exchange_rates,
    get_grpcclient,
    get_mongo_db,
    get_mongo_motor,
)

# from app.utils import TokenHolding

from .contract_v2 import (
    GetBalanceOfRequest,
    GetCIS5BalanceOfRequest,
    get_cis5_balance_of,
    get_balance_of,
    get_module_name_from_contract_address,
)


class CIS5PublicKeysContracts(BaseModel):
    id: str = Field(..., alias="_id")
    wallet_contract_address: str
    cis2_token_contract_address: str
    token_id: Optional[str] = None
    token_address: Optional[str] = None
    address_or_public_key: str
    address_canonical_or_public_key: str
    token_amount: Optional[str] = None
    decimals: Optional[int] = None
    token_symbol: Optional[str] = None
    token_value: Optional[float] = None
    token_value_USD: Optional[float] = None
    verified_information: Optional[dict] = None
    address_information: Optional[dict] = None


router = APIRouter(tags=["Smart Wallet"], prefix="/v2")


@router.get(
    "/{net}/smart-wallet/{wallet_contract_address_index}/{wallet_contract_address_subindex}/public-keys",
    response_class=JSONResponse,
)
async def get_smart_wallet_details_from_public_key(
    request: Request,
    net: str,
    wallet_contract_address_index: int,
    wallet_contract_address_subindex: int,
    mongodb: MongoDB = Depends(get_mongo_db),
    api_key: str = Security(API_KEY_HEADER),
) -> list[str]:
    """ """
    wallet_contract_address = CCD_ContractAddress.from_index(
        wallet_contract_address_index, wallet_contract_address_subindex
    ).to_str()
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    pipeline = [
        {"$match": {"wallet_contract_address": wallet_contract_address}},
        {"$group": {"_id": "$address_or_public_key"}},
    ]
    result = list(
        set(
            [
                x["_id"]
                for x in db_to_use[Collections.cis5_public_keys_contracts].aggregate(
                    pipeline
                )
            ]
        )
    )
    return result


@router.get(
    "/{net}/smart-wallet/public-key/{public_key}",
    response_class=JSONResponse,
)
async def get_all_public_keys_for_smart_wallet_contract(
    request: Request,
    net: str,
    public_key: str,
    mongodb: MongoDB = Depends(get_mongo_db),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """ """
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    result = db_to_use[Collections.cis5_public_keys_contracts].find_one(
        {"address_or_public_key": public_key}
    )
    if result:
        return {
            "wallet_contract_address": result["wallet_contract_address"],
            "public_key": public_key,
        }
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested public key {public_key} on {net} not found.",
        )


@router.get(
    "/{net}/smart-wallet/{wallet_contract_address_index}/{wallet_contract_address_subindex}/public-key/{public_key}/deployed",
    response_class=JSONResponse,
)
async def get_deployed_tx_for_public_key_from_smart_wallet_contract(
    request: Request,
    net: str,
    wallet_contract_address_index: int,
    wallet_contract_address_subindex: int,
    public_key: str,
    mongodb: MongoDB = Depends(get_mongo_db),
    api_key: str = Security(API_KEY_HEADER),
) -> CCD_BlockItemSummary:
    """ """
    wallet_contract_address = CCD_ContractAddress.from_index(
        wallet_contract_address_index, wallet_contract_address_subindex
    ).to_str()
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet

    pipeline = [
        {
            "$match": {
                "$or": [
                    {"to_address_canonical": public_key},
                    {"from_address_canonical": public_key},
                ]
            },
        },
        {"$match": {"event_info.contract": wallet_contract_address}},
        {"$sort": {"tx_info.block_height": ASCENDING}},
        {"$limit": 1},
    ]
    result = list(db_to_use[Collections.tokens_logged_events_v2].aggregate(pipeline))
    if len(result) > 0:
        deployment_logged_event = result[0]
        deployment_tx_hash = deployment_logged_event["tx_info"]["tx_hash"]
        result = db_to_use[Collections.transactions].find_one(deployment_tx_hash)
        if result:
            result = CCD_BlockItemSummary(**result)
            return result
        else:
            raise HTTPException(
                status_code=404,
                detail=f"For requested public key {public_key} for smart wallet {wallet_contract_address_index} on {net}, can't find the deployment tx {deployment_tx_hash}.",
            )

    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested public key {public_key} for smart wallet {wallet_contract_address_index} on {net} not found.",
        )


@router.get(
    "/{net}/smart-wallet/{wallet_contract_address_index}/{wallet_contract_address_subindex}/public-key/{public_key}/{skip}/{limit}/verified",
    response_class=JSONResponse,
)
async def get_public_key_fungible_tokens_verified(
    request: Request,
    net: str,
    wallet_contract_address_index: int,
    wallet_contract_address_subindex: int,
    public_key: str,
    skip: int,
    limit: int,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    exchange_rates: dict = Depends(get_exchange_rates),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """
    Endpoint to get verified fungible tokens for a given public key, as stored in MongoDB collection `cis5_public_keys_contracts`.
    """

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    fungible_token_result = (
        await db_to_use[Collections.tokens_tags]
        .find({"token_type": "fungible"}, {"contracts": 1})
        .to_list(length=None)
    )

    fungible_token_addresses = [
        x["contracts"][0]
        for x in fungible_token_result
        # if "related_token_address" in x
    ]

    pipeline = [
        {"$match": {"address_canonical_or_public_key": public_key}},
        {"$match": {"cis2_token_contract_address": {"$in": fungible_token_addresses}}},
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
        await db_to_use[Collections.cis5_public_keys_contracts]
        .aggregate(pipeline)
        .to_list(length=None)
    )
    all_tokens = [x for x in result[0]["data"]]
    if "total" in result[0]:
        total_token_count = result[0]["total"]
    else:
        total_token_count = 0
    tokens = [CIS5PublicKeysContracts(**x) for x in all_tokens]

    # add verified information and metadata and USD value
    for index, token in enumerate(tokens):
        token.token_id = "" if token.token_id is None else token.token_id
        token.token_address = f"{token.cis2_token_contract_address}-{token.token_id}"
        result = await db_to_use[Collections.tokens_tags].find_one(
            {"related_token_address": token.token_address}
        )
        token.verified_information = result

        module_name = await get_module_name_from_contract_address(
            db_to_use,
            CCD_ContractAddress.from_str(token.wallet_contract_address),
        )

        request = GetCIS5BalanceOfRequest(
            net=net,
            wallet_contract_address=CCD_ContractAddress.from_str(
                token.wallet_contract_address
            ),
            cis2_contract_address=CCD_ContractAddress.from_str(
                token.cis2_token_contract_address
            ),
            token_id=(
                ""
                if result["related_token_address"].replace(
                    token.cis2_token_contract_address, ""
                )
                == "-"
                else result["related_token_address"].replace(
                    f"{token.cis2_token_contract_address}-", ""
                )
            ),
            module_name=module_name,
            public_keys=[public_key],
            grpcclient=grpcclient,
        )
        token_amount_from_state = await get_cis5_balance_of(request)
        token.token_amount = token_amount_from_state.get(public_key, 0)

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
            detail=f"Requested public key ({public_key}) has no fungible verified tokens on {net}",
        )


@router.get(
    "/{net}/smart-wallet/{wallet_contract_address_index}/{wallet_contract_address_subindex}/public-key/{public_key}/transaction-count",
    response_class=JSONResponse,
)
async def get_tx_count_for_public_key_from_smart_wallet_contract(
    request: Request,
    net: str,
    wallet_contract_address_index: int,
    wallet_contract_address_subindex: int,
    public_key: str,
    mongodb: MongoDB = Depends(get_mongo_db),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """ """
    wallet_contract_address = CCD_ContractAddress.from_index(
        wallet_contract_address_index, wallet_contract_address_subindex
    ).to_str()
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet

    pipeline = [
        {
            "$match": {
                "$or": [
                    {"to_address_canonical": public_key},
                    {"from_address_canonical": public_key},
                ]
            },
        },
        {"$match": {"event_info.contract": wallet_contract_address}},
        {"$group": {"_id": "$tx_info.tx_hash"}},
        {"$count": "tx_count"},
    ]
    result = list(db_to_use[Collections.tokens_logged_events_v2].aggregate(pipeline))
    tx_count = result[0]["tx_count"] if len(result) > 0 else 0
    if tx_count > 0:
        return {
            "public_key": public_key,
            "contract": wallet_contract_address,
            "tx_count": tx_count,
        }
    else:
        raise HTTPException(
            status_code=404,
            detail=f"No transactions found for requested public key {public_key} for smart wallet {wallet_contract_address_index} on {net}.",
        )


@router.get(
    "/{net}/smart-wallet/{wallet_contract_address_index}/{wallet_contract_address_subindex}/public-key/{public_key}/logged-events/{skip}/{limit}",
    response_class=JSONResponse,
)
async def get_logged_events_for_public_key_from_smart_wallet_contract(
    request: Request,
    net: str,
    wallet_contract_address_index: int,
    wallet_contract_address_subindex: int,
    public_key: str,
    skip: int,
    limit: int,
    mongodb: MongoDB = Depends(get_mongo_db),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """ """
    wallet_contract_address = CCD_ContractAddress.from_index(
        wallet_contract_address_index, wallet_contract_address_subindex
    ).to_str()
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet

    pipeline = [
        {
            "$match": {
                "$or": [
                    {"to_address_canonical": public_key},
                    {"from_address_canonical": public_key},
                ]
            },
        },
        {"$match": {"event_info.contract": wallet_contract_address}},
        {"$sort": {"tx_info.block_height": DESCENDING}},
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
    result = list(db_to_use[Collections.tokens_logged_events_v2].aggregate(pipeline))
    logged_events_selected = result[0]["data"]
    if "total" in result[0]:
        all_logged_events_count = result[0]["total"]
    else:
        all_logged_events_count = 0

    return {
        "logged_events_selected": logged_events_selected,
        "all_logged_events_count": all_logged_events_count,
    }


@router.get(
    "/{net}/smart-wallet/{wallet_contract_address_index}/{wallet_contract_address_subindex}/public-key/{public_key}/balances",
    response_class=JSONResponse,
)
async def get_token_balances_for_public_key_from_smart_wallet_contract(
    request: Request,
    net: str,
    wallet_contract_address_index: int,
    wallet_contract_address_subindex: int,
    public_key: str,
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    exchange_rates: dict = Depends(get_exchange_rates),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """ """
    wallet_contract_address = CCD_ContractAddress.from_index(
        wallet_contract_address_index, wallet_contract_address_subindex
    ).to_str()
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet

    pipeline = [
        {"$match": {"wallet_contract_address": wallet_contract_address}},
        {"$match": {"address_or_public_key": public_key}},
        {"$group": {"_id": "$cis2_token_contract_address"}},
    ]
    cis2_contracts = [
        x["_id"]
        for x in db_to_use[Collections.cis5_public_keys_contracts].aggregate(pipeline)
    ]

    block_hash = "last_final"
    instance_index = wallet_contract_address_index
    instance_subindex = wallet_contract_address_subindex

    result = db_to_use[Collections.instances].find_one({"_id": wallet_contract_address})
    instance = MongoTypeInstance(**result)

    if instance and instance.v1:
        entrypoint = instance.v1.name[5:] + ".cis2BalanceOf"
        entrypoint_ccd = instance.v1.name[5:] + ".ccdBalanceOf"
    else:
        return []
    ci = CIS(grpcclient, instance_index, instance_subindex, entrypoint, NET(net))

    token_balances: dict[dict] = {}
    public_keys = [public_key]
    for cis_2_contract in cis2_contracts:
        if not isinstance(cis_2_contract, str):
            continue
        cis_2_contract_address = CCD_ContractAddress.from_str(cis_2_contract)
        token_id = ""

        rr, ii = ci.CIS2balanceOf(
            block_hash, cis_2_contract_address, token_id, public_keys
        )

        if ii.failure.used_energy > 0:
            print(ii.failure)
        else:
            token_balances[cis_2_contract] = {
                "contract": cis_2_contract,
                "public_key": public_key,
                "balance": rr[0],
            }

            token_amount = rr[0]
            # now try to get additional information from tokens_tags
            token_address = f"{cis_2_contract}-{token_id}"
            result = db_to_use[Collections.tokens_tags].find_one(
                {"related_token_address": token_address}
            )
            token_balances[cis_2_contract].update({"verified_information": result})

            result = db_to_use[Collections.tokens_token_addresses_v2].find_one(
                {"_id": token_address}
            )
            token_balances[cis_2_contract].update({"address_information": result})
            token_vi = token_balances[cis_2_contract]["verified_information"]

            token_balances[cis_2_contract].update(
                {"token_symbol": token_vi["get_price_from"]}
            )
            token_balances[cis_2_contract].update({"decimals": token_vi["decimals"]})
            token_balances[cis_2_contract].update(
                {
                    "token_value": int(token_amount)
                    * (math.pow(10, -token_balances[cis_2_contract]["decimals"]))
                }
            )
            if token_balances[cis_2_contract]["token_symbol"] in exchange_rates:
                token_balances[cis_2_contract].update(
                    {
                        "token_value_USD": (
                            token_balances[cis_2_contract]["token_value"]
                            * exchange_rates[
                                token_balances[cis_2_contract]["token_symbol"]
                            ]["rate"]
                        )
                    }
                )

            else:
                token_balances[cis_2_contract].update({"token_value_USD": 0})

    ## same for CCD
    ci = CIS(grpcclient, instance_index, instance_subindex, entrypoint_ccd, NET(net))
    rr, ii = ci.CCDbalanceOf(block_hash, public_keys)

    if ii.failure.used_energy > 0:
        print(ii.failure)
    else:
        token_balances["ccd"] = {
            "contract": "ccd",
            "public_key": public_key,
            "balance": rr[0],
        }
        token_balances["ccd"].update(
            {"ccd_balance_in_USD": (rr[0] / 1_000_000) * exchange_rates["CCD"]["rate"]}
        )

    return token_balances


@router.get(
    "/{net}/smart-wallet/{wallet_contract_address_index}/{wallet_contract_address_subindex}/public-key/{public_key}/cis2-contracts",
    response_class=JSONResponse,
)
async def get_all_cis2_contracts_for_public_key_from_smart_wallet_contract(
    request: Request,
    net: str,
    wallet_contract_address_index: int,
    wallet_contract_address_subindex: int,
    public_key: str,
    mongodb: MongoDB = Depends(get_mongo_db),
    api_key: str = Security(API_KEY_HEADER),
) -> list[str]:
    """ """
    wallet_contract_address = CCD_ContractAddress.from_index(
        wallet_contract_address_index, wallet_contract_address_subindex
    ).to_str()
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    pipeline = [
        {"$match": {"wallet_contract_address": wallet_contract_address}},
        {"$match": {"address_or_public_key": public_key}},
        {"$group": {"_id": "$cis2_token_contract_address"}},
    ]
    result = list(
        set(
            [
                x["_id"]
                for x in db_to_use[Collections.cis5_public_keys_contracts].aggregate(
                    pipeline
                )
            ]
        )
    )
    return result
