from fastapi import APIRouter

from app.api.dependencies import CurrentUserDep
from app.api.responses import ok
from app.chat.generation_state import generation_state_store

router = APIRouter()

INTERNAL_CMD_TOKEN = "WSS_STOP_CMD_PY"


@router.get("/websocket-token")
async def get_websocket_token(_: CurrentUserDep) -> dict[str, object]:
    return ok("Get WebSocket stop command token successful", {"cmdToken": INTERNAL_CMD_TOKEN})


@router.get("/generation/{generation_id}")
async def get_generation(generation_id: str, current_user: CurrentUserDep) -> dict[str, object]:
    snapshot = await generation_state_store.get_for_user(generation_id, str(current_user.id))
    return ok("Get generation status successful", snapshot.to_api_dict() if snapshot else None)


@router.get("/active-generation")
async def get_active_generation(current_user: CurrentUserDep) -> dict[str, object]:
    snapshot = await generation_state_store.get_active_for_user(str(current_user.id))
    return ok("Get active generation status successful", snapshot.to_api_dict() if snapshot else None)
