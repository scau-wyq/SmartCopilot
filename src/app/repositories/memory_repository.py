from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import UserMemory


class MemoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_active_by_user(self, user_id: int, limit: int = 100) -> list[UserMemory]:
        result = await self.session.execute(
            select(UserMemory)
            .where(UserMemory.user_id == user_id, UserMemory.status == "ACTIVE")
            .order_by(UserMemory.updated_at.desc(), UserMemory.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def find_active_by_content(self, user_id: int, content: str) -> UserMemory | None:
        result = await self.session.execute(
            select(UserMemory).where(
                UserMemory.user_id == user_id,
                UserMemory.status == "ACTIVE",
                UserMemory.content == content,
            )
        )
        return result.scalar_one_or_none()

    async def find_active_by_id(self, user_id: int, memory_id: int) -> UserMemory | None:
        result = await self.session.execute(
            select(UserMemory).where(
                UserMemory.id == memory_id,
                UserMemory.user_id == user_id,
                UserMemory.status == "ACTIVE",
            )
        )
        return result.scalar_one_or_none()

    async def save(self, memory: UserMemory) -> UserMemory:
        self.session.add(memory)
        await self.session.flush()
        return memory

    async def flush(self) -> None:
        await self.session.flush()
