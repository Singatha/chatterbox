from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.conversation import Conversation
from app.models.conversation_member import ConversationMember


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, conversation_id: UUID) -> Optional[Conversation]:
        result = await self.session.execute(
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .options(
                selectinload(Conversation.members).selectinload(ConversationMember.user)
            )
        )
        return result.scalar_one_or_none()

    async def get_direct_by_key(self, direct_key: str) -> Optional[Conversation]:
        result = await self.session.execute(
            select(Conversation)
            .where(Conversation.direct_key == direct_key)
            .options(
                selectinload(Conversation.members).selectinload(ConversationMember.user)
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: UUID) -> list[Conversation]:
        result = await self.session.execute(
            select(Conversation)
            .join(ConversationMember)
            .where(ConversationMember.user_id == user_id)
            .options(
                selectinload(Conversation.members).selectinload(ConversationMember.user)
            )
            .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        )
        return list(result.scalars().unique().all())

    async def is_member(self, conversation_id: UUID, user_id: UUID) -> bool:
        result = await self.session.execute(
            select(ConversationMember.user_id)
            .where(
                ConversationMember.conversation_id == conversation_id,
                ConversationMember.user_id == user_id,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def member_ids(self, conversation_id: UUID) -> list[UUID]:
        result = await self.session.execute(
            select(ConversationMember.user_id).where(
                ConversationMember.conversation_id == conversation_id
            )
        )
        return list(result.scalars().all())

    def add(self, conversation: Conversation) -> None:
        self.session.add(conversation)
