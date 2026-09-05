from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.dependencies import CurrentUser, DbSession
from app.schemas.user import UserPublicResponse
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserPublicResponse])
async def search_users(
    session: DbSession,
    current_user: CurrentUser,
    q: Annotated[str, Query(max_length=64)] = "",
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[UserPublicResponse]:
    return await UserService(session).search(q, current_user.id, limit)


@router.get("/{user_id}", response_model=UserPublicResponse)
async def get_user(
    user_id: UUID, session: DbSession, _: CurrentUser
) -> UserPublicResponse:
    return await UserService(session).get(user_id)

