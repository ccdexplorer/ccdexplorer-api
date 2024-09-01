from ccdexplorer_fundamentals.GRPCClient import GRPCClient
from ccdexplorer_fundamentals.enums import NET
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import (
    CCD_BlockInfo,
    CCD_FinalizedBlockInfo,
    CCD_BlockSpecialEvent,
    CCD_ChainParameters,
    CCD_BlockItemSummary,
)
from ccdexplorer_fundamentals.mongodb import MongoMotor, Collections, Collection
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.state.state import get_grpcclient, get_mongo_motor

router = APIRouter(tags=["Block"], prefix="/v1")


@router.get("/{net}/block/{height_or_hash}", response_class=JSONResponse)
async def get_block_at_height_from_grpc(
    request: Request,
    net: str,
    height_or_hash: int | str,
    grpcclient: GRPCClient = Depends(get_grpcclient),
) -> CCD_BlockInfo:
    """
    Endpoint to get blockInfo from the node.
    """
    try:
        height_or_hash = int(height_or_hash)
    except ValueError:
        pass
    result = grpcclient.get_block_info(height_or_hash, NET(net))
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
) -> list[CCD_BlockItemSummary]:
    """
    Endpoint to get transactions for the given block from mongodb.
    """

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


@router.get("/{net}/block/{height}/special-events", response_class=JSONResponse)
async def get_block_special_events(
    request: Request,
    net: str,
    height: int,
    grpcclient: GRPCClient = Depends(get_grpcclient),
) -> list[CCD_BlockSpecialEvent]:
    """
    Endpoint to get special events for the given block.
    """
    special_events = grpcclient.get_block_special_events(height, net=NET(net))

    if special_events:
        return special_events
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Can't retrieve special events for block at {height} on {net}",
        )


@router.get("/{net}/block/{height}/chain-parameters", response_class=JSONResponse)
async def get_block_chain_parameters(
    request: Request,
    net: str,
    height: int,
    grpcclient: GRPCClient = Depends(get_grpcclient),
) -> CCD_ChainParameters:
    """
    Endpoint to get chain parameters for the given block.
    """
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
) -> CCD_FinalizedBlockInfo:
    """
    Endpoint to get the last block from the node.
    """
    result = grpcclient.get_finalized_blocks()
    if result:
        return result
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Can't retrieve last finalized block for {net}",
        )
