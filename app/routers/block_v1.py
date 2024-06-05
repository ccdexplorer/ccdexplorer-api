from ccdexplorer_fundamentals.GRPCClient import GRPCClient
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import (
    CCD_BlockInfo,
    CCD_FinalizedBlockInfo,
)
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.state.state import get_grpcclient

router = APIRouter(tags=["Block"], prefix="/v1")


@router.get("/{net}/block/{height}", response_class=JSONResponse)
async def get_block_at_height_from_grpc(
    request: Request,
    net: str,
    height: int,
    grpcclient: GRPCClient = Depends(get_grpcclient),
) -> CCD_BlockInfo:
    """
    Endpoint to get blockInfo from the node.
    """
    result = grpcclient.get_block_info(height)
    if result:
        return result
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested block at {height} not found on {net}",
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
