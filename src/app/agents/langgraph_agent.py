from typing import Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.prompts import AGENT_SYSTEM_PROMPT, FINAL_ANSWER_INSTRUCTION
from app.agents.schemas import ToolCall, ToolEvent, ToolResult
from app.agents.tool_executor import ToolExecutor
from app.agents.tool_registry import ToolRegistry
from app.core.config import settings
from app.core.security import now_millis
from app.memory.service import MemoryService
from app.models.conversation import Conversation
from app.models.user import User
from app.repositories.conversation_repository import ConversationRepository
from app.services.llm_service import LLMService
from app.services.model_preference_service import ChatModelConfig

MAX_TOOL_RESULT_CHARS = 8000


class AgentState(TypedDict, total=False):
    question: str
    conversation_id: str
    messages: list[BaseMessage]
    reference_mappings: dict[str, dict[str, object]]
    tool_events: list[dict[str, object]]
    final_answer: str


class LangGraphAgent:
    def __init__(self, session: AsyncSession, user: User, model_config: ChatModelConfig | None = None) -> None:
        self.session = session
        self.user = user
        self.registry = ToolRegistry()
        self.executor = ToolExecutor(self.registry, session, user)
        self.model = LLMService().create_langchain_chat_model(temperature=0.2, model_config=model_config).bind_tools(
            self.registry.openai_tools()
        )
        self.graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(AgentState)
        builder.add_node("load_context", self._load_context)
        builder.add_node("agent", self._call_agent)
        builder.add_node("tools", self._call_tools)
        builder.add_node("finalize", self._finalize)

        builder.add_edge(START, "load_context")
        builder.add_edge("load_context", "agent")
        builder.add_conditional_edges(
            "agent",
            self._route_after_agent,
            {
                "tools": "tools",
                "finalize": "finalize",
            },
        )
        builder.add_edge("tools", "agent")
        builder.add_edge("finalize", END)
        return builder.compile()

    async def ainvoke(self, question: str, conversation_id: str) -> AgentState:
        result = await self.graph.ainvoke(
            self._initial_state(question, conversation_id),
            config={"configurable": {"thread_id": conversation_id}},
        )
        return result

    async def astream_updates(self, question: str, conversation_id: str):
        async for update in self.graph.astream(
            self._initial_state(question, conversation_id),
            config={"configurable": {"thread_id": conversation_id}},
            stream_mode="updates",
        ):
            yield update

    @staticmethod
    def _initial_state(question: str, conversation_id: str) -> AgentState:
        return {
            "question": question,
            "conversation_id": conversation_id,
            "reference_mappings": {},
            "tool_events": [],
        }

    async def _load_context(self, state: AgentState) -> AgentState:
        conversation_id = str(state["conversation_id"])
        question = str(state["question"])

        messages: list[BaseMessage] = [
            SystemMessage(content=AGENT_SYSTEM_PROMPT),
            SystemMessage(content=FINAL_ANSWER_INSTRUCTION),
        ]

        memory_context = await MemoryService(self.session).retrieve_context(
            user_id=int(self.user.id),
            query=question,
        )
        if memory_context:
            messages.append(SystemMessage(content=memory_context))

        history = await ConversationRepository(self.session).list_recent_turns_by_conversation_id(
            conversation_id,
            limit=max(settings.short_term_memory_turns, 0),
        )
        messages.extend(self._history_to_messages(history))
        messages.append(HumanMessage(content=question))
        return {"messages": messages}

    async def _call_agent(self, state: AgentState) -> AgentState:
        response = await self.model.ainvoke(state["messages"])
        return {"messages": [*state["messages"], response]}

    async def _call_tools(self, state: AgentState) -> AgentState:
        messages = list(state["messages"])
        last_message = messages[-1]
        tool_calls = getattr(last_message, "tool_calls", None) or []
        reference_mappings = dict(state.get("reference_mappings") or {})
        tool_events = list(state.get("tool_events") or [])

        for raw_tool_call in tool_calls:
            tool_call = self._to_tool_call(raw_tool_call)
            executing = ToolEvent(
                id=tool_call.id,
                tool=tool_call.name,
                status="executing",
                timestamp=now_millis(),
            )
            tool_events.append(executing.to_api_dict())

            result = await self.executor.execute(tool_call)
            final_event = ToolEvent(
                id=tool_call.id,
                tool=tool_call.name,
                status="success" if result.success else "failed",
                timestamp=now_millis(),
            )
            tool_events.append(final_event.to_api_dict())
            reference_mappings.update(self._new_reference_mappings(reference_mappings, result))
            messages.append(
                ToolMessage(
                    tool_call_id=tool_call.id,
                    content=self._limit_tool_result(result),
                )
            )

        return {
            "messages": messages,
            "reference_mappings": reference_mappings,
            "tool_events": tool_events,
        }

    async def _finalize(self, state: AgentState) -> AgentState:
        last_message = state["messages"][-1]
        content = getattr(last_message, "content", "")
        if isinstance(content, list):
            final_answer = "".join(str(item) for item in content)
        else:
            final_answer = str(content or "")
        return {"final_answer": final_answer}

    def _route_after_agent(self, state: AgentState) -> str:
        last_message = state["messages"][-1]
        tool_calls = getattr(last_message, "tool_calls", None) or []
        return "tools" if tool_calls else "finalize"

    @staticmethod
    def _history_to_messages(history: list[Conversation]) -> list[BaseMessage]:
        messages: list[BaseMessage] = []
        for turn in history:
            messages.append(HumanMessage(content=turn.question))
            messages.append(AIMessage(content=turn.answer))
        return messages

    @staticmethod
    def _to_tool_call(raw_tool_call: dict[str, Any]) -> ToolCall:
        args = raw_tool_call.get("args") or raw_tool_call.get("arguments") or {}
        if not isinstance(args, dict):
            args = {}
        return ToolCall(
            id=str(raw_tool_call.get("id") or raw_tool_call.get("name") or "tool_call"),
            name=str(raw_tool_call.get("name") or ""),
            arguments=args,
        )

    @staticmethod
    def _new_reference_mappings(
        existing: dict[str, dict[str, object]],
        result: ToolResult,
    ) -> dict[str, dict[str, object]]:
        merged: dict[str, dict[str, object]] = {}
        for key, value in result.reference_mappings.items():
            if key not in existing:
                merged[key] = value
        return merged

    @staticmethod
    def _limit_tool_result(result: ToolResult) -> str:
        content = result.content
        if len(content) > MAX_TOOL_RESULT_CHARS:
            content = content[:MAX_TOOL_RESULT_CHARS] + "..."
        return content
