from fastapi import APIRouter

from app.api.dependencies import CurrentUserDep, SessionDep
from app.api.responses import ok
from app.services.billing_service import BillingService
from app.services.model_preference_service import ModelPreferenceService

router = APIRouter()


@router.get("/options")
async def get_model_options(current_user: CurrentUserDep, session: SessionDep) -> dict[str, object]:
    balances = await BillingService(session).balance_snapshot(int(current_user.id))
    data = await ModelPreferenceService(session).model_options(current_user, balances)
    return ok("Get model options successful", data)
