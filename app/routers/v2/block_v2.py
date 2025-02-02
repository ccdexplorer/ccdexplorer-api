from ccdexplorer_fundamentals.GRPCClient import GRPCClient
from ccdexplorer_fundamentals.enums import NET
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import (
    CCD_BlockInfo,
    CCD_FinalizedBlockInfo,
    CCD_BlockSpecialEvent,
    CCD_ChainParameters,
    CCD_BlockItemSummary,
)
from ccdexplorer_fundamentals.mongodb import (
    MongoMotor,
    Collections,
    MongoTypePoolReward,
    MongoTypeAccountReward,
)
from fastapi import APIRouter, Depends, HTTPException, Request, Security
from app.ENV import API_KEY_HEADER
from fastapi.responses import JSONResponse
import grpc
from app.state_getters import get_grpcclient, get_mongo_motor

router = APIRouter(tags=["Block"], prefix="/v2")


@router.get("/{net}/block/{height_or_hash}", response_class=JSONResponse)
async def get_block_at_height_from_grpc(
    request: Request,
    net: str,
    height_or_hash: int | str,
    grpcclient: GRPCClient = Depends(get_grpcclient),
    api_key: str = Security(API_KEY_HEADER),
) -> CCD_BlockInfo:
    """
    Endpoint to get blockInfo from the node.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    try:
        height_or_hash = int(height_or_hash)
    except ValueError:
        pass
    try:
        result = grpcclient.get_block_info(height_or_hash, NET(net))
    except grpc._channel._InactiveRpcError:
        result = None
    except ValueError:
        result = None

    if result:
        return result
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested block at {height_or_hash} not found on {net}",
        )


@router.get(
    "/{net}/block/{height}/transactions/{skip}/{limit}", response_class=JSONResponse
)
async def get_block_txs(
    request: Request,
    net: str,
    height: int,
    skip: int,
    limit: int,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> list[CCD_BlockItemSummary]:
    """
    Endpoint to get transactions for the given block from mongodb.
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
    try:
        result = (
            await db_to_use[Collections.transactions]
            .find({"block_info.height": height})
            .sort({"index": 1})
            .skip(skip)
            .limit(limit)
            .to_list(limit)
        )
        error = None
    except Exception as error:
        print(error)
        result = None

    if result is not None:
        tx_result = [CCD_BlockItemSummary(**x) for x in result]
        return tx_result
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Can't retrieve transactions for block at {height} on {net}",
        )


@router.get(
    "/{net}/block/{height_or_hash}/payday",
    response_class=JSONResponse,
)
async def get_block_payday_true_false(
    request: Request,
    net: str,
    height_or_hash: int | str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> dict:
    """
    Endpoint to get determine if a block is a payday block.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    try:
        # if this doesn't fail, it's type int.
        height_or_hash = int(height_or_hash)
    except ValueError:
        pass
    db_to_use = mongomotor.mainnet
    try:
        if isinstance(height_or_hash, int):
            payday_result = await db_to_use[Collections.paydays].find_one(
                {"height_for_last_block": height_or_hash - 1}
            )
        else:
            payday_result = await db_to_use[Collections.paydays].find_one(
                {"_id": height_or_hash}
            )
        # if True, this block has payday rewards
        if payday_result:
            result_pool_rewards = (
                await db_to_use[Collections.paydays_rewards]
                .aggregate(
                    [
                        {"$match": {"date": payday_result["date"]}},
                        {"$match": {"pool_owner": {"$exists": True}}},
                        {"$count": "count_of_pool_rewards"},
                    ]
                )
                .to_list(length=None)
            )
            result_account_rewards = (
                await db_to_use[Collections.paydays_rewards]
                .aggregate(
                    [
                        {"$match": {"date": payday_result["date"]}},
                        {"$match": {"account_id": {"$exists": True}}},
                        {"$count": "count_of_account_rewards"},
                    ]
                )
                .to_list(length=None)
            )
            return {
                "is_payday": True,
                "count_of_account_rewards": result_account_rewards[0][
                    "count_of_account_rewards"
                ],
                "count_of_pool_rewards": result_pool_rewards[0][
                    "count_of_pool_rewards"
                ],
            }
        else:
            return {"is_payday": False}
    except Exception as error:
        print(error)
        raise HTTPException(
            status_code=404,
            detail=f"Can't determine whether block at {height_or_hash} on {net} is a payday.",
        )


@router.get(
    "/{net}/block/{height}/payday/pool-rewards/{skip}/{limit}",
    response_class=JSONResponse,
)
async def get_block_payday_pool_rewards(
    request: Request,
    net: str,
    height: int,
    skip: int,
    limit: int,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> list[MongoTypePoolReward]:
    """
    Endpoint to get pool rewards for the given block from mongodb.
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

    db_to_use = mongomotor.mainnet
    try:
        payday_result = await db_to_use[Collections.paydays].find_one(
            {"height_for_last_block": height - 1}
        )
        # if True, this block has payday rewards
        if payday_result:
            result = (
                await db_to_use[Collections.paydays_rewards]
                .aggregate(
                    [
                        {"$match": {"date": payday_result["date"]}},
                        {"$match": {"pool_owner": {"$exists": True}}},
                        {
                            "$facet": {
                                "metadata": [{"$count": "total"}],
                                "data": [
                                    {"$skip": int(skip)},
                                    {"$limit": int(limit)},
                                ],
                            }
                        },
                    ]
                )
                .to_list(length=None)
            )

        reward_result = [MongoTypePoolReward(**x) for x in result[0]["data"]]

        error = None
    except Exception as error:
        print(error)
        reward_result = None

    if reward_result is not None:

        return reward_result
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Can't retrieve pool rewards for block at {height} on {net}",
        )


@router.get(
    "/{net}/block/{height}/payday/account-rewards/{skip}/{limit}",
    response_class=JSONResponse,
)
async def get_block_payday_account_rewards(
    request: Request,
    net: str,
    height: int,
    skip: int,
    limit: int,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> list[MongoTypeAccountReward]:
    """
    Endpoint to get account rewards for the given block from mongodb.
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

    db_to_use = mongomotor.mainnet
    try:
        payday_result = await db_to_use[Collections.paydays].find_one(
            {"height_for_last_block": height - 1}
        )
        # if True, this block has payday rewards
        if payday_result:
            result = (
                await db_to_use[Collections.paydays_rewards]
                .aggregate(
                    [
                        {"$match": {"date": payday_result["date"]}},
                        {"$match": {"account_id": {"$exists": True}}},
                        {
                            "$facet": {
                                "metadata": [{"$count": "total"}],
                                "data": [
                                    {"$skip": int(skip)},
                                    {"$limit": int(limit)},
                                ],
                            }
                        },
                    ]
                )
                .to_list(length=None)
            )

        reward_result = [MongoTypeAccountReward(**x) for x in result[0]["data"]]

        error = None
    except Exception as error:
        print(error)
        reward_result = None

    if reward_result is not None:

        return reward_result
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Can't retrieve account rewards for block at {height} on {net}",
        )


@router.get("/{net}/block/{height}/special-events", response_class=JSONResponse)
async def get_block_special_events(
    request: Request,
    net: str,
    height: int,
    grpcclient: GRPCClient = Depends(get_grpcclient),
    api_key: str = Security(API_KEY_HEADER),
) -> list[CCD_BlockSpecialEvent]:
    """
    Endpoint to get special events for the given block.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    special_events = grpcclient.get_block_special_events(height, net=NET(net))

    return special_events
    # else:
    #     raise HTTPException(
    #         status_code=404,
    #         detail=f"Can't retrieve special events for block at {height} on {net}",
    #     )


@router.get("/{net}/block/{height}/chain-parameters", response_class=JSONResponse)
async def get_block_chain_parameters(
    request: Request,
    net: str,
    height: int,
    grpcclient: GRPCClient = Depends(get_grpcclient),
    api_key: str = Security(API_KEY_HEADER),
) -> CCD_ChainParameters:
    """
    Endpoint to get chain parameters for the given block.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    chain_parameters = grpcclient.get_block_chain_parameters(height, net=NET(net))

    if chain_parameters:
        return chain_parameters
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Can't retrieve chain parameters for block at {height} on {net}",
        )


@router.get("/{net}/block/height/finalized", response_class=JSONResponse)
async def get_last_finalized_block(
    request: Request,
    net: str,
    grpcclient: GRPCClient = Depends(get_grpcclient),
    api_key: str = Security(API_KEY_HEADER),
) -> CCD_FinalizedBlockInfo:
    """
    Endpoint to get the last block from the node.
    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    result = grpcclient.get_finalized_blocks()
    if result:
        return result
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Can't retrieve last finalized block for {net}",
        )
