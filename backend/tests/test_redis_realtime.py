import asyncio
from uuid import uuid4

import fakeredis
import fakeredis.aioredis

from app.websocket.manager import ConnectionManager, TypingTracker
from app.websocket.redis_backend import RedisRealtimeBackend


class FakeWebSocket:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self.accepted_subprotocol = None

    async def accept(self, subprotocol=None) -> None:  # type: ignore[no-untyped-def]
        self.accepted_subprotocol = subprotocol

    async def send_json(self, event: dict) -> None:
        self.events.append(event)


async def wait_until(predicate, timeout: float = 1.0) -> None:  # type: ignore[no-untyped-def]
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError("Condition did not become true")
        await asyncio.sleep(0.01)


async def build_backend(
    server: fakeredis.FakeServer,
    manager: ConnectionManager,
    instance_id: str,
    **kwargs,
) -> RedisRealtimeBackend:  # type: ignore[no-untyped-def]
    client = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    backend = RedisRealtimeBackend(
        "redis://unused",
        manager,
        key_prefix="test-chat",
        instance_id=instance_id,
        client=client,
        sweep_interval_seconds=0.01,
        **kwargs,
    )
    await backend.start()
    manager.attach_backend(backend)
    return backend


async def test_pubsub_routes_events_and_presence_across_instances() -> None:
    server = fakeredis.FakeServer()
    first_manager = ConnectionManager()
    second_manager = ConnectionManager()
    first_backend = await build_backend(server, first_manager, "instance-a")
    second_backend = await build_backend(server, second_manager, "instance-b")
    alice_id = uuid4()
    bob_id = uuid4()
    alice_socket = FakeWebSocket()
    bob_socket = FakeWebSocket()

    try:
        assert await first_manager.connect(alice_id, alice_socket) is True  # type: ignore[arg-type]
        assert await second_manager.connect(bob_id, bob_socket) is True  # type: ignore[arg-type]
        assert await first_manager.online_user_ids([alice_id, bob_id]) == [
            alice_id,
            bob_id,
        ]

        await first_manager.send_to_users(
            [alice_id, bob_id], {"type": "message.created", "data": {"id": "one"}}
        )
        await wait_until(lambda: len(alice_socket.events) == 1 and len(bob_socket.events) == 1)
        assert bob_socket.events[0]["type"] == "message.created"
    finally:
        first_manager.detach_backend(first_backend)
        second_manager.detach_backend(second_backend)
        await first_backend.stop()
        await second_backend.stop()


async def test_presence_uses_global_first_and_last_connection_transitions() -> None:
    server = fakeredis.FakeServer()
    first_manager = ConnectionManager()
    second_manager = ConnectionManager()
    first_backend = await build_backend(server, first_manager, "instance-a")
    second_backend = await build_backend(server, second_manager, "instance-b")
    user_id = uuid4()
    first_socket = FakeWebSocket()
    second_socket = FakeWebSocket()

    try:
        assert await first_manager.connect(user_id, first_socket) is True  # type: ignore[arg-type]
        assert await second_manager.connect(user_id, second_socket) is False  # type: ignore[arg-type]
        assert await first_manager.disconnect(user_id, first_socket) is False  # type: ignore[arg-type]
        assert await second_manager.disconnect(user_id, second_socket) is True  # type: ignore[arg-type]
    finally:
        first_manager.detach_backend(first_backend)
        second_manager.detach_backend(second_backend)
        await first_backend.stop()
        await second_backend.stop()


async def test_typing_expiration_is_coordinated_through_redis() -> None:
    server = fakeredis.FakeServer()
    first_manager = ConnectionManager()
    second_manager = ConnectionManager()
    first_backend = await build_backend(
        server, first_manager, "instance-a", typing_ttl_seconds=0.05
    )
    second_backend = await build_backend(
        server, second_manager, "instance-b", typing_ttl_seconds=0.05
    )
    alice_id = uuid4()
    bob_id = uuid4()
    conversation_id = uuid4()
    alice_socket = FakeWebSocket()
    bob_socket = FakeWebSocket()

    try:
        await first_manager.connect(alice_id, alice_socket)  # type: ignore[arg-type]
        await second_manager.connect(bob_id, bob_socket)  # type: ignore[arg-type]
        data = {"conversation_id": str(conversation_id), "user_id": str(alice_id)}
        await first_manager.typing_start(
            conversation_id,
            alice_id,
            [alice_id, bob_id],
            {"type": "typing.start", "data": data},
            {"type": "typing.stop", "data": data},
            TypingTracker(ttl_seconds=10),
        )

        await wait_until(lambda: len(bob_socket.events) >= 2)
        assert [event["type"] for event in bob_socket.events] == [
            "typing.start",
            "typing.stop",
        ]
    finally:
        first_manager.detach_backend(first_backend)
        second_manager.detach_backend(second_backend)
        await first_backend.stop()
        await second_backend.stop()


async def test_expired_presence_lease_is_detected_after_instance_loss() -> None:
    server = fakeredis.FakeServer()
    crashed_manager = ConnectionManager()
    surviving_manager = ConnectionManager()
    expired_users = []

    async def record_expired(user_id) -> None:  # type: ignore[no-untyped-def]
        expired_users.append(user_id)

    crashed_backend = await build_backend(
        server,
        crashed_manager,
        "crashed-instance",
        presence_ttl_seconds=1,
        presence_heartbeat_seconds=10,
    )
    surviving_backend = await build_backend(
        server,
        surviving_manager,
        "surviving-instance",
        presence_ttl_seconds=1,
        presence_heartbeat_seconds=10,
    )
    surviving_backend.on_presence_expired = record_expired
    user_id = uuid4()
    socket = FakeWebSocket()

    await crashed_manager.connect(user_id, socket)  # type: ignore[arg-type]
    crashed_manager.detach_backend(crashed_backend)
    await crashed_backend.stop()
    try:
        await wait_until(lambda: expired_users == [user_id], timeout=1.5)
        assert await surviving_manager.online_user_ids([user_id]) == []
    finally:
        surviving_manager.detach_backend(surviving_backend)
        await surviving_backend.stop()


async def test_realtime_rate_limit_is_shared_in_redis() -> None:
    server = fakeredis.FakeServer()
    first_manager = ConnectionManager()
    second_manager = ConnectionManager()
    first_backend = await build_backend(server, first_manager, "instance-a")
    second_backend = await build_backend(server, second_manager, "instance-b")
    user_id = uuid4()

    try:
        assert await first_manager.allow_action(user_id, "message.send", 2, 60) is True
        assert await second_manager.allow_action(user_id, "message.send", 2, 60) is True
        assert await first_manager.allow_action(user_id, "message.send", 2, 60) is False
        assert await second_manager.allow_action(user_id, "typing", 2, 60) is True
    finally:
        first_manager.detach_backend(first_backend)
        second_manager.detach_backend(second_backend)
        await first_backend.stop()
        await second_backend.stop()
