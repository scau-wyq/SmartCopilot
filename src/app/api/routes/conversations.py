from fastapi import APIRouter

from app.api.dependencies import CurrentUserDep, SessionDep
from app.api.responses import ApiError, ok
from app.services.conversation_service import ConversationService, parse_optional_datetime

router = APIRouter()


@router.get("/conversation")
async def get_conversations(
    current_user: CurrentUserDep,
    session: SessionDep,
    start_date: str | None = None,
    end_date: str | None = None,
    conversationId: str | None = None,
) -> dict[str, object]:
    try:
        messages = await ConversationService(session).get_message_history(
            user_id=current_user.id,
            start_date=parse_optional_datetime(start_date),
            end_date=parse_optional_datetime(end_date, is_end=True),
            conversation_id=conversationId,
        )
    except ValueError as exception:
        raise ApiError(400, str(exception))
    return ok("Get conversation history successful", messages)


@router.get("/conversations")
async def list_conversation_sessions(
    current_user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    sessions = await ConversationService(session).list_sessions(current_user.id)
    return ok("Get conversation sessions successful", sessions)


@router.post("/conversations")
async def create_conversation_session(
    current_user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    conversation_session = await ConversationService(session).create_session(current_user.id)
    return ok("Create conversation session successful", conversation_session)


@router.put("/conversations/{conversation_id}/switch")
async def switch_conversation_session(
    conversation_id: str,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    try:
        await ConversationService(session).switch_current_conversation(current_user.id, conversation_id)
    except ValueError:
        raise ApiError(404, "Conversation not found")
    return ok("Switch conversation successful")


@router.put("/conversations/{conversation_id}/archive")
async def archive_conversation_session(
    conversation_id: str,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    try:
        await ConversationService(session).archive_session(current_user.id, conversation_id)
    except ValueError:
        raise ApiError(404, "Conversation not found")
    return ok("Archive conversation successful")


@router.put("/conversations/{conversation_id}/unarchive")
async def unarchive_conversation_session(
    conversation_id: str,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    try:
        await ConversationService(session).unarchive_session(current_user.id, conversation_id)
    except ValueError:
        raise ApiError(404, "Conversation not found")
    return ok("Unarchive conversation successful")
