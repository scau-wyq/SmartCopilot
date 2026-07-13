from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from app.api.dependencies import CurrentUserDep, SessionDep
from app.api.responses import ApiError, ok
from app.schemas.organization import AssignOrgTagsRequest, OrganizationTagRequest
from app.services.conversation_service import ConversationService, parse_optional_datetime
from app.services.organization_service import OrganizationService
from app.services.billing_service import BillingService, RechargePackagePayload
from app.services.usage_dashboard_service import UsageDashboardService

router = APIRouter()


class AddUserTokensRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    llm_token: int = Field(default=0, alias="llmToken")
    embedding_token: int = Field(default=0, alias="embeddingToken")
    reason: str = "管理员手动追加"


@router.get("/conversation")
async def get_admin_conversations(
    current_user: CurrentUserDep,
    session: SessionDep,
    userid: int | None = None,
    user_id_alias: int | None = Query(default=None, alias="userId"),
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, object]:
    await OrganizationService(session).require_admin(current_user)
    try:
        messages = await ConversationService(session).get_admin_message_history(
            user_id=userid if userid is not None else user_id_alias,
            start_date=parse_optional_datetime(start_date),
            end_date=parse_optional_datetime(end_date, is_end=True),
        )
    except ValueError as exception:
        raise ApiError(400, str(exception))
    return ok("Get admin conversation history successful", messages)


@router.get("/org-tags/tree")
async def get_org_tag_tree(current_user: CurrentUserDep, session: SessionDep) -> dict[str, object]:
    service = OrganizationService(session)
    await service.require_admin(current_user)
    return ok("Get organization tag tree successful", await service.list_tag_tree())


@router.get("/org-tags")
async def get_org_tags(current_user: CurrentUserDep, session: SessionDep) -> dict[str, object]:
    service = OrganizationService(session)
    await service.require_admin(current_user)
    return ok("Get organization tags successful", await service.list_tags())


@router.post("/org-tags")
async def create_org_tag(
    payload: OrganizationTagRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    service = OrganizationService(session)
    return ok("Organization tag created successful", await service.create_tag(payload, current_user))


@router.put("/org-tags/{tag_id}")
async def update_org_tag(
    tag_id: str,
    payload: OrganizationTagRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    service = OrganizationService(session)
    return ok("Organization tag updated successful", await service.update_tag(tag_id, payload, current_user))


@router.delete("/org-tags/{tag_id}")
async def delete_org_tag(tag_id: str, current_user: CurrentUserDep, session: SessionDep) -> dict[str, object]:
    service = OrganizationService(session)
    await service.delete_tag(tag_id, current_user)
    return ok("Organization tag deleted successful")


@router.put("/users/{user_id}/org-tags")
async def assign_org_tags(
    user_id: int,
    payload: AssignOrgTagsRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    service = OrganizationService(session)
    await service.assign_org_tags_to_user(user_id, payload.org_tags, current_user)
    return ok("Organization tags assigned successful")


@router.get("/users/list")
async def list_users(
    current_user: CurrentUserDep,
    session: SessionDep,
    keyword: str | None = None,
    orgTag: str | None = None,
    page: int = 1,
    size: int = 20,
) -> dict[str, object]:
    service = OrganizationService(session)
    data = await service.list_users(current_user=current_user, keyword=keyword, org_tag=orgTag, page=page, size=size)
    return ok("Get user list successful", data)


@router.get("/usage/overview")
async def get_usage_overview(
    current_user: CurrentUserDep,
    session: SessionDep,
    days: int = Query(default=7, ge=1, le=30),
) -> dict[str, object]:
    await OrganizationService(session).require_admin(current_user)
    return ok("Get usage overview successful", await UsageDashboardService(session).overview(days))


@router.post("/users/{user_id}/tokens/add")
async def add_user_tokens(
    user_id: int,
    payload: AddUserTokensRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    await OrganizationService(session).require_admin(current_user)
    await BillingService(session).add_tokens(
        user_id=user_id,
        llm_token=payload.llm_token,
        embedding_token=payload.embedding_token,
        reason=payload.reason,
        remark=f"admin:{current_user.id}",
    )
    return ok("User tokens added successful")


@router.get("/recharge-packages")
async def admin_list_recharge_packages(current_user: CurrentUserDep, session: SessionDep) -> dict[str, object]:
    await OrganizationService(session).require_admin(current_user)
    return ok("Get recharge packages successful", await BillingService(session).list_packages(include_disabled=True))


@router.post("/recharge-packages")
async def admin_create_recharge_package(
    payload: RechargePackagePayload,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    await OrganizationService(session).require_admin(current_user)
    data = await BillingService(session).create_package(payload)
    return ok("Recharge package created successful", data)


@router.put("/recharge-packages/{package_id}")
async def admin_update_recharge_package(
    package_id: int,
    payload: RechargePackagePayload,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    await OrganizationService(session).require_admin(current_user)
    data = await BillingService(session).update_package(package_id, payload)
    return ok("Recharge package updated successful", data)


@router.delete("/recharge-packages/{package_id}")
async def admin_delete_recharge_package(
    package_id: int,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    await OrganizationService(session).require_admin(current_user)
    await BillingService(session).delete_package(package_id)
    return ok("Recharge package deleted successful")
