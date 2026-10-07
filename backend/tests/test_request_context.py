import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.core.logging import JsonFormatter, request_id_var


def test_generates_request_id(client: TestClient) -> None:
    assert len(client.get("/health").headers["x-request-id"]) == 32


def test_keeps_valid_incoming_request_id(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "edge-abc12345"})
    assert response.headers["x-request-id"] == "edge-abc12345"


def test_replaces_unsafe_incoming_request_id(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "bad id\nforged-log-line"})
    assert response.headers["x-request-id"] != "bad id\nforged-log-line"


def test_request_is_logged_as_json_with_request_id(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="app.request"):
        response = client.get("/health?email=someone@example.com")
    record = next(r for r in caplog.records if r.name == "app.request")
    assert record.path == "/health"  # type: ignore[attr-defined]
    assert record.status == 200  # type: ignore[attr-defined]
    # Query strings are not logged by our middleware (the test client's own httpx log is ignored).
    assert all(
        "someone@example.com" not in r.getMessage() + str(r.__dict__)
        for r in caplog.records
        if r.name == "app.request"
    )
    assert response.headers["x-request-id"]


def test_json_formatter_includes_context() -> None:
    token = request_id_var.set("req-12345678")
    try:
        record = logging.makeLogRecord({"msg": "hello", "levelname": "INFO", "outlet": "o1"})
        line = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)
    assert line["msg"] == "hello"
    assert line["request_id"] == "req-12345678"
    assert line["outlet"] == "o1"
