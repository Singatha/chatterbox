import asyncio
from collections import defaultdict
from uuid import UUID

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[UUID, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, user_id: UUID, websocket: WebSocket) -> None:
        await websocket.accept(subprotocol="access_token")
        async with self._lock:
            self._connections[user_id].add(websocket)

    async def disconnect(self, user_id: UUID, websocket: WebSocket) -> None:
        async with self._lock:
            connections = self._connections.get(user_id)
            if connections is None:
                return
            connections.discard(websocket)
            if not connections:
                self._connections.pop(user_id, None)

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

    async def send_to_users(self, user_ids: list[UUID], event: dict) -> None:
        await asyncio.gather(*(self.send_to_user(user_id, event) for user_id in user_ids))

    async def connection_count(self, user_id: UUID) -> int:
        async with self._lock:
            return len(self._connections.get(user_id, ()))


manager = ConnectionManager()

