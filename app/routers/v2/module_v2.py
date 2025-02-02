from fastapi import APIRouter, Request, Depends, Security, HTTPException
from app.ENV import API_KEY_HEADER
from fastapi.responses import JSONResponse
from ccdexplorer_fundamentals.GRPCClient import GRPCClient
from ccdexplorer_fundamentals.GRPCClient.types_pb2 import VersionedModuleSource
from ccdexplorer_fundamentals.enums import NET
from ccdexplorer_fundamentals.mongodb import (
    MongoMotor,
    Collections,
)
from app.state_getters import get_mongo_motor, get_grpcclient
import json
import base64
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import CCD_BlockItemSummary

router = APIRouter(tags=["Module"], prefix="/v2")


@router.get(
    "/{net}/module/{module_ref}/deployed",
    response_class=JSONResponse,
)
async def get_module_deployment_tx(
    request: Request,
    net: str,
    module_ref: str,
    mongodb: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> CCD_BlockItemSummary:
    """
    Endpoint to get tx in which the module was deployed.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet

    result = await db_to_use[Collections.transactions].find_one(
        {"account_transaction.effects.module_deployed": module_ref}
    )
    if result:
        result = CCD_BlockItemSummary(**result)
        return result


@router.get(
    "/{net}/module/{module_ref}/schema",
    response_class=JSONResponse,
)
async def get_module_schema(
    request: Request,
    net: str,
    module_ref: str,
    grpcclient: GRPCClient = Depends(get_grpcclient),
    api_key: str = Security(API_KEY_HEADER),
) -> JSONResponse:
    """
    Endpoint to get schema from module source.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    ms: VersionedModuleSource = grpcclient.get_module_source_original_classes(
        module_ref, "last_final", net=NET(net)
    )
    version = "v1" if ms.v1 else "v0"
    module_source = ms.v1.value if ms.v1 else ms.v0.value
    return JSONResponse(
        {
            "module_source": json.dumps(base64.encodebytes(module_source).decode()),
            "version": version,
        }
    )


@router.get(
    "/{net}/module/{module_ref}/instances/{skip}/{limit}",
    response_class=JSONResponse,
)
async def get_module_instances(
    request: Request,
    net: str,
    module_ref: str,
    skip: int,
    limit: int,
    mongodb: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> JSONResponse:
    """
    Endpoint to get instances from module ref.
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

    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    pipeline = [
        {"$match": {"source_module": module_ref}},
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
        await db_to_use[Collections.instances].aggregate(pipeline).to_list(length=None)
    )
    module_instances = [x["_id"] for x in result[0]["data"]]
    if "total" in result[0]:
        instances_count = result[0]["total"]
    else:
        instances_count = 0

    return {"module_instances": module_instances, "instances_count": instances_count}


@router.get(
    "/{net}/module/{module_ref}/usage",
    response_class=JSONResponse,
)
async def get_module_usage(
    request: Request,
    net: str,
    module_ref: str,
    mongodb: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> JSONResponse:
    """
    Endpoint to get usage over time for instances from module ref.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    module_instances_result = (
        await db_to_use[Collections.instances]
        .find({"source_module": module_ref})
        .to_list(length=None)
    )
    module_instances = [x["_id"] for x in module_instances_result]
    pipeline = [
        {"$match": {"impacted_address_canonical": {"$in": module_instances}}},
        {"$group": {"_id": "$date", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    result = (
        await db_to_use[Collections.impacted_addresses]
        .aggregate(pipeline)
        .to_list(length=None)
    )

    return result


@router.get(
    "/{net}/module/{module_ref}",
    response_class=JSONResponse,
)
async def get_module(
    request: Request,
    net: str,
    module_ref: str,
    mongodb: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> JSONResponse:
    """
    Endpoint to get schema from module source.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    result = await db_to_use[Collections.modules].find_one({"_id": module_ref})

    return result
