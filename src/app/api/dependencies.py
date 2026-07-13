from typing import Annotated

from fastapi import Depends, Header
from jwt import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responses import ApiError
from app.core.database import get_session
from app.core.security import decode_token
from app.models.user import User
from app.services.auth_service import AuthService

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_auth_service(session: SessionDep) -> AuthService:
    return AuthService(session)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


async def get_current_user(
    auth_service: AuthServiceDep,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise ApiError(401, "Invalid token")
    try:
        payload = decode_token(authorization.replace("Bearer ", "", 1))
    except InvalidTokenError:
        raise ApiError(401, "Invalid token")
    username = payload.get("sub")
    if not username:
        raise ApiError(401, "Invalid token")
    user = await auth_service.get_user_by_username(str(username))
    if user is None:
        raise ApiError(404, "User not found")
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]
