"""Performance guards (NFR-001: p95 under 300 ms on the launch VPS).

These are regression alarms, not benchmarks: in-process requests against the real test
database, with generous limits so CI machines do not flake. The query-count checks catch the
most common slow-down (N+1 queries) deterministically, independent of machine speed.
"""

import statistics
import time
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.core.config import Settings
from app.core.identity.passwords import _hasher
from app.main import create_app
from tests.factories import add_member, add_outlet, drop_tenant, seed_tenant
from tests.test_auth import new_client

PW = "performance test passphrase"
P95_LIMIT_MS = 300
MAX_QUERIES = {
    "/api/v1/auth/session": 6,
    "/api/v1/me/capabilities": 6,
    "/api/v1/outlets": 7,
    "/api/v1/settings": 8,
}


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    tenant, roles = seed_tenant("Perf")
    for i in range(30):  # enough rows that a per-row query would show up
        add_outlet(tenant, f"Outlet {i:02d}")
    _, email = add_member(tenant, roles["accountant"], _hasher.hash(PW))
    with new_client(app) as c:
        assert (
            c.post("/api/v1/auth/login", json={"email": email, "password": PW}).status_code == 200
        )
        yield c
    drop_tenant(tenant)


def _count_queries(app: FastAPI, client: TestClient, path: str) -> int:
    count = 0

    def on_execute(*_: object) -> None:
        nonlocal count
        count += 1

    engine = app.state.engine.sync_engine
    event.listen(engine, "before_cursor_execute", on_execute)
    try:
        assert client.get(path).status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", on_execute)
    return count


@pytest.mark.parametrize("path", sorted(MAX_QUERIES))
def test_query_count_does_not_grow_with_data(app: FastAPI, client: TestClient, path: str) -> None:
    assert _count_queries(app, client, path) <= MAX_QUERIES[path]


@pytest.mark.parametrize(
    "path", ["/health", "/api/v1/me/capabilities", "/api/v1/outlets", "/api/v1/settings"]
)
def test_nfr_001_p95_latency(client: TestClient, path: str) -> None:
    client.get(path)  # warm up connections
    timings = []
    for _ in range(40):
        start = time.perf_counter()
        assert client.get(path).status_code == 200
        timings.append((time.perf_counter() - start) * 1000)
    p95 = statistics.quantiles(timings, n=20)[18]
    assert p95 < P95_LIMIT_MS, f"{path} p95 {p95:.0f} ms"
