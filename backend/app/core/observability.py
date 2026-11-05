import contextvars
import json
import logging
import logging.config
import re
import socket
import time
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Gauge, Histogram
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.config import settings

request_id_context: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default=""
)

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
STANDARD_LOG_FIELDS = set(logging.makeLogRecord({}).__dict__) | {
    "message",
    "asctime",
}

HTTP_REQUESTS_TOTAL = Counter(
    "chatterbox_http_requests_total",
    "HTTP responses produced by the API.",
    ("method", "route", "status_code"),
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "chatterbox_http_request_duration_seconds",
    "HTTP request duration before the response body is streamed.",
    ("method", "route"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "chatterbox_http_requests_in_progress",
    "HTTP requests currently being processed.",
    ("method",),
)
WEBSOCKET_CONNECTIONS = Gauge(
    "chatterbox_websocket_connections",
    "WebSocket connections owned by this API instance.",
)
WEBSOCKET_EVENTS_TOTAL = Counter(
    "chatterbox_websocket_events_total",
    "WebSocket events handled by type and outcome.",
    ("event_type", "outcome"),
)
ATTACHMENT_SCANS_TOTAL = Counter(
    "chatterbox_attachment_scans_total",
    "Attachment malware scan outcomes.",
    ("scanner", "outcome"),
)


def _trace_id() -> str:
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return ""
    return format(context.trace_id, "032x")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_context.get()
        if request_id:
            payload["request_id"] = request_id
        trace_id = _trace_id()
        if trace_id:
            payload["trace_id"] = trace_id
        for key, value in record.__dict__.items():
            if key not in STANDARD_LOG_FIELDS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, separators=(",", ":"))


def configure_logging() -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"json": {"()": JsonFormatter}},
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "formatter": "json",
                    "stream": "ext://sys.stdout",
                }
            },
            "root": {"handlers": ["default"], "level": settings.log_level.upper()},
            "loggers": {
                "uvicorn.access": {
                    "handlers": [],
                    "level": "CRITICAL",
                    "propagate": False,
                }
            },
        }
    )


def normalize_request_id(candidate: Optional[str]) -> str:
    if candidate and REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return uuid4().hex


class RequestObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = normalize_request_id(request.headers.get("X-Request-ID"))
        token = request_id_context.set(request_id)
        request.state.request_id = request_id
        started = time.perf_counter()
        method = request.method
        status_code = 500
        HTTP_REQUESTS_IN_PROGRESS.labels(method=method).inc()
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception:
            logging.getLogger("chatterbox.http").exception(
                "HTTP request failed",
                extra={"method": method, "path": request.url.path},
            )
            raise
        finally:
            duration = time.perf_counter() - started
            route = getattr(request.scope.get("route"), "path", "unmatched")
            HTTP_REQUESTS_IN_PROGRESS.labels(method=method).dec()
            HTTP_REQUESTS_TOTAL.labels(
                method=method,
                route=route,
                status_code=str(status_code),
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(method=method, route=route).observe(
                duration
            )
            logging.getLogger("chatterbox.http").info(
                "HTTP request completed",
                extra={
                    "method": method,
                    "route": route,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": round(duration * 1000, 3),
                    "client_ip": request.client.host if request.client else None,
                },
            )
            request_id_context.reset(token)


def configure_tracing(app: FastAPI, engine: AsyncEngine) -> Optional[TracerProvider]:
    endpoint = settings.otel_exporter_otlp_traces_endpoint
    if not endpoint:
        return None
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": settings.otel_service_name,
                "service.instance.id": socket.gethostname(),
                "deployment.environment": settings.environment,
            }
        )
    )
    exporter = OTLPSpanExporter(
        endpoint=endpoint,
        timeout=settings.otel_export_timeout_seconds,
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=provider,
        excluded_urls="/health,/health/live,/health/ready,/metrics",
    )
    SQLAlchemyInstrumentor().instrument(
        engine=engine.sync_engine,
        tracer_provider=provider,
    )
    return provider
