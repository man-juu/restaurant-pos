"""Slice 2h: registered devices and PIN sign-in (FR-IDN-004): only on a registered device,
only after a full sign-in there, PIN set with the password, lock after 5 wrong tries,
manager reset, revoked devices stop at once, isolation."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.factories import add_member, add_outlet, drop_tenant, seed_tenant
from tests.test_inventory import HASH, PW, login
from tests.test_purchasing import client as client

COOKIE = "__Host-pos_device"


@pytest.fixture
def world() -> Iterator[dict[str, Any]]:
    a, roles = seed_tenant("Alpha", modules=("inventory", "sales"))
    b, roles_b = seed_tenant("Beta", modules=("inventory", "sales"))
    shop = add_outlet(a, "Shop")
    w: dict[str, Any] = {"a": a, "shop": shop}
    w["manager_a"] = add_member(a, roles["manager"], HASH)[1]
    w["cashier_id"], w["cashier_a"] = add_member(a, roles["cashier"], HASH, outlets=(shop,))
    w["waiter_id"], w["waiter_a"] = add_member(a, roles["waiter"], HASH, outlets=(shop,))
    w["manager_b"] = add_member(b, roles_b["manager"], HASH)[1]
    yield w
    drop_tenant(a)
    drop_tenant(b)


def on_device(client: TestClient, token: str, email: str) -> dict[str, str]:
    """Full sign-in on the till: login() clears cookies, so the device cookie is put back."""
    h = login(client, email)
    client.cookies.set(COOKIE, token)
    return h


def pin_login(client: TestClient, user_id: Any, pin: str) -> Any:
    client.cookies.delete("__Host-session")
    return client.post("/api/v1/auth/pin-login", json={"user_id": str(user_id), "pin": pin})


def test_fr_idn_004_pin_sign_in_on_a_registered_device(
    client: TestClient, world: dict[str, Any]
) -> None:
    m = login(client, world["manager_a"])
    made = client.post(
        "/api/v1/devices", json={"name": "Till 1", "outlet_id": str(world["shop"])}, headers=m
    )
    assert made.status_code == 201, made.text
    token = client.cookies.get(COOKIE)
    assert token
    h = on_device(client, token, world["cashier_a"])
    wrong = client.put("/api/v1/me/pin", json={"pin": "1234", "password": "nope"}, headers=h)
    assert wrong.status_code == 401
    assert (
        client.put("/api/v1/me/pin", json={"pin": "12a4", "password": PW}, headers=h).status_code
        == 422
    )
    assert (
        client.put("/api/v1/me/pin", json={"pin": "1234", "password": PW}, headers=h).status_code
        == 204
    )
    # A PIN only works where the person signed in fully: not yet enrolled here.
    assert client.get("/api/v1/auth/device").json()["staff"] == []
    assert client.post("/api/v1/devices/this/enrol", headers=h).status_code == 204
    staff = client.get("/api/v1/auth/device").json()["staff"]
    assert [s["user_id"] for s in staff] == [str(world["cashier_id"])]

    ok = pin_login(client, world["cashier_id"], "1234")
    assert ok.status_code == 200, ok.text
    assert client.get("/api/v1/me/capabilities").status_code == 200
    # Someone who never signed in on this device cannot use a PIN here.
    assert pin_login(client, world["waiter_id"], "1234").status_code == 401

    for _ in range(4):
        assert pin_login(client, world["cashier_id"], "0000").status_code == 401
    assert pin_login(client, world["cashier_id"], "0000").status_code == 429  # 5th: locked
    assert pin_login(client, world["cashier_id"], "1234").status_code == 429  # even the right one

    m = on_device(client, token, world["manager_a"])
    assert client.delete(f"/api/v1/pins/{world['cashier_id']}", headers=m).status_code == 204
    assert client.get("/api/v1/auth/device").json()["staff"] == []
    device_id = made.json()["id"]
    assert client.delete(f"/api/v1/devices/{device_id}", headers=m).status_code == 204
    assert client.get("/api/v1/auth/device").status_code == 404  # revoked: stops at once


def test_devices_need_permission_and_stay_in_their_tenant(
    client: TestClient, world: dict[str, Any]
) -> None:
    h = login(client, world["cashier_a"])
    assert client.post("/api/v1/devices", json={"name": "Mine"}, headers=h).status_code == 403
    assert (
        client.post(
            "/api/v1/auth/pin-login", json={"user_id": str(world["cashier_id"]), "pin": "1234"}
        ).status_code
        == 404
    )
    m = login(client, world["manager_a"])
    client.post("/api/v1/devices", json={"name": "Till 1"}, headers=m)
    token = client.cookies.get(COOKIE)
    b = login(client, world["manager_b"])
    assert client.get("/api/v1/devices", headers=b).json() == []
    client.cookies.set(COOKIE, token or "")
    # Beta's manager on Alpha's device cannot enrol there.
    assert client.post("/api/v1/devices/this/enrol", headers=b).status_code == 404
