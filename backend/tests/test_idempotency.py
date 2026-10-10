"""FR-X-003: idempotency key header validation and request fingerprint."""

import uuid
from typing import Annotated, Any

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from app.core.idempotency import request_fingerprint, required_idempotency_key


@pytest.fixture
def client(app: FastAPI) -> Any:
    @app.post("/_test/create")
    async def create(
        request: Request, key: Annotated[uuid.UUID, Depends(required_idempotency_key)]
    ) -> dict[str, str]:
        return {"key": str(key), "fingerprint": await request_fingerprint(request)}

    with TestClient(app) as c:
        yield c


def test_fr_x_003_accepts_uuid_key(client: TestClient) -> None:
    key = str(uuid.uuid4())
    response = client.post("/_test/create", headers={"Idempotency-Key": key}, json={"a": 1})
    assert response.status_code == 200
    assert response.json()["key"] == key


@pytest.mark.parametrize("headers", [{}, {"Idempotency-Key": "not-a-uuid"}])
def test_fr_x_003_rejects_missing_or_invalid_key(
    client: TestClient, headers: dict[str, str]
) -> None:
    response = client.post("/_test/create", headers=headers, json={})
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_idempotency_key"


def test_fr_x_003_fingerprint_depends_on_body(client: TestClient) -> None:
    headers = {"Idempotency-Key": str(uuid.uuid4())}
    a = client.post("/_test/create", headers=headers, json={"a": 1}).json()["fingerprint"]
    b = client.post("/_test/create", headers=headers, json={"a": 1}).json()["fingerprint"]
    c = client.post("/_test/create", headers=headers, json={"a": 2}).json()["fingerprint"]
    assert a == b != c
