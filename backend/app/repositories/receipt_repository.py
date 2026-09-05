from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.message import Message
from app.models.message_receipt import MessageReceipt


class ReceiptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def mark_delivered(
        self, message_id: UUID, user_ids: list[UUID]
    ) -> list[MessageReceipt]:
        if not user_ids:
            return []
        result = await self.session.execute(
            select(MessageReceipt)
            .where(
                MessageReceipt.message_id == message_id,
                MessageReceipt.user_id.in_(user_ids),
                MessageReceipt.delivered_at.is_(None),
            )
            .options(joinedload(MessageReceipt.message))
        )
        receipts = list(result.scalars().all())
        now = datetime.now(timezone.utc)
        for receipt in receipts:
            receipt.delivered_at = now
        return receipts

    async def mark_pending_delivered(self, user_id: UUID) -> list[MessageReceipt]:
        result = await self.session.execute(
            select(MessageReceipt)
            .where(
                MessageReceipt.user_id == user_id,
                MessageReceipt.delivered_at.is_(None),
            )
            .options(joinedload(MessageReceipt.message))
        )
        receipts = list(result.scalars().all())
        now = datetime.now(timezone.utc)
        for receipt in receipts:
            receipt.delivered_at = now
        return receipts

    async def mark_read_through(
        self,
        conversation_id: UUID,
        user_id: UUID,
        target_created_at: datetime,
        target_id: UUID,
    ) -> list[MessageReceipt]:
        result = await self.session.execute(
            select(MessageReceipt)
            .join(Message, Message.id == MessageReceipt.message_id)
            .where(
                Message.conversation_id == conversation_id,
                MessageReceipt.user_id == user_id,
                MessageReceipt.read_at.is_(None),
                or_(
                    Message.created_at < target_created_at,
                    and_(Message.created_at == target_created_at, Message.id <= target_id),
                ),
            )
            .options(joinedload(MessageReceipt.message))
        )
        receipts = list(result.scalars().all())
        now = datetime.now(timezone.utc)
        for receipt in receipts:
            receipt.delivered_at = receipt.delivered_at or now
            receipt.read_at = now
        return receipts

