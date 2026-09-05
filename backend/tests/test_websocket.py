import asyncio
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.datastructures import Headers
from starlette.websockets import WebSocketDisconnect

from app.core.database import get_session_factory
from app.main import app
from app.models.user import User
from app.services.receipt_service import ReceiptService
from app.websocket.auth import extract_access_token, get_websocket_user
from app.websocket.events import MessageReadRequest, MessageSendEvent, TypingStartEvent
from app.websocket.handlers import (
    dispatch_event,
    handle_message_read,
    handle_message_send,
    handle_typing,
)
from app.websocket.manager import ConnectionManager, TypingTracker
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


async def test_websocket_accepts_authenticated_connection(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = uuid4()

    async def override_user() -> User:
        return User(
            id=user_id,
            username="alice",
            email="alice@example.com",
            password_hash="unused",
        )

    app.dependency_overrides[get_websocket_user] = override_user
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    client = TestClient(app)
    try:
        with client.websocket_connect(
            "/ws", subprotocols=["access_token", "test-token"]
        ) as websocket:
            assert websocket.accepted_subprotocol == "access_token"
            assert websocket.receive_json() == {
                "type": "connection.ready",
                "data": {"user_id": str(user_id), "online_user_ids": []},
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
        created = next(event for event in socket.events if event["type"] == "message.created")
        assert created["request_id"] == "request-1"
        assert created["data"]["content"] == "Realtime hello"
        delivered = next(
            event for event in socket.events if event["type"] == "message.delivered"
        )
        assert delivered["data"]["user_id"] == str(bob_id)
        assert delivered["data"]["delivered_at"] is not None
    history = await client.get(
        f"/conversations/{conversation['id']}/messages", headers=auth_headers(bob)
    )
    persisted = history.json()["items"][-1]
    assert persisted["content"] == "Realtime hello"
    assert persisted["receipts"][0]["delivered_at"] is not None
    assert persisted["receipts"][0]["read_at"] is None


async def test_read_receipt_marks_messages_read_and_clears_unread_count(
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
            conversation_id=conversation["id"],
            content="Please read me",
        ),
        alice_id,
        manager,
        session_factory,
    )
    created = next(event for event in bob_socket.events if event["type"] == "message.created")
    unread = await client.get("/conversations", headers=auth_headers(bob))
    assert unread.json()[0]["unread_count"] == 1

    await handle_message_read(
        MessageReadRequest(
            type="message.read",
            request_id="read-1",
            conversation_id=conversation["id"],
            message_id=created["data"]["id"],
        ),
        bob_id,
        manager,
        session_factory,
    )

    read_event = next(event for event in alice_socket.events if event["type"] == "message.read")
    assert read_event["request_id"] == "read-1"
    assert read_event["data"]["user_id"] == str(bob_id)
    assert read_event["data"]["read_at"] is not None
    read = await client.get("/conversations", headers=auth_headers(bob))
    assert read.json()[0]["unread_count"] == 0


async def test_connecting_recipient_marks_pending_messages_delivered(
    client,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    alice = await register_user(client, "alice")
    bob = await register_user(client, "bob")
    conversation = await create_direct(client, alice, bob)
    alice_id = UUID(alice["user"]["id"])
    bob_id = UUID(bob["user"]["id"])
    alice_socket = FakeWebSocket()
    manager = ConnectionManager()
    await manager.connect(alice_id, alice_socket)  # type: ignore[arg-type]

    await handle_message_send(
        MessageSendEvent(
            type="message.send",
            conversation_id=conversation["id"],
            content="Waiting for reconnect",
        ),
        alice_id,
        manager,
        session_factory,
    )
    created = next(
        event for event in alice_socket.events if event["type"] == "message.created"
    )
    assert created["data"]["receipts"][0]["delivered_at"] is None

    async with session_factory() as session:
        receipts = await ReceiptService(session).mark_pending_delivered(bob_id)

    assert len(receipts) == 1
    assert receipts[0].message_id == UUID(created["data"]["id"])
    assert receipts[0].delivered_at is not None


async def test_typing_signal_expires_and_nonmember_is_rejected(
    client,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    alice = await register_user(client, "alice")
    bob = await register_user(client, "bob")
    charlie = await register_user(client, "charlie")
    conversation = await create_direct(client, alice, bob)
    alice_id = UUID(alice["user"]["id"])
    bob_id = UUID(bob["user"]["id"])
    charlie_id = UUID(charlie["user"]["id"])
    bob_socket = FakeWebSocket()
    charlie_socket = FakeWebSocket()
    manager = ConnectionManager()
    tracker = TypingTracker(ttl_seconds=0.01)
    await manager.connect(bob_id, bob_socket)  # type: ignore[arg-type]
    await manager.connect(charlie_id, charlie_socket)  # type: ignore[arg-type]

    event = TypingStartEvent(type="typing.start", conversation_id=conversation["id"])
    await handle_typing(event, alice_id, manager, tracker, session_factory)
    assert bob_socket.events[-1]["type"] == "typing.start"
    await asyncio.sleep(0.02)
    assert bob_socket.events[-1]["type"] == "typing.stop"

    await dispatch_event(
        event.model_dump(mode="json"),
        charlie_id,
        manager,
        session_factory,
        tracker,
    )
    assert charlie_socket.events[-1]["type"] == "error"
    assert charlie_socket.events[-1]["error"]["code"] == "CONVERSATION_FORBIDDEN"


async def test_presence_changes_only_on_first_connect_and_last_disconnect() -> None:
    user_id = uuid4()
    first = FakeWebSocket()
    second = FakeWebSocket()
    manager = ConnectionManager()

    assert await manager.connect(user_id, first) is True  # type: ignore[arg-type]
    assert await manager.connect(user_id, second) is False  # type: ignore[arg-type]
    assert await manager.disconnect(user_id, first) is False  # type: ignore[arg-type]
    assert await manager.disconnect(user_id, second) is True  # type: ignore[arg-type]


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
