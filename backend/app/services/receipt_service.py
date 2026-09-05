from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.repositories.message_repository import MessageRepository
from app.repositories.receipt_repository import ReceiptRepository
from app.schemas.receipt import ReceiptEventData
from app.services.conversation_service import ConversationService


class ReceiptService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.receipts = ReceiptRepository(session)
        self.messages = MessageRepository(session)
        self.conversations = ConversationService(session)

    async def mark_delivered(
        self, message_id: UUID, user_ids: list[UUID]
    ) -> list[ReceiptEventData]:
        receipts = await self.receipts.mark_delivered(message_id, user_ids)
        await self.session.commit()
        return [self._to_event(receipt) for receipt in receipts]

    async def mark_pending_delivered(self, user_id: UUID) -> list[ReceiptEventData]:
        receipts = await self.receipts.mark_pending_delivered(user_id)
        await self.session.commit()
        return [self._to_event(receipt) for receipt in receipts]

    async def mark_read(
        self, conversation_id: UUID, message_id: UUID, user_id: UUID
    ) -> list[ReceiptEventData]:
        await self.conversations.get_authorized(conversation_id, user_id)
        target = await self.messages.get_by_id(message_id)
        if target is None or target.conversation_id != conversation_id:
            raise AppError(404, "MESSAGE_NOT_FOUND", "Message was not found")
        receipts = await self.receipts.mark_read_through(
            conversation_id, user_id, target.created_at, target.id
        )
        await self.session.commit()
        receipts.sort(key=lambda receipt: (receipt.message.created_at, receipt.message_id))
        return [self._to_event(receipt) for receipt in receipts]

    @staticmethod
    def _to_event(receipt) -> ReceiptEventData:  # type: ignore[no-untyped-def]
        return ReceiptEventData(
            message_id=receipt.message_id,
            conversation_id=receipt.message.conversation_id,
            user_id=receipt.user_id,
            delivered_at=receipt.delivered_at,
            read_at=receipt.read_at,
        )
