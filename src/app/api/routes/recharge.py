from pydantic import BaseModel, ConfigDict, Field

from app.api.dependencies import CurrentUserDep, SessionDep
from app.api.responses import ok
from app.services.billing_service import BillingService

from fastapi import APIRouter

router = APIRouter()


class CreateRechargeOrderRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    package_id: int | None = Field(default=None, alias="packageId")
    custom_amount: int | None = Field(default=None, alias="customAmount")


@router.get("/packages")
async def list_packages(session: SessionDep) -> dict[str, object]:
    return ok("Get recharge packages successful", await BillingService(session).list_packages())


@router.post("/create-order")
async def create_order(
    payload: CreateRechargeOrderRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    data = await BillingService(session).create_order(current_user, payload.package_id, payload.custom_amount)
    return ok("Recharge order created successful", data)


@router.get("/orders")
async def list_orders(
    current_user: CurrentUserDep,
    session: SessionDep,
    status: str | None = None,
) -> dict[str, object]:
    return ok("Get recharge orders successful", await BillingService(session).list_orders(current_user, status))


@router.get("/orders/{trade_no}")
async def get_order(trade_no: str, current_user: CurrentUserDep, session: SessionDep) -> dict[str, object]:
    return ok("Get recharge order successful", await BillingService(session).get_order(current_user, trade_no))


@router.post("/orders/{trade_no}/mock-pay")
async def mock_pay(trade_no: str, current_user: CurrentUserDep, session: SessionDep) -> dict[str, object]:
    return ok("Recharge order paid successful", await BillingService(session).mock_pay(current_user, trade_no))
