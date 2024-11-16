from ccdexplorer_fundamentals.enums import NET
from ccdexplorer_fundamentals.GRPCClient import GRPCClient
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import (
    CCD_ContractAddress,
    CCD_BlockItemSummary,
)
from ccdexplorer_fundamentals.GRPCClient.types_pb2 import VersionedModuleSource
from ccdexplorer_fundamentals.cis import StandardIdentifiers, CIS
from ccdexplorer_fundamentals.mongodb import (
    Collections,
    MongoMotor,
)
from fastapi import APIRouter, Depends, HTTPException, Request, Security
from app.ENV import API_KEY_HEADER
from fastapi.responses import JSONResponse
import json
import base64
from pymongo import DESCENDING

from app.state_getters import get_grpcclient, get_mongo_motor

router = APIRouter(tags=["Contract"], prefix="/v2")


@router.get(
    "/{net}/contract/{contract_index}/{contract_subindex}/schema-from-source",
    response_class=JSONResponse,
)
async def get_schema_from_source(
    request: Request,
    net: str,
    contract_index: int,
    contract_subindex: int,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    api_key: str = Security(API_KEY_HEADER),
) -> JSONResponse:
    """
    Endpoint to get the schema as extracted from the source of a smart contract.
    """

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet

    result = await db_to_use[Collections.instances].find_one(
        {
            "_id": CCD_ContractAddress.from_index(
                contract_index, contract_subindex
            ).to_str()
        }
    )
    if result:
        module_ref = (
            result["v1"]["source_module"]
            if result.get("v1")
            else result["v0"]["source_module"]
        )
        source_module_name = (
            result["v1"]["name"][5:] if result.get("v1") else result["v0"]["name"][5:]
        )
        try:
            ms: VersionedModuleSource = grpcclient.get_module_source_original_classes(
                module_ref, "last_final", net=NET(net)
            )

            version = "v1" if ms.v1 else "v0"
            module_source = ms.v1.value if ms.v1 else ms.v0.value
            return JSONResponse(
                {
                    "source_module_name": source_module_name,
                    "module_source": json.dumps(
                        base64.encodebytes(module_source).decode()
                    ),
                    "version": version,
                }
            )
        except Exception as _:
            raise HTTPException(
                status_code=404,
                detail=f"Requested smart contract '<{contract_index},{contract_subindex}>' has no published schema on {net}.",
            )
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested smart contract '<{contract_index},{contract_subindex}>' is not found on {net}.",
        )


@router.get(
    "/{net}/contract/{contract_index}/{contract_subindex}/token-information",
    response_class=JSONResponse,
)
async def get_token_information(
    request: Request,
    net: str,
    contract_index: int,
    contract_subindex: int,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> JSONResponse:
    """
    Endpoint to get the token information a smart contract.
    """

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet

    result = (
        await db_to_use[Collections.tokens_tags]
        .find(
            {
                "contracts": CCD_ContractAddress.from_index(
                    contract_index, contract_subindex
                ).to_str()
            }
        )
        .to_list(length=1)
    )
    if result:
        return result[0]
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested smart contract '<{contract_index},{contract_subindex}>' token information not found on {net}.",
        )


@router.get(
    "/{net}/contract/{contract_index}/{contract_subindex}/info",
    response_class=JSONResponse,
)
async def get_instance_information(
    request: Request,
    net: str,
    contract_index: int,
    contract_subindex: int,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> JSONResponse:
    """
    Endpoint to get the instance information for a smart contract.
    """

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    instance_address = f"<{contract_index},{contract_subindex}>"
    result = await db_to_use[Collections.instances].find_one({"_id": instance_address})
    if result:
        return result
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested smart contract '<{contract_index},{contract_subindex}>' not found on {net}.",
        )


@router.get(
    "/{net}/contract/{contract_index}/{contract_subindex}/supports-cis-standard/{cis_standard}",
    response_class=JSONResponse,
)
async def get_instance_CIS_support(
    request: Request,
    net: str,
    contract_index: int,
    contract_subindex: int,
    cis_standard: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    api_key: str = Security(API_KEY_HEADER),
) -> JSONResponse:
    """
    Endpoint to get CIS support for instance.
    """
    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    instance_address = f"<{contract_index},{contract_subindex}>"
    result = await db_to_use[Collections.instances].find_one({"_id": instance_address})
    if result:
        if result.get("v0"):
            module_name = result["v0"]["name"][5:]
        if result.get("v1"):
            module_name = result["v1"]["name"][5:]
        cis: CIS = CIS(
            grpcclient,
            contract_index,
            contract_subindex,
            f"{module_name}.supports",
            NET(net),
        )
        supports_cis_standard = cis.supports_standard(StandardIdentifiers(cis_standard))

        return supports_cis_standard
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested smart contract '<{contract_index},{contract_subindex}>' not found on {net}.",
        )


@router.get(
    "/{net}/contract/{contract_index}/{contract_subindex}/tnt/ids",
    response_class=JSONResponse,
)
async def get_instance_tnt_ids(
    request: Request,
    net: str,
    contract_index: int,
    contract_subindex: int,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> JSONResponse:
    """
    Endpoint to get all tnt ids for instance.
    """
    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    instance_address = f"<{contract_index},{contract_subindex}>"
    pipeline = [
        {
            "$match": {"contract": instance_address},
        },
        {
            "$group": {
                "_id": "$item_id",
            }
        },
        {
            "$project": {
                "_id": 0,
                "distinctValues": "$_id",
            }
        },
    ]
    item_ids = [
        x["distinctValues"]
        for x in await db_to_use[Collections.tnt_logged_events]
        .aggregate(pipeline)
        .to_list(length=None)
    ]

    return item_ids


@router.get(
    "/{net}/contract/{contract_index}/{contract_subindex}/tnt/logged-events",
    response_class=JSONResponse,
)
async def get_instance_tnt_logged_events(
    request: Request,
    net: str,
    contract_index: int,
    contract_subindex: int,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> JSONResponse:
    """
    Endpoint to get all tnt logged events for instance.
    """
    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    instance_address = f"<{contract_index},{contract_subindex}>"
    pipeline_for_all = [
        {
            "$match": {"contract": instance_address},
        },
        {
            "$project": {
                "_id": 0,
                "result": 1,
                "contract": 1,
                "tx_hash": 1,
                "sender": 1,
                "timestamp": 1,
            }
        },
    ]
    all_logged_events = (
        await db_to_use[Collections.tnt_logged_events]
        .aggregate(pipeline_for_all)
        .to_list(length=None)
    )

    return all_logged_events


@router.get(
    "/{net}/contract/{contract_index}/{contract_subindex}/tnt/logged-events/{item_id}",
    response_class=JSONResponse,
)
async def get_instance_tnt_logged_events_for_item_id(
    request: Request,
    net: str,
    contract_index: int,
    contract_subindex: int,
    item_id: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> JSONResponse:
    """
    Endpoint to get all tnt logged events for instance.
    """
    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    instance_address = f"<{contract_index},{contract_subindex}>"
    pipeline = [
        {"$match": {"contract": instance_address}},
        {"$match": {"item_id": item_id}},
        {"$sort": {"block_height": DESCENDING}},
    ]
    item_id_statuses = (
        await db_to_use[Collections.tnt_logged_events]
        .aggregate(pipeline)
        .to_list(length=None)
    )

    return item_id_statuses


@router.get(
    "/{net}/contract/{contract_index}/{contract_subindex}/tokens-available",
    response_class=JSONResponse,
)
async def get_contract_tokens_available(
    request: Request,
    net: str,
    contract_index: int,
    contract_subindex: int,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> bool:
    """
    Endpoint to determine if a given contract instance holds tokens,
    as stored in MongoDB collection `tokens_links_v2`.
    """
    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    instance_address = f"<{contract_index},{contract_subindex}>"
    result_list = list(
        await db_to_use[Collections.tokens_links_v2]
        .find({"account_address_canonical": instance_address})
        .to_list(length=1)
    )
    tokens = [x["token_holding"] for x in result_list]

    return len(tokens) > 0


@router.get(
    "/{net}/contract/{contract_index}/{contract_subindex}/tag-info",
    response_class=JSONResponse,
)
async def get_instance_tag_information(
    request: Request,
    net: str,
    contract_index: int,
    contract_subindex: int,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> JSONResponse:
    """
    Endpoint to get the recognized tag information for a smart contract.
    """

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    instance_address = f"<{contract_index},{contract_subindex}>"
    result = await db_to_use[Collections.tokens_tags].find_one(
        {"contracts": {"$in": [instance_address]}}
    )
    if result:
        return result
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested smart contract tag information for '<{contract_index},{contract_subindex}>' not found on {net}.",
        )


@router.get(
    "/{net}/contract/{contract_index}/{contract_subindex}/deployed",
    response_class=JSONResponse,
)
async def get_contract_deployment_tx(
    request: Request,
    net: str,
    contract_index: int,
    contract_subindex: int,
    mongodb: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> CCD_BlockItemSummary:
    """
    Endpoint to get tx in which the instance was deployed.
    """
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    pipeline = [
        {
            "$match": {
                "account_transaction.effects.contract_initialized": {"$exists": True}
            }
        },
        {
            "$match": {
                "account_transaction.effects.contract_initialized.address.index": contract_index
            }
        },
    ]
    result = (
        await db_to_use[Collections.transactions].aggregate(pipeline).to_list(length=1)
    )

    if result:
        result = CCD_BlockItemSummary(**result[0])
        return result
