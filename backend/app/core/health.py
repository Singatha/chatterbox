import asyncio
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.storage import ObjectStorage
from app.websocket.redis_backend import RedisRealtimeBackend


async def _check_database(session: AsyncSession) -> bool:
    await session.execute(text("SELECT 1"))
    return True


async def readiness_report(
    session: AsyncSession,
    storage: ObjectStorage,
    redis_backend: Optional[RedisRealtimeBackend],
) -> tuple[bool, dict[str, Any]]:
    timeout = settings.health_check_timeout_seconds

    try:
        database_ok = await asyncio.wait_for(_check_database(session), timeout)
    except Exception:
        database_ok = False

    if redis_backend is None:
        redis_ok = not settings.redis_required
        redis_status = "local" if redis_ok else "unavailable"
    else:
        try:
            redis_ok = await asyncio.wait_for(redis_backend.ping(), timeout)
        except Exception:
            redis_ok = False
        redis_status = "redis" if redis_ok else "unavailable"

    try:
        storage_ok = await asyncio.wait_for(storage.healthcheck(), timeout)
    except Exception:
        storage_ok = False
    storage_required_ok = storage_ok or not settings.minio_required

    ready = database_ok and redis_ok and storage_required_ok
    return ready, {
        "status": "ready" if ready else "not_ready",
        "checks": {
            "database": "ok" if database_ok else "unavailable",
            "realtime": redis_status,
            "storage": "minio" if storage_ok else "unavailable",
        },
    }
