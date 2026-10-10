"""Slice 3k: web push on installed apps (FR-NTF-005). Only real browser push services are
accepted as endpoints (no request to arbitrary hosts); new notifications are pushed once."""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.admin.alerts_job import run_alerts
from app.core.config import Settings
from app.core.notifications import push
from app.main import create_app
from tests.factories import add_member, drop_tenant, seed_tenant
from tests.test_auth import new_client
from tests.test_inventory import HASH, login
from tests.test_purchasing import tenant_sql

P = "/api/v1/push"
FCM = "https://fcm.googleapis.com/fcm/send/abc123"
GONE = "https://fcm.googleapis.com/fcm/send/gone"
SUB = {"endpoint": FCM, "keys": {"p256dh": "B" * 87, "auth": "a" * 22}}


@pytest.mark.parametrize(
    ("url", "ok"),
    [
        (FCM, True),
        ("https://updates.push.services.mozilla.com/wpush/v2/x", True),
        ("https://web.push.apple.com/QWERTY", True),
        ("https://wns2-par02p.notify.windows.com/w/?token=x", True),
        ("http://fcm.googleapis.com/fcm/send/x", False),  # not HTTPS
        ("https://169.254.169.254/latest/meta-data", False),  # internal address
        ("https://evil.example/fcm.googleapis.com", False),
        ("https://fcm.googleapis.com.evil.example/x", False),
        ("https://fcm.googleapis.com:8443/x", False),
    ],
)
def test_fr_ntf_005_only_push_services_are_endpoints(url: str, ok: bool) -> None:
    assert push.allowed_endpoint(url) is ok


def test_fr_ntf_005_subscribe_and_push_new_notifications(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conf = settings.model_copy(
        update={
            "vapid_public_key": "BPub",
            "vapid_private_key": "x" * 43,
            "upload_dir": str(tmp_path),
        }
    )
    sent: list[tuple[str, str]] = []

    def fake_send(sub: Any, payload: str, s: Settings) -> int:
        sent.append((sub.endpoint, payload))
        return 410 if "gone" in sub.endpoint else 201

    monkeypatch.setattr(push, "_send", fake_send)
    a, roles = seed_tenant("Alpha")
    try:
        user_id, email = add_member(a, roles["manager"], HASH)
        with new_client(create_app(conf)) as c:
            h = login(c, email)
            assert c.get(f"{P}/key", headers=h).json() == {"enabled": True, "public_key": "BPub"}
            assert c.put(f"{P}/subscription", json=SUB, headers=h).status_code == 204
            gone = {**SUB, "endpoint": GONE}
            assert c.put(f"{P}/subscription", json=gone, headers=h).status_code == 204
            evil = {**SUB, "endpoint": "https://10.0.0.5/push"}
            bad = c.put(f"{P}/subscription", json=evil, headers=h)
            assert bad.status_code == 422 and bad.json()["code"] == "push_endpoint_not_allowed"
        tenant_sql(
            a,
            "INSERT INTO notifications (id, tenant_id, user_id, kind, params, link)"
            " VALUES (gen_random_uuid(), :t, :u, 'low_stock', '{}', '/inventory')",
            {"t": a, "u": user_id},
        )

        def run() -> None:
            async def go() -> None:
                engine = create_async_engine(str(conf.database_url))
                maker = async_sessionmaker(engine, expire_on_commit=False)
                try:
                    await run_alerts([a], maker, conf)
                finally:
                    await engine.dispose()

            asyncio.run(go())

        run()
        assert sorted(e for e, _ in sent) == sorted([FCM, GONE])
        assert '"count": 1' in sent[0][1] and "/inventory" in sent[0][1]
        left = tenant_sql(a, "SELECT endpoint FROM push_subscriptions")
        assert [r[0] for r in left] == [FCM]  # the 410 one was removed
        sent.clear()
        run()
        assert sent == []  # pushed once only
    finally:
        drop_tenant(a)


def test_push_is_off_without_keys(settings: Settings) -> None:
    a, roles = seed_tenant("Alpha")
    try:
        with new_client(create_app(settings)) as client:
            h = login(client, add_member(a, roles["cashier"], HASH)[1])
            off = client.get(f"{P}/key", headers=h).json()
            assert off == {"enabled": False, "public_key": None}
    finally:
        drop_tenant(a)
