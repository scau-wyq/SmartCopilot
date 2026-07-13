import json
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import redis_client
from app.models.conversation import Conversation, ConversationSession
from app.repositories.conversation_repository import ConversationRepository

TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S"
DEFAULT_SESSION_TITLE = "新对话"
CURRENT_CONVERSATION_TTL_SECONDS = 7 * 24 * 60 * 60


class ConversationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = ConversationRepository(session)

    async def create_session(self, user_id: int) -> dict[str, object]:
        conversation_id = str(uuid4())
        conversation_session = ConversationSession(
            user_id=user_id,
            conversation_id=conversation_id,
            title=DEFAULT_SESSION_TITLE,
            status="ACTIVE",
        )
        await self.repository.save_session(conversation_session)
        await self.session.refresh(conversation_session)
        result = self._session_to_dict(conversation_session)
        await self.session.commit()
        await self._set_current_conversation_id(user_id, conversation_id)
        return result

    async def list_sessions(self, user_id: int) -> list[dict[str, object]]:
        sessions = await self.repository.list_sessions_by_user(user_id)
        return [self._session_to_dict(item) for item in sessions]

    async def switch_current_conversation(self, user_id: int, conversation_id: str) -> None:
        session = await self.repository.find_session_by_conversation_id(conversation_id)
        if session is None or session.user_id != user_id:
            raise ValueError("Conversation not found")
        await self._set_current_conversation_id(user_id, conversation_id)

    async def archive_session(self, user_id: int, conversation_id: str) -> None:
        await self._set_session_status(user_id, conversation_id, "ARCHIVED")

    async def unarchive_session(self, user_id: int, conversation_id: str) -> None:
        await self._set_session_status(user_id, conversation_id, "ACTIVE")

    async def record_turn(
        self,
        user_id: int,
        question: str,
        answer: str,
        conversation_id: str | None = None,
        reference_mappings: dict[str, dict[str, object]] | None = None,
    ) -> str:
        effective_conversation_id = conversation_id or await self.ensure_current_session(user_id)
        await self.repository.save_turn(
            user_id=user_id,
            question=question,
            answer=answer,
            conversation_id=effective_conversation_id,
            reference_mappings_json=self._dump_reference_mappings(reference_mappings),
        )
        await self._update_session_after_message(effective_conversation_id, question)
        await self.session.commit()
        return effective_conversation_id

    async def ensure_current_session(self, user_id: int) -> str:
        current_conversation_id = await self._get_current_conversation_id(user_id)
        if current_conversation_id:
            existing = await self.repository.find_session_by_conversation_id(current_conversation_id)
            if existing is not None and existing.user_id == user_id and existing.status == "ACTIVE":
                return current_conversation_id

        conversation_id = str(uuid4())
        session = ConversationSession(
            user_id=user_id,
            conversation_id=conversation_id,
            title=DEFAULT_SESSION_TITLE,
            status="ACTIVE",
        )
        await self.repository.save_session(session)
        await self.session.flush()
        await self._set_current_conversation_id(user_id, conversation_id)
        return conversation_id

    async def get_message_history(
        self,
        user_id: int,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        conversation_id: str | None = None,
    ) -> list[dict[str, object]]:
        if conversation_id:
            session = await self.repository.find_session_by_conversation_id(conversation_id)
            if session is None or session.user_id != user_id:
                return []
            conversations = await self.repository.list_turns_by_conversation_id(conversation_id)
        else:
            conversations = await self.repository.list_turns_by_user(user_id, start_date, end_date)
        return self.to_message_history(conversations)

    async def get_admin_message_history(
        self,
        user_id: int | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[dict[str, object]]:
        rows = await self.repository.list_turns_for_admin(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
        )
        return self.to_admin_message_history(rows)

    def to_message_history(self, conversations: list[Conversation]) -> list[dict[str, object]]:
        messages: list[dict[str, object]] = []
        for conversation in conversations:
            timestamp = self._format_datetime(conversation.timestamp)
            conversation_id = conversation.conversation_id or str(conversation.id)
            messages.append(
                {
                    "role": "user",
                    "content": conversation.question,
                    "timestamp": timestamp,
                    "conversationId": conversation_id,
                }
            )
            assistant_message: dict[str, object] = {
                "role": "assistant",
                "content": conversation.answer,
                "timestamp": timestamp,
                "conversationId": conversation_id,
            }
            reference_mappings = self._load_reference_mappings(conversation.reference_mappings_json)
            if reference_mappings:
                assistant_message["referenceMappings"] = reference_mappings
            messages.append(assistant_message)
        return messages

    def to_admin_message_history(self, rows: list[tuple[Conversation, str]]) -> list[dict[str, object]]:
        messages: list[dict[str, object]] = []
        for conversation, username in rows:
            turn_messages = self.to_message_history([conversation])
            for message in turn_messages:
                message["userId"] = conversation.user_id
                message["username"] = username
            messages.extend(turn_messages)
        return messages

    async def _set_session_status(self, user_id: int, conversation_id: str, status: str) -> None:
        session = await self.repository.find_session_by_conversation_id(conversation_id)
        if session is None or session.user_id != user_id:
            raise ValueError("Conversation not found")
        session.status = status
        session.updated_at = datetime.now()
        await self.repository.save_session(session)
        await self.session.commit()

    async def _update_session_after_message(self, conversation_id: str, question: str) -> None:
        session = await self.repository.find_session_by_conversation_id(conversation_id)
        if session is None:
            return
        if session.title == DEFAULT_SESSION_TITLE and question.strip():
            session.title = question.strip()[:50]
        session.updated_at = datetime.now()
        await self.repository.save_session(session)

    async def _get_current_conversation_id(self, user_id: int) -> str | None:
        value = await redis_client.get(self._current_conversation_key(user_id))
        return value if isinstance(value, str) and value else None

    async def _set_current_conversation_id(self, user_id: int, conversation_id: str) -> None:
        await redis_client.set(
            self._current_conversation_key(user_id),
            conversation_id,
            ex=CURRENT_CONVERSATION_TTL_SECONDS,
        )

    @staticmethod
    def _current_conversation_key(user_id: int) -> str:
        return f"user:{user_id}:current_conversation"

    @staticmethod
    def _session_to_dict(session: ConversationSession) -> dict[str, object]:
        return {
            "id": session.id,
            "conversationId": session.conversation_id,
            "title": session.title or DEFAULT_SESSION_TITLE,
            "status": session.status,
            "createdAt": ConversationService._format_datetime(session.created_at),
            "updatedAt": ConversationService._format_datetime(session.updated_at),
        }

    @staticmethod
    def _format_datetime(value: datetime | None) -> str | None:
        return value.strftime(TIMESTAMP_FORMAT) if value else None

    @staticmethod
    def _dump_reference_mappings(
        reference_mappings: dict[str, dict[str, object]] | None,
    ) -> str | None:
        if not reference_mappings:
            return None
        return json.dumps(reference_mappings, ensure_ascii=False)

    @staticmethod
    def _load_reference_mappings(raw: str | None) -> dict[str, dict[str, object]] | None:
        if not raw:
            return None
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None


def parse_optional_datetime(value: str | None, is_end: bool = False) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    if len(value) == 10:
        parsed = datetime.fromisoformat(value)
        return parsed + timedelta(days=1) - timedelta(seconds=1) if is_end else parsed
    if len(value) == 13:
        value = f"{value}:59:59" if is_end else f"{value}:00:00"
    elif len(value) == 16:
        value = f"{value}:59" if is_end else f"{value}:00"
    return datetime.fromisoformat(value)
