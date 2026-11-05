import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.storage import ObjectStorage
from app.services.attachment_service import AttachmentService

logger = logging.getLogger(__name__)

RELEASE_LOCK_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


class AttachmentCleanupWorker:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        storage: ObjectStorage,
    ) -> None:
        self.session_factory = session_factory
        self.storage = storage
        self.redis = Redis.from_url(settings.redis_url, decode_responses=True)
        self.lock_key = f"{settings.redis_key_prefix}:locks:attachment-cleanup"
        self._task: Optional[asyncio.Task[None]] = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="attachment-cleanup")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        await self.redis.aclose()

    async def _run(self) -> None:
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Attachment cleanup failed")
            await asyncio.sleep(settings.attachment_cleanup_interval_seconds)

    async def run_once(self) -> int:
        token = uuid4().hex
        acquired = await self.redis.set(
            self.lock_key,
            token,
            nx=True,
            ex=settings.attachment_cleanup_interval_seconds,
        )
        if not acquired:
            return 0
        removed = 0
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(
                hours=settings.attachment_pending_ttl_hours
            )
            while True:
                async with self.session_factory() as session:
                    batch = await AttachmentService(
                        session, self.storage
                    ).cleanup_abandoned(cutoff)
                removed += batch
                if batch < 100:
                    break
            if removed:
                logger.info("Removed abandoned attachments", extra={"count": removed})
            return removed
        finally:
            await self.redis.eval(RELEASE_LOCK_SCRIPT, 1, self.lock_key, token)
