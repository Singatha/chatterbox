import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.conversations import router as conversations_router
from app.api.users import router as users_router
from app.api.websocket import router as websocket_router
from app.core.config import settings
from app.core.database import engine
from app.core.errors import register_error_handlers
from app.services.presence_service import mark_user_offline
from app.websocket.manager import manager
from app.websocket.redis_backend import RedisRealtimeBackend

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    redis_backend = None
    if settings.environment != "test":
        redis_backend = RedisRealtimeBackend(
            settings.redis_url,
            manager,
            key_prefix=settings.redis_key_prefix,
            presence_ttl_seconds=settings.presence_ttl_seconds,
            presence_heartbeat_seconds=settings.presence_heartbeat_seconds,
            typing_ttl_seconds=settings.typing_ttl_seconds,
            sweep_interval_seconds=settings.realtime_sweep_interval_seconds,
            on_presence_expired=lambda user_id: mark_user_offline(user_id, manager),
        )
        try:
            await redis_backend.start()
            manager.attach_backend(redis_backend)
        except Exception:
            logger.exception("Redis realtime backend could not start")
            await redis_backend.stop()
            redis_backend = None
            if settings.redis_required:
                raise
    try:
        yield
    finally:
        if redis_backend is not None:
            manager.detach_backend(redis_backend)
            await redis_backend.stop()
        await engine.dispose()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_error_handlers(app)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(conversations_router)
app.include_router(websocket_router)


@app.get("/health", tags=["system"])
async def health(response: Response) -> dict[str, str]:
    realtime_status = "redis" if manager.distributed else "local"
    if settings.redis_required and not manager.distributed:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded", "realtime": realtime_status}
    return {
        "status": "ok",
        "realtime": realtime_status,
    }
