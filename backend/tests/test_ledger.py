"""Slice 3c: general ledger (FR-FIN-002), manual journals with approval (FR-FIN-004),
period close (FR-FIN-005), start date and opening balances (FR-FIN-009); isolation."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.factories import add_member, add_outlet, drop_tenant, seed_tenant
from tests.test_auth_mfa import enroll_as
from tests.test_inventory import HASH, PW, login
from tests.test_purchasing import client as client

G = "/api/v1/finance/gl"


@pytest.fixture
def world() -> Iterator[dict[str, Any]]:
    a, roles = seed_tenant("Alpha", modules=("inventory", "sales", "finance"))
    b, roles_b = seed_tenant("Beta", modules=("inventory", "sales", "finance"))
    w: dict[str, Any] = {"a": a, "shop": add_outlet(a, "Shop"), "roles": roles}
    w["owner_a"] = add_member(a, roles["owner"], HASH)[1]
    w["acc1"] = add_member(a, roles["accountant"], HASH)[1]
    w["acc2"] = add_member(a, roles["accountant"], HASH)[1]
    w["cashier_a"] = add_member(a, roles["cashier"], HASH)[1]
    w["acc_b"] = add_member(b, roles_b["accountant"], HASH)[1]
    yield w
    drop_tenant(a)
    drop_tenant(b)


def accounts(client: TestClient, h: dict[str, str]) -> dict[str, str]:
    rows = client.get(f"{G}/accounts", headers=h).json()
    return {r["system_key"] or r["code"]: r["id"] for r in rows}


def journal(client: TestClient, h: dict[str, str], day: str, lines: list[Any]) -> Any:
    return client.post(
        f"{G}/journals", json={"entry_date": day, "memo": "x", "lines": lines}, headers=h
    )


def test_fr_fin_002_009_setup_journals_and_statements(
    client: TestClient, world: dict[str, Any]
) -> None:
    h = login(client, world["acc1"])
    assert client.get(f"{G}/setup", headers=h).json() is None
    early = journal(client, h, "2026-01-05", [])
    assert early.status_code == 422  # at least two lines
    opening = [{"account_code": "1-1200", "debit": 3_000_000}]  # bank; equity balances it
    made = client.post(
        f"{G}/setup", json={"start_date": "2026-01-01", "opening": opening}, headers=h
    )
    assert made.status_code == 201, made.text
    assert made.json()["opening_entry_id"]
    acc = accounts(client, h)
    assert acc["cash"] and acc["6-1100"]  # Indonesian F&B template, rent is 6-1100
    assert (
        client.post(f"{G}/setup", json={"start_date": "2026-01-01"}, headers=h).json()["code"]
        == "ledger_already_set_up"
    )

    # Opening cash would normally come with setup; here a journal moves capital into cash.
    capital = [
        {"account_id": acc["cash"], "debit": 5_000_000},
        {"account_id": acc["3-1000"], "credit": 5_000_000},
    ]
    assert journal(client, h, "2026-01-02", capital).json()["status"] == "posted"
    rent = [
        {"account_id": acc["6-1100"], "debit": 1_000_000},
        {"account_id": acc["cash"], "credit": 1_000_000},
    ]
    posted = journal(client, h, "2026-01-10", rent).json()
    assert posted["number"].startswith("JE-2026-") and posted["total"] == 1_000_000
    bad = [{"account_id": acc["cash"], "debit": 10}, {"account_id": acc["6-1100"], "credit": 9}]
    assert journal(client, h, "2026-01-10", bad).json()["code"] == "journal_not_balanced"
    before = journal(client, h, "2025-12-31", rent)
    assert before.json()["code"] == "before_books_start"

    trial = {
        r["code"]: r for r in client.get(f"{G}/trial-balance?until=2026-01-31", headers=h).json()
    }
    assert trial["1-1100"]["balance"] == 4_000_000 and trial["6-1100"]["balance"] == 1_000_000
    assert trial["1-1200"]["balance"] == trial["3-9000"]["balance"] == 3_000_000  # opening
    assert sum(r["debit"] for r in trial.values()) == sum(r["credit"] for r in trial.values())
    sheet = client.get(f"{G}/balance-sheet?as_of=2026-01-31", headers=h).json()
    assert sheet["total_assets"] == sheet["total_liabilities_equity"] == 7_000_000
    assert sheet["current_earnings"] == -1_000_000
    flow = client.get(f"{G}/cash-flow?since=2026-01-01&until=2026-01-31", headers=h).json()
    assert (flow["opening"], flow["financing"], flow["operating"]) == (
        3_000_000,
        5_000_000,
        -1_000_000,
    )
    assert flow["closing"] == 7_000_000

    # A correction is a reversing entry, once.
    back = client.post(
        f"{G}/journals/{posted['id']}/reverse", json={"entry_date": "2026-01-11"}, headers=h
    ).json()
    assert back["reverses_id"] == posted["id"] and back["lines"][0]["credit"] == 1_000_000
    again = client.post(
        f"{G}/journals/{posted['id']}/reverse", json={"entry_date": "2026-01-11"}, headers=h
    )
    assert again.json()["code"] == "already_reversed"


def test_fr_fin_005_closed_period_blocks_posting(client: TestClient, world: dict[str, Any]) -> None:
    h = login(client, world["acc1"])
    client.post(f"{G}/setup", json={"start_date": "2026-01-01"}, headers=h)
    acc = accounts(client, h)
    lines = [
        {"account_id": acc["6-1100"], "debit": 100},
        {"account_id": acc["cash"], "credit": 100},
    ]
    assert client.post(f"{G}/periods/2026/1/close", headers=h).json()["status"] == "closed"
    shut = journal(client, h, "2026-01-20", lines)
    assert shut.status_code == 409 and shut.json()["code"] == "period_closed"
    assert journal(client, h, "2026-02-01", lines).json()["status"] == "posted"
    assert client.post(f"{G}/periods/2026/1/reopen", headers=h).json()["status"] == "open"
    assert journal(client, h, "2026-01-20", lines).json()["status"] == "posted"


def test_fr_fin_004_large_journal_needs_another_persons_approval(
    client: TestClient, world: dict[str, Any]
) -> None:
    csrf = enroll_as(client, world["owner_a"], PW)[2]
    o = {"X-CSRF-Token": csrf}
    rule = {
        "document_type": "journal",
        "min_amount": 1_000_000,
        "approver_role_id": str(world["roles"]["accountant"]),
    }
    assert client.post("/api/v1/approval-rules", json=rule, headers=o).status_code == 201
    client.post(f"{G}/setup", json={"start_date": "2026-01-01"}, headers=o)
    h = login(client, world["acc1"])
    acc = accounts(client, h)
    big = [
        {"account_id": acc["6-1100"], "debit": 2_000_000},
        {"account_id": acc["cash"], "credit": 2_000_000},
    ]
    entry = journal(client, h, "2026-01-15", big).json()
    assert entry["status"] == "submitted"
    trial = client.get(f"{G}/trial-balance?until=2026-01-31", headers=h).json()
    assert trial == []  # not in the books until approved
    own = client.post(f"{G}/journals/{entry['id']}/approve", headers=h)
    assert own.status_code == 403 and own.json()["code"] == "cannot_approve_own_request"
    assert (
        client.post(f"{G}/periods/2026/1/close", headers=h).json()["code"]
        == "period_has_pending_journals"
    )
    h2 = login(client, world["acc2"])
    assert (
        client.post(f"{G}/journals/{entry['id']}/approve", headers=h2).json()["status"] == "posted"
    )
    # Isolation and permissions.
    assert client.get(f"{G}/accounts", headers=login(client, world["cashier_a"])).status_code == 403
    assert client.get(f"{G}/accounts", headers=login(client, world["acc_b"])).json() == []
