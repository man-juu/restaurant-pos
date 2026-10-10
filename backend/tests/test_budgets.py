"""Slice 4b: budgets per outlet and month with actual vs budget (FR-FIN-010)."""

from typing import Any

from fastapi.testclient import TestClient

from app.modules.finance.budget import _line
from tests.test_finance import world as world
from tests.test_inventory import login
from tests.test_purchasing import client as client
from tests.test_sales_days import DAY, enter, entry
from tests.test_sales_days import menu as menu

B = "/api/v1/finance/budgets"


def test_fr_fin_010_variance_direction() -> None:
    sales = _line("net_sales", 1000, 900)
    assert (sales.variance, sales.variance_pct, sales.favourable) == (-100, "-10.0", False)
    cost = _line("labor", 1000, 900)
    assert cost.favourable and _line("expenses", 0, 5).variance_pct is None


def test_fr_fin_010_budget_vs_actual(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    m = login(client, world["manager_a"])
    assert enter(client, m, entry(world, menu, "10")).status_code == 201
    acc = login(client, world["accountant_a"])
    plan = {
        "outlet_id": str(world["shop"]),
        "month": DAY,
        "net_sales": 300_000,
        "cost_of_sales": 50_000,
        "labor": 0,
        "expenses": 0,
    }
    assert client.put(B, json=plan, headers=acc).status_code == 204
    again = {**plan, "net_sales": 200_000}  # saving the month again replaces it
    assert client.put(B, json=again, headers=acc).status_code == 204
    q = f"from={DAY[:8]}01&to={DAY[:8]}31&outlet_id={world['shop']}"
    [saved] = client.get(f"{B}?{q}", headers=acc).json()
    assert saved["net_sales"] == 200_000
    r = client.get(f"{B}/vs-actual?{q}", headers=acc)
    assert r.status_code == 200, r.text
    lines = {x["line"]: x for x in r.json()["lines"]}
    assert lines["net_sales"]["actual"] == 250_000 and lines["net_sales"]["variance"] == 50_000
    assert lines["net_sales"]["favourable"] and r.json()["months_missing"] == []
    assert lines["net_profit"]["budget"] == 150_000

    # Server decides: a cashier may neither set nor read budgets.
    c = login(client, world["cashier_a"])
    assert client.put(B, json=plan, headers=c).status_code == 403
    assert client.get(f"{B}/vs-actual?{q}", headers=c).status_code == 403

    # Tenant isolation: another tenant's accountant cannot budget this outlet or see the plan.
    accb = login(client, world["accountant_b"])
    assert client.put(B, json=plan, headers=accb).status_code in (403, 404)
    assert client.get(f"{B}?from={DAY[:8]}01&to={DAY[:8]}31", headers=accb).json() == []
