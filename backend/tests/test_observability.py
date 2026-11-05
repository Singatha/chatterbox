import json
import logging

from app.core.observability import JsonFormatter, request_id_context
from app.core.storage import get_object_storage
from app.main import app


class HealthyStorage:
    async def healthcheck(self) -> bool:
        return True


async def test_liveness_preserves_valid_request_id(client) -> None:
    response = await client.get(
        "/health/live", headers={"X-Request-ID": "edge-request-123"}
    )

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
    assert response.headers["X-Request-ID"] == "edge-request-123"


async def test_invalid_request_id_is_replaced(client) -> None:
    response = await client.get(
        "/health/live", headers={"X-Request-ID": "invalid request id"}
    )

    request_id = response.headers["X-Request-ID"]
    assert len(request_id) == 32
    assert request_id.isalnum()


async def test_readiness_checks_dependencies(client) -> None:
    app.dependency_overrides[get_object_storage] = lambda: HealthyStorage()

    response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {
            "database": "ok",
            "realtime": "local",
            "storage": "minio",
        },
    }


async def test_metrics_expose_bounded_http_labels(client) -> None:
    await client.get("/health/live")

    response = await client.get("/metrics")

    assert response.status_code == 200
    assert "chatterbox_http_requests_total" in response.text
    assert 'route="/health/live"' in response.text


def test_json_formatter_adds_correlation_id() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="chatterbox.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request handled",
        args=(),
        exc_info=None,
    )
    token = request_id_context.set("request-456")
    try:
        payload = json.loads(formatter.format(record))
    finally:
        request_id_context.reset(token)

    assert payload["level"] == "INFO"
    assert payload["message"] == "request handled"
    assert payload["request_id"] == "request-456"
