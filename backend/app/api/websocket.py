import json
import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import get_session_factory
from app.models.user import User
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.user_repository import UserRepository
from app.services.receipt_service import ReceiptService
from app.websocket.auth import get_websocket_user
from app.websocket.events import (
    ConnectionReadyData,
    ConnectionReadyEvent,
    ErrorDetail,
    ErrorEvent,
    MessageDeliveredEvent,
    PresenceOfflineData,
    PresenceOfflineEvent,
    PresenceOnlineData,
    PresenceOnlineEvent,
)
from app.websocket.handlers import dispatch_event
from app.websocket.manager import manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    current_user: Annotated[User, Depends(get_websocket_user)],
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> None:
    became_online = await manager.connect(current_user.id, websocket)
    try:
        logger.info("WebSocket connected", extra={"user_id": str(current_user.id)})
        async with session_factory() as session:
            conversations = ConversationRepository(session)
            peer_ids = await conversations.peer_ids(current_user.id)
            pending_receipts = await ReceiptService(session).mark_pending_delivered(
                current_user.id
            )
            receipt_members = {
                receipt.conversation_id: await conversations.member_ids(
                    receipt.conversation_id
                )
                for receipt in pending_receipts
            }
        online_peer_ids = await manager.online_user_ids(peer_ids)
        await websocket.send_json(
            ConnectionReadyEvent(
                data=ConnectionReadyData(
                    user_id=current_user.id,
                    online_user_ids=online_peer_ids,
                )
            ).model_dump(mode="json")
        )
        if became_online:
            await manager.send_to_users(
                peer_ids,
                PresenceOnlineEvent(
                    data=PresenceOnlineData(user_id=current_user.id)
                ).model_dump(mode="json"),
                exclude_user_id=current_user.id,
            )
        for receipt in pending_receipts:
            await manager.send_to_users(
                receipt_members[receipt.conversation_id],
                MessageDeliveredEvent(data=receipt).model_dump(mode="json"),
            )
        while True:
            raw_payload = await websocket.receive_text()
            try:
                payload = json.loads(raw_payload)
            except json.JSONDecodeError:
                await manager.send_to_user(
                    current_user.id,
                    ErrorEvent(
                        error=ErrorDetail(
                            code="INVALID_JSON", message="WebSocket payload must be valid JSON"
                        )
                    ).model_dump(mode="json"),
                )
                continue
            await dispatch_event(payload, current_user.id, manager, session_factory)
    except (WebSocketDisconnect, RuntimeError, ValueError):
        pass
    finally:
        became_offline = await manager.disconnect(current_user.id, websocket)
        if became_offline:
            last_seen = datetime.now(timezone.utc)
            async with session_factory() as session:
                await UserRepository(session).set_last_seen(current_user.id, last_seen)
                peer_ids = await ConversationRepository(session).peer_ids(current_user.id)
                await session.commit()
            await manager.send_to_users(
                peer_ids,
                PresenceOfflineEvent(
                    data=PresenceOfflineData(
                        user_id=current_user.id,
                        last_seen=last_seen.isoformat(),
                    )
                ).model_dump(mode="json"),
                exclude_user_id=current_user.id,
            )
        logger.info("WebSocket disconnected", extra={"user_id": str(current_user.id)})
