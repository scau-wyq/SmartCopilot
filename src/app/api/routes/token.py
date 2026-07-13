from fastapi import APIRouter

from app.api.dependencies import AuthServiceDep
from app.api.responses import error, ok
from app.schemas.auth import RefreshTokenRequest
from app.services.auth_service import AuthError

router = APIRouter()


@router.post("/refreshToken")
async def refresh_token(payload: RefreshTokenRequest, auth_service: AuthServiceDep) -> dict[str, object]:
    try:
        tokens = await auth_service.refresh_token(payload.refreshToken)
    except AuthError as exception:
        return error(exception.status_code, exception.message)
    return ok("Token refreshed successfully", tokens)
