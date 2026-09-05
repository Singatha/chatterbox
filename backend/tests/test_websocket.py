from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.datastructures import Headers
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.models.user import User
from app.websocket.auth import extract_access_token, get_websocket_user
from app.websocket.events import MessageSendEvent
from app.websocket.handlers import dispatch_event, handle_message_send
from app.websocket.manager import ConnectionManager
from tests.test_direct_messaging import auth_headers, create_direct, register_user


class FakeWebSocket:
    def __init__(self) -> None:
        self.accepted_subprotocol = None
        self.events: list[dict] = []

    async def accept(self, subprotocol=None) -> None:  # type: ignore[no-untyped-def]
        self.accepted_subprotocol = subprotocol

    async def send_json(self, event: dict) -> None:
        self.events.append(event)


def test_access_token_uses_websocket_subprotocol_header() -> None:
    websocket = SimpleNamespace(
        headers=Headers({"sec-websocket-protocol": "access_token, signed.jwt.token"})
    )
    assert extract_access_token(websocket) == "signed.jwt.token"


def test_websocket_rejects_missing_authentication() -> None:
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws"):
            pass
    assert exc.value.code == 1008


def test_websocket_accepts_authenticated_connection() -> None:
    user_id = uuid4()

    async def override_user() -> User:
        return User(
            id=user_id,
            username="alice",
            email="alice@example.com",
            password_hash="unused",
        )

    app.dependency_overrides[get_websocket_user] = override_user
    client = TestClient(app)
    try:
        with client.websocket_connect(
            "/ws", subprotocols=["access_token", "test-token"]
        ) as websocket:
            assert websocket.accepted_subprotocol == "access_token"
            assert websocket.receive_json() == {
                "type": "connection.ready",
                "data": {"user_id": str(user_id)},
            }
    finally:
        app.dependency_overrides.clear()


async def test_message_send_persists_and_broadcasts_to_both_members(
    client,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    alice = await register_user(client, "alice")
    bob = await register_user(client, "bob")
    conversation = await create_direct(client, alice, bob)
    alice_id = UUID(alice["user"]["id"])
    bob_id = UUID(bob["user"]["id"])
    alice_socket = FakeWebSocket()
    bob_socket = FakeWebSocket()
    manager = ConnectionManager()
    await manager.connect(alice_id, alice_socket)  # type: ignore[arg-type]
    await manager.connect(bob_id, bob_socket)  # type: ignore[arg-type]

    await handle_message_send(
        MessageSendEvent(
            type="message.send",
            request_id="request-1",
            conversation_id=conversation["id"],
            content="Realtime hello",
        ),
        alice_id,
        manager,
        session_factory,
    )

    for socket in (alice_socket, bob_socket):
        assert socket.events[-1]["type"] == "message.created"
        assert socket.events[-1]["request_id"] == "request-1"
        assert socket.events[-1]["data"]["content"] == "Realtime hello"
    history = await client.get(
        f"/conversations/{conversation['id']}/messages", headers=auth_headers(bob)
    )
    assert history.json()["items"][-1]["content"] == "Realtime hello"


async def test_invalid_event_returns_typed_error() -> None:
    user_id = uuid4()
    socket = FakeWebSocket()
    manager = ConnectionManager()
    await manager.connect(user_id, socket)  # type: ignore[arg-type]

    await dispatch_event({"type": "unknown", "request_id": "bad-1"}, user_id, manager)

    assert socket.events[-1] == {
        "type": "error",
        "request_id": "bad-1",
        "error": {"code": "INVALID_EVENT", "message": "WebSocket event is invalid"},
    }
