from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment import Attachment


class AttachmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, attachment: Attachment) -> None:
        self.session.add(attachment)

    async def get_by_id(self, attachment_id: UUID) -> Optional[Attachment]:
        return await self.session.get(Attachment, attachment_id)

    async def get_by_id_for_update(
        self, attachment_id: UUID
    ) -> Optional[Attachment]:
        result = await self.session.execute(
            select(Attachment)
            .where(Attachment.id == attachment_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def lock_for_message(self, attachment_ids: list[UUID]) -> list[Attachment]:
        if not attachment_ids:
            return []
        result = await self.session.execute(
            select(Attachment)
            .where(Attachment.id.in_(attachment_ids))
            .with_for_update()
        )
        return list(result.scalars().all())

    async def list_abandoned(self, cutoff: datetime, limit: int = 100) -> list[Attachment]:
        result = await self.session.execute(
            select(Attachment)
            .where(Attachment.message_id.is_(None), Attachment.created_at < cutoff)
            .order_by(Attachment.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(result.scalars().all())

    async def delete(self, attachment: Attachment) -> None:
        await self.session.delete(attachment)
