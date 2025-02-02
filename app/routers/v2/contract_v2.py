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
from pydantic import BaseModel, ConfigDict


from app.state_getters import get_grpcclient, get_mongo_motor

router = APIRouter(tags=["Contract"], prefix="/v2")


class GetBalanceOfRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    net: str
    contract_address: CCD_ContractAddress
    token_id: str
    module_name: str
    addresses: list[str]
    grpcclient: GRPCClient


class GetCIS5BalanceOfRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    net: str
    wallet_contract_address: CCD_ContractAddress
    cis2_contract_address: CCD_ContractAddress
    token_id: str
    module_name: str
    public_keys: list[str]
    grpcclient: GRPCClient


async def get_module_name_from_contract_address(
    db_to_use, contract_address: CCD_ContractAddress
):
    instance_result = await db_to_use[Collections.instances].find_one(
        {"_id": contract_address.to_str()}
    )
    if "v1" in instance_result:
        module_name = instance_result["v1"]["name"].replace("init_", "")
    elif "v0" in instance_result:
        module_name = instance_result["v1"]["name"].replace("init_", "")
    return module_name


async def get_balance_of(req: GetBalanceOfRequest):
    """
    This function allows the api to get the balance for a specified account
    from the specified contract. This is reading from the internal state of the contract through
    invoking the balanceOf method on the CIS-2 compatible contract.
    To make this call, we need the contract, the corresponding module name and token_id.
    """
    ci = CIS(
        req.grpcclient,
        req.contract_address.index,
        req.contract_address.subindex,
        f"{req.module_name}.balanceOf",
        NET(req.net),
    )
    response, ii = ci.balanceOf("last_final", req.token_id, req.addresses)

    if ii.failure.used_energy > 0:
        return {}
    else:
        return {req.addresses[i]: str(response[i]) for i in range(len(req.addresses))}


async def get_cis5_balance_of(req: GetCIS5BalanceOfRequest):
    """
    This function allows the api to get the balance for a specified account
    from the specified contract. This is reading from the internal state of the contract through
    invoking the balanceOf method on the CIS-2 compatible contract.
    To make this call, we need the contract, the corresponding module name and token_id.
    """
    ci = CIS(
        req.grpcclient,
        req.wallet_contract_address.index,
        req.wallet_contract_address.subindex,
        f"{req.module_name}.cis2BalanceOf",
        NET(req.net),
    )
    response, ii = ci.CIS2balanceOf(
        "last_final", req.cis2_contract_address, req.token_id, req.public_keys
    )

    if ii.failure.used_energy > 0:
        return {}
    else:
        return {
            req.public_keys[i]: str(response[i]) for i in range(len(req.public_keys))
        }


async def find_cis_standards_support(cis: CIS) -> list[StandardIdentifiers]:
    """
    This lists all Standards that are said to be supported.
    """
    standards_supported = []
    for standard in reversed(StandardIdentifiers):
        if cis.supports_standards([standard]):
            standards_supported.append(standard)
    return standards_supported


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
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

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
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

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
    grpcclient: GRPCClient = Depends(get_grpcclient),
    api_key: str = Security(API_KEY_HEADER),
) -> JSONResponse:
    """
    Endpoint to get the instance information for a smart contract.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )
    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    instance_info_grpc = grpcclient.get_instance_info(
        contract_index,
        contract_subindex,
        "last_final",
        NET(net),
    )
    result = instance_info_grpc.model_dump(exclude_none=True)
    result.update(
        {
            "_id": CCD_ContractAddress.from_index(
                contract_index, contract_subindex
            ).to_str()
        }
    )
    if result["v0"]["source_module"] == "":
        source_module = result["v1"]["source_module"]
        del result["v0"]
    if result["v1"]["source_module"] == "":
        source_module = result["v0"]["source_module"]
        del result["v1"]

    if result:
        module_result = await db_to_use[Collections.modules].find_one(
            {"_id": source_module}
        )
        if module_result:
            if module_result.get("verification"):
                result["module_verification"] = module_result["verification"]
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
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    if "." in net:
        net_to_use = NET(net.split(".")[1].lower())
    else:
        net_to_use = NET(net)

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
            net_to_use,
        )
        supports_cis_standard = cis.supports_standard(StandardIdentifiers(cis_standard))

        return supports_cis_standard
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested smart contract '<{contract_index},{contract_subindex}>' not found on {net_to_use.value}.",
        )


@router.get(
    "/{net}/contract/{contract_index}/{contract_subindex}/supports-cis-standards",
    response_class=JSONResponse,
)
async def get_instance_CIS_support_multiple(
    request: Request,
    net: str,
    contract_index: int,
    contract_subindex: int,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    api_key: str = Security(API_KEY_HEADER),
) -> list[str]:
    """
    Endpoint to get which CIS standard the instance reportedly supports.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    if "." in net:
        net_to_use = NET(net.split(".")[1].lower())
    else:
        net_to_use = NET(net)

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
            net_to_use,
        )
        supports_cis_standards = await find_cis_standards_support(cis)
        supports_cis_standards = [x.value for x in supports_cis_standards]
        return supports_cis_standards
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested smart contract '<{contract_index},{contract_subindex}>' not found on {net_to_use.value}.",
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
    Endpoint to get all CIS-6 ids for instance.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    instance_address = f"<{contract_index},{contract_subindex}>"
    pipeline = [
        {"$match": {"event_info.standard": "CIS-6"}},
        {
            "$match": {"event_info.contract": instance_address},
        },
        {
            "$group": {
                "_id": "$recognized_event.item_id",
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
        for x in await db_to_use[Collections.tokens_logged_events_v2]
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
    Endpoint to get all CIS-6 logged events for instance.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    instance_address = f"<{contract_index},{contract_subindex}>"
    pipeline_for_all = [
        {"$match": {"event_info.standard": "CIS-6"}},
        {
            "$match": {"event_info.contract": instance_address},
        },
        {
            "$project": {
                "_id": 0,
                "recognized_event": 1,
                "event_info": 1,
                "tx_info": 1,
                "date": 1,
            }
        },
    ]
    all_logged_events = (
        await db_to_use[Collections.tokens_logged_events_v2]
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
    Endpoint to get all CIS-6 logged events for instance.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    instance_address = f"<{contract_index},{contract_subindex}>"
    pipeline = [
        {"$match": {"event_info.standard": "CIS-6"}},
        {"$match": {"event_info.contract": instance_address}},
        {"$match": {"recognized_event.item_id": item_id}},
        {"$sort": {"tx_info.block_height": DESCENDING}},
    ]
    item_id_statuses = (
        await db_to_use[Collections.tokens_logged_events_v2]
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
    as stored in MongoDB collection `tokens_links_v3`.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    instance_address = f"<{contract_index},{contract_subindex}>"
    result_list = list(
        await db_to_use[Collections.tokens_links_v3]
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
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

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
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

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
