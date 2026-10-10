"""Slice 3j: menu engineering (FR-RPT-007) and prime cost with typed-in labour (FR-RPT-008)."""

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient

from app.modules.finance.prime import months, share
from app.modules.sales.menu_engineering import _rows, classify
from tests.test_finance import world as world
from tests.test_inventory import login
from tests.test_purchasing import client as client
from tests.test_sales_days import DAY, enter, entry
from tests.test_sales_days import menu as menu

R = "/api/v1/sales/reports"
F = "/api/v1/finance"


class _Name:
    def __init__(self, name: str) -> None:
        self.name = name


def test_fr_rpt_007_kasavana_smith_classes() -> None:
    assert [classify(*k) for k in ((True, True), (True, False), (False, True), (False, False))] == [
        "star",
        "plowhorse",
        "puzzle",
        "dog",
    ]
    ids = ["a", "b", "c", "d"]
    sold = {  # qty, net sales
        "a": (Decimal(50), Decimal(1_500_000)),  # popular, margin 20.000 a plate
        "b": (Decimal(40), Decimal(600_000)),  # popular, margin 5.000
        "c": (Decimal(5), Decimal(250_000)),  # rare, margin 40.000
        "d": (Decimal(5), Decimal(50_000)),  # rare, margin 2.000
    }
    costs = {"a": Decimal(10_000), "b": Decimal(10_000), "c": Decimal(10_000), "d": Decimal(8_000)}
    rows, totals = _rows(sold, costs, {i: _Name(i) for i in ids}, 70)  # type: ignore[arg-type]
    assert {r["name"]: r["class"] for r in rows} == {
        "a": "star",
        "b": "plowhorse",
        "c": "puzzle",
        "d": "dog",
    }
    assert totals["popularity_bar_pct"] == "17.5"  # 70 % of a 25 % fair share


def test_fr_rpt_008_labour_share_by_days() -> None:
    assert months(date(2026, 2, 20), date(2026, 3, 5)) == [date(2026, 2, 1), date(2026, 3, 1)]
    assert share(date(2026, 2, 1), 2_800_000, date(2026, 2, 15), date(2026, 3, 31)) == 1_400_000
    assert share(date(2026, 3, 1), 3_100_000, date(2026, 3, 1), date(2026, 3, 10)) == 1_000_000


def test_menu_engineering_and_prime_cost_endpoints(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    m = login(client, world["manager_a"])
    assert enter(client, m, entry(world, menu, "10")).status_code == 201
    q = f"from={DAY[:8]}01&to={DAY[:8]}31&outlet_id={world['shop']}"
    me = client.get(f"{R}/menu-engineering?{q}", headers=m)
    assert me.status_code == 200, me.text
    [row] = me.json()["rows"]
    assert row["class"] == "star" and row["net_sales"] == 250_000  # the only dish
    c = login(client, world["cashier_a"])
    assert client.get(f"{R}/menu-engineering?{q}", headers=c).status_code == 403

    acc = login(client, world["accountant_a"])
    labour = {"outlet_id": str(world["shop"]), "month": DAY, "amount": 3_100_000}
    assert client.put(f"{F}/labor", json=labour, headers=acc).status_code == 204
    again = {**labour, "amount": 6_200_000}  # saving the month again replaces it
    assert client.put(f"{F}/labor", json=again, headers=acc).status_code == 204
    pc = client.get(f"{F}/prime-cost?{q}", headers=acc).json()
    assert pc["labor"] == 6_200_000 and pc["net_sales"] == 250_000
    assert pc["prime_cost"] == pc["food_cost"] + 6_200_000 and pc["labor_months_missing"] == []
    [saved] = client.get(f"{F}/labor?{q}", headers=acc).json()
    assert saved["amount"] == 6_200_000 and saved["month"] == f"{DAY[:8]}01"
    assert client.put(f"{F}/labor", json=labour, headers=c).status_code == 403
