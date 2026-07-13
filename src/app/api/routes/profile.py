from app.api.dependencies import CurrentUserDep, SessionDep
from app.api.responses import ok
from app.services.billing_service import BillingService
from app.services.model_preference_service import CustomLLMPayload, ModelPreferencePayload, ModelPreferenceService
from app.services.organization_service import OrganizationService

from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def get_profile(current_user: CurrentUserDep, session: SessionDep) -> dict[str, object]:
    billing = BillingService(session)
    model_preferences = ModelPreferenceService(session)
    return ok(
        "Get profile successful",
        {
            "id": current_user.id,
            "username": current_user.username,
            "role": current_user.role,
            "orgTags": await OrganizationService(session).get_current_user_org_tags(current_user),
            "balances": await billing.balance_snapshot(int(current_user.id)),
            "usage": await billing.usage_snapshot(int(current_user.id)),
            "modelSettings": await model_preferences.to_profile_model_settings(current_user),
        },
    )


@router.put("/model-preference")
async def set_model_preference(
    payload: ModelPreferencePayload,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    data = await ModelPreferenceService(session).set_model_preference(current_user, payload)
    return ok("Model preference updated successful", data)


@router.put("/custom-llm")
async def save_custom_llm(
    payload: CustomLLMPayload,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    data = await ModelPreferenceService(session).save_custom_llm(current_user, payload)
    return ok("Custom model saved successful", data)


@router.post("/custom-llm/test")
async def test_custom_llm(
    payload: CustomLLMPayload,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    data = await ModelPreferenceService(session).test_custom_llm(current_user, payload)
    return ok("Custom model test successful", data)
