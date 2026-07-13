from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, ConversationSession
from app.models.user import User


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save_turn(
        self,
        user_id: int,
        question: str,
        answer: str,
        conversation_id: str,
        reference_mappings_json: str | None = None,
    ) -> Conversation:
        conversation = Conversation(
            user_id=user_id,
            question=question,
            answer=answer,
            conversation_id=conversation_id,
            reference_mappings_json=reference_mappings_json,
        )
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def list_turns_by_user(
        self,
        user_id: int,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[Conversation]:
        statement = select(Conversation).where(Conversation.user_id == user_id)
        if start_date is not None:
            statement = statement.where(Conversation.timestamp >= start_date)
        if end_date is not None:
            statement = statement.where(Conversation.timestamp <= end_date)
        statement = statement.order_by(Conversation.timestamp.asc(), Conversation.id.asc())
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def list_turns_for_admin(
        self,
        user_id: int | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[tuple[Conversation, str]]:
        statement = select(Conversation, User.username).join(User, Conversation.user_id == User.id)
        if user_id is not None:
            statement = statement.where(Conversation.user_id == user_id)
        if start_date is not None:
            statement = statement.where(Conversation.timestamp >= start_date)
        if end_date is not None:
            statement = statement.where(Conversation.timestamp <= end_date)
        statement = statement.order_by(Conversation.timestamp.asc(), Conversation.id.asc())
        result = await self.session.execute(statement)
        return [(conversation, username) for conversation, username in result.all()]

    async def list_turns_by_conversation_id(self, conversation_id: str) -> list[Conversation]:
        result = await self.session.execute(
            select(Conversation)
            .where(Conversation.conversation_id == conversation_id)
            .order_by(Conversation.timestamp.asc(), Conversation.id.asc())
        )
        return list(result.scalars().all())

    async def list_recent_turns_by_conversation_id(
        self,
        conversation_id: str,
        limit: int,
    ) -> list[Conversation]:
        result = await self.session.execute(
            select(Conversation)
            .where(Conversation.conversation_id == conversation_id)
            .order_by(Conversation.timestamp.desc(), Conversation.id.desc())
            .limit(limit)
        )
        rows = list(result.scalars().all())
        rows.reverse()
        return rows

    async def count_turns_by_conversation_id(self, conversation_id: str) -> int:
        result = await self.session.execute(
            select(func.count(Conversation.id)).where(Conversation.conversation_id == conversation_id)
        )
        return int(result.scalar_one() or 0)

    async def find_session_by_conversation_id(
        self,
        conversation_id: str,
    ) -> ConversationSession | None:
        result = await self.session.execute(
            select(ConversationSession).where(
                ConversationSession.conversation_id == conversation_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_sessions_by_user(self, user_id: int) -> list[ConversationSession]:
        result = await self.session.execute(
            select(ConversationSession)
            .where(ConversationSession.user_id == user_id)
            .order_by(ConversationSession.updated_at.desc(), ConversationSession.id.desc())
        )
        return list(result.scalars().all())

    async def save_session(self, session: ConversationSession) -> ConversationSession:
        self.session.add(session)
        await self.session.flush()
        return session
