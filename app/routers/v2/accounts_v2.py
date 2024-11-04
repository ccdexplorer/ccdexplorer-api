from ccdexplorer_fundamentals.mongodb import (
    Collections,
    MongoMotor,
)
from ccdexplorer_fundamentals.node import ConcordiumNodeFromDashboard
from ccdexplorer_fundamentals.enums import NET
from ccdexplorer_fundamentals.GRPCClient import GRPCClient
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import (
    CCD_AccountInfo,
    CCD_BlockItemSummary,
)
from fastapi import APIRouter, Depends, HTTPException, Request, Security
from app.ENV import API_KEY_HEADER
from fastapi.responses import JSONResponse
import json
from app.state_getters import get_mongo_motor, get_grpcclient

router = APIRouter(tags=["Accounts"], prefix="/v2")


@router.get("/{net}/accounts/info/count", response_class=JSONResponse)
async def get_accounts_count_estimate(
    request: Request,
    net: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> int:
    """
    Endpoint to get the accounts estimated count.

    """

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    try:
        result = (
            await db_to_use[Collections.all_account_addresses]
            .find({})
            .sort({"account_index": -1})
            .limit(1)
            .to_list(length=1)
        )
        error = None
    except Exception as error:
        print(error)
        result = None

    if result:
        return int(result[0]["account_index"]) + 1
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Error retrieving accounts count on {net}, {error}.",
        )


@router.post("/{net}/accounts/get-indexes", response_class=JSONResponse)
async def get_account_indexes(
    request: Request,
    net: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """
    Endpoint to get the the account_indexes for a list of canonical account_ids.

    """
    body = await request.body()
    if body:
        account_ids = json.loads(body.decode("utf-8"))

    else:
        account_ids = []
    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    try:
        result = (
            await db_to_use[Collections.all_account_addresses]
            .find({"_id": {"$in": account_ids}})
            .to_list(length=None)
        )
        error = None
    except Exception as error:
        print(error)
        result = None

    if result:
        return {x["_id"]: x["account_index"] for x in result}
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Error retrieving accounts list on {net}, {error}.",
        )


@router.post("/{net}/accounts/get-addresses", response_class=JSONResponse)
async def get_account_addresses(
    request: Request,
    net: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """
    Endpoint to get the the account_addresses for a list of account_indexes.

    """
    body = await request.body()
    if body:
        account_indexes = json.loads(body.decode("utf-8"))

    else:
        account_indexes = []
    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    try:
        result = (
            await db_to_use[Collections.all_account_addresses]
            .find({"account_index": {"$in": account_indexes}})
            .to_list(length=None)
        )
        error = None
    except Exception as error:
        print(error)
        result = None

    if result:
        return {x["account_index"]: x["_id"] for x in result}
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Error retrieving accounts list on {net}, {error}.",
        )


@router.get("/{net}/accounts/current-payday/info", response_class=JSONResponse)
async def get_current_payday_info(
    request: Request,
    net: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> list[dict]:
    """
    Endpoint to get the current payday info.

    """

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    try:
        result = (
            await db_to_use[Collections.paydays_current_payday]
            .find({})
            .to_list(length=None)
        )
        error = None
    except Exception as error:
        print(error)
        result = None

    if result:
        return result
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Error retrieving current payday info, {error}.",
        )


@router.get("/{net}/accounts/last-payday-block/info", response_class=JSONResponse)
async def get_last_payday_info(
    request: Request,
    net: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """
    Endpoint to get the last payday block info.

    """

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    result = await db_to_use[Collections.paydays].find_one(sort=[("date", -1)])
    if result:
        return result
    else:
        raise HTTPException(
            status_code=404,
            detail="Error retrieving last payday block info.",
        )


@router.get("/{net}/accounts/last/{count}", response_class=JSONResponse)
async def get_last_accounts(
    request: Request,
    net: str,
    count: int,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    api_key: str = Security(API_KEY_HEADER),
) -> list[dict]:
    """
    Endpoint to get the last X accounts. Maxes out at 50.

    """
    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    count = min(50, max(count, 1))
    try:
        result = [
            x["account_index"]
            for x in await db_to_use[Collections.all_account_addresses]
            .find({}, {"account_index": 1, "_id": 0})
            .sort({"account_index": -1})
            .to_list(count)
        ]
        error = None
        accounts = []
        for account_index in result:
            account_info = grpcclient.get_account_info(
                "last_final", account_index=account_index, net=NET(net)
            )

            pipeline = [
                {"$match": {"account_creation": {"$exists": True}}},
                {"$match": {"account_creation.address": account_info.address}},
            ]
            result = (
                await db_to_use[Collections.transactions]
                .aggregate(pipeline)
                .to_list(length=1)
            )

            if len(result) > 0:
                result = CCD_BlockItemSummary(**result[0])
            else:
                result = None
            accounts.append({"account_info": account_info, "deployment_tx": result})

    except Exception as error:
        print(error)
        result = None

    if result:
        return accounts
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Error retrieving last {count} accounts on {net}, {error}.",
        )


@router.get("/{net}/accounts/nodes-validators", response_class=JSONResponse)
async def get_nodes_and_validators(
    request: Request,
    net: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """
    Endpoint to get nodes and validators.

    """
    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet

    all_nodes = (
        await db_to_use[Collections.dashboard_nodes].find({}).to_list(length=None)
    )
    all_nodes_by_node_id = {x["nodeId"]: x for x in all_nodes}

    if net == "mainnet":
        all_validators = [
            x
            for x in await db_to_use[Collections.paydays_current_payday]
            .find({})
            .to_list(length=None)
        ]

        all_validators_by_validator_id = {x["baker_id"]: x for x in all_validators}

        validator_nodes_by_validator_id = {
            x["consensusBakerId"]: {
                "node": ConcordiumNodeFromDashboard(**x),
                "validator": all_validators_by_validator_id[str(x["consensusBakerId"])],
            }
            for x in all_nodes
            if x["consensusBakerId"] is not None
            if str(x["consensusBakerId"]) in all_validators_by_validator_id.keys()
        }

        validator_nodes_by_account_id = {
            all_validators_by_validator_id[str(x["consensusBakerId"])]["pool_status"][
                "address"
            ]: {
                "node": ConcordiumNodeFromDashboard(**x),
                "validator": all_validators_by_validator_id[str(x["consensusBakerId"])],
            }
            for x in all_nodes
            if x["consensusBakerId"] is not None
            if str(x["consensusBakerId"]) in all_validators_by_validator_id.keys()
        }

        non_validator_nodes_by_node_id = {
            x["nodeId"]: {"node": ConcordiumNodeFromDashboard(**x), "validator": None}
            for x in all_nodes
            if x["consensusBakerId"] is None
        }

        non_reporting_validators_by_validator_id = {
            x["baker_id"]: {
                "node": None,
                "validator": all_validators_by_validator_id[str(x["baker_id"])],
            }
            for x in all_validators
            if x["baker_id"] not in validator_nodes_by_validator_id.keys()
        }

        non_reporting_validators_by_account_id = {
            all_validators_by_validator_id[x["baker_id"]]["pool_status"]["address"]: {
                "node": None,
                "validator": all_validators_by_validator_id[str(x["baker_id"])],
            }
            for x in all_validators
            if x["baker_id"] not in validator_nodes_by_validator_id.keys()
        }

    result_dict = {"all_nodes_by_node_id": all_nodes_by_node_id}
    if net == "mainnet":
        result_dict.update(
            {
                "all_validators_by_validator_id": all_validators_by_validator_id,
                "validator_nodes_by_account_id": validator_nodes_by_account_id,
                "non_validator_nodes_by_node_id": non_validator_nodes_by_node_id,
                "non_reporting_validators_by_validator_id": non_reporting_validators_by_validator_id,
                "non_reporting_validators_by_account_id": non_reporting_validators_by_account_id,
            }
        )
    return result_dict
