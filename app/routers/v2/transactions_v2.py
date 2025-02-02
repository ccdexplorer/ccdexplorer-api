from fastapi import APIRouter, Request, Depends, HTTPException, Security
from app.ENV import API_KEY_HEADER
from fastapi.responses import JSONResponse
from ccdexplorer_fundamentals.mongodb import (
    MongoMotor,
    Collections,
)
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import (
    CCD_BlockItemSummary,
    CCD_RejectReason,
    CCD_UpdatePayload,
)
from app.state_getters import get_mongo_motor
from enum import Enum
from pydantic import BaseModel

from collections import defaultdict


router = APIRouter(tags=["Transactions"], prefix="/v2")


class TypeContentsCategories(Enum):
    transfer = "transfers"
    smart_contract = "smart_contracts"
    data_registered = "data"
    staking = "staking"
    identity = "identity"
    chain = "chain"
    rejected = "rejected"


class TypeContentsCategoryColors(Enum):
    transfer = ("#33C364",)
    smart_contract = ("#E87E90", "#7939BA", "#B37CDF")
    data_registered = ("#48A2AE",)
    staking = ("#8BE7AA",)
    identity = ("#F6DB9A",)
    chain = ("#FFFDE4",)
    rejected = ("#DC5050",)


class TypeContents(BaseModel):
    display_str: str
    category: TypeContentsCategories
    color: str


tx_type_translation = {}
# smart contracts
tx_type_translation["module_deployed"] = TypeContents(
    display_str="new module",
    category=TypeContentsCategories.smart_contract,
    color=TypeContentsCategoryColors.smart_contract.value[0],
)
tx_type_translation["contract_initialized"] = TypeContents(
    display_str="new contract",
    category=TypeContentsCategories.smart_contract,
    color=TypeContentsCategoryColors.smart_contract.value[1],
)
tx_type_translation["contract_update_issued"] = TypeContents(
    display_str="contract updated",
    category=TypeContentsCategories.smart_contract,
    color=TypeContentsCategoryColors.smart_contract.value[2],
)

# account transfer
tx_type_translation["account_transfer"] = TypeContents(
    display_str="transfer",
    category=TypeContentsCategories.transfer,
    color=TypeContentsCategoryColors.transfer.value[0],
)
tx_type_translation["transferred_with_schedule"] = TypeContents(
    display_str="scheduled transfer",
    category=TypeContentsCategories.transfer,
    color=TypeContentsCategoryColors.transfer.value[0],
)

# staking
tx_type_translation["baker_added"] = TypeContents(
    display_str="validator added",
    category=TypeContentsCategories.staking,
    color=TypeContentsCategoryColors.staking.value[0],
)

tx_type_translation["baker_removed"] = TypeContents(
    display_str="validator removed",
    category=TypeContentsCategories.staking,
    color=TypeContentsCategoryColors.staking.value[0],
)

tx_type_translation["baker_stake_updated"] = TypeContents(
    display_str="validator updated",
    category=TypeContentsCategories.staking,
    color=TypeContentsCategoryColors.staking.value[0],
)

tx_type_translation["baker_restake_earnings_updated"] = TypeContents(
    display_str="validator updated",
    category=TypeContentsCategories.staking,
    color=TypeContentsCategoryColors.staking.value[0],
)

tx_type_translation["baker_restake_earnings_updated"] = TypeContents(
    display_str="validator updated",
    category=TypeContentsCategories.staking,
    color=TypeContentsCategoryColors.staking.value[0],
)

tx_type_translation["baker_keys_updated"] = TypeContents(
    display_str="validator updated",
    category=TypeContentsCategories.staking,
    color=TypeContentsCategoryColors.staking.value[0],
)

tx_type_translation["baker_configured"] = TypeContents(
    display_str="validator configured",
    category=TypeContentsCategories.staking,
    color=TypeContentsCategoryColors.staking.value[0],
)

tx_type_translation["delegation_configured"] = TypeContents(
    display_str="delegation configured",
    category=TypeContentsCategories.staking,
    color=TypeContentsCategoryColors.staking.value[0],
)
# credentials
tx_type_translation["credential_keys_updated"] = TypeContents(
    display_str="credentials updated",
    category=TypeContentsCategories.identity,
    color=TypeContentsCategoryColors.identity.value[0],
)

tx_type_translation["credentials_updated"] = TypeContents(
    display_str="credentials updated",
    category=TypeContentsCategories.identity,
    color=TypeContentsCategoryColors.identity.value[0],
)

tx_type_translation["credentials_updated"] = TypeContents(
    display_str="credentials updated",
    category=TypeContentsCategories.identity,
    color=TypeContentsCategoryColors.identity.value[0],
)
# data registered
tx_type_translation["data_registered"] = TypeContents(
    display_str="data registered",
    category=TypeContentsCategories.data_registered,
    color=TypeContentsCategoryColors.data_registered.value[0],
)

# rejected
for reason in CCD_RejectReason.model_fields:
    tx_type_translation[reason] = TypeContents(
        display_str=reason.replace("_", " "),
        category=TypeContentsCategories.rejected,
        color=TypeContentsCategoryColors.rejected.value[0],
    )

payload_translation = {}
payload_translation["protocol_update"] = "protocol"
payload_translation["election_difficulty_update"] = "election difficulty"
payload_translation["euro_per_energy_update"] = "EUR per NRG"
payload_translation["micro_ccd_per_euro_update"] = "CCD per EUR"
payload_translation["foundation_account_update"] = "foundation account"
payload_translation["mint_distribution_update"] = "mint distribution"
payload_translation["transaction_fee_distribution_update"] = "tx fee distribution"
payload_translation["baker_stake_threshold_update"] = "validator stake threshold"
payload_translation["root_update"] = "root"
payload_translation["level_1_update"] = "level 1"
payload_translation["add_anonymity_revoker_update"] = "add anonymity revoker"
payload_translation["add_identity_provider_update"] = "add identity provider"
payload_translation["cooldown_parameters_cpv_1_update"] = "cooldown parameters"
payload_translation["pool_parameters_cpv_1_update"] = "pool parameters"
payload_translation["time_parameters_cpv_1_update"] = "time parameters"
payload_translation["mint_distribution_cpv_1_update"] = "mint distribution"
payload_translation["finalization_committee_parameters_update"] = (
    "finalization committee parameters"
)


# update
for payload in CCD_UpdatePayload.model_fields:
    tx_type_translation[payload] = TypeContents(
        display_str=payload_translation[payload],
        category=TypeContentsCategories.chain,
        color=TypeContentsCategoryColors.chain.value[0],
    )

# identity
tx_type_translation["normal"] = TypeContents(
    display_str="account creation",
    category=TypeContentsCategories.identity,
    color=TypeContentsCategoryColors.identity.value[0],
)

tx_type_translation["initial"] = TypeContents(
    display_str="account creation",
    category=TypeContentsCategories.identity,
    color=TypeContentsCategoryColors.identity.value[0],
)


def tx_type_translator(tx_type_contents: str, request_type: str) -> str:
    result = tx_type_translation.get(tx_type_contents, None)
    if result:
        result: TypeContents
        result.category.value

    else:
        return None


def reverse_tx_type_translation(tx_type_translation: dict) -> dict:
    category_to_types = defaultdict(list)

    for tx_type, contents in tx_type_translation.items():
        category_to_types[contents.category.value].append(tx_type)

    return dict(category_to_types)


reversed_type_contents_dict = reverse_tx_type_translation(tx_type_translation)


@router.get(
    "/{net}/transactions/last/{count}/{skip}/{filter}", response_class=JSONResponse
)
@router.get("/{net}/transactions/last/{count}", response_class=JSONResponse)
async def get_last_transactions(
    request: Request,
    net: str,
    count: int,
    skip: int = None,
    filter: str = None,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    api_key: str = Security(API_KEY_HEADER),
) -> list[dict]:
    """
    Endpoint to get the last X transactions as stored in MongoDB collection `transactions`. Maxes out at 50.

    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    count = min(50, max(count, 1))
    error = None

    if filter:
        filter = reversed_type_contents_dict.get(filter, None)
        if not filter:
            raise HTTPException(
                status_code=404,
                detail="Invalid filter provided. Please use one of the following: "
                + ", ".join(reversed_type_contents_dict.keys()),
            )
        filter_dict = {"type.contents": {"$in": filter}}
    else:
        filter_dict = {}
    try:
        pipeline = [
            {"$match": filter_dict} if filter_dict else {"$match": {}},
            {"$sort": {"block_info.height": -1}},
            {"$skip": skip} if skip else {"$skip": 0},
            {"$limit": count},
        ]

        result = (
            await db_to_use[Collections.transactions].aggregate(pipeline).to_list(None)
        )

    except Exception as error:
        print(error)
        result = None

    if result:
        last_txs = [
            CCD_BlockItemSummary(**x).model_dump(exclude_none=True) for x in result
        ]
        return last_txs
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Error retrieving last {count} transactions on {net}, {error}.",
        )


@router.get("/{net}/transactions/info/tps", response_class=JSONResponse)
async def get_transactions_tps(
    request: Request,
    net: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
) -> dict:
    """
    Endpoint to get the transactions TPS as stored in MongoDB collection `pre_render`.

    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    if net != "mainnet":
        raise HTTPException(
            status_code=404,
            detail="Transactions TPS information only available for mainnet.",
        )

    db_to_use = mongomotor.mainnet
    try:
        result = await db_to_use[Collections.pre_render].find_one({"_id": "tps_table"})
        error = None
    except Exception as error:
        print(error)
        result = None

    if result:
        return result
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Error retrieving last transactions tps, {error}.",
        )


@router.get("/{net}/transactions/info/count", response_class=JSONResponse)
async def get_transactions_count_estimate(
    request: Request,
    net: str,
    mongomotor: MongoMotor = Depends(get_mongo_motor),
) -> int:
    """
    Endpoint to get the transactions estimated count.

    """
    if net not in ["mainnet", "testnet"]:
        raise HTTPException(
            status_code=404,
            detail="Don't be silly. We only support mainnet and testnet.",
        )

    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    try:
        result = await db_to_use[Collections.transactions].estimated_document_count()
        error = None
    except Exception as error:
        print(error)
        result = None

    if result:
        return result
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Error retrieving transactions count on {net}, {error}.",
        )
