"""Seed a load-test tenant on a running API (NFR-001 load test, slice 1n).

    python -m tests.load.seed http://127.0.0.1:8000 > /tmp/load-seed.json

Uses the test database owner to create the tenant and a manager (like tests/factories.py),
then the public API for everything else: 40 ingredients, 30 menu items with recipes, a
delivery channel with prices, opening stock and 60 days of daily sales. Local only."""

import json
import random
import sys
import uuid
from datetime import date, timedelta
from typing import Any

import httpx

from tests.factories import add_member, add_outlet, seed_tenant
from tests.test_inventory import HASH, PW

DAYS = 60


class Api:
    def __init__(self, base: str) -> None:
        self.http = httpx.Client(base_url=base, timeout=30)
        self.headers: dict[str, str] = {}

    def login(self, email: str) -> None:
        res = self.http.post("/api/v1/auth/login", json={"email": email, "password": PW})
        # The session cookie is Secure (__Host-); locally there is no TLS, so send it as a header.
        cookie = res.headers["set-cookie"].split(";", 1)[0]
        self.headers = {"X-CSRF-Token": res.json()["csrf_token"], "Cookie": cookie}

    def call(self, method: str, path: str, body: Any = None, key: bool = False) -> Any:
        headers = {**self.headers, **({"Idempotency-Key": str(uuid.uuid4())} if key else {})}
        res = self.http.request(method, path, json=body, headers=headers)
        if res.status_code >= 400:
            raise SystemExit(f"{method} {path}: {res.status_code} {res.text}")
        return res.json() if res.content else None


def item(api: Api, units: dict[str, str], sku: str, kind: str, unit: str) -> str:
    body = {
        "sku": sku,
        "type": kind,
        "base_unit_id": units[unit],
        "is_stocked": kind != "menu",
        "storage_type": "dry",
        "translations": [
            {"language": "en", "name": sku.title()},
            {"language": "id", "name": sku.title()},
        ],
    }
    return str(api.call("POST", "/api/v1/catalog/items", body)["id"])


def main(base: str) -> None:
    rng = random.Random(7)  # noqa: S311 - test data, same every run; not security
    tenant, roles = seed_tenant(
        "Load test kitchen", modules=("inventory", "sales", "purchasing", "production")
    )
    outlet = add_outlet(tenant, "Load shop")
    _, email = add_member(tenant, roles["manager"], HASH)
    api = Api(base)
    api.login(email)
    units = {u["code"]: u["id"] for u in api.call("GET", "/api/v1/catalog/units")}
    ingredients = [item(api, units, f"ING-{i:02d}", "ingredient", "g") for i in range(40)]
    channel = api.call(
        "POST",
        "/api/v1/catalog/channels",
        {"code": "gofood", "name": "GoFood", "kind": "platform", "platform": "gofood"},
    )["id"]
    menu = []
    for i in range(30):
        dish = item(api, units, f"MENU-{i:02d}", "menu", "pcs")
        lines = [
            {
                "component_item_id": c,
                "qty": str(rng.randint(20, 200)),
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
    start = date.today() - timedelta(days=DAYS)
    opening = [
        {
            "item_id": c,
            "qty": "500",
            "unit_id": units["kg"],
            "unit_cost": str(rng.randint(10, 80) * 1000),
        }
        for c in ingredients
    ]
    api.call(
        "POST",
        "/api/v1/inventory/opening",
        {"outlet_id": str(outlet), "business_date": start.isoformat(), "lines": opening},
        key=True,
    )
    for d in range(DAYS):
        lines = [{"item_id": m, "qty": str(rng.randint(1, 12))} for m in rng.sample(menu, 15)]
        day = (start + timedelta(days=d + 1)).isoformat()
        api.call(
            "POST",
            "/api/v1/sales/days/entries",
            {"outlet_id": str(outlet), "business_date": day, "channel_id": channel, "lines": lines},
            key=True,
        )
    json.dump(
        {
            "email": email,
            "password": PW,
            "outlet_id": str(outlet),
            "channel_id": channel,
            "menu": menu,
            "ingredients": ingredients,
            "tenant_id": str(tenant),
            "gram": units["g"],
        },
        sys.stdout,
    )


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000")
