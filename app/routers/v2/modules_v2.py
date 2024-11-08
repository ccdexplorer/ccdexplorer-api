from fastapi import APIRouter, Request, Depends, HTTPException, Security
from app.ENV import API_KEY_HEADER
from fastapi.responses import JSONResponse
from ccdexplorer_fundamentals.tooter import Tooter, TooterType, TooterChannel  # noqa
from ccdexplorer_fundamentals.mongodb import MongoMotor, Collections, MongoTypeModule
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import CCD_BlockItemSummary
from app.state_getters import get_mongo_motor
import datetime as dt

router = APIRouter(tags=["Modules"], prefix="/v2")


# @router.get("/{net}/modules/{year}/{month}", response_class=JSONResponse)
# async def get_all_modules(
#     request: Request,
#     net: str,
#     year: int,
#     month: int,
#     mongomotor: MongoMotor = Depends(get_mongo_motor),
#     api_key: str = Security(API_KEY_HEADER),
# ) -> list[CCD_BlockItemSummary]:
#     """
#     Endpoint to get all modules on net.

#     """

#     db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
#     error = None
#     try:
#         start_date = dt.datetime(year, month, 1)
#         end_date = dt.datetime(year + (month // 12), (month % 12) + 1, 1)

#         # # If it's December, the next month will be January of the next year
#         # if month == 12:
#         #     end_date = dt.datetime(year + 1, 1, 1)
#         # else:
#         #     end_date = dt.datetime(year, month + 1, 1)

#         # Query to match "module_deployed" and filter by `slot_time` in the specified month
#         pipeline = [
#             # Match documents where "type.contents" is "module_deployed"
#             {
#                 "$match": {
#                     "$expr": {
#                         "$and": [
#                             {"$eq": ["$type.contents", "module_deployed"]},
#                             {
#                                 "$eq": [
#                                     {"$year": {"$toDate": "$block_info.slot_time"}},
#                                     year,
#                                 ]
#                             },
#                             {
#                                 "$eq": [
#                                     {"$month": {"$toDate": "$block_info.slot_time"}},
#                                     month,
#                                 ]
#                             },
#                         ]
#                     }
#                 }
#             },
#             {"$sort": {"block_info.slot_time": -1}},
#         ]
#         result = [
#             CCD_BlockItemSummary(**x)
#             for x in await db_to_use[Collections.transactions]
#             .aggregate(pipeline)
#             .to_list(length=None)
#         ]
#     except Exception as error:
#         print(error)
#         result = None

#     if result:
#         return result
#     else:
#         raise HTTPException(
#             status_code=404,
#             detail=f"Error retrieving modules on {net}, {error}.",
#         )
