from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Optional, Protocol
from uuid import UUID

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class DistributedRealtimeBackend(Protocol):
    @property
    def available(self) -> bool: ...

    async def publish_users(self, user_ids: list[UUID], event: dict) -> bool: ...

    async def user_connected(self, user_id: UUID) -> bool: ...

    async def user_disconnected(self, user_id: UUID) -> bool: ...

    async def online_user_ids(self, user_ids: list[UUID]) -> list[UUID]: ...

    async def allow_action(
        self, user_id: UUID, action: str, limit: int, window_seconds: int
    ) -> bool: ...

    async def typing_started(
        self,
        conversation_id: UUID,
        user_id: UUID,
        target_ids: list[UUID],
        started_event: dict,
        stopped_event: dict,
    ) -> bool: ...

    async def typing_stopped(
        self,
        conversation_id: UUID,
        user_id: UUID,
        target_ids: list[UUID],
        stopped_event: dict,
    ) -> bool: ...


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


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[UUID, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._backend: Optional[DistributedRealtimeBackend] = None

    def attach_backend(self, backend: DistributedRealtimeBackend) -> None:
        self._backend = backend

    def detach_backend(self, backend: DistributedRealtimeBackend) -> None:
        if self._backend is backend:
            self._backend = None

    @property
    def distributed(self) -> bool:
        return self._backend is not None and self._backend.available

    async def connect(self, user_id: UUID, websocket: WebSocket) -> bool:
        await websocket.accept(subprotocol="access_token")
        async with self._lock:
            was_locally_offline = not self._connections[user_id]
            self._connections[user_id].add(websocket)
        if was_locally_offline and self.distributed:
            try:
                return await self._backend.user_connected(user_id)  # type: ignore[union-attr]
            except Exception:
                logger.exception("Redis presence connect failed", extra={"user_id": str(user_id)})
        return was_locally_offline

    async def disconnect(self, user_id: UUID, websocket: WebSocket) -> bool:
        async with self._lock:
            connections = self._connections.get(user_id)
            if connections is None:
                return False
            connections.discard(websocket)
            if connections:
                return False
            self._connections.pop(user_id, None)
        if self.distributed:
            try:
                return await self._backend.user_disconnected(user_id)  # type: ignore[union-attr]
            except Exception:
                logger.exception(
                    "Redis presence disconnect failed", extra={"user_id": str(user_id)}
                )
        return True

    async def deliver_to_user_local(self, user_id: UUID, event: dict) -> None:
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

    async def deliver_to_users_local(self, user_ids: list[UUID], event: dict) -> None:
        await asyncio.gather(
            *(self.deliver_to_user_local(user_id, event) for user_id in user_ids)
        )

    async def send_to_user(self, user_id: UUID, event: dict) -> None:
        await self.send_to_users([user_id], event)

    async def send_to_users(
        self, user_ids: list[UUID], event: dict, exclude_user_id: Optional[UUID] = None
    ) -> None:
        targets = list(
            dict.fromkeys(user_id for user_id in user_ids if user_id != exclude_user_id)
        )
        if not targets:
            return
        if self.distributed:
            try:
                if await self._backend.publish_users(targets, event):  # type: ignore[union-attr]
                    return
            except Exception:
                logger.exception("Redis realtime publish failed")
        await self.deliver_to_users_local(targets, event)

    async def connection_count(self, user_id: UUID) -> int:
        async with self._lock:
            return len(self._connections.get(user_id, ()))

    async def local_user_ids(self) -> list[UUID]:
        async with self._lock:
            return list(self._connections)

    async def is_online(self, user_id: UUID) -> bool:
        return bool(await self.online_user_ids([user_id]))

    async def online_user_ids(self, user_ids: list[UUID]) -> list[UUID]:
        if self.distributed:
            try:
                return await self._backend.online_user_ids(user_ids)  # type: ignore[union-attr]
            except Exception:
                logger.exception("Redis presence lookup failed")
        async with self._lock:
            return [user_id for user_id in user_ids if self._connections.get(user_id)]

    async def allow_action(
        self, user_id: UUID, action: str, limit: int, window_seconds: int
    ) -> bool:
        if self.distributed:
            try:
                return await self._backend.allow_action(  # type: ignore[union-attr]
                    user_id, action, limit, window_seconds
                )
            except Exception:
                logger.exception("Redis realtime rate-limit check failed")
        return True

    async def typing_start(
        self,
        conversation_id: UUID,
        user_id: UUID,
        member_ids: list[UUID],
        started_event: dict,
        stopped_event: dict,
        fallback_tracker: TypingTracker,
    ) -> None:
        targets = [member_id for member_id in member_ids if member_id != user_id]
        if self.distributed:
            try:
                if await self._backend.typing_started(  # type: ignore[union-attr]
                    conversation_id,
                    user_id,
                    targets,
                    started_event,
                    stopped_event,
                ):
                    return
            except Exception:
                logger.exception("Redis typing start failed")

        async def expire() -> None:
            await self.send_to_users(targets, stopped_event)

        await fallback_tracker.start(conversation_id, user_id, expire)
        await self.send_to_users(targets, started_event)

    async def typing_stop(
        self,
        conversation_id: UUID,
        user_id: UUID,
        member_ids: list[UUID],
        stopped_event: dict,
        fallback_tracker: TypingTracker,
    ) -> None:
        targets = [member_id for member_id in member_ids if member_id != user_id]
        await fallback_tracker.stop(conversation_id, user_id)
        if self.distributed:
            try:
                if await self._backend.typing_stopped(  # type: ignore[union-attr]
                    conversation_id, user_id, targets, stopped_event
                ):
                    return
            except Exception:
                logger.exception("Redis typing stop failed")
        await self.send_to_users(targets, stopped_event)


manager = ConnectionManager()
typing_tracker = TypingTracker()
