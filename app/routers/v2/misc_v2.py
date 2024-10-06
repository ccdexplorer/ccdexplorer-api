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

    identity_providers = {}
    tmp = grpcclient.get_identity_providers("last_final", NET(net))

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
        dd[paa["account_address"]] = projects_display_names[paa["project_id"]]
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

    tags = {
        "labels": labeled_accounts,
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
    db_to_use = mongomotor.mainnet
    result = await db_to_use[Collections.paydays_current_payday].count_documents({})
    if result:
        return result
    else:
        raise HTTPException(
            status_code=404,
            detail="Error requesting nodes for {net}.",
        )
