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
    "/{net}/token/{contract_index}/{contract_subindex}/{token_id}/info",
    response_class=JSONResponse,
)
async def get_info_for_token_address(
    request: Request,
    net: str,
    contract_index: int,
    contract_subindex: int,
    token_id: str | None,
    mongodb: MongoDB = Depends(get_mongo_db),
) -> JSONResponse:
    """
    Endpoint to get information for a given token address..
    """
    # token_id = "" if token_id == "_" else token_id
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    token_address = f"<{contract_index},{contract_subindex}>-{token_id}"
    token_from_collection = db_to_use[Collections.tokens_token_addresses_v2].find_one(
        {"_id": token_address}
    )

    if token_from_collection:
        # get mint event from the logged events collection
        mint_event_logged_event = db_to_use[Collections.tokens_logged_events].find_one(
            {"$and": [{"token_address": token_address}, {"event_type": "mint_event"}]}
        )
        token_from_collection.update(
            {"mint_tx_hash": mint_event_logged_event["tx_hash"]}
        )

        # get current owner from the token_links collection
        current_owner_link = db_to_use[Collections.tokens_links_v2].find_one(
            {"token_holding.token_address": token_address}
        )
        token_from_collection.update(
            {"current_owner": current_owner_link["account_address"]}
        )
        if "hidden" in token_from_collection:
            del token_from_collection["hidden"]
        return JSONResponse(token_from_collection)
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Requested token_id {token_id} from contract <{contract_index},{contract_subindex}> is not found on {net}.",
        )


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
            detail=f"Requested token_id {token_id} from contract <{contract_index},{contract_subindex}> is not found on {net}.",
        )
