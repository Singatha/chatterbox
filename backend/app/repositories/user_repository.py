from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        return await self.session.get(User, user_id)

    async def get_by_email_or_username(self, value: str) -> Optional[User]:
        normalized = value.lower()
        result = await self.session.execute(
            select(User).where(or_(User.email == normalized, User.username == normalized))
        )
        return result.scalar_one_or_none()

    async def email_or_username_exists(self, email: str, username: str) -> bool:
        result = await self.session.execute(
            select(User.id).where(or_(User.email == email, User.username == username)).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def search(self, query: str, exclude_user_id: UUID, limit: int) -> list[User]:
        normalized = query.strip().lower()
        statement = select(User).where(User.id != exclude_user_id)
        if normalized:
            statement = statement.where(
                or_(
                    User.username.contains(normalized, autoescape=True),
                    User.email.contains(normalized, autoescape=True),
                )
            )
        result = await self.session.execute(statement.order_by(User.username).limit(limit))
        return list(result.scalars().all())

    def add(self, user: User) -> None:
        self.session.add(user)
