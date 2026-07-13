import base64
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import settings


def hash_password(raw_password: str) -> str:
    password_bytes = raw_password.encode("utf-8")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(raw_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(raw_password.encode("utf-8"), hashed_password.encode("utf-8"))


def _jwt_secret() -> bytes | str:
    secret = settings.jwt_secret
    try:
        decoded = base64.b64decode(secret, validate=True)
    except Exception:
        return secret
    return decoded if decoded else secret


def create_access_token(user: Any) -> str:
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=settings.access_token_expire_seconds)
    payload: dict[str, Any] = {
        "tokenId": uuid.uuid4().hex,
        "role": user.role,
        "userId": str(user.id),
        "sub": user.username,
        "exp": expires_at,
        "iat": now,
    }
    if user.org_tags:
        payload["orgTags"] = user.org_tags
    if user.primary_org:
        payload["primaryOrg"] = user.primary_org
    return jwt.encode(payload, _jwt_secret(), algorithm=settings.jwt_algorithm)


def create_refresh_token(user: Any) -> str:
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=settings.refresh_token_expire_seconds)
    payload: dict[str, Any] = {
        "refreshTokenId": uuid.uuid4().hex,
        "userId": str(user.id),
        "type": "refresh",
        "sub": user.username,
        "exp": expires_at,
        "iat": now,
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, _jwt_secret(), algorithms=[settings.jwt_algorithm])


def now_millis() -> int:
    return int(time.time() * 1000)
