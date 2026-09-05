from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.message import Message


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, message: Message) -> None:
        self.session.add(message)

    async def get_latest(self, conversation_id: UUID) -> Optional[Message]:
        result = await self.session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id, Message.deleted_at.is_(None))
            .options(joinedload(Message.sender))
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def page_before(
        self,
        conversation_id: UUID,
        limit: int,
        before_created_at: Optional[datetime] = None,
        before_id: Optional[UUID] = None,
    ) -> list[Message]:
        statement = (
            select(Message)
            .where(Message.conversation_id == conversation_id, Message.deleted_at.is_(None))
            .options(joinedload(Message.sender))
        )
        if before_created_at is not None and before_id is not None:
            statement = statement.where(
                or_(
                    Message.created_at < before_created_at,
                    and_(Message.created_at == before_created_at, Message.id < before_id),
                )
            )
        result = await self.session.execute(
            statement.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit + 1)
        )
        return list(result.scalars().all())

