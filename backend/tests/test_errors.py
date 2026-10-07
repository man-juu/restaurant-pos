"""One error shape everywhere: code, message, details, request_id (docs/04 section 9)."""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import ConflictError

KEYS = {"code", "message", "details", "request_id"}


class Body(BaseModel):
    password: str
    quantity: int


@pytest.fixture
def client(app: FastAPI) -> Any:
    @app.get("/_test/conflict")
    async def conflict() -> None:
        raise ConflictError(details={"field": "sku"})

    @app.post("/_test/validate")
    async def validate(body: Body) -> None:
        return None

    @app.get("/_test/crash")
    async def crash() -> None:
        raise RuntimeError("secret internals")

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def assert_error(response: Any, status: int, code: str) -> dict[str, Any]:
    body: dict[str, Any] = response.json()
    assert response.status_code == status
    assert set(body) == KEYS
    assert body["code"] == code
    assert body["message"] == f"errors.{code}"
    assert body["request_id"] == response.headers["x-request-id"]
    return body


def test_app_error(client: TestClient) -> None:
    body = assert_error(client.get("/_test/conflict"), 409, "conflict")
    assert body["details"] == {"field": "sku"}


def test_unknown_route(client: TestClient) -> None:
    assert_error(client.get("/nope"), 404, "not_found")


def test_validation_error_does_not_echo_input(client: TestClient) -> None:
    response = client.post("/_test/validate", json={"password": "hunter2", "quantity": "x"})
    body = assert_error(response, 422, "validation_error")
    assert body["details"][0]["loc"] == ["body", "quantity"]
    assert "hunter2" not in response.text


def test_unhandled_error_hides_internals(client: TestClient) -> None:
    response = client.get("/_test/crash")
    assert_error(response, 500, "internal_error")
    assert "secret internals" not in response.text
