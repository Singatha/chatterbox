from __future__ import annotations

from typing import Annotated, Optional

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import AppError
from app.core.security import InvalidTokenError, decode_token
from app.models.user import User
from app.repositories.user_repository import UserRepository

DbSession = Annotated[AsyncSession, Depends(get_db)]
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    session: DbSession,
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer_scheme)],
) -> User:
    if credentials is None:
        raise AppError(401, "AUTHENTICATION_REQUIRED", "Authentication is required")
    try:
        payload = decode_token(credentials.credentials, "access")
    except InvalidTokenError as exc:
        raise AppError(401, "INVALID_ACCESS_TOKEN", "Access token is invalid or expired") from exc

    user = await UserRepository(session).get_by_id(payload.subject)
    if user is None:
        raise AppError(401, "INVALID_ACCESS_TOKEN", "Access token is invalid or expired")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
