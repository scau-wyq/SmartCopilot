import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from redis.asyncio import Redis

from app.core.redis import redis_client


class GenerationStatus(StrEnum):
    STREAMING = "STREAMING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class GenerationSnapshot:
    generation_id: str
    user_id: str
    conversation_id: str
    question: str
    status: GenerationStatus
    created_at: str
    updated_at: str
    error_message: str | None = None
    content: str = ""
    reference_mappings: dict[str, dict[str, object]] = field(default_factory=dict)

    @classmethod
    def from_api_dict(cls, data: dict[str, object]) -> "GenerationSnapshot":
        return cls(
            generation_id=str(data["generationId"]),
            user_id=str(data["userId"]),
            conversation_id=str(data["conversationId"]),
            question=str(data.get("question") or ""),
            status=GenerationStatus(str(data.get("status") or GenerationStatus.STREAMING.value)),
            created_at=str(data.get("createdAt") or ""),
            updated_at=str(data.get("updatedAt") or ""),
            error_message=data.get("errorMessage") if isinstance(data.get("errorMessage"), str) else None,
            content=str(data.get("content") or ""),
            reference_mappings=data.get("referenceMappings")
            if isinstance(data.get("referenceMappings"), dict)
            else {},
        )

    def to_api_dict(self) -> dict[str, object]:
        return {
            "generationId": self.generation_id,
            "userId": self.user_id,
            "conversationId": self.conversation_id,
            "question": self.question,
            "status": self.status.value,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "errorMessage": self.error_message,
            "content": self.content,
            "referenceMappings": self.reference_mappings,
        }


class RedisGenerationStateStore:
    generation_ttl_seconds = 30 * 60

    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def create(
        self,
        user_id: str,
        question: str,
        conversation_id: str | None = None,
    ) -> GenerationSnapshot:
        now = datetime.now().isoformat()
        generation = GenerationSnapshot(
            generation_id=str(uuid4()),
            user_id=user_id,
            conversation_id=conversation_id or str(uuid4()),
            question=question,
            status=GenerationStatus.STREAMING,
            created_at=now,
            updated_at=now,
        )
        await self._write(generation)
        await self.redis.set(
            self._active_key(user_id),
            generation.generation_id,
            ex=self.generation_ttl_seconds,
        )
        return generation

    async def append_chunk(self, generation_id: str, chunk: str) -> None:
        generation = await self.get(generation_id)
        if generation is None:
            return
        generation.content += chunk
        generation.updated_at = datetime.now().isoformat()
        await self._write(generation)

    async def set_reference_mappings(
        self,
        generation_id: str,
        reference_mappings: dict[str, dict[str, object]],
    ) -> None:
        generation = await self.get(generation_id)
        if generation is None:
            return
        generation.reference_mappings = reference_mappings
        generation.updated_at = datetime.now().isoformat()
        await self._write(generation)

    async def mark_completed(self, generation_id: str) -> None:
        await self._update_terminal_state(generation_id, GenerationStatus.COMPLETED)

    async def mark_failed(self, generation_id: str, message: str) -> None:
        await self._update_terminal_state(generation_id, GenerationStatus.FAILED, message)

    async def mark_cancelled(self, generation_id: str) -> None:
        await self._update_terminal_state(generation_id, GenerationStatus.CANCELLED)

    async def get(self, generation_id: str) -> GenerationSnapshot | None:
        raw = await self.redis.get(self._generation_key(generation_id))
        if not raw:
            return None
        return GenerationSnapshot.from_api_dict(json.loads(raw))

    async def get_for_user(self, generation_id: str, user_id: str) -> GenerationSnapshot | None:
        generation = await self.get(generation_id)
        if generation is None or generation.user_id != user_id:
            return None
        return generation

    async def get_active_for_user(self, user_id: str) -> GenerationSnapshot | None:
        generation_id = await self.redis.get(self._active_key(user_id))
        if not generation_id:
            return None
        return await self.get_for_user(generation_id, user_id)

    async def _update_terminal_state(
        self,
        generation_id: str,
        status: GenerationStatus,
        error_message: str | None = None,
    ) -> None:
        generation = await self.get(generation_id)
        if generation is None:
            return
        generation.status = status
        generation.error_message = error_message
        generation.updated_at = datetime.now().isoformat()
        await self._write(generation)
        active_key = self._active_key(generation.user_id)
        if await self.redis.get(active_key) == generation_id:
            await self.redis.delete(active_key)

    async def _write(self, generation: GenerationSnapshot) -> None:
        await self.redis.set(
            self._generation_key(generation.generation_id),
            json.dumps(generation.to_api_dict(), ensure_ascii=False),
            ex=self.generation_ttl_seconds,
        )

    @staticmethod
    def _generation_key(generation_id: str) -> str:
        return f"chat:generation:{generation_id}"

    @staticmethod
    def _active_key(user_id: str) -> str:
        return f"chat:active-generation:{user_id}"


generation_state_store = RedisGenerationStateStore(redis_client)
