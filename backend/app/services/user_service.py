from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserPublicResponse


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.users = UserRepository(session)

    async def search(
        self, query: str, current_user_id: UUID, limit: int
    ) -> list[UserPublicResponse]:
        users = await self.users.search(query, current_user_id, limit)
        return [UserPublicResponse.model_validate(user) for user in users]

    async def get(self, user_id: UUID) -> UserPublicResponse:
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise AppError(404, "USER_NOT_FOUND", "User was not found")
        return UserPublicResponse.model_validate(user)
