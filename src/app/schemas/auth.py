from datetime import datetime

from pydantic import BaseModel, Field


class UserCredentials(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class RefreshTokenRequest(BaseModel):
    refreshToken: str


class TokenPair(BaseModel):
    token: str
    refreshToken: str


class CurrentUserResponse(BaseModel):
    id: int
    username: str
    role: str
    orgTags: list[str]
    primaryOrg: str | None = None
    createdAt: datetime | None = None
    updatedAt: datetime | None = None
