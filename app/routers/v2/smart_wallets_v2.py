from ccdexplorer_fundamentals.mongodb import (
    Collections,
    MongoDB,
)
from fastapi import APIRouter, Depends, Request, Security, HTTPException
from fastapi.responses import JSONResponse
from pymongo.collection import Collection
from app.ENV import API_KEY_HEADER
from app.state_getters import get_mongo_db

router = APIRouter(tags=["Smart Wallets"], prefix="/v2")


@router.get("/{net}/smart-wallets/overview/all", response_class=JSONResponse)
async def get_all_smart_wallet_contracts_info(
    request: Request,
    net: str,
    mongodb: MongoDB = Depends(get_mongo_db),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """
    Fetches all unique smart wallet contract addresses from the specified MongoDB collection.

    Args:
        request (Request): The request object.
        net (str): The network type, either "testnet" or "mainnet".
        mongodb (MongoDB, optional): The MongoDB dependency, defaults to the result of get_mongo_db.
        api_key (str, optional): The API key for security, defaults to the result of API_KEY_HEADER.

    Returns:
        list[str]: A list of unique smart wallet contract addresses.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    distinct_wallet_addresses = list(
        db_to_use[Collections.cis5_public_keys_contracts].distinct(
            "wallet_contract_address"
        )
    )
    distinct_wallet_addresses_result = list(
        db_to_use[Collections.instances].find(
            {"_id": {"$in": distinct_wallet_addresses}}
        )
    )
    wallets_dict = {}

    for x in distinct_wallet_addresses_result:
        wallets_dict[x["_id"]] = {
            "name": x["v1"]["name"][5:].replace("_", " ").capitalize(),
            "source_module": x["source_module"],
        }
        pipeline = [
            {"$match": {"wallet_contract_address": x["_id"]}},
            {"$count": "count"},
        ]
        # pipeline = [
        #     {"$match": {"wallet_contract_address": x["_id"]}},
        #     {
        #         "$match": {
        #             "$expr": {"$eq": [{"$strLenCP": "$address_or_public_key"}, 64]}
        #         }
        #     },
        #     {"$group": {"_id": "$address_or_public_key"}},
        #     {"$count": "distinct_count"},
        # ]

        count = list(db_to_use[Collections.cis5_public_keys_info].aggregate(pipeline))
        wallets_dict[x["_id"]].update({"count_of_unique_addresses": count[0]["count"]})
        pipeline = [
            {"$match": {"event_info.standard": "CIS-5"}},
            {"$match": {"event_info.contract": x["_id"]}},
            {"$sort": {"tx_info.block_height": -1}},
            {"$limit": 100},
        ]

        result = list(
            db_to_use[Collections.tokens_logged_events_v2].aggregate(pipeline)
        )
        active_addresses = {}
        for log in result:
            if "to_address_canonical" in log:
                if len(log["to_address_canonical"]) == 64:
                    if (log["to_address_canonical"] not in active_addresses) and (
                        log["from_address_canonical"] not in active_addresses
                    ):
                        active_addresses[log["to_address_canonical"]] = {
                            "public_key": log["to_address_canonical"],
                            "last_active_date": log["tx_info"]["date"],
                            "last_active_block": log["tx_info"]["block_height"],
                        }

            if "from_address_canonical" in log:
                if (log["to_address_canonical"] not in active_addresses) and (
                    log["from_address_canonical"] not in active_addresses
                ):
                    if len(log["from_address_canonical"]) == 64:
                        active_addresses[log["from_address_canonical"]] = {
                            "public_key": log["from_address_canonical"],
                            "last_active_date": log["tx_info"]["date"],
                            "last_active_block": log["tx_info"]["block_height"],
                        }
        # Sort and limit active_addresses
        sorted_addresses = dict(
            sorted(
                active_addresses.items(),
                key=lambda x: x[1]["last_active_block"],
                reverse=True,
            )[:10]
        )
        wallets_dict[x["_id"]].update({"active_addresses": sorted_addresses})
    return wallets_dict


@router.get("/{net}/smart-wallets/overview", response_class=JSONResponse)
async def get_all_smart_wallet_contracts(
    request: Request,
    net: str,
    mongodb: MongoDB = Depends(get_mongo_db),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """
    Fetches all unique smart wallet contract addresses from the specified MongoDB collection.

    Args:
        request (Request): The request object.
        net (str): The network type, either "testnet" or "mainnet".
        mongodb (MongoDB, optional): The MongoDB dependency, defaults to the result of get_mongo_db.
        api_key (str, optional): The API key for security, defaults to the result of API_KEY_HEADER.

    Returns:
        list[str]: A list of unique smart wallet contract addresses.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    distinct_wallet_addresses = list(
        db_to_use[Collections.cis5_public_keys_contracts].distinct(
            "wallet_contract_address"
        )
    )
    distinct_wallet_addresses_result = list(
        db_to_use[Collections.instances].find(
            {"_id": {"$in": distinct_wallet_addresses}}
        )
    )
    wallets_dict = {}

    for x in distinct_wallet_addresses_result:
        wallets_dict[x["_id"]] = {
            "name": x["v1"]["name"][5:].replace("_", " ").capitalize(),
            "source_module": x["source_module"],
        }

    return wallets_dict


def get_block_ranges_from_start_and_end_dates(
    start_date: str, end_date: str, db_to_use: dict[Collections, Collection]
) -> str:

    start_date_result = db_to_use[Collections.blocks_per_day].find_one(
        {"date": start_date}
    )
    if start_date_result:
        height_for_first_block_start_date = start_date_result["height_for_first_block"]
    else:
        height_for_first_block_start_date = 0

    end_date_result = db_to_use[Collections.blocks_per_day].find_one({"date": end_date})
    if end_date_result:
        height_for_last_block_end_date = end_date_result["height_for_last_block"]
    else:
        height_for_last_block_end_date = 1_000_000_000

    return height_for_first_block_start_date, height_for_last_block_end_date


@router.get(
    "/{net}/smart-wallets/public-key-creation/{start_date}/{end_date}",
    response_class=JSONResponse,
)
async def get_smart_wallet_public_key_creations_per_day(
    request: Request,
    net: str,
    start_date: str,
    end_date: str,
    mongodb: MongoDB = Depends(get_mongo_db),
    api_key: str = Security(API_KEY_HEADER),
) -> list:
    """ """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    height_for_first_block_start_date, height_for_last_block_end_date = (
        get_block_ranges_from_start_and_end_dates(start_date, end_date, db_to_use)
    )
    pipeline = [
        {
            "$match": {
                "deployment_block_height": {
                    "$gte": height_for_first_block_start_date,
                    "$lte": height_for_last_block_end_date,
                }
            }
        },
        {"$group": {"_id": "$date", "count": {"$count": {}}}},
    ]
    result = db_to_use[Collections.cis5_public_keys_info].aggregate(pipeline)

    return result
