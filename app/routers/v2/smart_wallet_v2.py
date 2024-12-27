from ccdexplorer_fundamentals.mongodb import Collections, MongoDB, MongoTypeInstance
from ccdexplorer_fundamentals.cis import CIS
from ccdexplorer_fundamentals.GRPCClient import GRPCClient
from fastapi import APIRouter, Depends, Request, Security
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import CCD_ContractAddress
from ccdexplorer_fundamentals.enums import NET
from fastapi.responses import JSONResponse
from pymongo import DESCENDING
from app.ENV import API_KEY_HEADER
from app.state_getters import get_mongo_db, get_grpcclient

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

    token_balances = {}
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
