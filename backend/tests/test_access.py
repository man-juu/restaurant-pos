"""Slice 0.5: authorization (FR-IDN-010, FR-TEN-003, FR-SUB-003/004; docs/03, docs/06 sec. 4)."""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

import app.modules
from app.core.access.permissions import PermissionError_, build_registry
from app.core.access.policy import (
    Principal,
    permissions_by_route,
    require,
    undeclared_routes,
)
from app.core.access.subscription import SubscriptionInfo, effective_state
from app.core.approvals import (
    LimitExceeded,
    SelfApprovalForbidden,
    ensure_not_own_request,
    ensure_within_limit,
)
from app.core.config import Settings
from app.core.identity.passwords import _hasher
from app.core.modules import ModuleManifest, discover
from app.main import create_app
from tests.factories import add_member, add_outlet, drop_tenant, seed_tenant
from tests.test_auth import new_client, owner
from tests.test_auth_mfa import enroll_as

PW = "access test passphrase"
HASH = _hasher.hash(PW)


def signin(client: TestClient, email: str) -> str:
    client.cookies.clear()
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PW})
    assert response.status_code == 200, response.text
    return str(response.json()["csrf_token"])


@dataclass
class Tenants:
    a: uuid.UUID
    roles_a: dict[str, uuid.UUID]
    b: uuid.UUID
    outlet_a1: uuid.UUID
    outlet_a2: uuid.UUID
    outlet_b: uuid.UUID


@pytest.fixture
def tenants() -> Iterator[Tenants]:
    a, roles_a = seed_tenant("Alpha")
    b, _ = seed_tenant("Beta")
    t = Tenants(a, roles_a, b, add_outlet(a, "A1"), add_outlet(a, "A2"), add_outlet(b, "B1"))
    yield t
    drop_tenant(a)
    drop_tenant(b)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with new_client(create_app(settings)) as c:
        yield c


# --- Deny by default ------------------------------------------------------------------


def test_every_route_declares_an_access_rule(settings: Settings) -> None:
    api = create_app(settings)  # also asserted at start-up
    registry = api.state.permission_registry
    assert undeclared_routes(api, registry) == []
    assert any(True for _ in permissions_by_route(api))


def test_undeclared_route_is_reported(settings: Settings) -> None:
    api = create_app(settings)

    @api.get("/api/v1/forgotten")
    async def forgotten() -> None:
        return None

    problems = undeclared_routes(api, api.state.permission_registry)
    assert problems == ["GET /api/v1/forgotten: no require(...) or public()"]


def test_app_refuses_to_start_with_unprotected_module_route(settings: Settings) -> None:
    router = APIRouter()

    @router.get("/leaky")
    async def leaky() -> None:
        return None

    with pytest.raises(RuntimeError, match="no require"):
        create_app(settings, manifests=[ModuleManifest("inventory", routers=(router,))])


def test_fr_idn_010_role_without_permission_gets_403_on_every_protected_route(
    client: TestClient, tenants: Tenants
) -> None:
    """Generated over all routes: a member whose role has no permissions is refused."""
    empty_role = uuid.uuid4()
    owner(
        "INSERT INTO roles (id, tenant_id, name) VALUES (:r, :t, 'Nothing')",
        {"r": empty_role, "t": tenants.a},
    )
    _, email = add_member(tenants.a, empty_role, HASH)
    csrf = signin(client, email)
    checked = 0
    for full_path, route, permission in permissions_by_route(client.app):  # type: ignore[arg-type]
        path = full_path
        for name in route.param_convertors:
            path = path.replace("{" + name + "}", str(uuid.uuid4()))
        for method in route.methods or ():
            response = client.request(method, path, json={}, headers={"X-CSRF-Token": csrf})
            assert response.status_code == 403, (method, path, response.text)
            assert response.json()["code"] == "permission_denied"
            assert response.json()["details"] == {"permission": permission}
            checked += 1
    assert checked >= 3


# --- Tenant and outlet scope ------------------------------------------------------------


def test_other_tenants_object_is_404(client: TestClient, tenants: Tenants) -> None:
    _, email = add_member(tenants.a, tenants.roles_a["viewer"], HASH)
    signin(client, email)
    assert client.get(f"/api/v1/outlets/{tenants.outlet_a1}").status_code == 200
    response = client.get(f"/api/v1/outlets/{tenants.outlet_b}")
    assert response.status_code == 404


def test_outlet_scope_limits_lists_and_objects(client: TestClient, tenants: Tenants) -> None:
    _, email = add_member(tenants.a, tenants.roles_a["manager"], HASH, outlets=(tenants.outlet_a1,))
    signin(client, email)
    names = [o["name"] for o in client.get("/api/v1/outlets").json()]
    assert names == ["A1"]
    assert client.get(f"/api/v1/outlets/{tenants.outlet_a2}").status_code == 404


def test_removed_outlet_assignment_applies_immediately(
    client: TestClient, tenants: Tenants
) -> None:
    _, email = add_member(tenants.a, tenants.roles_a["manager"], HASH, outlets=(tenants.outlet_a1,))
    signin(client, email)
    assert client.get(f"/api/v1/outlets/{tenants.outlet_a1}").status_code == 200
    owner("DELETE FROM membership_outlets WHERE outlet_id = :o", {"o": tenants.outlet_a1})
    assert client.get(f"/api/v1/outlets/{tenants.outlet_a1}").status_code == 404


# --- Subscription state -----------------------------------------------------------------


@pytest.fixture
def expired() -> Iterator[tuple[uuid.UUID, dict[str, uuid.UUID]]]:
    tenant, roles = seed_tenant(
        "Expired", plan_type="paid", ends_at=datetime.now(UTC) - timedelta(days=30)
    )
    yield tenant, roles
    drop_tenant(tenant)


def test_fr_sub_004_read_only_blocks_writes_but_allows_reads(
    client: TestClient, expired: tuple[uuid.UUID, dict[str, uuid.UUID]]
) -> None:
    tenant, roles = expired
    _, email = add_member(tenant, roles["owner"], HASH)
    csrf = enroll_as(client, email, PW)[2]
    assert client.get("/api/v1/outlets").status_code == 200
    caps = client.get("/api/v1/me/capabilities").json()
    assert caps["subscription"]["state"] == "read_only"
    blocked = client.post(
        "/api/v1/invitations",
        json={"email": "x@example.test", "role_id": str(roles["cashier"])},
        headers={"X-CSRF-Token": csrf},
    )
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "subscription_read_only"


def test_suspended_tenant_blocks_everything(client: TestClient, tenants: Tenants) -> None:
    _, email = add_member(tenants.a, tenants.roles_a["viewer"], HASH)
    signin(client, email)
    owner("UPDATE subscriptions SET suspended = true WHERE tenant_id = :t", {"t": tenants.a})
    response = client.get("/api/v1/outlets")
    assert response.status_code == 403
    assert response.json()["code"] == "tenant_suspended"


NOW = datetime(2026, 10, 7, tzinfo=UTC)


@pytest.mark.parametrize(
    ("ends_in_days", "expected"),
    [(30, "active"), (10, "expiring"), (0, "grace"), (-6, "grace"), (-7, "read_only")],
)
def test_fr_sub_003_state_follows_the_clock(ends_in_days: int, expected: str) -> None:
    sub = SubscriptionInfo("paid", NOW + timedelta(days=ends_in_days), 7, True, (14, 7), False)
    assert effective_state(sub, NOW) == expected


def test_subscription_edge_cases() -> None:
    assert effective_state(None, NOW) == "read_only"  # fail closed
    assert effective_state(SubscriptionInfo("free", None, 7, True, (), False), NOW) == "free"
    paid_suspended = SubscriptionInfo("paid", NOW + timedelta(days=99), 7, True, (), True)
    assert effective_state(paid_suspended, NOW) == "suspended"


# --- Modules ------------------------------------------------------------------------------


def _inventory_manifest() -> ModuleManifest:
    router = APIRouter(prefix="/api/v1/inventory")

    @router.get("/items")
    async def items(
        p: Annotated[Principal, Depends(require("inventory.item.view"))],
    ) -> dict[str, Any]:
        return {"ok": True}

    return ModuleManifest(
        "inventory",
        routers=(router,),
        permissions=("inventory.item.view",),
        role_templates={"manager": ("inventory.item.view",)},
        nav=("inventory",),
    )


def test_fr_ten_003_disabled_module_returns_403(settings: Settings, tenants: Tenants) -> None:
    api = create_app(settings, manifests=[_inventory_manifest()])
    # Seeded roles predate this fake module, so grant the permission explicitly.
    owner(
        "INSERT INTO role_permissions (id, tenant_id, role_id, permission_code) "
        "VALUES (gen_random_uuid(), :t, :r, 'inventory.item.view')",
        {"t": tenants.a, "r": tenants.roles_a["manager"]},
    )
    _, email = add_member(tenants.a, tenants.roles_a["manager"], HASH)
    with new_client(api) as client:
        signin(client, email)
        off = client.get("/api/v1/inventory/items")
        assert off.status_code == 403
        assert off.json()["code"] == "module_disabled"
        assert "inventory" not in client.get("/api/v1/me/capabilities").json()["nav"]
        owner(
            "INSERT INTO tenant_modules (tenant_id, module) VALUES (:t, 'inventory')",
            {"t": tenants.a},
        )
        assert client.get("/api/v1/inventory/items").status_code == 200
        assert "inventory" in client.get("/api/v1/me/capabilities").json()["nav"]


# --- Templates, approvals, capabilities -------------------------------------------------


def test_role_templates_follow_docs_03() -> None:
    registry = build_registry(discover(app.modules))
    assert registry.templates["owner"] == registry.permissions
    assert "tenant.ownership.transfer" not in registry.templates["co_owner"]
    assert "tenant.user.manage" not in registry.templates["manager"]
    assert all(code.endswith(".view") for code in registry.templates["viewer"])  # read-only
    with pytest.raises(PermissionError_):
        build_registry([ModuleManifest("sales", permissions=("inventory.x.view",))])


def test_cannot_approve_own_request_and_limits() -> None:
    me, other = uuid.uuid4(), uuid.uuid4()
    with pytest.raises(SelfApprovalForbidden):
        ensure_not_own_request(requested_by=me, approver=me)
    ensure_not_own_request(requested_by=other, approver=me)
    ensure_within_limit(10, 10, what="discount_percent")
    ensure_within_limit(10_000_000, None, what="approval_amount")
    with pytest.raises(LimitExceeded):
        ensure_within_limit(11, 10, what="discount_percent")


def test_capabilities_reflect_role(client: TestClient, tenants: Tenants) -> None:
    _, email = add_member(tenants.a, tenants.roles_a["viewer"], HASH)
    signin(client, email)
    caps = client.get("/api/v1/me/capabilities").json()
    assert set(caps["permissions"]) == {
        "tenant.outlet.view",
        "audit.log.view",
        "catalog.item.view",
        "catalog.cost.view",
    }
    assert caps["subscription"] == {"state": "free", "days_left": None}


def test_co_owner_cannot_grant_owner_role(client: TestClient, tenants: Tenants) -> None:
    _, email = add_member(tenants.a, tenants.roles_a["co_owner"], HASH)
    csrf = enroll_as(client, email, PW)[2]
    response = client.post(
        "/api/v1/invitations",
        json={"email": "boss@example.test", "role_id": str(tenants.roles_a["owner"])},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 403
    ok = client.post(
        "/api/v1/invitations",
        json={"email": "cook@example.test", "role_id": str(tenants.roles_a["cashier"])},
        headers={"X-CSRF-Token": csrf},
    )
    assert ok.status_code == 201
