from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
import datetime as dt


class APIPlansDetail(BaseModel):
    plan_name: str
    rate: float


class APIPlans(Enum):
    free = "Free"
    standard = "Standard"
    pro = "Pro"
    unrestricted = "Unrestricted"


plans = {}
plans.update(
    {APIPlans.free: APIPlansDetail(plan_name=APIPlans.free.value, rate=0.0000001)}
)
plans.update(
    {APIPlans.standard: APIPlansDetail(plan_name=APIPlans.standard.value, rate=1)}
)
plans.update({APIPlans.pro: APIPlansDetail(plan_name=APIPlans.pro.value, rate=3)})
plans.update(
    {
        APIPlans.unrestricted: APIPlansDetail(
            plan_name=APIPlans.unrestricted.value, rate=0.0000001
        )
    }
)


class APIPayment(BaseModel):
    tx_hash: str
    tx_date: str
    amount_euroe: float
    paid_days_for_plan: int  # this is the result of the amount and the plan type
    # if users want to change paid plans, this lets us retroactively change the
    # paid days. For example, suppose a user starts with the Standard plan and pays 100 EUROe
    # for 100 paid days. If they decide to change to the Pro plan after 10 days,
    # we can manually override the number of days for the first 10 days to be 10
    # The automatic calculation will take the new plan into account, which would
    # make the 100 EUROe count as only 33.3 days, while in effect the fair amount would
    # be 10 days + 90/3 = 40 days in total. So the end date needs to be adjusted based on
    # if the manual override is present.
    manual_override: Optional[int] = None


class User(BaseModel):
    scope: str  # localhost/dev/prod url
    token: str  # uuid
    alias_id: int  # this generates the account to send tokens to
    alias_account_id: str  # this is the alias account
    api_account_id: str  # uuid
    email: str
    password: str  # hashed
    plan: Optional[str] = None
    payments: Optional[dict[str, APIPayment]] = None
    # this field is generated from the payments array
    active: Optional[bool] = None
    plan_end_date: dt.datetime


class APIKey(BaseModel):
    id: str = Field(default=None, alias="_id")
    scope: str  # localhost/dev/prod url
    api_account_id: str  # uuid
    api_group: str  # this group/tier determines the limits
    api_key_end_date: dt.datetime
