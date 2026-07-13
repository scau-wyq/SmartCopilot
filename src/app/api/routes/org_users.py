from fastapi import APIRouter

from app.api.dependencies import CurrentUserDep, SessionDep
from app.api.responses import ok
from app.schemas.organization import PrimaryOrgRequest
from app.services.organization_service import OrganizationService
from app.services.billing_service import BillingService

router = APIRouter()


@router.get("/org-tags")
async def get_user_org_tags(current_user: CurrentUserDep, session: SessionDep) -> dict[str, object]:
    service = OrganizationService(session)
    return ok("Get user organization tags successful", await service.get_current_user_org_tags(current_user))


@router.put("/primary-org")
async def set_primary_org(
    payload: PrimaryOrgRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    service = OrganizationService(session)
    await service.set_primary_org(current_user, payload.primary_org)
    return ok("Primary organization set successful")


@router.get("/usage")
async def get_user_usage(current_user: CurrentUserDep, session: SessionDep) -> dict[str, object]:
    return ok("Get user usage successful", await BillingService(session).usage_snapshot(int(current_user.id)))


@router.get("/token-records")
async def get_user_token_records(
    current_user: CurrentUserDep,
    session: SessionDep,
    page: int = 0,
    size: int = 10,
) -> dict[str, object]:
    data = await BillingService(session).list_token_records(int(current_user.id), page, size)
    return ok("Get user token records successful", data)
