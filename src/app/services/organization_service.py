import re
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responses import ApiError
from app.models.organization_tag import OrganizationTag
from app.models.user import User
from app.repositories.organization_tag_repository import OrganizationTagRepository
from app.repositories.user_repository import UserRepository
from app.schemas.organization import OrganizationTagRequest, OrganizationTagResponse
from app.services.billing_service import BillingService
from app.services.permission_service import PermissionService

BYTES_PER_MB = 1024 * 1024
MAX_TAG_ID_LENGTH = 255


class OrganizationService:
    default_org_tag = "DEFAULT"
    private_tag_prefix = "PRIVATE_"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.tags = OrganizationTagRepository(session)
        self.users = UserRepository(session)
        self.permissions = PermissionService()

    async def require_admin(self, current_user: User) -> None:
        if not self.permissions.can_manage_org(current_user):
            raise ApiError(403, "Only administrators can manage organization tags")

    async def list_tag_tree(self) -> list[dict[str, object]]:
        return [item.model_dump(by_alias=True) for item in self._build_tree(await self.tags.find_all())]

    async def list_tags(self) -> list[dict[str, object]]:
        return [self._to_response(tag).model_dump(by_alias=True) for tag in await self.tags.find_all()]

    async def create_tag(self, payload: OrganizationTagRequest, current_user: User) -> dict[str, object]:
        await self.require_admin(current_user)
        tag_id = await self._resolve_or_generate_tag_id(payload.tag_id, payload.name)
        await self._validate_parent(payload.parent_tag, tag_id)
        tag = OrganizationTag(
            tag_id=tag_id,
            name=payload.name.strip(),
            description=(payload.description or "").strip(),
            parent_tag=payload.parent_tag,
            upload_max_size_bytes=self._normalize_upload_max_size_bytes(payload.upload_max_size_mb),
            created_by=current_user.id,
        )
        await self.tags.save(tag)
        await self.session.commit()
        return self._to_response(tag).model_dump(by_alias=True)

    async def update_tag(
        self,
        tag_id: str,
        payload: OrganizationTagRequest,
        current_user: User,
    ) -> dict[str, object]:
        await self.require_admin(current_user)
        tag = await self.tags.find_by_tag_id(tag_id)
        if tag is None:
            raise ApiError(404, "Organization tag not found")
        if tag.tag_id.startswith(self.private_tag_prefix):
            raise ApiError(400, "Private organization tag cannot be edited")
        await self._validate_parent(payload.parent_tag, tag_id)
        tag.name = payload.name.strip()
        tag.description = (payload.description or "").strip()
        tag.parent_tag = payload.parent_tag
        tag.upload_max_size_bytes = self._normalize_upload_max_size_bytes(payload.upload_max_size_mb)
        await self.session.commit()
        return self._to_response(tag).model_dump(by_alias=True)

    async def delete_tag(self, tag_id: str, current_user: User) -> None:
        await self.require_admin(current_user)
        tag = await self.tags.find_by_tag_id(tag_id)
        if tag is None:
            raise ApiError(404, "Organization tag not found")
        if tag.tag_id == self.default_org_tag or tag.tag_id.startswith(self.private_tag_prefix):
            raise ApiError(400, "System organization tag cannot be deleted")
        children = await self.tags.find_by_parent_tag(tag_id)
        if children:
            raise ApiError(400, "Organization tag has child tags")
        await self.tags.delete(tag)
        await self.session.commit()

    async def get_current_user_org_tags(self, current_user: User) -> dict[str, object]:
        tag_details = await self._tag_details(current_user.org_tag_list)
        return {
            "orgTags": current_user.org_tag_list,
            "primaryOrg": current_user.primary_org,
            "orgTagDetails": tag_details,
        }

    async def set_primary_org(self, current_user: User, primary_org: str) -> None:
        if primary_org not in current_user.org_tag_list:
            raise ApiError(400, "Organization tag not assigned to user")
        current_user.primary_org = primary_org
        await self.session.commit()

    async def assign_org_tags_to_user(self, user_id: int, org_tags: list[str], current_user: User) -> None:
        await self.require_admin(current_user)
        target = await self.users.find_by_id(user_id)
        if target is None:
            raise ApiError(404, "User not found")
        normalized = self._normalize_org_tags(org_tags)
        for tag_id in normalized:
            if not tag_id.startswith(self.private_tag_prefix) and not await self.tags.exists_by_tag_id(tag_id):
                raise ApiError(404, f"Organization tag not found: {tag_id}")
        private_tags = [tag for tag in target.org_tag_list if tag.startswith(self.private_tag_prefix)]
        merged = self._normalize_org_tags([*normalized, *private_tags])
        if self.default_org_tag not in merged:
            merged.insert(0, self.default_org_tag)
        target.org_tags = ",".join(merged)
        if not target.primary_org or target.primary_org not in merged:
            target.primary_org = private_tags[0] if private_tags else merged[0]
        await self.session.commit()

    async def list_users(
        self,
        *,
        current_user: User,
        keyword: str | None,
        org_tag: str | None,
        page: int,
        size: int,
    ) -> dict[str, object]:
        await self.require_admin(current_user)
        users, total = await self.users.list_users(keyword=keyword, org_tag=org_tag, page=page, size=size)
        records = []
        billing = BillingService(self.session)
        for user in users:
            records.append(
                {
                    "userId": str(user.id),
                    "username": user.username,
                    "status": 1,
                    "orgTags": await self._tag_briefs(user.org_tag_list),
                    "primaryOrg": user.primary_org,
                    "createdAt": user.created_at.isoformat() if user.created_at else None,
                    "usage": await billing.usage_snapshot(int(user.id)),
                }
            )
        return {
            "records": records,
            "content": records,
            "data": records,
            "total": total,
            "totalElements": total,
            "pages": (total + size - 1) // size if size else 0,
            "totalPages": (total + size - 1) // size if size else 0,
            "current": page,
            "page": page,
            "size": size,
        }

    async def effective_org_tags(self, user: User) -> list[str]:
        result = set(user.org_tag_list)
        result.add(self.default_org_tag)
        for tag_id in list(result):
            await self._collect_parent_tags(tag_id, result)
        return list(result)

    async def _collect_parent_tags(self, tag_id: str, result: set[str]) -> None:
        tag = await self.tags.find_by_tag_id(tag_id)
        if tag and tag.parent_tag and tag.parent_tag not in result:
            result.add(tag.parent_tag)
            await self._collect_parent_tags(tag.parent_tag, result)

    async def _tag_details(self, tag_ids: list[str]) -> list[dict[str, object]]:
        tags = {tag.tag_id: tag for tag in await self.tags.find_all()}
        return [self._to_response(tags[tag_id]).model_dump(by_alias=True) for tag_id in tag_ids if tag_id in tags]

    async def _tag_briefs(self, tag_ids: list[str]) -> list[dict[str, str]]:
        tags = {tag.tag_id: tag for tag in await self.tags.find_all()}
        return [{"tagId": tag_id, "name": tags[tag_id].name if tag_id in tags else tag_id} for tag_id in tag_ids]

    def _build_tree(self, tags: list[OrganizationTag]) -> list[OrganizationTagResponse]:
        children_by_parent: dict[str | None, list[OrganizationTag]] = defaultdict(list)
        for tag in tags:
            children_by_parent[tag.parent_tag].append(tag)

        def build(parent_tag: str | None) -> list[OrganizationTagResponse]:
            nodes = []
            for tag in children_by_parent.get(parent_tag, []):
                response = self._to_response(tag)
                response.children = build(tag.tag_id) or None
                nodes.append(response)
            return nodes

        return build(None)

    def _to_response(self, tag: OrganizationTag) -> OrganizationTagResponse:
        return OrganizationTagResponse(
            tagId=tag.tag_id,
            name=tag.name,
            description=tag.description,
            parentTag=tag.parent_tag,
            uploadMaxSizeBytes=tag.upload_max_size_bytes,
            uploadMaxSizeMb=self._to_upload_max_size_mb(tag.upload_max_size_bytes),
            createdBy=tag.created_by,
            createdAt=tag.created_at,
            updatedAt=tag.updated_at,
        )

    async def _resolve_or_generate_tag_id(self, tag_id: str | None, name: str) -> str:
        normalized = (tag_id or "").strip()
        if normalized:
            if normalized.startswith(self.private_tag_prefix):
                raise ApiError(400, "Tag ID cannot start with PRIVATE_")
            if await self.tags.exists_by_tag_id(normalized):
                raise ApiError(400, "Tag ID already exists")
            return normalized
        base = re.sub(r"[^A-Za-z0-9_]+", "_", name.strip()).strip("_").upper() or "ORG"
        base = base[:MAX_TAG_ID_LENGTH]
        candidate = base
        suffix = 1
        while await self.tags.exists_by_tag_id(candidate):
            suffix_text = f"_{suffix}"
            candidate = f"{base[: MAX_TAG_ID_LENGTH - len(suffix_text)]}{suffix_text}"
            suffix += 1
        return candidate

    async def _validate_parent(self, parent_tag: str | None, tag_id: str) -> None:
        if not parent_tag:
            return
        if parent_tag == tag_id:
            raise ApiError(400, "Organization tag cannot be its own parent")
        if await self.tags.find_by_tag_id(parent_tag) is None:
            raise ApiError(404, "Parent tag not found")

    def _normalize_upload_max_size_bytes(self, upload_max_size_mb: int | None) -> int | None:
        if upload_max_size_mb is None:
            return None
        if upload_max_size_mb <= 0:
            raise ApiError(400, "Upload max size must be greater than 0 MB")
        return upload_max_size_mb * BYTES_PER_MB

    def _to_upload_max_size_mb(self, upload_max_size_bytes: int | None) -> int | None:
        if upload_max_size_bytes is None:
            return None
        return upload_max_size_bytes // BYTES_PER_MB

    def _normalize_org_tags(self, org_tags: list[str]) -> list[str]:
        result = []
        for tag in org_tags:
            normalized = tag.strip()
            if normalized and normalized not in result:
                result.append(normalized)
        return result

    def _empty_usage_snapshot(self) -> dict[str, object]:
        quota = {"enabled": False, "usedTokens": 0, "limitTokens": 0, "remainingTokens": 0, "requestCount": 0}
        return {"day": "", "chatRequestCount": 0, "llm": quota, "embedding": quota}
