from fastapi import APIRouter

from app.api.dependencies import AuthServiceDep, CurrentUserDep
from app.api.responses import error, ok
from app.schemas.auth import UserCredentials
from app.services.auth_service import AuthError

router = APIRouter()


@router.post("/login")
async def login(payload: UserCredentials, auth_service: AuthServiceDep) -> dict[str, object]:
    try:
        tokens = await auth_service.login(payload.username, payload.password)
    except AuthError as exception:
        return error(exception.status_code, exception.message)
    return ok("Login successful", tokens)


@router.post("/register")
async def register(payload: UserCredentials, auth_service: AuthServiceDep) -> dict[str, object]:
    try:
        await auth_service.register(payload.username, payload.password)
    except AuthError as exception:
        return error(exception.status_code, exception.message)
    return {"code": 200, "message": "User registered successfully"}


@router.get("/me")
async def get_current_user(current_user: CurrentUserDep, auth_service: AuthServiceDep) -> dict[str, object]:
    return ok(
        "Get user detail successful",
        auth_service.to_current_user_response(current_user).model_dump(by_alias=True),
    )


@router.post("/logout")
async def logout() -> dict[str, object]:
    return {"code": 200, "message": "Logout successful"}
