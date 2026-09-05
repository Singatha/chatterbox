import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.models.user import User
from app.websocket.auth import get_websocket_user
from app.websocket.events import ConnectionReadyEvent, ErrorDetail, ErrorEvent
from app.websocket.handlers import dispatch_event
from app.websocket.manager import manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    current_user: Annotated[User, Depends(get_websocket_user)],
) -> None:
    await manager.connect(current_user.id, websocket)
    logger.info("WebSocket connected", extra={"user_id": str(current_user.id)})
    await websocket.send_json(
        ConnectionReadyEvent(data={"user_id": str(current_user.id)}).model_dump(mode="json")
    )
    try:
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
            await dispatch_event(payload, current_user.id, manager)
    except (WebSocketDisconnect, RuntimeError, ValueError):
        pass
    finally:
        await manager.disconnect(current_user.id, websocket)
        logger.info("WebSocket disconnected", extra={"user_id": str(current_user.id)})
