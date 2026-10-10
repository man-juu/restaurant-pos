"""Slice 3a: customers with consent (FR-SAL-012), reservations with conflict detection and
suggested tables (FR-TBL-005, 006), seating and no-shows (FR-TBL-007), waitlist with an
estimated wait (FR-TBL-008); scope and isolation."""

from typing import Any

from fastapi.testclient import TestClient

from tests.test_inventory import login
from tests.test_purchasing import client as client
from tests.test_sales_days import menu as menu
from tests.test_tables import T, tables
from tests.test_tables import floor as floor
from tests.test_tables import world as world

B = "/api/v1/bookings"
C = "/api/v1/customers"
AT = "2026-11-20T19:00:00+07:00"


def booking(world: dict[str, Any], tables_: list[str], **extra: Any) -> dict[str, Any]:
    return {
        "outlet_id": str(world["shop"]),
        "guest": {"name": "Budi", "phone": "0812-3456-7890"},
        "party_size": 4,
        "starts_at": AT,
        "table_ids": tables_,
        **extra,
    }


def test_fr_tbl_005_006_booking_conflicts_and_suggestions(
    client: TestClient, world: dict[str, Any], floor: dict[str, str]
) -> None:
    h = login(client, world["waiter_a"])
    made = client.post(f"{B}/reservations", json=booking(world, [floor["T1"]]), headers=h)
    assert made.status_code == 201, made.text
    r = made.json()
    assert (
        r["status"] == "pending" and r["duration_min"] == 90 and r["guest_phone"] == "6281234567890"
    )
    # The same table an hour later overlaps (90 minutes): refused.
    later = booking(world, [floor["T1"]], starts_at="2026-11-20T20:00:00+07:00")
    clash = client.post(f"{B}/reservations", json=later, headers=h)
    assert clash.status_code == 409 and clash.json()["code"] == "table_already_booked"
    # Right after it ends is fine; the guest is found again by phone (one customer record).
    after = booking(world, [floor["T1"]], starts_at="2026-11-20T20:30:00+07:00")
    again = client.post(f"{B}/reservations", json=after, headers=h).json()
    assert again["customer_id"] == r["customer_id"]
    big = client.post(
        f"{B}/reservations", json=booking(world, [floor["T2"]], party_size=6), headers=h
    )
    assert big.json()["code"] == "tables_too_small"
    # Suggestions: T1 is taken at 19:00, so a party of 4 gets T2 or T3; a party of 7 gets a pair.
    q = f"{B}/suggest?outlet_id={world['shop']}&starts_at={AT.replace('+', '%2B')}"
    four = client.get(f"{q}&party_size=4", headers=h).json()
    assert {s["names"][0] for s in four} == {"T2", "T3"}
    seven = client.get(f"{q}&party_size=7", headers=h).json()
    assert seven and all(len(s["table_ids"]) == 2 and s["capacity"] >= 7 for s in seven)
    day = client.get(f"{B}/reservations?outlet_id={world['shop']}&day=2026-11-20", headers=h).json()
    assert [x["id"] for x in day] == [r["id"], again["id"]]


def test_fr_tbl_007_seat_and_no_shows(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any], floor: dict[str, str]
) -> None:
    h = login(client, world["waiter_a"])
    r = client.post(
        f"{B}/reservations",
        json=booking(world, [floor["T1"], floor["T2"]], party_size=7),
        headers=h,
    ).json()
    seated = client.post(
        f"{B}/reservations/{r['id']}/seat", json={"channel_id": menu["gofood"]}, headers=h
    ).json()
    assert seated["status"] == "seated" and seated["session_id"]
    view = tables(client, h, world)
    assert view["T1"]["status"] == view["T2"]["status"] == "occupied"
    # A guest who did not come: marked no-show, and the next booking shows it.
    other = booking(world, [floor["T3"]], guest={"name": "Sari", "phone": "08111"})
    gone = client.post(f"{B}/reservations", json=other, headers=h).json()
    out = client.put(f"{B}/reservations/{gone['id']}/status", json={"status": "no_show"}, headers=h)
    assert out.json()["status"] == "no_show"
    later = booking(
        world,
        [floor["T3"]],
        guest={"name": "Sari", "phone": "08111"},
        starts_at="2026-11-21T19:00:00+07:00",
    )
    assert client.post(f"{B}/reservations", json=later, headers=h).json()["no_shows"] == 1
    assert (
        client.put(
            f"{B}/reservations/{gone['id']}/status", json={"status": "confirmed"}, headers=h
        ).status_code
        == 409
    )


def test_fr_tbl_008_waitlist_estimates_and_seats(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any], floor: dict[str, str]
) -> None:
    h = login(client, world["waiter_a"])
    party = {"channel_id": menu["gofood"], "party_size": 2}
    for name in ("T2", "T3"):
        client.post(f"{T}/{floor[name]}/seat", json=party, headers=h)
    body = {"outlet_id": str(world["shop"]), "guest": {"name": "Ani"}, "party_size": 2}
    [ani] = client.post(f"{B}/waitlist", json=body, headers=h).json()
    assert ani["estimated_wait_min"] == 0  # T1 is free now
    seat = {"table_ids": [floor["T1"]], "channel_id": menu["gofood"]}
    assert client.post(f"{B}/waitlist/{ani['id']}/seat", json=seat, headers=h).json() == []
    assert tables(client, h, world)["T1"]["status"] == "occupied"
    # Every table is taken: the next party waits about one dwell time (90 minutes).
    [rudi] = client.post(
        f"{B}/waitlist", json={**body, "guest": {"name": "Rudi"}}, headers=h
    ).json()
    assert 85 <= rudi["estimated_wait_min"] <= 90
    taken = client.post(f"{B}/waitlist/{rudi['id']}/seat", json=seat, headers=h)
    assert taken.json()["code"] == "table_not_free"
    assert client.post(f"{B}/waitlist/{rudi['id']}/leave", headers=h).json() == []
    other = login(client, world["manager_b"])
    assert client.post(f"{B}/waitlist/{rudi['id']}/leave", headers=other).status_code == 404


def test_customers_need_permission_search_and_erase(
    client: TestClient, world: dict[str, Any]
) -> None:
    h = login(client, world["waiter_a"])
    made = client.post(
        C, json={"name": "Dewi", "phone": "0813 999 000", "consent": True}, headers=h
    ).json()
    assert made["consent_at"] and made["phone"] == "62813999000"
    assert [c["id"] for c in client.get(f"{C}?q=dew", headers=h).json()] == [made["id"]]
    assert [c["id"] for c in client.get(f"{C}?q=0813999", headers=h).json()] == [made["id"]]
    assert client.get(f"{C}?q=%25", headers=h).status_code == 422  # too short
    dup = client.post(C, json={"name": "Other", "phone": "62813999000"}, headers=h)
    assert dup.json()["code"] == "customer_phone_exists"
    assert client.delete(f"{C}/{made['id']}", headers=h).status_code == 204
    assert client.get(f"{C}?q=dew", headers=h).json() == []
    other = login(client, world["manager_b"])
    assert client.get(f"{C}?q=dew", headers=other).json() == []
