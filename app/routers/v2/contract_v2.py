from ccdexplorer_fundamentals.enums import NET
from ccdexplorer_fundamentals.GRPCClient import GRPCClient
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import CCD_ContractAddress
from ccdexplorer_fundamentals.GRPCClient.types_pb2 import VersionedModuleSource
from ccdexplorer_fundamentals.mongodb import (
    Collections,
    MongoMotor,
)
from fastapi import APIRouter, Depends, HTTPException, Request, Security
from app.ENV import API_KEY_HEADER
from fastapi.responses import JSONResponse
import json
import base64

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
        ms: VersionedModuleSource = grpcclient.get_module_source_original_classes(
            module_ref, "last_final", net=NET(net)
        )
        version = "v1" if ms.v1 else "v0"
        module_source = ms.v1.value if ms.v1 else ms.v0.value
        return JSONResponse(
            {
                "source_module_name": source_module_name,
                "module_source": json.dumps(base64.encodebytes(module_source).decode()),
                "version": version,
            }
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
