import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Optional
from uuid import UUID

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[UUID, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, user_id: UUID, websocket: WebSocket) -> bool:
        await websocket.accept(subprotocol="access_token")
        async with self._lock:
            was_offline = not self._connections[user_id]
            self._connections[user_id].add(websocket)
        return was_offline

    async def disconnect(self, user_id: UUID, websocket: WebSocket) -> bool:
        async with self._lock:
            connections = self._connections.get(user_id)
            if connections is None:
                return False
            connections.discard(websocket)
            if not connections:
                self._connections.pop(user_id, None)
                return True
        return False

    async def send_to_user(self, user_id: UUID, event: dict) -> None:
        async with self._lock:
            connections = tuple(self._connections.get(user_id, ()))
        stale: list[WebSocket] = []
        for websocket in connections:
            try:
                await websocket.send_json(event)
            except RuntimeError:
                stale.append(websocket)
        for websocket in stale:
            await self.disconnect(user_id, websocket)

    async def send_to_users(
        self, user_ids: list[UUID], event: dict, exclude_user_id: Optional[UUID] = None
    ) -> None:
        await asyncio.gather(
            *(
                self.send_to_user(user_id, event)
                for user_id in user_ids
                if user_id != exclude_user_id
            )
        )

    async def connection_count(self, user_id: UUID) -> int:
        async with self._lock:
            return len(self._connections.get(user_id, ()))

    async def is_online(self, user_id: UUID) -> bool:
        return await self.connection_count(user_id) > 0

    async def online_user_ids(self, user_ids: list[UUID]) -> list[UUID]:
        async with self._lock:
            return [user_id for user_id in user_ids if self._connections.get(user_id)]


class TypingTracker:
    def __init__(self, ttl_seconds: float = 5.0) -> None:
        self.ttl_seconds = ttl_seconds
        self._tasks: dict[tuple[UUID, UUID], asyncio.Task[None]] = {}

    async def start(
        self,
        conversation_id: UUID,
        user_id: UUID,
        on_expire: Callable[[], Awaitable[None]],
    ) -> None:
        await self.stop(conversation_id, user_id)
        key = (conversation_id, user_id)

        async def expire() -> None:
            try:
                await asyncio.sleep(self.ttl_seconds)
                self._tasks.pop(key, None)
                await on_expire()
            except asyncio.CancelledError:
                pass

        self._tasks[key] = asyncio.create_task(expire())

    async def stop(self, conversation_id: UUID, user_id: UUID) -> None:
        task = self._tasks.pop((conversation_id, user_id), None)
        if task is not None:
            task.cancel()

manager = ConnectionManager()
typing_tracker = TypingTracker()
