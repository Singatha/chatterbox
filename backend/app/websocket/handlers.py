import logging
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import AsyncSessionLocal
from app.core.errors import AppError
from app.repositories.conversation_repository import ConversationRepository
from app.services.message_service import MessageService
from app.websocket.events import (
    ErrorDetail,
    ErrorEvent,
    MessageCreatedEvent,
    MessageSendEvent,
    client_event_adapter,
)
from app.websocket.manager import ConnectionManager

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


async def dispatch_event(payload: object, user_id: UUID, manager: ConnectionManager) -> None:
    request_id = payload.get("request_id") if isinstance(payload, dict) else None
    try:
        event = client_event_adapter.validate_python(payload)
        if isinstance(event, MessageSendEvent):
            await handle_message_send(event, user_id, manager)
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
