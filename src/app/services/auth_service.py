import re

from jwt import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.models.organization_tag import OrganizationTag
from app.repositories.organization_tag_repository import OrganizationTagRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import CurrentUserResponse


class AuthError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class AuthService:
    default_org_tag = "DEFAULT"
    private_tag_prefix = "PRIVATE_"
    password_pattern = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{6,18}$")

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.organization_tags = OrganizationTagRepository(session)

    async def register(self, username: str, password: str) -> None:
        normalized_username = username.strip()
        if not normalized_username or not password:
            raise AuthError(400, "Username and password cannot be empty")
        self._validate_password(password)
        if await self.users.find_by_username(normalized_username):
            raise AuthError(400, "Username already exists")

        private_org = f"{self.private_tag_prefix}{normalized_username}"
        user = User(
            username=normalized_username,
            password=hash_password(password),
            role="USER",
            org_tags=",".join([self.default_org_tag, private_org]),
            primary_org=private_org,
        )
        await self.users.save(user)
        await self._ensure_registration_org_tags(user, private_org)
        await self.session.commit()

    async def login(self, username: str, password: str) -> dict[str, str]:
        if not username or not password:
            raise AuthError(400, "Username and password cannot be empty")
        user = await self.users.find_by_username(username.strip())
        if user is None or not verify_password(password, user.password):
            raise AuthError(401, "Invalid credentials")
        return {
            "token": create_access_token(user),
            "refreshToken": create_refresh_token(user),
        }

    async def refresh_token(self, refresh_token: str) -> dict[str, str]:
        if not refresh_token:
            raise AuthError(400, "Refresh token cannot be empty")
        try:
            payload = decode_token(refresh_token)
        except InvalidTokenError:
            raise AuthError(401, "Invalid refresh token") from None
        if payload.get("type") != "refresh":
            raise AuthError(401, "Invalid refresh token")
        username = payload.get("sub")
        if not username:
            raise AuthError(401, "Cannot extract username from refresh token")
        user = await self.users.find_by_username(str(username))
        if user is None:
            raise AuthError(404, "User not found")
        return {
            "token": create_access_token(user),
            "refreshToken": create_refresh_token(user),
        }

    async def get_user_by_username(self, username: str) -> User | None:
        return await self.users.find_by_username(username)

    def to_current_user_response(self, user: User) -> CurrentUserResponse:
        return CurrentUserResponse(
            id=user.id,
            username=user.username,
            role=user.role,
            orgTags=user.org_tag_list,
            primaryOrg=user.primary_org,
            createdAt=user.created_at,
            updatedAt=user.updated_at,
        )

    def _validate_password(self, password: str) -> None:
        if not self.password_pattern.match(password):
            raise AuthError(400, "Password must be 6-18 chars and contain letters and numbers")
        if len(password.encode("utf-8")) > 72:
            raise AuthError(400, "Password cannot be longer than 72 bytes")

    async def _ensure_registration_org_tags(self, user: User, private_org: str) -> None:
        if not await self.organization_tags.exists_by_tag_id(self.default_org_tag):
            await self.organization_tags.save(
                OrganizationTag(
                    tag_id=self.default_org_tag,
                    name="默认组织",
                    description="系统默认组织标签，自动分配给所有新用户",
                    parent_tag=None,
                    upload_max_size_bytes=None,
                    created_by=user.id,
                )
            )
        if not await self.organization_tags.exists_by_tag_id(private_org):
            await self.organization_tags.save(
                OrganizationTag(
                    tag_id=private_org,
                    name=f"{user.username}的私人空间",
                    description="用户的私人组织标签，仅用户本人可访问",
                    parent_tag=None,
                    upload_max_size_bytes=None,
                    created_by=user.id,
                )
            )
