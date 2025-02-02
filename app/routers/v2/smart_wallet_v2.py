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
)

# from app.utils import TokenHolding


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
async def get_all_public_keys_for_smart_wallet_contract(
    request: Request,
    net: str,
    wallet_contract_address_index: int,
    wallet_contract_address_subindex: int,
    mongodb: MongoDB = Depends(get_mongo_db),
    api_key: str = Security(API_KEY_HEADER),
) -> list[str]:
    """ """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

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
async def get_smart_wallet_details_from_public_key(
    request: Request,
    net: str,
    public_key: str,
    mongodb: MongoDB = Depends(get_mongo_db),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """ """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

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
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

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
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    wallet_contract_address = CCD_ContractAddress.from_index(
        wallet_contract_address_index, wallet_contract_address_subindex
    ).to_str()
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet

    pipeline = [
        {"$match": {"wallet_contract_address": wallet_contract_address}},
        {"$match": {"address_or_public_key": public_key}},
    ]

    links_for_key = [
        x for x in db_to_use[Collections.cis5_public_keys_contracts].aggregate(pipeline)
    ]
    cis2_contracts_dict = {
        f'{x["cis2_token_contract_address"]}-{x["token_id_or_ccd"]}': {
            "token_id": x["token_id_or_ccd"],
            "contract": x["cis2_token_contract_address"],
        }
        for x in links_for_key
        if x["token_id_or_ccd"] != "ccd"
    }

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

    token_balance_ccd: dict[dict] = {}
    token_balances_fungible: dict[dict] = {}
    token_balances_non_fungible: dict[dict] = {}
    token_balances_unverified: dict[dict] = {}

    public_keys = [public_key]
    for cis_2_contract_address_str, cis2_dict in cis2_contracts_dict.items():

        cis_2_contract_address = CCD_ContractAddress.from_str(cis2_dict["contract"])
        token_id = cis2_dict["token_id"]
        rr, ii = ci.CIS2balanceOf(
            block_hash, cis_2_contract_address, token_id, public_keys
        )

        if ii.failure.used_energy > 0:
            print(ii.failure)
        else:

            token_amount = rr[0]
            fungible = False
            unverified = True
            fungible_result = None
            non_fungible_result = None
            # now try to get additional information from tokens_tags
            token_address = cis_2_contract_address_str
            if token_id == "":
                # search for fungible token
                fungible_result = db_to_use[Collections.tokens_tags].find_one(
                    {"related_token_address": token_address}
                )
            else:
                non_fungible_result = db_to_use[Collections.tokens_tags].find_one(
                    {"contracts": {"$in": [cis2_dict["contract"]]}}
                )

            fungible = fungible_result is not None
            unverified = (fungible_result is None) and (non_fungible_result is None)

            this_token = {
                "token_address": cis_2_contract_address_str,
                "contract": cis2_dict["contract"],
                "public_key": public_key,
                "balance": rr[0],
            }
            if fungible:
                this_token.update({"verified_information": fungible_result})
            else:
                this_token.update({"verified_information": non_fungible_result})

            result = db_to_use[Collections.tokens_token_addresses_v2].find_one(
                {"_id": token_address}
            )
            this_token.update({"address_information": result})

            token_vi = this_token["verified_information"]
            if not token_vi:
                continue

            if fungible:
                if "get_price_from" not in token_vi:
                    continue
                this_token = update_fungible_token_with_price_info(
                    exchange_rates, this_token, token_amount, token_vi
                )
                token_balances_fungible[cis_2_contract_address_str] = this_token
            else:
                token_balances_non_fungible[cis_2_contract_address_str] = this_token

            if unverified:
                token_balances_unverified[cis_2_contract_address_str] = this_token

    ## same for CCD
    ci = CIS(grpcclient, instance_index, instance_subindex, entrypoint_ccd, NET(net))
    rr, ii = ci.CCDbalanceOf(block_hash, public_keys)

    if ii.failure.used_energy > 0:
        print(ii.failure)
    else:
        token_balance_ccd["ccd"] = {
            "contract": "ccd",
            "public_key": public_key,
            "balance": rr[0],
        }
        token_balance_ccd["ccd"].update(
            {"ccd_balance_in_USD": (rr[0] / 1_000_000) * exchange_rates["CCD"]["rate"]}
        )

    return {
        "ccd": token_balance_ccd,
        "fungible": token_balances_fungible,
        "non_fungible": token_balances_non_fungible,
        "unverified": token_balances_unverified,
    }


def update_fungible_token_with_price_info(
    exchange_rates,
    this_token_: dict,
    token_amount,
    token_vi,
):

    this_token_.update({"token_symbol": token_vi["get_price_from"]})
    this_token_.update({"decimals": token_vi["decimals"]})
    this_token_.update(
        {"token_value": int(token_amount) * (math.pow(10, -token_vi["decimals"]))}
    )
    if this_token_["token_symbol"] in exchange_rates:
        this_token_.update(
            {
                "token_value_USD": (
                    this_token_["token_value"]
                    * exchange_rates[this_token_["token_symbol"]]["rate"]
                )
            }
        )
    else:
        this_token_.update({"token_value_USD": 0})

    return this_token_


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
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

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
