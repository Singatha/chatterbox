import logging
from typing import Union
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import AsyncSessionLocal
from app.core.errors import AppError
from app.repositories.conversation_repository import ConversationRepository
from app.services.message_service import MessageService
from app.services.receipt_service import ReceiptService
from app.websocket.events import (
    ErrorDetail,
    ErrorEvent,
    MessageCreatedEvent,
    MessageDeliveredEvent,
    MessageReadEvent,
    MessageReadRequest,
    MessageSendEvent,
    TypingEventData,
    TypingStartedEvent,
    TypingStartEvent,
    TypingStopEvent,
    TypingStoppedEvent,
    client_event_adapter,
)
from app.websocket.manager import ConnectionManager, TypingTracker, typing_tracker

logger = logging.getLogger(__name__)


async def handle_message_send(
    event: MessageSendEvent,
    user_id: UUID,
    manager: ConnectionManager,
    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
) -> None:
    async with session_factory() as session:
        message = await MessageService(session).create(
            event.conversation_id, user_id, event.content
        )
        member_ids = await ConversationRepository(session).member_ids(event.conversation_id)
    outgoing = MessageCreatedEvent(
        request_id=event.request_id, data=message
    ).model_dump(mode="json")
    await manager.send_to_users(member_ids, outgoing)

    recipient_ids = [member_id for member_id in member_ids if member_id != user_id]
    online_recipient_ids = await manager.online_user_ids(recipient_ids)
    if not online_recipient_ids:
        return
    async with session_factory() as session:
        receipts = await ReceiptService(session).mark_delivered(message.id, online_recipient_ids)
    for receipt in receipts:
        await manager.send_to_users(
            member_ids,
            MessageDeliveredEvent(data=receipt).model_dump(mode="json"),
        )


async def handle_message_read(
    event: MessageReadRequest,
    user_id: UUID,
    manager: ConnectionManager,
    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
) -> None:
    async with session_factory() as session:
        receipts = await ReceiptService(session).mark_read(
            event.conversation_id, event.message_id, user_id
        )
        member_ids = await ConversationRepository(session).member_ids(event.conversation_id)
    for receipt in receipts:
        await manager.send_to_users(
            member_ids,
            MessageReadEvent(request_id=event.request_id, data=receipt).model_dump(mode="json"),
        )


async def handle_typing(
    event: Union[TypingStartEvent, TypingStopEvent],
    user_id: UUID,
    manager: ConnectionManager,
    tracker: TypingTracker = typing_tracker,
    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
) -> None:
    async with session_factory() as session:
        if not await ConversationRepository(session).is_member(event.conversation_id, user_id):
            raise AppError(403, "CONVERSATION_FORBIDDEN", "You are not a conversation member")
        member_ids = await ConversationRepository(session).member_ids(event.conversation_id)

    data = TypingEventData(conversation_id=event.conversation_id, user_id=user_id)
    if isinstance(event, TypingStartEvent):
        stopped_event = TypingStoppedEvent(data=data).model_dump(mode="json")

        async def expire() -> None:
            await manager.send_to_users(member_ids, stopped_event, exclude_user_id=user_id)

        await tracker.start(event.conversation_id, user_id, expire)
        outgoing = TypingStartedEvent(data=data).model_dump(mode="json")
    else:
        await tracker.stop(event.conversation_id, user_id)
        outgoing = TypingStoppedEvent(data=data).model_dump(mode="json")
    await manager.send_to_users(member_ids, outgoing, exclude_user_id=user_id)


async def dispatch_event(
    payload: object,
    user_id: UUID,
    manager: ConnectionManager,
    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
    tracker: TypingTracker = typing_tracker,
) -> None:
    request_id = payload.get("request_id") if isinstance(payload, dict) else None
    try:
        event = client_event_adapter.validate_python(payload)
        if isinstance(event, MessageSendEvent):
            await handle_message_send(event, user_id, manager, session_factory)
        elif isinstance(event, MessageReadRequest):
            await handle_message_read(event, user_id, manager, session_factory)
        elif isinstance(event, (TypingStartEvent, TypingStopEvent)):
            await handle_typing(event, user_id, manager, tracker, session_factory)
    except ValidationError:
        await manager.send_to_user(
            user_id,
            ErrorEvent(
                request_id=request_id if isinstance(request_id, str) else None,
                error=ErrorDetail(code="INVALID_EVENT", message="WebSocket event is invalid"),
            ).model_dump(mode="json"),
        )
    except AppError as exc:
        await manager.send_to_user(
            user_id,
            ErrorEvent(
                request_id=request_id if isinstance(request_id, str) else None,
                error=ErrorDetail(code=exc.code, message=exc.message),
            ).model_dump(mode="json"),
        )
    except Exception:
        logger.exception("Unexpected WebSocket event failure", extra={"user_id": str(user_id)})
        await manager.send_to_user(
            user_id,
            ErrorEvent(
                request_id=request_id if isinstance(request_id, str) else None,
                error=ErrorDetail(code="INTERNAL_ERROR", message="Event could not be processed"),
            ).model_dump(mode="json"),
        )
