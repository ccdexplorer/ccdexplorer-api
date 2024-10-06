from fastapi import APIRouter, Request, Depends, HTTPException, Security
from app.ENV import API_KEY_HEADER
from fastapi.responses import JSONResponse, RedirectResponse
from ccdexplorer_fundamentals.GRPCClient import GRPCClient
from ccdexplorer_fundamentals.cis import CIS
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import CCD_ContractAddress
from ccdexplorer_fundamentals.enums import NET
from ccdexplorer_fundamentals.mongodb import (
    MongoDB,
    Collections,
)
from pydantic import BaseModel
from pymongo import ReplaceOne
from app.state_getters import get_mongo_db, get_grpcclient


class TokenHolding(BaseModel):
    token_address: str
    contract: str
    token_id: str
    token_amount: str


router = APIRouter(tags=["Token"], prefix="/v2")


def get_owner_history_for_provenance(
    grpcclient: GRPCClient,
    tokenID: str,
    contract_address: CCD_ContractAddress,
    net: NET,
):
    entrypoint = "provenance_tag_nft.view_owner_history"
    ci = CIS(
        grpcclient,
        contract_address.index,
        contract_address.subindex,
        entrypoint,
        net,
    )
    parameter_bytes = ci.viewOwnerHistoryRequest(tokenID)

    ii = grpcclient.invoke_instance(
        "last_final",
        contract_address.index,
        contract_address.subindex,
        entrypoint,
        parameter_bytes,
        net,
    )

    result = ii.success.return_value
    return ci.viewOwnerHistoryResponse(result)


@router.get(
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
    grpcclient: GRPCClient = Depends(get_grpcclient),
    api_key: str = Security(API_KEY_HEADER),
) -> JSONResponse:
    """
    Endpoint to get information for a given token address. For Provenance Tags specifically, the `owner_history`
    property is added if available.
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
        current_owner_link = list(
            db_to_use[Collections.tokens_links_v2].find(
                {"token_holding.token_address": token_address}
            )
        )
        current_owners = []
        for link in current_owner_link:
            current_owners.append(
                {
                    "address": link["account_address"],
                    "balance": int(link["token_holding"]["token_amount"]),
                }
            )

        token_from_collection.update({"current_owners": current_owners})

        # Provenance Tags Owner History
        provenance_tag_stored = db_to_use[Collections.tokens_tags].find_one(
            {"_id": "provenance-tags"}
        )
        if provenance_tag_stored:
            owner_history_list = get_owner_history_for_provenance(
                grpcclient,
                token_id,
                CCD_ContractAddress.from_index(contract_index, contract_subindex),
                NET(net),
            )
            if owner_history_list:
                token_from_collection.update({"owner_history": owner_history_list})

        if "hidden" in token_from_collection:
            del token_from_collection["hidden"]
        if "token_holders" in token_from_collection:
            del token_from_collection["token_holders"]

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
    api_key: str = Security(API_KEY_HEADER),
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
    api_key: str = Security(API_KEY_HEADER),
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
