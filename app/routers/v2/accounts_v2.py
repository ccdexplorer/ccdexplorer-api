from ccdexplorer_fundamentals.mongodb import (
    Collections,
    MongoMotor,
    MongoTypePayday,
    MongoTypePaydaysPerformance,
)
from ccdexplorer_fundamentals.node import ConcordiumNodeFromDashboard
from ccdexplorer_fundamentals.enums import NET
from ccdexplorer_fundamentals.GRPCClient import GRPCClient
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import CCD_BlockItemSummary
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
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

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
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

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
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

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
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

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
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

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
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    count = min(50, max(count, 1))
    error = None
    try:
        result = [
            x["account_index"]
            for x in await db_to_use[Collections.all_account_addresses]
            .find({}, {"account_index": 1, "_id": 0})
            .sort({"account_index": -1})
            .to_list(count)
        ]

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

    except Exception as error:  # noqa: F811
        print(error)
        result = None

    if result:
        return accounts
    else:
        error = None
        raise HTTPException(
            status_code=404,
            detail=f"Error retrieving last {count} accounts on {net}, {error}.",
        )


@router.get("/{net}/accounts/nodes-validators", response_class=JSONResponse)
async def get_nodes_and_validators(
    request: Request,
    net: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """
    Endpoint to get nodes and validators.

    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

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


@router.get("/{net}/accounts/paydays/pools/{status}", response_class=JSONResponse)
async def get_payday_pools(
    request: Request,
    net: str,
    status: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """
    Endpoint to get payday pools.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    last_payday = MongoTypePayday(
        **await db_to_use[Collections.paydays].find_one(sort=[("date", -1)])
    )
    pools_for_status = last_payday.pool_status_for_bakers[status]
    result = (
        await mongomotor.mainnet[Collections.paydays_current_payday]
        .find()
        .to_list(100_000)
    )
    last_payday_performance = {
        x["baker_id"]: MongoTypePaydaysPerformance(
            **x
        )  # .model_dump(exclude_none=True)
        for x in result
        if (
            (str(x["baker_id"]).isnumeric())
            and (int(x["baker_id"]) in pools_for_status)
        )
    }
    result = (
        await mongomotor.mainnet[Collections.paydays_apy_intermediate]
        .find({"_id": {"$in": list(last_payday_performance.keys())}})
        .to_list(100_000)
    )
    last_payday_apy_objects = {x["_id"]: x for x in result}

    dd = {}
    for baker_id in last_payday_performance.keys():
        # print(baker_id)
        if "d30_apy_dict" in last_payday_apy_objects[baker_id]:
            if last_payday_apy_objects[baker_id]["d30_apy_dict"] is not None:
                d30_day = list(
                    last_payday_apy_objects[baker_id]["d30_apy_dict"].keys()
                )[-1]
            else:
                d30_day = None
        else:
            d30_day = None

        if "d90_apy_dict" in last_payday_apy_objects[baker_id]:
            if last_payday_apy_objects[baker_id]["d90_apy_dict"] is not None:
                d90_day = list(
                    last_payday_apy_objects[baker_id]["d90_apy_dict"].keys()
                )[-1]
            else:
                d90_day = None
        else:
            d90_day = None

        if "d180_apy_dict" in last_payday_apy_objects[baker_id]:
            if last_payday_apy_objects[baker_id]["d180_apy_dict"] is not None:
                d180_day = list(
                    last_payday_apy_objects[baker_id]["d180_apy_dict"].keys()
                )[-1]
            else:
                d180_day = None
        else:
            d180_day = None

        delegated_percentage = (
            (
                last_payday_performance[baker_id].pool_status.delegated_capital
                / last_payday_performance[baker_id].pool_status.delegated_capital_cap
            )
            * 100
            if last_payday_performance[baker_id].pool_status.delegated_capital_cap > 0
            else 0
        )

        delegated_percentage_remaining = 100 - delegated_percentage
        pie = (
            f"<style> .pie_{baker_id} {{\n"
            f"width: 20px;\nheight: 20px;\n"
            f"background-image: conic-gradient(#AE7CF7 0%, #AE7CF7 {delegated_percentage}%, #70B785 0%, #70B785 {delegated_percentage_remaining}%);\n"
            f" border-radius: 50%\n"
            f"}}\n</style>\n"
        )

        d = {
            "baker_id": baker_id,
            "block_commission_rate": last_payday_performance[
                baker_id
            ].pool_status.pool_info.commission_rates.baking,
            "tx_commission_rate": last_payday_performance[
                baker_id
            ].pool_status.pool_info.commission_rates.transaction,
            "expectation": last_payday_performance[baker_id].expectation,
            "lottery_power": last_payday_performance[
                baker_id
            ].pool_status.current_payday_info.lottery_power,
            "url": last_payday_performance[baker_id].pool_status.pool_info.url,
            "effective_stake": last_payday_performance[
                baker_id
            ].pool_status.current_payday_info.effective_stake,
            "delegated_capital": last_payday_performance[
                baker_id
            ].pool_status.delegated_capital,
            "delegated_capital_cap": last_payday_performance[
                baker_id
            ].pool_status.delegated_capital_cap,
            "baker_equity_capital": last_payday_performance[
                baker_id
            ].pool_status.current_payday_info.baker_equity_capital,
            "delegated_percentage": delegated_percentage,
            "delegated_percentage_remaining": delegated_percentage_remaining,
            "pie": pie,
            "d30": (
                last_payday_apy_objects[baker_id].get("d30_apy_dict")[d30_day]
                if d30_day
                else {"apy": 0.0, "sum_of_rewards": 0, "count_of_days": 0}
            ),
            "d90": (
                last_payday_apy_objects[baker_id].get("d90_apy_dict")[d90_day]
                if d90_day
                else {"apy": 0.0, "sum_of_rewards": 0, "count_of_days": 0}
            ),
            "d180": (
                last_payday_apy_objects[baker_id].get("d180_apy_dict")[d180_day]
                if d180_day
                else {"apy": 0.0, "sum_of_rewards": 0, "count_of_days": 0}
            ),
        }
        dd[baker_id] = d

    return dd


@router.get(
    "/{net}/accounts/paydays/{skip}/{limit}",
    response_class=JSONResponse,
)
async def get_paydays(
    request: Request,
    net: str,
    skip: int,
    limit: int,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> list[MongoTypePayday]:
    """
    Endpoint to get paydays.
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

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    result = (
        await db_to_use[Collections.paydays]
        .find(sort=[("date", -1)])
        .skip(skip)
        .limit(limit)
        .to_list(length=limit)
    )
    return result


@router.get(
    "/{net}/accounts/paydays/passive-delegation",
    response_class=JSONResponse,
)
async def get_payday_passive_info(
    request: Request,
    net: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """
    Endpoint to get payday passive information.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    passive_delegation_info = grpcclient.get_passive_delegation_info("last_final")
    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    passive_delegation_apy_object = await db_to_use[
        Collections.paydays_apy_intermediate
    ].find_one({"_id": "passive_delegation"})

    passive_delegation_rewards = {
        "d30": {"sum_of_rewards": 0, "apy": 0},
        "d90": {"sum_of_rewards": 0, "apy": 0},
        "d180": {"sum_of_rewards": 0, "apy": 0},
    }
    if passive_delegation_apy_object:
        d30_day = list(passive_delegation_apy_object["d30_apy_dict"].keys())[-1]
        d90_day = list(passive_delegation_apy_object["d90_apy_dict"].keys())[-1]
        d180_day = list(passive_delegation_apy_object["d180_apy_dict"].keys())[-1]

        passive_delegation_rewards["d30"] = passive_delegation_apy_object[
            "d30_apy_dict"
        ][d30_day]
        passive_delegation_rewards["d90"] = passive_delegation_apy_object[
            "d90_apy_dict"
        ][d90_day]
        passive_delegation_rewards["d180"] = passive_delegation_apy_object[
            "d180_apy_dict"
        ][d180_day]

    return {
        "passive_delegation_info": passive_delegation_info,
        "passive_delegation_rewards": passive_delegation_rewards,
    }


@router.get(
    "/{net}/accounts/paydays/passive-delegators/{skip}/{limit}",
    response_class=JSONResponse,
)
async def get_payday_passive_delegators(
    request: Request,
    net: str,
    skip: int,
    limit: int,
    grpcclient: GRPCClient = Depends(get_grpcclient),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """
    Endpoint to get payday passive delegators.
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

    delegators_current_payday = [
        x
        for x in grpcclient.get_delegators_for_passive_delegation_in_reward_period(
            "last_final"
        )
    ]
    delegators_in_block = [
        x for x in grpcclient.get_delegators_for_passive_delegation("last_final")
    ]

    delegators_current_payday_list = set([x.account for x in delegators_current_payday])

    delegators_in_block_list = set([x.account for x in delegators_in_block])

    delegators_current_payday_dict = {x.account: x for x in delegators_current_payday}
    delegators_in_block_dict = {x.account: x for x in delegators_in_block}

    new_delegators = delegators_in_block_list - delegators_current_payday_list

    # delegators_in_block_list = list(delegators_in_block_list)
    new_delegators_dict = {x: delegators_in_block_dict[x] for x in new_delegators}

    delegators = sorted(delegators_current_payday, key=lambda x: x.stake, reverse=True)
    return {
        "delegators": delegators[skip : (skip + limit)],
        "delegators_current_payday_dict": delegators_current_payday_dict,
        "delegators_in_block_dict": delegators_in_block_dict,
        "new_delegators_dict": new_delegators_dict,
    }
