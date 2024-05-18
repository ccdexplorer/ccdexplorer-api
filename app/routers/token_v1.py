from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from ccdexplorer_fundamentals.mongodb import (
    MongoDB,
    Collections,
)
from pydantic import BaseModel
from pymongo import ReplaceOne
from app.state.state import get_mongo_db


class TokenHolding(BaseModel):
    token_address: str
    contract: str
    token_id: str
    token_amount: str


router = APIRouter(tags=["Token"], prefix="/v1")


@router.post(
    "/{net}/token/{contract_index}/{contract_subindex}/refresh",
    response_class=RedirectResponse,
)
async def add_token_address_without_token_id_to_metadata_refresh_queue(
    request: Request,
    net: str,
    contract_index: int,
    contract_subindex: int,
    mongodb: MongoDB = Depends(get_mongo_db),
) -> RedirectResponse:
    """
    Endpoint to queue a token for a refresh of the metadata from the token metadataUrl where the token_id is None.
    """

    return RedirectResponse(
        f"{router.prefix}/{net}/token/{contract_index}/{contract_subindex}/_/refresh"
    )


@router.post(
    "/{net}/token/{contract_index}/{contract_subindex}/{token_id}/refresh",
    response_class=JSONResponse,
)
async def add_token_address_to_metadata_refresh_queue(
    request: Request,
    net: str,
    contract_index: int,
    contract_subindex: int,
    token_id: str | None,
    mongodb: MongoDB = Depends(get_mongo_db),
) -> JSONResponse:
    """
    Endpoint to queue a token for a refresh of the metadata from the token metadataUrl.
    """
    token_id = "" if token_id == "_" else token_id
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    token_address = f"<{contract_index},{contract_subindex}>-{token_id}"
    token_from_collection = db_to_use[Collections.tokens_token_addresses_v2].find_one(
        {"_id": token_address}
    )

    if token_from_collection:
        result = db_to_use[Collections.helpers].find_one(
            {"_id": "refetch_token_metadata_url"}
        )
        current_token_addresses: list = result["token_addresses"]
        current_token_addresses.append(
            {
                "contract_index": contract_index,
                "contract_subindex": contract_subindex,
                "token_id": token_id,
            }
        )

        queue_item = [
            ReplaceOne(
                {"_id": "refetch_token_metadata_url"},
                replacement={
                    "_id": "refetch_token_metadata_url",
                    "token_addresses": current_token_addresses,
                },
                upsert=True,
            )
        ]
        _ = db_to_use[Collections.helpers].bulk_write(queue_item)
        return JSONResponse({"detail": "Ok"})
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested token_id({token_id}) from contract <{contract_index},{contract_subindex}> is not found on {net}.",
        )
