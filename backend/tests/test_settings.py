"""Slice 1a: tenant settings (FR-TEN-004 to 009)."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from hypothesis import example, given
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.config import Settings
from app.core.identity.passwords import _hasher
from app.core.settings import service
from app.core.settings.pricing import calculate, round_half_up_div
from app.core.settings.schemas import ServiceChargeSettings, TaxRule, TaxSettings
from app.core.tenancy import tenant_session
from app.main import create_app
from tests.factories import add_member, drop_tenant, seed_tenant
from tests.test_auth import new_client, owner
from tests.test_auth_mfa import enroll_as

PW = "settings test passphrase"
HASH = _hasher.hash(PW)


# --- Pricing (FR-TEN-004/005, docs/05 section 6) -----------------------------------------


def taxes(*rules: TaxRule) -> TaxSettings:
    return TaxSettings(rules=list(rules))


PBJT = TaxRule(id="pbjt", name="PBJT", rate_bp=1000)
NO_SC = ServiceChargeSettings()


def test_fr_ten_004_exclusive_tax_example() -> None:
    totals = calculate([25000], tax=taxes(PBJT), service_charge=NO_SC, channel="dine_in")
    assert (totals.net, totals.tax_total, totals.total) == (25000, 2500, 27500)


def test_fr_ten_005_service_charge_before_tax() -> None:
    sc = ServiceChargeSettings(enabled=True, rate_bp=500)
    totals = calculate([100000], tax=taxes(PBJT), service_charge=sc, channel="dine_in")
    assert (totals.service_charge, totals.tax_total, totals.total) == (5000, 10500, 115500)
    takeaway_only = ServiceChargeSettings(enabled=True, rate_bp=500, channels=["dine_in"])
    assert (
        calculate(
            [100000], tax=taxes(PBJT), service_charge=takeaway_only, channel="takeaway"
        ).service_charge
        == 0
    )


def test_rounding_is_half_up_once_per_document() -> None:
    assert round_half_up_div(5, 10) == 1 and round_half_up_div(4, 10) == 0
    assert round_half_up_div(-5, 10) == -1  # refunds round symmetrically
    # Three lines of Rp 333 at 10 %: one rounding on 999 (99.9 -> 100), not three of 33.3.
    totals = calculate([333, 333, 333], tax=taxes(PBJT), service_charge=NO_SC, channel="x")
    assert totals.tax_total == 100


@example(lines=[9620], rates=[1867, 0], inclusive=True, sc_bp=0)  # found by Hypothesis
@given(
    lines=st.lists(st.integers(min_value=0, max_value=50_000_000), min_size=1, max_size=30),
    rates=st.lists(st.integers(min_value=0, max_value=3000), min_size=0, max_size=3),
    inclusive=st.booleans(),
    sc_bp=st.integers(min_value=0, max_value=2000),
)
def test_totals_always_add_up(
    lines: list[int], rates: list[int], inclusive: bool, sc_bp: int
) -> None:
    rules = [
        TaxRule(id=f"t{i}", name="T", rate_bp=r, price_includes_tax=inclusive, order=i)
        for i, r in enumerate(rates)
    ]
    sc = ServiceChargeSettings(enabled=sc_bp > 0, rate_bp=sc_bp)
    totals = calculate(lines, tax=taxes(*rules), service_charge=sc, channel="dine_in")
    assert totals.total == totals.net + totals.service_charge + totals.tax_total
    assert all(t.amount >= 0 for t in totals.taxes) and totals.net >= 0
    if inclusive:  # customer pays exactly the listed prices plus service charge
        assert totals.net + sum(t.amount for t in totals.taxes) == sum(lines)


# --- API -----------------------------------------------------------------------------------


@pytest.fixture
def world() -> Iterator[dict[str, object]]:
    a, roles_a = seed_tenant("Alpha")
    ck, roles_ck = seed_tenant("Cloud")
    owner("UPDATE tenants SET profile = 'cloud_kitchen' WHERE id = :t", {"t": ck})
    _, owner_a = add_member(a, roles_a["owner"], HASH)
    _, cashier_a = add_member(a, roles_a["cashier"], HASH)
    _, owner_ck = add_member(ck, roles_ck["owner"], HASH)
    yield {
        "a": a,
        "ck": ck,
        "roles_a": roles_a,
        "owner_a": owner_a,
        "cashier_a": cashier_a,
        "owner_ck": owner_ck,
    }
    drop_tenant(a)
    drop_tenant(ck)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with new_client(create_app(settings)) as c:
        yield c


def signin(client: TestClient, email: str) -> str:
    client.cookies.clear()
    body = client.post("/api/v1/auth/login", json={"email": email, "password": PW}).json()
    return str(body["csrf_token"])


def test_defaults_come_from_the_country(client: TestClient, world: dict[str, object]) -> None:
    signin(client, str(world["cashier_a"]))
    data = client.get("/api/v1/settings").json()
    assert data["tax"]["rules"][0]["id"] == "pbjt"
    assert data["service_charge"]["enabled"] is False
    assert {m["code"] for m in data["payment_methods"]["methods"]} >= {"cash", "qris"}


def test_owner_changes_settings_with_audit_and_cashier_cannot(
    client: TestClient, world: dict[str, object]
) -> None:
    csrf = enroll_as(client, str(world["owner_a"]), PW)[2]
    new = {
        "rules": [
            {"id": "pbjt", "name": "PBJT Jakarta", "rate_bp": 1000},
            {"id": "ppn", "name": "PPN", "rate_bp": 1100, "order": 1},
        ]
    }
    ok = client.put("/api/v1/settings/tax", json=new, headers={"X-CSRF-Token": csrf})
    assert ok.status_code == 200, ok.text
    audit = owner(
        "SELECT summary FROM audit_log WHERE tenant_id = :t AND action = 'settings.tax.updated'",
        {"t": world["a"]},
    )
    assert audit and audit[0][0]["before"]["rules"][0]["name"] == "PBJT"

    csrf = signin(client, str(world["cashier_a"]))
    assert len(client.get("/api/v1/settings").json()["tax"]["rules"]) == 2
    denied = client.put("/api/v1/settings/tax", json=new, headers={"X-CSRF-Token": csrf})
    assert denied.status_code == 403


@pytest.mark.parametrize(
    "body",
    [
        {"rules": [{"id": "x", "name": "X", "rate_bp": 20000}]},  # over 100 %
        {"rules": [{"id": "x", "name": "X", "rate_bp": 10, "surprise": True}]},  # unknown field
        {"rules": [{"id": "x", "name": "X", "rate_bp": 1}, {"id": "x", "name": "Y", "rate_bp": 2}]},
        {"rules": [{"id": "x", "name": "X", "rate_bp": 0.5}]},  # no floats
    ],
)
def test_invalid_settings_are_rejected(
    client: TestClient, world: dict[str, object], body: dict[str, object]
) -> None:
    csrf = enroll_as(client, str(world["owner_a"]), PW)[2]
    response = client.put("/api/v1/settings/tax", json=body, headers={"X-CSRF-Token": csrf})
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_setting"


def test_fr_ten_005_cloud_kitchen_cannot_enable_service_charge(
    client: TestClient, world: dict[str, object]
) -> None:
    csrf = enroll_as(client, str(world["owner_ck"]), PW)[2]
    response = client.put(
        "/api/v1/settings/service_charge",
        json={"enabled": True, "rate_bp": 500},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 422


def test_settings_are_isolated_per_tenant(client: TestClient, world: dict[str, object]) -> None:
    csrf = enroll_as(client, str(world["owner_a"]), PW)[2]
    client.put(
        "/api/v1/settings/session", json={"idle_minutes": 15}, headers={"X-CSRF-Token": csrf}
    )
    enroll_as(client, str(world["owner_ck"]), PW)
    assert client.get("/api/v1/settings").json()["session"]["idle_minutes"] == 60


def test_fr_ten_007_approval_rules(client: TestClient, world: dict[str, object]) -> None:
    roles = world["roles_a"]
    assert isinstance(roles, dict)
    csrf = enroll_as(client, str(world["owner_a"]), PW)[2]
    for amount, role in ((5_000_000, "manager"), (20_000_000, "co_owner")):
        r = client.post(
            "/api/v1/approval-rules",
            headers={"X-CSRF-Token": csrf},
            json={
                "document_type": "purchase_order",
                "min_amount": amount,
                "approver_role_id": str(roles[role]),
            },
        )
        assert r.status_code == 201, r.text
    foreign_role = uuid.uuid4()  # not a role of this tenant: rejected by the database
    bad = client.post(
        "/api/v1/approval-rules",
        headers={"X-CSRF-Token": csrf},
        json={
            "document_type": "purchase_order",
            "min_amount": 1,
            "approver_role_id": str(foreign_role),
        },
    )
    assert bad.status_code == 422, bad.text
    assert bad.json()["code"] == "invalid_reference"
    assert len(client.get("/api/v1/approval-rules").json()) == 2


# --- Numbering (FR-TEN-009) ------------------------------------------------------------------


@pytest.mark.anyio
async def test_fr_ten_009_numbers_are_unique_under_concurrency(
    engine: AsyncEngine, world: dict[str, object]
) -> None:
    tenant = world["a"]
    assert isinstance(tenant, uuid.UUID)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def one() -> str:
        async with tenant_session(sessions, tenant) as db:
            return await service.allocate_number(
                db, tenant_id=tenant, doc_type="purchase_order", on=date(2026, 10, 7)
            )

    numbers = await asyncio.gather(*(one() for _ in range(20)))
    assert len(set(numbers)) == 20
    assert sorted(numbers)[0] == "PO-2026-00001" and sorted(numbers)[-1] == "PO-2026-00020"
    async with tenant_session(sessions, tenant) as db:  # yearly reset
        assert (
            await service.allocate_number(
                db, tenant_id=tenant, doc_type="purchase_order", on=date(2027, 1, 1)
            )
            == "PO-2027-00001"
        )


@pytest.mark.anyio
async def test_rolled_back_document_does_not_burn_a_number(
    engine: AsyncEngine, world: dict[str, object]
) -> None:
    tenant = world["a"]
    assert isinstance(tenant, uuid.UUID)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    with pytest.raises(RuntimeError):
        async with tenant_session(sessions, tenant) as db:
            await service.allocate_number(
                db, tenant_id=tenant, doc_type="transfer", on=date(2026, 1, 1)
            )
            raise RuntimeError("document failed")
    async with tenant_session(sessions, tenant) as db:
        assert (
            await service.allocate_number(
                db, tenant_id=tenant, doc_type="transfer", on=date(2026, 1, 1)
            )
            == "TRF-2026-00001"
        )
