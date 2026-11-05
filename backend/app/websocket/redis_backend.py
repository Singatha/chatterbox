import asyncio
import json
import logging
import socket
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Optional
from uuid import UUID, uuid4

from redis.asyncio import Redis

from app.websocket.manager import ConnectionManager

logger = logging.getLogger(__name__)

PRESENCE_CONNECT_SCRIPT = """
local now = tonumber(ARGV[1])
local expires_at = tonumber(ARGV[2])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
local was_offline = redis.call('ZCARD', KEYS[1]) == 0
redis.call('ZADD', KEYS[1], expires_at, ARGV[3])
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[4]))
redis.call('ZADD', KEYS[2], expires_at, ARGV[5])
if was_offline then return 1 else return 0 end
"""

PRESENCE_DISCONNECT_SCRIPT = """
redis.call('ZREM', KEYS[1], ARGV[1])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', tonumber(ARGV[2]))
if redis.call('ZCARD', KEYS[1]) == 0 then
  redis.call('DEL', KEYS[1])
  redis.call('ZREM', KEYS[2], ARGV[3])
  return 1
end
local latest = redis.call('ZRANGE', KEYS[1], -1, -1, 'WITHSCORES')
if #latest == 2 then redis.call('ZADD', KEYS[2], latest[2], ARGV[3]) end
return 0
"""

TYPING_SWEEP_SCRIPT = """
local expired = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[1], 'LIMIT', 0, 100)
local result = {}
for _, member in ipairs(expired) do
  if redis.call('ZREM', KEYS[1], member) == 1 then
    local data = redis.call('HGET', KEYS[2], member)
    redis.call('HDEL', KEYS[2], member)
    if data then
      table.insert(result, data)
    end
  end
end
return result
"""

RATE_LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2])) end
if count <= tonumber(ARGV[1]) then return 1 else return 0 end
"""


class RedisRealtimeBackend:
    def __init__(
        self,
        redis_url: str,
        manager: ConnectionManager,
        *,
        key_prefix: str = "chatterbox",
        presence_ttl_seconds: int = 30,
        presence_heartbeat_seconds: int = 10,
        typing_ttl_seconds: float = 5.0,
        sweep_interval_seconds: float = 1.0,
        instance_id: Optional[str] = None,
        client: Optional[Redis] = None,
        on_presence_expired: Optional[Callable[[UUID], Awaitable[None]]] = None,
    ) -> None:
        self.manager = manager
        self.instance_id = instance_id or f"{socket.gethostname()}-{uuid4().hex[:8]}"
        self.key_prefix = key_prefix
        self.presence_ttl_seconds = presence_ttl_seconds
        self.presence_heartbeat_seconds = presence_heartbeat_seconds
        self.typing_ttl_seconds = typing_ttl_seconds
        self.sweep_interval_seconds = sweep_interval_seconds
        self.on_presence_expired = on_presence_expired
        self._redis = client or Redis.from_url(redis_url, decode_responses=True)
        self._pubsub = None
        self._listener_task: Optional[asyncio.Task[None]] = None
        self._maintenance_task: Optional[asyncio.Task[None]] = None
        self._stopping = False
        self._available = False

    @property
    def available(self) -> bool:
        return self._available

    async def ping(self) -> bool:
        return bool(await self._redis.ping())

    @property
    def events_channel(self) -> str:
        return f"{self.key_prefix}:realtime:events"

    @property
    def presence_users_key(self) -> str:
        return f"{self.key_prefix}:presence:users"

    @property
    def typing_expirations_key(self) -> str:
        return f"{self.key_prefix}:typing:expirations"

    @property
    def typing_data_key(self) -> str:
        return f"{self.key_prefix}:typing:data"

    def presence_key(self, user_id: UUID) -> str:
        return f"{self.key_prefix}:presence:{user_id}"

    @staticmethod
    def typing_member(conversation_id: UUID, user_id: UUID) -> str:
        return f"{conversation_id}:{user_id}"

    async def start(self) -> None:
        self._stopping = False
        await self._redis.ping()
        await self._subscribe()
        self._available = True
        self._listener_task = asyncio.create_task(
            self._listen(), name=f"redis-listener-{self.instance_id}"
        )
        self._maintenance_task = asyncio.create_task(
            self._maintain(), name=f"redis-maintenance-{self.instance_id}"
        )
        logger.info("Redis realtime backend started", extra={"instance_id": self.instance_id})

    async def stop(self) -> None:
        self._stopping = True
        self._available = False
        for task in (self._listener_task, self._maintenance_task):
            if task is not None:
                task.cancel()
        await asyncio.gather(
            *(task for task in (self._listener_task, self._maintenance_task) if task),
            return_exceptions=True,
        )
        if self._pubsub is not None:
            with suppress(Exception):
                await self._pubsub.aclose()
        await self._redis.aclose()
        logger.info("Redis realtime backend stopped", extra={"instance_id": self.instance_id})

    async def _subscribe(self) -> None:
        if self._pubsub is not None:
            with suppress(Exception):
                await self._pubsub.aclose()
        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe(self.events_channel)

    async def _listen(self) -> None:
        retry_delay = 0.5
        while not self._stopping:
            try:
                if self._pubsub is None:
                    await self._subscribe()
                message = await self._pubsub.get_message(  # type: ignore[union-attr]
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if message is None:
                    await asyncio.sleep(0.01)
                    continue
                await self._deliver_envelope(message.get("data"))
                self._available = True
                retry_delay = 0.5
            except asyncio.CancelledError:
                raise
            except Exception:
                self._available = False
                logger.exception("Redis Pub/Sub listener disconnected")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 10.0)
                try:
                    await self._redis.ping()
                    await self._subscribe()
                    self._available = True
                except Exception:
                    continue

    async def _deliver_envelope(self, raw_data: object) -> None:
        if isinstance(raw_data, bytes):
            raw_data = raw_data.decode()
        if not isinstance(raw_data, str):
            return
        try:
            envelope = json.loads(raw_data)
            targets = [UUID(value) for value in envelope["targets"]]
            event = envelope["event"]
            if not isinstance(event, dict):
                return
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            logger.warning("Ignored malformed Redis realtime envelope")
            return
        await self.manager.deliver_to_users_local(targets, event)

    async def publish_users(self, user_ids: list[UUID], event: dict) -> bool:
        if not self.available:
            return False
        envelope = json.dumps(
            {
                "source": self.instance_id,
                "targets": [str(user_id) for user_id in user_ids],
                "event": event,
            },
            separators=(",", ":"),
        )
        await self._redis.publish(self.events_channel, envelope)
        return True

    async def user_connected(self, user_id: UUID) -> bool:
        now = time.time()
        result = await self._redis.eval(
            PRESENCE_CONNECT_SCRIPT,
            2,
            self.presence_key(user_id),
            self.presence_users_key,
            now,
            now + self.presence_ttl_seconds,
            self.instance_id,
            self.presence_ttl_seconds * 2,
            str(user_id),
        )
        return bool(result)

    async def user_disconnected(self, user_id: UUID) -> bool:
        result = await self._redis.eval(
            PRESENCE_DISCONNECT_SCRIPT,
            2,
            self.presence_key(user_id),
            self.presence_users_key,
            self.instance_id,
            time.time(),
            str(user_id),
        )
        return bool(result)

    async def online_user_ids(self, user_ids: list[UUID]) -> list[UUID]:
        if not user_ids:
            return []
        now = time.time()
        pipeline = self._redis.pipeline(transaction=False)
        for user_id in user_ids:
            pipeline.zremrangebyscore(self.presence_key(user_id), "-inf", now)
            pipeline.zcard(self.presence_key(user_id))
        results = await pipeline.execute()
        return [
            user_id
            for index, user_id in enumerate(user_ids)
            if int(results[index * 2 + 1]) > 0
        ]

    async def allow_action(
        self, user_id: UUID, action: str, limit: int, window_seconds: int
    ) -> bool:
        safe_action = action.replace(":", "_")
        key = f"{self.key_prefix}:rate:{safe_action}:{user_id}"
        result = await self._redis.eval(
            RATE_LIMIT_SCRIPT,
            1,
            key,
            limit,
            window_seconds,
        )
        return bool(result)

    async def typing_started(
        self,
        conversation_id: UUID,
        user_id: UUID,
        target_ids: list[UUID],
        started_event: dict,
        stopped_event: dict,
    ) -> bool:
        if not self.available:
            return False
        member = self.typing_member(conversation_id, user_id)
        expiration_data = json.dumps(
            {
                "targets": [str(target_id) for target_id in target_ids],
                "event": stopped_event,
            },
            separators=(",", ":"),
        )
        pipeline = self._redis.pipeline(transaction=True)
        pipeline.hset(self.typing_data_key, member, expiration_data)
        pipeline.zadd(
            self.typing_expirations_key,
            {member: time.time() + self.typing_ttl_seconds},
        )
        await pipeline.execute()
        return await self.publish_users(target_ids, started_event)

    async def typing_stopped(
        self,
        conversation_id: UUID,
        user_id: UUID,
        target_ids: list[UUID],
        stopped_event: dict,
    ) -> bool:
        if not self.available:
            return False
        member = self.typing_member(conversation_id, user_id)
        pipeline = self._redis.pipeline(transaction=True)
        pipeline.zrem(self.typing_expirations_key, member)
        pipeline.hdel(self.typing_data_key, member)
        await pipeline.execute()
        return await self.publish_users(target_ids, stopped_event)

    async def _maintain(self) -> None:
        next_heartbeat = 0.0
        while not self._stopping:
            try:
                now = time.time()
                if now >= next_heartbeat:
                    for user_id in await self.manager.local_user_ids():
                        await self.user_connected(user_id)
                    next_heartbeat = now + self.presence_heartbeat_seconds
                await self._sweep_typing(now)
                await self._sweep_presence(now)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Redis realtime maintenance iteration failed")
            await asyncio.sleep(self.sweep_interval_seconds)

    async def _sweep_typing(self, now: float) -> None:
        expired = await self._redis.eval(
            TYPING_SWEEP_SCRIPT,
            2,
            self.typing_expirations_key,
            self.typing_data_key,
            now,
        )
        for raw_data in expired:
            if isinstance(raw_data, bytes):
                raw_data = raw_data.decode()
            try:
                data = json.loads(raw_data)
                targets = [UUID(value) for value in data["targets"]]
                event = data["event"]
            except (ValueError, TypeError, KeyError, json.JSONDecodeError):
                logger.warning("Ignored malformed expired typing state")
                continue
            await self.publish_users(targets, event)

    async def _sweep_presence(self, now: float) -> None:
        expired_users = await self._redis.zrangebyscore(
            self.presence_users_key, "-inf", now, start=0, num=100
        )
        for raw_user_id in expired_users:
            user_value = raw_user_id.decode() if isinstance(raw_user_id, bytes) else raw_user_id
            claimed = await self._redis.zrem(self.presence_users_key, user_value)
            if not claimed:
                continue
            try:
                user_id = UUID(user_value)
            except ValueError:
                continue
            presence_key = self.presence_key(user_id)
            await self._redis.zremrangebyscore(presence_key, "-inf", now)
            latest = await self._redis.zrange(presence_key, -1, -1, withscores=True)
            if latest:
                await self._redis.zadd(self.presence_users_key, {user_value: latest[0][1]})
                continue
            await self._redis.delete(presence_key)
            if self.on_presence_expired is not None:
                if not await self.online_user_ids([user_id]):
                    await self.on_presence_expired(user_id)
