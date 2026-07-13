from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization_tag import OrganizationTag


class OrganizationTagRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_all(self) -> list[OrganizationTag]:
        result = await self.session.execute(select(OrganizationTag).order_by(OrganizationTag.tag_id.asc()))
        return list(result.scalars().all())

    async def find_by_tag_id(self, tag_id: str) -> OrganizationTag | None:
        result = await self.session.execute(select(OrganizationTag).where(OrganizationTag.tag_id == tag_id))
        return result.scalar_one_or_none()

    async def exists_by_tag_id(self, tag_id: str) -> bool:
        return await self.find_by_tag_id(tag_id) is not None

    async def find_by_parent_tag(self, parent_tag: str) -> list[OrganizationTag]:
        result = await self.session.execute(
            select(OrganizationTag).where(OrganizationTag.parent_tag == parent_tag).order_by(OrganizationTag.tag_id.asc())
        )
        return list(result.scalars().all())

    async def save(self, tag: OrganizationTag) -> OrganizationTag:
        self.session.add(tag)
        await self.session.flush()
        return tag

    async def delete(self, tag: OrganizationTag) -> None:
        await self.session.delete(tag)

    async def delete_by_tag_id(self, tag_id: str) -> None:
        await self.session.execute(delete(OrganizationTag).where(OrganizationTag.tag_id == tag_id))
