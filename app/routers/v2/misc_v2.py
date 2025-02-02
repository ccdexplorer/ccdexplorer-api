from datetime import timedelta

import dateutil
from ccdexplorer_fundamentals.enums import NET
from ccdexplorer_fundamentals.GRPCClient import GRPCClient
from ccdexplorer_fundamentals.mongodb import (
    Collections,
    CollectionsUtilities,
    MongoMotor,
)
from fastapi import APIRouter, Depends, HTTPException, Request, Security
from app.ENV import API_KEY_HEADER
from fastapi.responses import JSONResponse
from app.state_getters import get_grpcclient, get_mongo_motor

router = APIRouter(tags=["Misc"], prefix="/v2")


@router.get(
    "/{net}/misc/tx-data/{project_id}/{start_date}/{end_date}",
    response_class=JSONResponse,
)
async def get_tx_data_for_project(
    request: Request,
    net: str,
    project_id: str,
    start_date: str,
    end_date: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> JSONResponse:
    """
    Endpoint to get transactions counts for projects (and the chain).
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    dates_to_include = generate_dates_from_start_until_end(start_date, end_date)
    pipeline = [
        {"$match": {"date": {"$in": dates_to_include}}},
        {"$match": {"type": "statistics_transaction_types"}},
        {"$match": {"project": project_id}},
        {"$project": {"_id": 0, "type": 0, "usecase": 0}},
        {"$sort": {"date": 1}},
    ]
    result = (
        await mongomotor.mainnet[Collections.statistics]
        .aggregate(pipeline)
        .to_list(length=None)
    )
    return JSONResponse([x for x in result])


@router.get(
    "/{net}/misc/today-in/{date}",
    response_class=JSONResponse,
)
async def get_today_in_data(
    request: Request,
    net: str,
    date: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> JSONResponse:
    """
    Endpoint to get all interesting facts for this day.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet

    return_result = {"date": date}

    # day data
    result = await db_to_use[Collections.blocks_per_day].find_one({"date": date})
    if result:
        return_result["day_data"] = result

        pipeline = [
            {"$match": {"account_transaction": {"$exists": True}}},
            {
                "$match": {
                    "block_info.height": {
                        "$gte": result["height_for_first_block"],
                        "$lte": result["height_for_last_block"],
                    }
                }
            },
            {
                "$group": {
                    "_id": None,
                    "tx_count": {"$count": {}},
                    "fee_for_day": {"$sum": "$account_transaction.cost"},
                }
            },
        ]
        result = (
            await db_to_use[Collections.transactions]
            .aggregate(pipeline)
            .to_list(length=None)
        )
        return_result["tx_count"] = result[0]["tx_count"]
        return_result["fee_for_day"] = result[0]["fee_for_day"]

    # logged events by contract
    pipeline = [
        {"$match": {"tx_info.date": date}},
        {"$group": {"_id": "$event_info.contract", "count": {"$count": {}}}},
        {"$sort": {"count": -1}},
    ]
    result = (
        await db_to_use[Collections.tokens_logged_events_v2]
        .aggregate(pipeline)
        .to_list(length=None)
    )
    return_result["logged_events_by_contract"] = result

    # tx types
    pipeline = [
        {"$match": {"date": date}},
        {"$match": {"type": "statistics_transaction_types"}},
        {"$match": {"project": "all"}},
        {"$project": {"_id": 0, "type": 0, "usecase": 0}},
        {"$sort": {"date": 1}},
    ]
    result = (
        await mongomotor.mainnet[Collections.statistics]
        .aggregate(pipeline)
        .to_list(length=None)
    )
    if len(result) > 0:
        if "tx_type_counts" in result[0]:
            result = result[0]["tx_type_counts"]
        else:
            result = {}
    else:
        result = {}
    return_result["tx_types"] = result

    # impacted addresses
    pipeline = [
        {"$match": {"date": date}},
        {  # this filters out account rewards, as they are special events
            "$match": {"tx_hash": {"$exists": True}},
        },
        {"$group": {"_id": "$impacted_address_canonical", "count": {"$count": {}}}},
        {"$sort": {"count": -1}},
    ]
    result = (
        await db_to_use[Collections.impacted_addresses]
        .aggregate(pipeline)
        .to_list(length=None)
    )
    return_result["impacted_addresses"] = result
    return return_result


@router.get(
    "/{net}/misc/cns-domain/{tokenID}",
    response_class=JSONResponse,
)
async def get_bictory_cns_domain(
    request: Request,
    net: str,
    tokenID: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> JSONResponse:
    """
    Endpoint to get possible Bictory CNS Domain name from tokenId.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    result = await db_to_use[Collections.cns_domains].find_one({"_id": tokenID})
    if result:
        return JSONResponse({"domain_name": result["domain_name"]})
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Domain name for tokenID {tokenID} is not found on {net}.",
        )


@router.get(
    "/{net}/misc/credential-issuers",
    response_class=JSONResponse,
)
async def get_credential_issuers(
    request: Request,
    net: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> JSONResponse:
    """
    Endpoint to get credential issuers for the requested net.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    result = (
        await db_to_use[Collections.credentials_issuers].find({}).to_list(length=None)
    )
    if result:
        credential_issuers = [x["_id"] for x in result]
        return JSONResponse(credential_issuers)
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Error getting credential issuers on {net}.",
        )


@router.get(
    "/{net}/misc/identity-providers",
    response_class=JSONResponse,
)
async def get_identity_providers(
    request: Request,
    net: str,
    grpcclient: GRPCClient = Depends(get_grpcclient),
    api_key: str = Security(API_KEY_HEADER),
) -> JSONResponse:
    """
    Endpoint to get identity providers for the requested net.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    identity_providers = {}
    try:
        tmp = grpcclient.get_identity_providers("last_final", NET(net))
    except:  # noqa: E722
        raise HTTPException(
            status_code=404,
            detail=f"Error getting identity providers on {net}.",
        )

    for id in tmp:
        identity_providers[id.identity] = {
            "ip_identity": id.identity,
            "ip_description": id.description.name,
        }

    if len(identity_providers.keys()) > 0:
        return JSONResponse(identity_providers)
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Error getting identity providers on {net}.",
        )


@router.get(
    "/{net}/misc/labeled-accounts",
    response_class=JSONResponse,
)
async def get_labeled_accounts(
    request: Request,
    net: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> JSONResponse:
    """
    Endpoint to get community labeled accounts.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    # labeled accounts only exist for mainnet
    # db_to_use = mongomotor.mainnet
    db_utilities = mongomotor.utilities

    result = (
        await db_utilities[CollectionsUtilities.labeled_accounts]
        .find({})
        .to_list(length=None)
    )
    labeled_accounts = {}
    for r in result:
        current_group = labeled_accounts.get(r["label_group"], {})
        current_group[r["_id"]] = r["label"]
        labeled_accounts[r["label_group"]] = current_group

    result = (
        await db_utilities[CollectionsUtilities.labeled_accounts_metadata]
        .find({})
        .to_list(length=None)
    )

    colors = {}
    descriptions = {}
    for r in result:
        colors[r["_id"]] = r.get("color")
        descriptions[r["_id"]] = r.get("description")

    tags = {
        "labels": labeled_accounts,
        "colors": colors,
        "descriptions": descriptions,
    }

    return JSONResponse(tags)


@router.get(
    "/{net}/misc/community-labeled-accounts",
    response_class=JSONResponse,
)
async def get_community_labeled_accounts(
    request: Request,
    net: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> JSONResponse:
    """
    Endpoint to get community labeled accounts (indexes).
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    # labeled accounts only exist for mainnet
    db_to_use = mongomotor.mainnet
    db_utilities = mongomotor.utilities

    result = (
        await db_utilities[CollectionsUtilities.labeled_accounts]
        .find({})
        .to_list(length=None)
    )
    labeled_accounts = {}
    for r in result:
        current_group = labeled_accounts.get(r["label_group"], {})
        if "account_index" in r:
            current_group[r["account_index"]] = r["label"]
        else:
            current_group[r["_id"]] = r["label"]
        labeled_accounts[r["label_group"]] = current_group

    result = (
        await db_utilities[CollectionsUtilities.labeled_accounts_metadata]
        .find({})
        .to_list(length=None)
    )

    colors = {}
    descriptions = {}
    for r in result:
        colors[r["_id"]] = r.get("color")
        descriptions[r["_id"]] = r.get("description")

    ### insert projects into tags
    # display_names
    projects_display_names = {
        x["_id"]: x["display_name"]
        for x in await db_utilities[CollectionsUtilities.projects]
        .find({})
        .to_list(length=None)
    }
    # account addresses
    project_account_addresses = (
        await db_to_use[Collections.projects]
        .find({"type": "account_address"})
        .to_list(length=None)
    )

    dd = {}
    for paa in project_account_addresses:
        dd[paa["account_index"]] = projects_display_names[paa["project_id"]]
    labeled_accounts["projects"] = dd

    # contract addresses
    project_contract_addresses = (
        await db_to_use[Collections.projects]
        .find({"type": "contract_address"})
        .to_list(length=None)
    )

    dd = {}
    for paa in project_contract_addresses:
        dd[paa["contract_address"]] = projects_display_names[paa["project_id"]]
    labeled_accounts["contracts"].update(dd)

    labels_melt = {}
    for label_group in labeled_accounts.keys():
        label_group_color = colors[label_group]
        for address, tag in labeled_accounts[label_group].items():
            labels_melt[address] = {
                "label": tag,
                "group": label_group,
                "color": label_group_color,
            }

    colors = {}
    descriptions = {}
    for r in result:
        colors[r["_id"]] = r.get("color")
        descriptions[r["_id"]] = r.get("description")

    del labeled_accounts["projects"]
    tags = {
        "labels_melt": labels_melt,
        "labeled_accounts": labeled_accounts,
        "colors": colors,
        "descriptions": descriptions,
    }

    return JSONResponse(tags)


def generate_dates_from_start_until_end(start: str, end: str):
    start_date = dateutil.parser.parse(start)
    end_date = dateutil.parser.parse(end)
    date_range = []

    current_date = start_date
    while current_date <= end_date:
        date_range.append(current_date.strftime("%Y-%m-%d"))
        current_date += timedelta(days=1)

    return date_range


@router.get(
    "/{net}/misc/tx-data/{project_id}/{start_date}/{end_date}",
    response_class=JSONResponse,
)
async def get_tx_data_for_project(
    request: Request,
    net: str,
    project_id: str,
    start_date: str,
    end_date: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> JSONResponse:
    """
    Endpoint to get transactions counts for projects (and the chain).
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    dates_to_include = generate_dates_from_start_until_end(start_date, end_date)
    pipeline = [
        {"$match": {"date": {"$in": dates_to_include}}},
        {"$match": {"type": "statistics_transaction_types"}},
        {"$match": {"project": project_id}},
        {"$project": {"_id": 0, "type": 0, "usecase": 0}},
        {"$sort": {"date": 1}},
    ]
    result = (
        await mongomotor.mainnet[Collections.statistics]
        .aggregate(pipeline)
        .to_list(length=None)
    )
    return JSONResponse([x for x in result])


@router.get(
    "/{net}/misc/statistics-chain/{start_date}/{end_date}",
    response_class=JSONResponse,
)
async def get_data_for_chain_analysis(
    request: Request,
    net: str,
    start_date: str,
    end_date: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> JSONResponse:
    """
    Endpoint to get data for analysis.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    dates_to_include = generate_dates_from_start_until_end(start_date, end_date)
    pipeline = [
        {"$match": {"date": {"$in": dates_to_include}}},
        {"$match": {"type": "statistics_transaction_types"}},
        {"$match": {"project": "all"}},
        {"$project": {"_id": 0, "type": 0, "usecase": 0, "project": 0}},
        {"$sort": {"date": 1}},
    ]
    result = (
        await mongomotor.mainnet[Collections.statistics]
        .aggregate(pipeline)
        .to_list(length=None)
    )
    return JSONResponse([x for x in result])


@router.get(
    "/{net}/misc/statistics/{analysis}/{start_date}/{end_date}",
    response_class=JSONResponse,
)
async def get_data_for_analysis(
    request: Request,
    net: str,
    analysis: str,
    start_date: str,
    end_date: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> JSONResponse:
    """
    Endpoint to get data for analysis.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    dates_to_include = generate_dates_from_start_until_end(start_date, end_date)
    pipeline = [
        {"$match": {"date": {"$in": dates_to_include}}},
        {"$match": {"type": analysis}},
        {"$project": {"_id": 0, "type": 0, "usecase": 0}},
        {"$sort": {"date": 1}},
    ]
    result = (
        await mongomotor.mainnet[Collections.statistics]
        .aggregate(pipeline)
        .to_list(length=None)
    )
    return JSONResponse([x for x in result])


@router.get(
    "/{net}/misc/validator-nodes/count",
    response_class=JSONResponse,
)
async def get_nodes_count(
    request: Request,
    net: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> JSONResponse:
    """
    Endpoint to get count of all validator nodes.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    db_to_use = mongomotor.mainnet
    result = await db_to_use[Collections.paydays_current_payday].count_documents({})
    if result:
        return result
    else:
        raise HTTPException(
            status_code=404,
            detail="Error requesting nodes for {net}.",
        )


@router.get(
    "/{net}/misc/node/{node_id}",
    response_class=JSONResponse,
)
async def get_node_info(
    request: Request,
    net: str,
    node_id: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> JSONResponse:
    """
    Endpoint to get node information for a given node id.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    db_to_use = mongomotor.mainnet
    result = await db_to_use[Collections.dashboard_nodes].find_one({"_id": node_id})
    if result:
        return result
    else:
        raise HTTPException(
            status_code=404,
            detail="Error requesting nodes for {net}.",
        )


@router.get(
    "/{net}/misc/projects/all-ids",
    response_class=JSONResponse,
)
async def get_all_project_ids(
    request: Request,
    net: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> JSONResponse:
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    project_ids = {}
    result = (
        await mongomotor.utilities[CollectionsUtilities.projects]
        .find({})
        .to_list(length=None)
    )
    for project in result:
        project_ids[project["_id"]] = project

    return project_ids


@router.get(
    "/{net}/misc/projects/{project_id}",
    response_class=JSONResponse,
)
async def get_project_id(
    request: Request,
    net: str,
    project_id: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> JSONResponse:
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    result = await mongomotor.utilities[CollectionsUtilities.projects].find_one(
        {"_id": project_id}
    )

    return result


@router.get(
    "/{net}/misc/projects/{project_id}/addresses",
    response_class=JSONResponse,
)
async def get_project_addresses(
    request: Request,
    net: str,
    project_id: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> JSONResponse:
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    project_addresses = (
        await db_to_use[Collections.projects]
        .find({"project_id": project_id})
        .to_list(length=None)
    )

    return project_addresses


@router.get(
    "/misc/release-notes",
    response_class=JSONResponse,
)
async def get_release_notes(
    request: Request,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> JSONResponse:
    db_to_use = mongomotor.utilities
    release_notes = list(
        reversed(
            await db_to_use[CollectionsUtilities.release_notes]
            .find({})
            .to_list(length=None)
        )
    )

    return release_notes


# @router.get("/{net}/misc/search/{search_term}", response_class=JSONResponse)
# async def get_accounts_search(
#     request: Request,
#     net: str,
#     search_term: str,
#     mongomotor: MongoMotor = Depends(get_mongo_motor),
#     api_key: str = Security(API_KEY_HEADER),
# ) -> dict:
#     """
#     Endpoint to get to search for everything.

#     """
#     db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
#     search_result = {}

#     # # Accounts
#     # search_on_address = (
#     #     await db_to_use[Collections.all_account_addresses]
#     #     .find({"_id": {"$regex": re.compile(r"{}".format(search_term))}})
#     #     .to_list(length=5)
#     # )
#     # search_on_index = (
#     #     await db_to_use[Collections.all_account_addresses]
#     #     .find(
#     #         {
#     #             "$expr": {
#     #                 "$regexMatch": {
#     #                     "input": {"$toString": "$account_index"},
#     #                     "regex": f"{search_term}",
#     #                 }
#     #             }
#     #         }
#     #     )
#     #     .to_list(length=5)
#     # )

#     # search_accounts = search_on_address + search_on_index

#     # search_result["accounts"] = search_accounts
#     # search_term = str(search_term)[:3]
#     # Blocks
#     caret = re.compile(r"{}$".format(search_term))
#     search_on_blocks = (
#         await db_to_use[Collections.blocks].find(
#             {"_id": {"$regex": f"/{caret.pattern}/"}}
#         )
#         # .find({"_id": {"$regex": re.compile(r"^{}".format(search_term))}})
#         .to_list(length=5)
#     )
#     search_result["blocks"] = search_on_blocks

#     # # Transactions
#     # search_on_transactions = (
#     #     await db_to_use[Collections.transactions]
#     #     .find({"_id": {"$regex": re.compile(r"{}".format(search_term))}})
#     #     .to_list(length=5)
#     # )
#     # search_result["transactions"] = search_on_transactions
#     return search_result
