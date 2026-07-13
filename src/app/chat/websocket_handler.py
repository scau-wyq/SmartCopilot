import json
from dataclasses import dataclass
from uuid import uuid4

from fastapi import APIRouter, WebSocket
from jwt import InvalidTokenError
from starlette.websockets import WebSocketDisconnect
from uvicorn.protocols.utils import ClientDisconnected

from app.agents.agent_service import AgentService
from app.api.routes.chat import INTERNAL_CMD_TOKEN
from app.chat.generation_state import generation_state_store
from app.core.database import AsyncSessionLocal
from app.core.security import decode_token, now_millis
from app.memory.service import MemoryService
from app.models.user import User
from app.services.auth_service import AuthService
from app.services.billing_service import BillingService
from app.services.conversation_service import ConversationService
from app.services.model_preference_service import ChatModelConfig, ModelPreferenceService

router = APIRouter()

HEARTBEAT_PING = "__chat_ping__"
HEARTBEAT_PONG = "__chat_pong__"


@dataclass(frozen=True)
class ChatRequest:
    question: str
    model_mode: str | None = None


@router.websocket("/chat/{token}")
async def chat_websocket(websocket: WebSocket, token: str) -> None:
    try:
        payload = decode_token(token)
    except InvalidTokenError:
        await websocket.close(code=1008)
        return

    user_id = str(payload.get("userId") or "")
    username = payload.get("sub")
    if not user_id or not username:
        await websocket.close(code=1008)
        return

    async with AsyncSessionLocal() as session:
        user = await AuthService(session).get_user_by_username(str(username))
    if user is None or str(user.id) != user_id:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    session_id = str(uuid4())
    if not await _safe_send_json(
        websocket,
        {
            "type": "connection",
            "sessionId": session_id,
            "message": "WebSocket connection established",
        },
    ):
        return

    try:
        while True:
            message = await websocket.receive_text()
            if message == HEARTBEAT_PING:
                if not await _safe_send_text(websocket, HEARTBEAT_PONG):
                    return
                continue
            if await _handle_control_message(websocket, user_id, message):
                continue
            await _stream_llm_response(websocket, user, _parse_chat_request(message))
    except WebSocketDisconnect:
        return


async def _handle_control_message(websocket: WebSocket, user_id: str, message: str) -> bool:
    stripped = message.strip()
    if not stripped.startswith("{"):
        return False
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return False
    if payload.get("type") != "stop" or payload.get("_internal_cmd_token") != INTERNAL_CMD_TOKEN:
        return False

    generation_id = payload.get("generationId")
    snapshot = None
    if isinstance(generation_id, str) and generation_id:
        snapshot = await generation_state_store.get_for_user(generation_id, user_id)
    if snapshot is None:
        snapshot = await generation_state_store.get_active_for_user(user_id)
    if snapshot is None:
        return True

    await generation_state_store.mark_cancelled(snapshot.generation_id)
    await _safe_send_json(
        websocket,
        {
            "type": "stop",
            "generationId": snapshot.generation_id,
            "message": "Response stopped",
            "timestamp": now_millis(),
        },
    )
    return True


async def _stream_llm_response(websocket: WebSocket, user: User, request: ChatRequest) -> None:
    user_id = str(user.id)
    question = request.question
    try:
        async with AsyncSessionLocal() as session:
            conversation_id = await ConversationService(session).ensure_current_session(int(user_id))
            model_config = await ModelPreferenceService(session).resolve_chat_model(user, request.model_mode)
            if model_config.billable:
                await BillingService(session).ensure_enough(int(user_id), "LLM", 1)
            await session.commit()
    except Exception as exception:
        await _safe_send_json(
            websocket,
            {
                "type": "error",
                "code": getattr(exception, "status_code", 500),
                "error": str(exception),
                "message": getattr(exception, "message", str(exception)),
                "timestamp": now_millis(),
            },
        )
        return

    snapshot = await generation_state_store.create(
        user_id=user_id,
        question=question,
        conversation_id=conversation_id,
    )
    if not await _safe_send_json(
        websocket,
        {
            "type": "start",
            "generationId": snapshot.generation_id,
            "conversationId": snapshot.conversation_id,
            "modelMode": model_config.mode,
            "timestamp": now_millis(),
        },
    ):
        return

    try:
        reference_mappings: dict[str, dict[str, object]] = {}
        tool_events: list[dict[str, object]] = []
        async with AsyncSessionLocal() as agent_session:
            agent = AgentService(agent_session, user, model_config)
            async for event in agent.stream_answer(question, snapshot.conversation_id):
                active = await generation_state_store.get_for_user(snapshot.generation_id, user_id)
                if active is None or active.status != "STREAMING":
                    return
                if event.type == "tool" and event.tool_event is not None:
                    payload = event.tool_event.to_api_dict()
                    tool_events.append(payload)
                    if not await _safe_send_json(
                        websocket,
                        {
                            "type": "tool_call",
                            "generationId": snapshot.generation_id,
                            "conversationId": snapshot.conversation_id,
                            "toolCallId": payload.get("id"),
                            "tool": payload.get("tool"),
                            "status": payload.get("status"),
                            "timestamp": payload.get("timestamp"),
                        },
                    ):
                        return
                    continue

                chunk = event.chunk
                if not chunk:
                    continue
                await generation_state_store.append_chunk(snapshot.generation_id, chunk)
                if not await _safe_send_json(
                    websocket,
                    {
                        "type": "chunk",
                        "generationId": snapshot.generation_id,
                        "conversationId": snapshot.conversation_id,
                        "chunk": chunk,
                    },
                ):
                    return

            reference_mappings = agent.reference_mappings

        active = await generation_state_store.get_for_user(snapshot.generation_id, user_id)
        if active is not None and reference_mappings and not _has_reference_citation(active.content):
            footer = _build_reference_footer(reference_mappings)
            if footer:
                await generation_state_store.append_chunk(snapshot.generation_id, footer)
                if not await _safe_send_json(
                    websocket,
                    {
                        "type": "chunk",
                        "generationId": snapshot.generation_id,
                        "conversationId": snapshot.conversation_id,
                        "chunk": footer,
                    },
                ):
                    return
        if reference_mappings:
            await generation_state_store.set_reference_mappings(snapshot.generation_id, reference_mappings)

        await generation_state_store.mark_completed(snapshot.generation_id)
        completed_snapshot = await generation_state_store.get_for_user(snapshot.generation_id, user_id)
        answer = completed_snapshot.content if completed_snapshot else ""
        used_tokens = _estimate_llm_tokens(question, answer) if model_config.billable else 0
        async with AsyncSessionLocal() as session:
            await ConversationService(session).record_turn(
                user_id=int(user_id),
                question=question,
                answer=answer,
                conversation_id=snapshot.conversation_id,
                reference_mappings=reference_mappings,
            )
            if model_config.billable:
                await _consume_billable_llm_tokens(session, model_config, int(user_id), used_tokens, snapshot.conversation_id)
        MemoryService.schedule_extraction(
            user_id=int(user_id),
            conversation_id=snapshot.conversation_id,
            question=question,
            answer=answer,
            model_config=model_config,
        )
        await _safe_send_json(
            websocket,
            {
                "type": "completion",
                "generationId": snapshot.generation_id,
                "conversationId": snapshot.conversation_id,
                "status": "finished",
                "message": "Response completed",
                "referenceMappings": reference_mappings,
                "toolEvents": tool_events,
                "modelMode": model_config.mode,
                "usedTokens": used_tokens,
                "timestamp": now_millis(),
            },
        )
    except Exception as exception:
        await generation_state_store.mark_failed(snapshot.generation_id, str(exception))
        await _safe_send_json(
            websocket,
            {
                "type": "error",
                "generationId": snapshot.generation_id,
                "error": str(exception) or "AI service is temporarily unavailable. Please try again later.",
            },
        )


async def _safe_send_json(websocket: WebSocket, payload: dict[str, object]) -> bool:
    try:
        await websocket.send_json(payload)
    except (ClientDisconnected, WebSocketDisconnect, RuntimeError):
        return False
    return True


async def _safe_send_text(websocket: WebSocket, text: str) -> bool:
    try:
        await websocket.send_text(text)
    except (ClientDisconnected, WebSocketDisconnect, RuntimeError):
        return False
    return True


async def _consume_billable_llm_tokens(
    session,
    model_config: ChatModelConfig,
    user_id: int,
    used_tokens: int,
    conversation_id: str,
) -> None:
    if not model_config.billable:
        return
    await BillingService(session).consume_tokens(
        user_id=user_id,
        token_type="LLM",
        amount=used_tokens,
        reason="计费模型聊天消耗",
        remark=conversation_id,
    )


def _parse_chat_request(message: str) -> ChatRequest:
    stripped = message.strip()
    if not stripped.startswith("{"):
        return ChatRequest(question=message)
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return ChatRequest(question=message)
    if payload.get("type") and payload.get("type") != "chat":
        return ChatRequest(question=message)
    question = payload.get("message") or payload.get("question") or ""
    if not isinstance(question, str) or not question.strip():
        return ChatRequest(question=message)
    model_mode = payload.get("modelMode")
    return ChatRequest(question=question, model_mode=model_mode if isinstance(model_mode, str) else None)


def _estimate_llm_tokens(question: str, answer: str) -> int:
    return max(1, (len(question) + len(answer)) // 4)


def _has_reference_citation(content: str) -> bool:
    return "来源#" in content


def _build_reference_footer(reference_mappings: dict[str, dict[str, object]]) -> str:
    lines = []
    for key in sorted(reference_mappings, key=lambda value: int(value) if value.isdigit() else value):
        item = reference_mappings[key]
        file_name = str(item.get("fileName") or item.get("fileMd5") or "未知文件")
        page_number = item.get("pageNumber")
        if page_number:
            lines.append(f"- 来源#{key}: {file_name} | 第{page_number}页")
        else:
            lines.append(f"- 来源#{key}: {file_name}")
    if not lines:
        return ""
    return "\n\n参考来源：\n" + "\n".join(lines)
