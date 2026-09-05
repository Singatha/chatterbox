from typing import Optional

from fastapi import WebSocket, WebSocketException, status

from app.core.database import AsyncSessionLocal
from app.core.security import InvalidTokenError, decode_token
from app.models.user import User
from app.repositories.user_repository import UserRepository


def extract_access_token(websocket: WebSocket) -> Optional[str]:
    raw_protocols = websocket.headers.get("sec-websocket-protocol", "")
    protocols = [item.strip() for item in raw_protocols.split(",")]
    if len(protocols) == 2 and protocols[0] == "access_token" and protocols[1]:
        return protocols[1]
    return None


async def get_websocket_user(websocket: WebSocket) -> User:
    token = extract_access_token(websocket)
    if token is None:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION, reason="Authentication required"
        )
    try:
        payload = decode_token(token, "access")
    except InvalidTokenError as exc:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired token"
        ) from exc
    async with AsyncSessionLocal() as session:
        user = await UserRepository(session).get_by_id(payload.subject)
    if user is None:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired token"
        )
    return user

