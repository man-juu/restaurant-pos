"""Seed a POS load-test tenant on a running API (slice 2l, NFR-001 and NFR-002).

    python -m tests.load.seed_pos http://127.0.0.1:8000 > /tmp/pos-seed.json

Four outlets, each with opening stock, 30 menu items with recipes and a dine-in price, and
an open cash shift for the cashier at every outlet. Local only (uses the test database
owner like tests/factories.py)."""

import json
import random
import sys

from tests.factories import add_member, add_outlet, seed_tenant
from tests.load.seed import Api, item
from tests.test_inventory import HASH, PW

OUTLETS = 4


def main(base: str) -> None:
    rng = random.Random(11)  # noqa: S311 - test data, same every run; not security
    tenant, roles = seed_tenant("POS load test", modules=("inventory", "sales"))
    outlets = [str(add_outlet(tenant, f"Outlet {i + 1}")) for i in range(OUTLETS)]
    _, email = add_member(tenant, roles["manager"], HASH)
    api = Api(base)
    api.login(email)
    units = {u["code"]: u["id"] for u in api.call("GET", "/api/v1/catalog/units")}
    ingredients = [item(api, units, f"ING-{i:02d}", "ingredient", "g") for i in range(25)]
    channel = api.call(
        "POST",
        "/api/v1/catalog/channels",
        {"code": "dinein", "name": "Dine in", "kind": "dine_in"},
    )["id"]
    menu = []
    for i in range(30):
        dish = item(api, units, f"MENU-{i:02d}", "menu", "pcs")
        lines = [
            {
                "component_item_id": c,
                "qty": str(rng.randint(20, 150)),
                "unit_id": units["g"],
                "waste_pct": "0",
            }
            for c in rng.sample(ingredients, 4)
        ]
        bom = api.call("POST", f"/api/v1/catalog/items/{dish}/boms", {"lines": lines})
        api.call("POST", f"/api/v1/catalog/boms/{bom['id']}/activate", {"valid_from": "2025-01-01"})
        price = {
            "channel_id": channel,
            "valid_from": "2025-01-01",
            "price": rng.randint(15, 45) * 1000,
        }
        api.call("PUT", f"/api/v1/catalog/items/{dish}/prices", price)
        menu.append(dish)
    opening = [
        {
            "item_id": c,
            "qty": "2000",
            "unit_id": units["kg"],
            "unit_cost": str(rng.randint(10, 80) * 1000),
        }
        for c in ingredients
    ]
    for outlet in outlets:
        api.call(
            "POST",
            "/api/v1/inventory/opening",
            {"outlet_id": outlet, "business_date": "2025-01-01", "lines": opening},
            key=True,
        )
        api.call("POST", "/api/v1/pos/shifts", {"outlet_id": outlet, "opening_float": 500000})
    json.dump(
        {"email": email, "password": PW, "outlets": outlets, "channel_id": channel, "menu": menu},
        sys.stdout,
    )


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000")
