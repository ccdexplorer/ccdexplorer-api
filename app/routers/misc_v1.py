from ccdexplorer_fundamentals.enums import NET
from ccdexplorer_fundamentals.GRPCClient import GRPCClient
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import CCD_ContractAddress
from ccdexplorer_fundamentals.GRPCClient.types_pb2 import VersionedModuleSource
from ccdexplorer_fundamentals.mongodb import (
    Collections,
    CollectionsUtilities,
    MongoMotor,
)
from ccdexplorer_schema_parser.Schema import Schema
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
import json
import base64

from app.state.state import get_grpcclient, get_mongo_motor

router = APIRouter(tags=["Misc"], prefix="/v1")


@router.get(
    "/{net}/misc/cns-domain/{tokenID}",
    response_class=JSONResponse,
)
async def get_schema_from_source(
    request: Request,
    net: str,
    tokenID: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
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
    "/{net}/misc/labeled-accounts",
    response_class=JSONResponse,
)
async def get_labeled_accounts(
    request: Request,
    net: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
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
