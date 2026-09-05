from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

password_hash = PasswordHash.recommended()


class InvalidTokenError(Exception):
    pass


@dataclass(frozen=True)
class TokenPayload:
    subject: UUID
    token_type: Literal["access", "refresh"]
    jti: UUID
    expires_at: datetime


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def _create_token(
    subject: UUID, token_type: str, lifetime: timedelta
) -> tuple[str, UUID, datetime]:
    now = datetime.now(timezone.utc)
    expires_at = now + lifetime
    jti = uuid4()
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "jti": str(jti),
        "iat": now,
        "exp": expires_at,
    }
    encoded = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return encoded, jti, expires_at


def create_access_token(subject: UUID) -> str:
    token, _, _ = _create_token(
        subject, "access", timedelta(minutes=settings.access_token_expire_minutes)
    )
    return token


def create_refresh_token(subject: UUID) -> tuple[str, UUID, datetime]:
    return _create_token(subject, "refresh", timedelta(days=settings.refresh_token_expire_days))


def decode_token(token: str, expected_type: Literal["access", "refresh"]) -> TokenPayload:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != expected_type:
            raise InvalidTokenError("Unexpected token type")
        return TokenPayload(
            subject=UUID(payload["sub"]),
            token_type=expected_type,
            jti=UUID(payload["jti"]),
            expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
        )
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise InvalidTokenError("Invalid or expired token") from exc
