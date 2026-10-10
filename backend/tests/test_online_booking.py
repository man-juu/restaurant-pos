"""Slice 4f: public booking page and reminders (FR-TBL-010). Links, slots, limits, the token
as the only key, staff reminders, scope and isolation."""

import uuid
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.modules.tables.online import reminder_text
from tests.test_inventory import login
from tests.test_purchasing import client as client
from tests.test_tables import floor as floor
from tests.test_tables import world as world

B = "/api/v1/bookings"
P = "/api/v1/public/booking"


def new_link(client: TestClient, world: dict[str, Any]) -> dict[str, Any]:
    h = login(client, world["manager_a"])
    made = client.post(f"{B}/links", json={"outlet_id": str(world["shop"])}, headers=h)
    assert made.status_code == 201, made.text
    return dict(made.json())


def tomorrow(client: TestClient, token: str) -> date:
    tz = ZoneInfo(client.get(f"{P}/{token}").json()["timezone"])
    return datetime.now(tz).date() + timedelta(days=1)


def guest_post(client: TestClient, token: str, body: dict[str, Any]) -> Any:
    client.cookies.clear()  # a guest has no session
    return client.post(f"{P}/{token}", json=body, headers={"Idempotency-Key": str(uuid.uuid4())})


def form(starts_at: str, **extra: Any) -> dict[str, Any]:
    return {
        "name": "Rina",
        "phone": "0813 1111 2222",
        "party_size": 2,
        "starts_at": starts_at,
        "consent": True,
        **extra,
    }


def test_fr_tbl_010_guest_books_from_the_public_page(
    client: TestClient, world: dict[str, Any], floor: dict[str, str]
) -> None:
    link = new_link(client, world)
    token = link["token"]
    client.cookies.clear()
    page = client.get(f"{P}/{token}")
    assert page.status_code == 200 and page.json()["max_party"] == 8
    day = tomorrow(client, token)
    slots = client.get(f"{P}/{token}/slots?day={day}&party_size=2").json()
    assert slots and len(slots) == 23  # 10:00 to 21:00 every 30 minutes
    key = str(uuid.uuid4())
    made = client.post(f"{P}/{token}", json=form(slots[0]), headers={"Idempotency-Key": key})
    assert made.status_code == 201, made.text
    assert made.json()["status"] == "pending" and "table_ids" not in made.json()
    # A retry with the same key returns the same booking, not a second one.
    again = client.post(f"{P}/{token}", json=form(slots[0]), headers={"Idempotency-Key": key})
    assert again.json()["id"] == made.json()["id"]
    # Staff see it as an online booking with a table already chosen.
    h = login(client, world["waiter_a"])
    rows = client.get(f"{B}/reservations?outlet_id={world['shop']}&day={day}", headers=h).json()
    [r] = rows
    assert r["source"] == "online" and r["table_ids"] and r["guest_phone"] == "6281311112222"


def test_fr_tbl_010_limits(
    client: TestClient, world: dict[str, Any], floor: dict[str, str]
) -> None:
    token = new_link(client, world)["token"]
    day = tomorrow(client, token)
    client.cookies.clear()
    slots = client.get(f"{P}/{token}/slots?day={day}&party_size=2").json()
    # Bigger than the setting allows: no times and refused.
    assert client.get(f"{P}/{token}/slots?day={day}&party_size=9").json() == []
    big = guest_post(client, token, form(slots[0], party_size=9))
    assert big.json()["code"] == "slot_not_available"
    # A time that is not on the grid (03:00) and a day beyond `days_ahead`.
    night = datetime.fromisoformat(slots[0]).replace(hour=3).isoformat()
    assert guest_post(client, token, form(night)).json()["code"] == "slot_not_available"
    far = (datetime.fromisoformat(slots[0]) + timedelta(days=60)).isoformat()
    assert guest_post(client, token, form(far)).json()["code"] == "slot_not_available"
    # Consent is required.
    assert guest_post(client, token, form(slots[0], consent=False)).status_code == 422
    # One phone may hold two open online bookings; the third is refused.
    assert guest_post(client, token, form(slots[0])).status_code == 201
    assert guest_post(client, token, form(slots[4])).status_code == 201
    third = guest_post(client, token, form(slots[8]))
    assert third.status_code == 409 and third.json()["code"] == "too_many_bookings"


def test_fr_tbl_010_tokens_and_scope(
    client: TestClient, world: dict[str, Any], floor: dict[str, str]
) -> None:
    link = new_link(client, world)
    client.cookies.clear()
    assert client.get(f"{P}/not-a-real-token-at-all").status_code == 404
    assert client.get(f"{P}/short").status_code == 404
    # Waiters cannot make links; another tenant cannot see or switch off this one.
    w = login(client, world["waiter_a"])
    assert (
        client.post(f"{B}/links", json={"outlet_id": str(world["shop"])}, headers=w).status_code
        == 403
    )
    b = login(client, world["manager_b"])
    assert client.post(f"{B}/links/{link['id']}/disable", headers=b).status_code == 404
    listed = client.get(f"{B}/links?outlet_id={world['shop']}", headers=b)
    assert listed.status_code == 404 or listed.json() == []
    # Switched off: the page is closed for good and the token is never shown again.
    m = login(client, world["manager_a"])
    off = client.post(f"{B}/links/{link['id']}/disable", headers=m).json()
    assert off["disabled_at"] and "token" not in off
    links = client.get(f"{B}/links?outlet_id={world['shop']}", headers=m).json()
    assert all("token" not in x for x in links)
    client.cookies.clear()
    assert client.get(f"{P}/{link['token']}").status_code == 404


def test_fr_tbl_010_reminder(
    client: TestClient, world: dict[str, Any], floor: dict[str, str]
) -> None:
    token = new_link(client, world)["token"]
    day = tomorrow(client, token)
    client.cookies.clear()
    slot = client.get(f"{P}/{token}/slots?day={day}&party_size=2").json()[2]
    made = guest_post(client, token, form(slot)).json()
    h = login(client, world["waiter_a"])
    sent = client.post(f"{B}/reservations/{made['id']}/remind", headers=h)
    assert sent.status_code == 200, sent.text
    out = sent.json()
    assert (
        out["phone"] == "6281311112222" and "Rina" in out["message"] and "11:00" in out["message"]
    )
    rows = client.get(f"{B}/reservations?outlet_id={world['shop']}&day={day}", headers=h).json()
    assert rows[0]["reminded_at"]
    b = login(client, world["manager_b"])
    assert client.post(f"{B}/reservations/{made['id']}/remind", headers=b).status_code == 404


def test_reminder_text_is_plain_replacement() -> None:
    values = {"name": "Ana", "party": "2"}
    assert reminder_text("Hi {name} x{party}", values) == "Hi Ana x2"
    # Format-string tricks stay literal text.
    assert reminder_text("{name.__class__} {0}", values) == "{name.__class__} {0}"
