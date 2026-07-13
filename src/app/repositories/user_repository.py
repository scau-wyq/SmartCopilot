from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_by_username(self, username: str) -> User | None:
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def find_by_id(self, user_id: int) -> User | None:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def list_users(
        self,
        *,
        keyword: str | None,
        org_tag: str | None,
        page: int,
        size: int,
    ) -> tuple[list[User], int]:
        conditions = []
        if keyword:
            conditions.append(User.username.like(f"%{keyword}%"))
        if org_tag:
            conditions.append(User.org_tags.like(f"%{org_tag}%"))

        statement = select(User)
        count_statement = select(func.count()).select_from(User)
        if conditions:
            statement = statement.where(and_(*conditions))
            count_statement = count_statement.where(and_(*conditions))
        statement = statement.order_by(User.created_at.desc(), User.id.desc()).offset(max(page - 1, 0) * size).limit(size)

        users_result = await self.session.execute(statement)
        total_result = await self.session.execute(count_statement)
        return list(users_result.scalars().all()), int(total_result.scalar_one())

    async def save(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        return user
