from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.langgraph_agent import LangGraphAgent
from app.agents.schemas import AgentStreamEvent, ToolEvent
from app.models.user import User
from app.services.model_preference_service import ChatModelConfig


class AgentService:
    def __init__(self, session: AsyncSession, user: User, model_config: ChatModelConfig | None = None) -> None:
        self.session = session
        self.user = user
        self.model_config = model_config
        self.reference_mappings: dict[str, dict[str, object]] = {}
        self.tool_events: list[dict[str, object]] = []

    async def stream_answer(
        self,
        question: str,
        conversation_id: str,
    ) -> AsyncIterator[AgentStreamEvent]:
        agent = LangGraphAgent(self.session, self.user, self.model_config)
        emitted_tool_events = 0
        async for update in agent.astream_updates(question=question, conversation_id=conversation_id):
            state = next(iter(update.values())) if update else {}
            if not isinstance(state, dict):
                continue

            self.reference_mappings = state.get("reference_mappings") or self.reference_mappings
            self.tool_events = state.get("tool_events") or self.tool_events

            while emitted_tool_events < len(self.tool_events):
                raw_event = self.tool_events[emitted_tool_events]
                emitted_tool_events += 1
                yield AgentStreamEvent(type="tool", tool_event=self._to_tool_event(raw_event))

            final_answer = str(state.get("final_answer") or "")
            if final_answer:
                yield AgentStreamEvent(type="chunk", chunk=final_answer)

    @staticmethod
    def _to_tool_event(raw_event: dict[str, object]) -> ToolEvent:
        status = raw_event.get("status")
        if status not in {"executing", "success", "failed"}:
            status = "failed"
        return ToolEvent(
            id=raw_event.get("id") if isinstance(raw_event.get("id"), str) else None,
            tool=str(raw_event.get("tool") or ""),
            status=status,  # type: ignore[arg-type]
            timestamp=raw_event.get("timestamp") if isinstance(raw_event.get("timestamp"), int) else None,
        )
