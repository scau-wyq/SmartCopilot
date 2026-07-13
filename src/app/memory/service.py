import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.prompts import MEMORY_EXTRACTION_SYSTEM_PROMPT
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.integrations.llm_client import ChatMessage
from app.models.conversation import Conversation
from app.models.memory import UserMemory
from app.rag.embeddings import EmbeddingService
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.memory_repository import MemoryRepository
from app.services.llm_service import LLMService
from app.services.model_preference_service import ChatModelConfig

logger = logging.getLogger(__name__)

ALLOWED_MEMORY_TYPES = {"preference", "fact", "task_context", "project_context"}


@dataclass(frozen=True)
class RetrievedMemory:
    content: str
    memory_type: str
    score: float


class MemoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = MemoryRepository(session)
        self.embedding_service = EmbeddingService()

    async def retrieve_context(self, user_id: int, query: str) -> str:
        if not settings.long_term_memory_enabled or not query.strip():
            return ""

        try:
            vectors = await self.embedding_service.embed_texts([query], str(user_id), "MEMORY_QUERY")
        except Exception as exception:
            logger.warning("Failed to embed memory query: %s", exception)
            memories = await self.repository.list_active_by_user(
                user_id,
                limit=settings.long_term_memory_top_k,
            )
            retrieved = [
                RetrievedMemory(
                    content=memory.content,
                    memory_type=memory.memory_type,
                    score=0,
                )
                for memory in memories
            ]
        else:
            if not vectors:
                return ""
            from app.memory.indexer import MemoryIndex

            index = MemoryIndex()
            try:
                rows = await index.search(
                    user_id=user_id,
                    query_vector=vectors[0],
                    top_k=settings.long_term_memory_top_k,
                )
            except Exception as exception:
                logger.warning("Failed to search long-term memory index: %s", exception)
                rows = []
            finally:
                await index.close()
            retrieved = [
                RetrievedMemory(
                    content=str(row.get("content") or ""),
                    memory_type=str(row.get("memoryType") or "fact"),
                    score=float(row.get("score") or 0),
                )
                for row in rows
                if str(row.get("content") or "").strip()
            ]

        if not retrieved:
            return ""

        lines = [
            f"- [{memory.memory_type}] {memory.content}"
            for memory in retrieved[: settings.long_term_memory_top_k]
        ]
        return "以下是与当前用户相关的长期记忆，仅作为偏好和长期背景参考：\n" + "\n".join(lines)

    async def extract_and_store(
        self,
        *,
        user_id: int,
        conversation_id: str,
        question: str,
        answer: str,
        model_config: ChatModelConfig | None = None,
    ) -> None:
        if not settings.long_term_memory_enabled:
            return
        conversation_repository = ConversationRepository(self.session)
        turn_count = await conversation_repository.count_turns_by_conversation_id(conversation_id)
        extract_every = max(settings.long_term_memory_extract_every_turns, 1)
        if turn_count == 0 or turn_count % extract_every != 0:
            return

        window_size = max(settings.long_term_memory_extract_window_turns, extract_every)
        turns = await conversation_repository.list_recent_turns_by_conversation_id(conversation_id, window_size)
        if not turns:
            return

        existing_memories = await self.repository.list_active_by_user(user_id, limit=200)
        payload = await self._extract_memories(turns, existing_memories, model_config)
        if not payload:
            return

        from app.memory.indexer import MemoryIndex

        index = MemoryIndex()
        try:
            for item in payload:
                action = str(item.get("action") or "create").strip().lower()
                content = str(item.get("content") or "").strip()
                memory_type = str(item.get("memory_type") or "fact").strip()
                if action == "ignore":
                    continue
                if action not in {"create", "update", "replace"}:
                    continue
                if not content or memory_type not in ALLOWED_MEMORY_TYPES:
                    continue

                memory = await self._resolve_memory_for_action(user_id, item, action, content)
                if action in {"update", "replace"} and memory is None:
                    continue
                if memory is None:
                    memory = UserMemory(
                        user_id=user_id,
                        content=content,
                        memory_type=memory_type,
                        source_conversation_id=conversation_id,
                        confidence=self._normalize_confidence(item.get("confidence")),
                        status="ACTIVE",
                    )
                    await self.repository.save(memory)
                else:
                    memory.content = content
                    memory.memory_type = memory_type
                    memory.source_conversation_id = conversation_id
                    memory.confidence = self._normalize_confidence(item.get("confidence"))
                    await self.repository.flush()

                vectors = await self.embedding_service.embed_texts(
                    [content],
                    str(user_id),
                    "MEMORY_WRITE",
                )
                if vectors:
                    await index.index_memory(memory, vectors[0])
            await self.session.commit()
        finally:
            await index.close()

    async def _extract_memories(
        self,
        turns: list[Conversation],
        existing_memories: list[UserMemory],
        model_config: ChatModelConfig | None = None,
    ) -> list[dict[str, Any]]:
        content = await LLMService().complete_messages(
            [
                ChatMessage(role="system", content=MEMORY_EXTRACTION_SYSTEM_PROMPT),
                ChatMessage(
                    role="user",
                    content=self._build_extraction_input(turns, existing_memories),
                ),
            ],
            temperature=0.1,
            model_config=model_config,
        )
        try:
            parsed = json.loads(self._strip_json_fence(content))
        except json.JSONDecodeError:
            logger.warning("Long-term memory extraction returned non-JSON content")
            return []
        if not isinstance(parsed, list):
            return []
        return [item for item in parsed if isinstance(item, dict)]

    async def _resolve_memory_for_action(
        self,
        user_id: int,
        item: dict[str, Any],
        action: str,
        content: str,
    ) -> UserMemory | None:
        existing_id = self._parse_existing_memory_id(item.get("existing_memory_id"))
        if action in {"update", "replace"}:
            if existing_id is None:
                return None
            return await self.repository.find_active_by_id(user_id, existing_id)

        existing = await self.repository.find_active_by_content(user_id, content)
        return existing

    @staticmethod
    def _build_extraction_input(turns: list[Conversation], existing_memories: list[UserMemory]) -> str:
        memory_lines = []
        for memory in existing_memories:
            memory_lines.append(
                json.dumps(
                    {
                        "id": memory.id,
                        "content": memory.content,
                        "memory_type": memory.memory_type,
                        "confidence": memory.confidence,
                    },
                    ensure_ascii=False,
                )
            )
        turn_lines = []
        for index, turn in enumerate(turns, start=1):
            turn_lines.append(
                json.dumps(
                    {
                        "turn": index,
                        "question": turn.question,
                        "answer": turn.answer,
                    },
                    ensure_ascii=False,
                )
            )

        return (
            "请基于最近多轮对话维护长期记忆。\n\n"
            "已有长期记忆（可用于合并、更新或替换）：\n"
            f"{chr(10).join(memory_lines) if memory_lines else '[]'}\n\n"
            "最近对话窗口：\n"
            f"{chr(10).join(turn_lines)}"
        )

    @staticmethod
    def _parse_existing_memory_id(value: object) -> int | None:
        try:
            memory_id = int(value)
        except (TypeError, ValueError):
            return None
        return memory_id if memory_id > 0 else None

    @staticmethod
    def _strip_json_fence(content: str) -> str:
        stripped = content.strip()
        if stripped.startswith("```"):
            stripped = stripped.removeprefix("```json").removeprefix("```").strip()
            if stripped.endswith("```"):
                stripped = stripped[:-3].strip()
        return stripped

    @staticmethod
    def _normalize_confidence(value: object) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.7
        return max(0.0, min(1.0, confidence))

    @classmethod
    def schedule_extraction(
        cls,
        *,
        user_id: int,
        conversation_id: str,
        question: str,
        answer: str,
        model_config: ChatModelConfig | None = None,
    ) -> None:
        async def _run() -> None:
            try:
                async with AsyncSessionLocal() as session:
                    await cls(session).extract_and_store(
                        user_id=user_id,
                        conversation_id=conversation_id,
                        question=question,
                        answer=answer,
                        model_config=model_config,
                    )
            except Exception:
                logger.exception("Long-term memory extraction failed")

        asyncio.create_task(_run())
