import grpc
from ccdexplorer_fundamentals.enums import NET
from ccdexplorer_fundamentals.cis import MongoTypeLoggedEvent
from ccdexplorer_fundamentals.GRPCClient import GRPCClient
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import (
    CCD_AccountInfo,
    CCD_PoolInfo,
    CCD_BlockItemSummary,
)
from ccdexplorer_fundamentals.mongodb import (
    Collections,
    MongoMotor,
    MongoDB,
    MongoTypePayday,
)
from ccdexplorer_fundamentals.tooter import Tooter, TooterChannel, TooterType  # noqa
from fastapi import APIRouter, Depends, HTTPException, Request, Security
from app.ENV import API_KEY_HEADER
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import datetime as dt
from pymongo import DESCENDING, ASCENDING
from app.state_getters import get_grpcclient, get_mongo_db, get_mongo_motor


class TokenHolding(BaseModel):
    token_address: str
    contract: str
    token_id: str
    token_amount: str


router = APIRouter(tags=["Account"], prefix="/v2")


@router.get(
    "/{net}/account/{account_address}/received-tokens/{contract_index}/{contract_subindex}",
    response_class=JSONResponse,
)
async def get_account_tokens_received(
    request: Request,
    net: str,
    account_address: str,
    contract_index: int,
    contract_subindex: int,
    mongodb: MongoDB = Depends(get_mongo_db),
    api_key: str = Security(API_KEY_HEADER),
) -> list[TokenHolding]:
    """
    Endpoint to get all received tokens for a given account, as stored in MongoDB collection `tokens_logged_events`.


    """
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    pipeline = [
        {"$match": {"contract": f"<{contract_index},{contract_subindex}>"}},
        {"$match": {"event_type": "transfer_event"}},
        {"$match": {"result.to_address": f"{account_address}"}},
    ]
    result_list = list(db_to_use[Collections.tokens_logged_events].aggregate(pipeline))

    logged_events = [MongoTypeLoggedEvent(**x) for x in result_list]

    if len(logged_events) > 0:

        return logged_events
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested account ({account_address}) has not received tokens from contract <{contract_index},{contract_subindex}> on {net}",
        )


@router.get("/{net}/account/{account_address}/tokens", response_class=JSONResponse)
async def get_account_tokens(
    request: Request,
    net: str,
    account_address: str,
    mongodb: MongoDB = Depends(get_mongo_db),
    api_key: str = Security(API_KEY_HEADER),
) -> list[TokenHolding]:
    """
    Endpoint to get all tokens for a given account, as stored in MongoDB collection `tokens_links_v2`.


    """
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    result_list = list(
        db_to_use[Collections.tokens_links_v2].find(
            {"account_address_canonical": account_address[:29]}
        )
    )
    tokens = [TokenHolding(**x["token_holding"]) for x in result_list]

    if len(tokens) > 0:

        return tokens
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested account ({account_address}) has no tokens on {net}",
        )


@router.get(
    "/{net}/account/{account_address}/balance/block/{block}",
    response_class=JSONResponse,
)
async def get_account_balance_at_block(
    request: Request,
    net: str,
    account_address: str,
    block: int,
    grpcclient: GRPCClient = Depends(get_grpcclient),
    api_key: str = Security(API_KEY_HEADER),
) -> int:
    """
    Endpoint to get all CCD balance in microCCD for a given account at the given block.


    """
    try:
        result = grpcclient.get_account_info(block, account_address, net=NET(net))
    except grpc._channel._InactiveRpcError:
        result = None

    if result:
        return result.amount
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested account {account_address} or block {block:,.0f} not found on {net}",
        )


@router.get("/{net}/account/{account_address}/balance", response_class=JSONResponse)
async def get_account_balance(
    request: Request,
    net: str,
    account_address: str,
    grpcclient: GRPCClient = Depends(get_grpcclient),
    api_key: str = Security(API_KEY_HEADER),
) -> int:
    """
    Endpoint to get all CCD balance in microCCD for a given account at the last final block.


    """
    try:
        result = grpcclient.get_account_info(
            "last_final", account_address, net=NET(net)
        )
    except grpc._channel._InactiveRpcError:
        result = None

    if result:
        return result.amount
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested account {account_address} not found on {net}",
        )


@router.get("/{net}/account/{index_or_hash}/info", response_class=JSONResponse)
async def get_account_info(
    request: Request,
    net: str,
    index_or_hash: int | str,
    grpcclient: GRPCClient = Depends(get_grpcclient),
    api_key: str = Security(API_KEY_HEADER),
) -> CCD_AccountInfo:
    """
    Endpoint to get all account info for a given account at the last final block.


    """

    try:
        # if this doesn't fail, it's type int.
        index_or_hash = int(index_or_hash)
    except ValueError:
        pass
    try:
        if isinstance(index_or_hash, int):
            try:
                result = grpcclient.get_account_info(
                    "last_final", account_index=index_or_hash, net=NET(net)
                )
            except grpc._channel._InactiveRpcError:
                result = None
        else:
            try:
                result = grpcclient.get_account_info(
                    "last_final", hex_address=index_or_hash, net=NET(net)
                )
            except grpc._channel._InactiveRpcError:
                result = None
    except:  # noqa: E722
        raise HTTPException(
            status_code=404,
            detail=f"Requested account {index_or_hash} not found on {net}",
        )

    if result:
        return result
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested account {index_or_hash} not found on {net}",
        )


@router.get("/{net}/account/{index}/earliest-win-time", response_class=JSONResponse)
async def get_validator_earliest_win_time(
    request: Request,
    net: str,
    index: int,
    grpcclient: GRPCClient = Depends(get_grpcclient),
    api_key: str = Security(API_KEY_HEADER),
) -> dt.datetime:
    """
    Endpoint to get earliest win time for an account that is an active validator.
    """

    try:
        result = grpcclient.get_baker_earliest_win_time(baker_id=index, net=NET(net))
    except grpc._channel._InactiveRpcError:
        result = None

    if result:
        return result
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Can't get earliest win time for account {index} on {net}",
        )


def expectation(value, blocks_validated):
    if round(value, 0) == 1:
        plural = ""
    else:
        plural = "s"
    if value < 5:
        expectation_string = f"{blocks_validated:,.0f} / {value:,.2f} block{plural}"
    else:
        expectation_string = f"{blocks_validated:,.0f} / {value:,.0f} block{plural}"
    return expectation_string


@router.get("/{net}/account/{index}/current-payday-stats", response_class=JSONResponse)
async def get_validator_current_payday_stats(
    request: Request,
    net: str,
    index: int,
    grpcclient: GRPCClient = Depends(get_grpcclient),
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> str:
    """
    Endpoint to get current payday stats for an account that is an active validator.
    """
    pipeline = [{"$sort": {"date": -1}}, {"$limit": 1}]
    mongo_result = (
        await mongomotor.mainnet[Collections.paydays]
        .aggregate(pipeline)
        .to_list(length=1)
    )
    if mongo_result:
        mongo_result = MongoTypePayday(**mongo_result[0])
        paydays_last_blocks_validated = (
            mongo_result.height_for_last_block - mongo_result.height_for_first_block + 1
        )

        try:
            pool = grpcclient.get_pool_info_for_pool(index, "last_final", net=NET(net))
            stats = expectation(
                pool.current_payday_info.lottery_power * paydays_last_blocks_validated,
                pool.current_payday_info.blocks_baked,
            )
        except grpc._channel._InactiveRpcError:
            pass

        if stats:
            return stats
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Can't get earliest win time for account {index} on {net}",
        )


@router.get("/{net}/account/{index}/pool-info", response_class=JSONResponse)
async def get_validator_pool_info(
    request: Request,
    net: str,
    index: int,
    grpcclient: GRPCClient = Depends(get_grpcclient),
    api_key: str = Security(API_KEY_HEADER),
) -> CCD_PoolInfo:
    """
    Endpoint to get the current pool info for an account that is an active validator.
    """

    try:
        result = grpcclient.get_pool_info_for_pool(
            pool_id=index, block_hash="last_final", net=NET(net)
        )
    except grpc._channel._InactiveRpcError:
        result = None

    if result:
        return result
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Can't get pool info for account {index} on {net}",
        )


@router.get(
    "/{net}/account/{account_id}/staking-rewards-bucketed", response_class=JSONResponse
)
async def get_staking_rewards_bucketed(
    request: Request,
    net: str,
    account_id: int | str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> list:
    """
    Endpoint to get staking rewards info for a given account for graphing.


    """
    db_to_use = mongomotor.mainnet
    pp = [
        {"$match": {"account_id": account_id}},
    ]
    try:
        result_pp = (
            await db_to_use[Collections.paydays_rewards]
            .aggregate(pp)
            .to_list(length=None)
        )
        return result_pp
    except Exception as error:
        raise HTTPException(
            status_code=404,
            detail=f"Can't retrieve staking rewards for account at {account_id} on {net} with error {error}.",
        )


@router.get("/{net}/account/{index}/validator-performance", response_class=JSONResponse)
async def get_validator_performance(
    request: Request,
    net: str,
    index: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> list:
    """
    Endpoint to get validator performance for a given validator.


    """
    db_to_use = mongomotor.mainnet
    try:
        result = (
            await db_to_use[Collections.paydays_performance]
            .find({"baker_id": index})
            .sort("date", ASCENDING)
            .to_list(length=None)
        )
        return result
    except Exception as error:
        raise HTTPException(
            status_code=404,
            detail=f"Can't retrieve validator performance for validator {index} on {net} with error {error}.",
        )


@router.get(
    "/{net}/account/{account_id}/rewards-available", response_class=JSONResponse
)
async def get_bool_account_rewards_available(
    request: Request,
    net: str,
    account_id: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> bool:
    """
    Endpoint to get determine if payday rewards are available for an account.
    """
    db_to_use = mongomotor.mainnet
    try:
        result = await db_to_use[Collections.paydays_rewards].find_one(
            {"account_id": account_id}
        )

        return result is not None

    except Exception as error:
        raise HTTPException(
            status_code=404,
            detail=f"Can't determine whether account {account_id} on {net}  has rewards with error {error}.",
        )


@router.get(
    "/{net}/account/{index}/validator-tally/{skip}/{limit}", response_class=JSONResponse
)
async def get_validator_tally(
    request: Request,
    net: str,
    index: int,
    skip: int,
    limit: int,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """
    Endpoint to get validator tally data.


    """
    limit = limit if limit <= 50 else 50
    db_to_use = mongomotor.mainnet
    try:
        account_info = grpcclient.get_account_info(
            block_hash="last_final", account_index=index, net=NET(net)
        )

        if account_info.stake:
            if account_info.stake.baker:
                validator_id = account_info.stake.baker.baker_info.baker_id
            else:
                validator_id = None
        else:
            validator_id = None

        data = None
        if validator_id:
            pipeline = [
                {
                    "$match": {"baker_id": str(validator_id)},
                },
                {"$sort": {"date": DESCENDING}},
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
                await db_to_use[Collections.paydays_performance]
                .aggregate(pipeline)
                .to_list(length=limit)
            )

            data = {
                v["date"]: {
                    "actuals": v["pool_status"]["current_payday_info"]["blocks_baked"],
                    "lp": v["pool_status"]["current_payday_info"]["lottery_power"],
                    "expectation": v["expectation"],
                }
                for v in result[0]["data"]
            }
            return {"data": data, "total_row_count": result[0]["total"]}
    except Exception as error:
        raise HTTPException(
            status_code=404,
            detail=f"Can't retrieve validator tally with error {error}.",
        )


@router.get(
    "/{net}/account/{index}/pool/delegators/{skip}/{limit}", response_class=JSONResponse
)
async def get_account_pool_delegators(
    request: Request,
    net: str,
    index: int,
    skip: int,
    limit: int,
    grpcclient: GRPCClient = Depends(get_grpcclient),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """
    Endpoint to get all delegators to pool.


    """
    try:
        account_info = grpcclient.get_account_info(
            block_hash="last_final", account_index=index, net=NET(net)
        )
        validator = account_info.stake.baker
        if validator:
            try:
                delegators_current_payday = [
                    x
                    for x in grpcclient.get_delegators_for_pool_in_reward_period(
                        pool_id=validator.baker_info.baker_id,
                        block_hash="last_final",
                        net=NET(net),
                    )
                ]
            except:  # noqa: E722
                delegators_current_payday = []

            try:
                delegators_in_block = [
                    x
                    for x in grpcclient.get_delegators_for_pool(
                        pool_id=validator.baker_info.baker_id,
                        block_hash="last_final",
                        net=NET(net),
                    )
                ]
            except:  # noqa: E722
                delegators_in_block = []

            delegators_current_payday_list = set(
                [x.account for x in delegators_current_payday]
            )
            delegators_in_block_list = set([x.account for x in delegators_in_block])

            new_delegators = delegators_in_block_list - delegators_current_payday_list

            delegators = sorted(
                delegators_current_payday, key=lambda x: x.stake, reverse=True
            )
            return {
                "delegators": delegators[skip : (skip + limit)],
                "delegators_in_block": delegators_in_block,
                "delegators_current_payday": delegators_current_payday,
                "new_delegators": new_delegators,
                "total_delegators": len(delegators_current_payday),
            }
    except Exception as error:
        raise HTTPException(
            status_code=404,
            detail=f"Can't retrieve delegators with error {error}.",
        )


@router.get("/{net}/account/{index_or_hash}/apy-data", response_class=JSONResponse)
async def get_account_apy_data(
    request: Request,
    net: str,
    index_or_hash: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """
    Endpoint to get account APY data.


    """
    db_to_use = mongomotor.mainnet
    try:
        result = await db_to_use[Collections.paydays_apy_intermediate].find_one(
            {"_id": {"$eq": str(index_or_hash)}}
        )
        return result
    except Exception as error:
        raise HTTPException(
            status_code=404,
            detail=f"Can't retrieve account APY data with error {error}.",
        )


@router.get(
    "/{net}/account/{index_or_hash}/staking-rewards-object", response_class=JSONResponse
)
async def get_staking_rewards_object(
    request: Request,
    net: str,
    index_or_hash: int | str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """
    Endpoint to get all account info for a given account at the last final block.


    """
    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    raw_apy_object = await db_to_use[Collections.paydays_apy_intermediate].find_one(
        {"_id": index_or_hash}
    )

    lookup_apy_object = {
        "d30": {"sum_of_rewards": 0, "apy": 0},
        "d90": {"sum_of_rewards": 0, "apy": 0},
        "d180": {"sum_of_rewards": 0, "apy": 0},
    }
    if raw_apy_object:
        if "d30_apy_dict" in raw_apy_object:
            if raw_apy_object["d30_apy_dict"] is not None:
                d30_day = list(raw_apy_object["d30_apy_dict"].keys())[-1]
                lookup_apy_object["d30"] = raw_apy_object["d30_apy_dict"][d30_day]

        if "d90_apy_dict" in raw_apy_object:
            if raw_apy_object["d90_apy_dict"] is not None:
                d90_day = list(raw_apy_object["d90_apy_dict"].keys())[-1]
                lookup_apy_object["d90"] = raw_apy_object["d90_apy_dict"][d90_day]

        if "d180_apy_dict" in raw_apy_object:
            if raw_apy_object["d180_apy_dict"] is not None:
                d180_day = list(raw_apy_object["d180_apy_dict"].keys())[-1]
                lookup_apy_object["d180"] = raw_apy_object["d180_apy_dict"][d180_day]

    return lookup_apy_object


@router.get(
    "/{net}/account/{account_id}/transactions/{skip}/{limit}",
    response_class=JSONResponse,
)
async def get_account_txs(
    request: Request,
    net: str,
    account_id: str,
    skip: int,
    limit: int,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """
    Endpoint to get all account transactions.
    """

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet

    try:
        top_list_member = await db_to_use[
            Collections.impacted_addresses_all_top_list
        ].find_one({"_id": account_id[:29]})

        if not top_list_member:
            pipeline = [
                {
                    "$match": {"impacted_address_canonical": {"$eq": account_id[:29]}},
                },
                {  # this filters out account rewards, as they are special events
                    "$match": {"tx_hash": {"$exists": True}},
                },
                {"$sort": {"block_height": DESCENDING}},
                {"$project": {"_id": 0, "tx_hash": 1}},
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
                await db_to_use[Collections.impacted_addresses]
                .aggregate(pipeline)
                .to_list(limit)
            )
            all_txs_hashes = [x["tx_hash"] for x in result[0]["data"]]
            if "total" in result[0]:
                total_tx_count = result[0]["total"]
            else:
                total_tx_count = 0

        else:
            #### This is a TOP_TX_COUNT account
            pipeline = [
                {
                    "$match": {"impacted_address_canonical": {"$eq": account_id[:29]}},
                },
                {  # this filters out account rewards, as they are special events
                    "$match": {"tx_hash": {"$exists": True}},
                },
                {"$sort": {"block_height": DESCENDING}},
                {"$skip": skip},
                {"$limit": limit},
                {"$project": {"tx_hash": 1}},
            ]
            result = (
                await db_to_use[Collections.impacted_addresses]
                .aggregate(pipeline)
                .to_list(limit)
            )
            all_txs_hashes = [x["tx_hash"] for x in result]
            total_tx_count = top_list_member["count"]

        int_result = (
            await db_to_use[Collections.transactions]
            .find({"_id": {"$in": all_txs_hashes}})
            .sort("block_info.height", DESCENDING)
            .to_list(limit)
        )
        tx_result = [CCD_BlockItemSummary(**x) for x in int_result]
        return {"transactions": tx_result, "total_tx_count": total_tx_count}
    except Exception as error:
        raise HTTPException(
            status_code=404,
            detail=f"Can't retrieve transactions for account at {account_id} on {net} with error {error}.",
        )


@router.get(
    "/{net}/account/{account_id}/validator-transactions/{skip}/{limit}",
    response_class=JSONResponse,
)
async def get_account_validator_txs(
    request: Request,
    net: str,
    account_id: str,
    skip: int,
    limit: int,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """
    Endpoint to get all account validator transactions.
    """

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet

    try:
        pipeline = [
            {
                "$match": {"impacted_address_canonical": {"$eq": account_id[:29]}},
            },
            {  # this filters out account rewards, as they are special events
                "$match": {
                    "$or": [
                        {"effect_type": "baker_added"},
                        {"effect_type": "baker_removed"},
                        {"effect_type": "baker_stake_updated"},
                        {"effect_type": "baker_restake_earnings_updated"},
                        {"effect_type": "baker_keys_updated"},
                        {"effect_type": "baker_configured"},
                    ]
                },
            },
            {"$sort": {"block_height": DESCENDING}},
            {"$project": {"_id": 0, "tx_hash": 1}},
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
            await db_to_use[Collections.impacted_addresses]
            .aggregate(pipeline)
            .to_list(limit)
        )
        all_txs_hashes = [x["tx_hash"] for x in result[0]["data"]]
        if "total" in result[0]:
            total_tx_count = result[0]["total"]
        else:
            total_tx_count = 0

        int_result = (
            await db_to_use[Collections.transactions]
            .find({"_id": {"$in": all_txs_hashes}})
            .sort("block_info.height", DESCENDING)
            .to_list(limit)
        )
        tx_result = [CCD_BlockItemSummary(**x) for x in int_result]
        return {"transactions": tx_result, "total_tx_count": total_tx_count}
    except Exception as error:
        raise HTTPException(
            status_code=404,
            detail=f"Can't retrieve validator transactions for account at {account_id} on {net} with error {error}.",
        )
