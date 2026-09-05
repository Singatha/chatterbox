import base64
import binascii
import json
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.message import Message
from app.repositories.message_repository import MessageRepository
from app.schemas.message import MessagePage, MessageResponse
from app.services.conversation_service import ConversationService


def encode_cursor(message: Message) -> str:
    payload = json.dumps({"created_at": message.created_at.isoformat(), "id": str(message.id)})
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        return datetime.fromisoformat(payload["created_at"]), UUID(payload["id"])
    except (
        binascii.Error,
        UnicodeDecodeError,
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
    ) as exc:
        raise AppError(422, "INVALID_CURSOR", "Message cursor is invalid") from exc


class MessageService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.messages = MessageRepository(session)
        self.conversation_service = ConversationService(session)

    async def create(
        self, conversation_id: UUID, sender_id: UUID, content: str
    ) -> MessageResponse:
        conversation = await self.conversation_service.get_authorized(conversation_id, sender_id)
        message = Message(
            conversation_id=conversation_id,
            sender_id=sender_id,
            content=content,
        )
        self.messages.add(message)
        await self.session.flush()
        await self.conversation_service.touch(conversation)
        await self.session.commit()
        await self.session.refresh(message, attribute_names=["sender"])
        return self._to_response(message)

    async def list(
        self,
        conversation_id: UUID,
        current_user_id: UUID,
        limit: int,
        before: Optional[str],
        after: Optional[str] = None,
    ) -> MessagePage:
        await self.conversation_service.get_authorized(conversation_id, current_user_id)
        if before and after:
            raise AppError(422, "INVALID_CURSOR", "Use either before or after, not both")
        before_created_at = None
        before_id = None
        if after:
            after_created_at, after_id = decode_cursor(after)
            records = await self.messages.page_after(
                conversation_id, limit, after_created_at, after_id
            )
            has_more = len(records) > limit
            records = records[:limit]
            next_cursor = encode_cursor(records[-1]) if has_more and records else None
            return MessagePage(
                items=[self._to_response(message) for message in records],
                next_cursor=next_cursor,
            )
        if before:
            before_created_at, before_id = decode_cursor(before)
        records = await self.messages.page_before(
            conversation_id, limit, before_created_at, before_id
        )
        has_more = len(records) > limit
        records = records[:limit]
        next_cursor = encode_cursor(records[-1]) if has_more and records else None
        records.reverse()
        return MessagePage(
            items=[self._to_response(message) for message in records],
            next_cursor=next_cursor,
        )

    @staticmethod
    def _to_response(message: Message) -> MessageResponse:
        return MessageResponse(
            id=message.id,
            conversation_id=message.conversation_id,
            sender_id=message.sender_id,
            sender_username=message.sender.username,
            content=message.content,
            created_at=message.created_at,
            edited_at=message.edited_at,
            cursor=encode_cursor(message),
        )
