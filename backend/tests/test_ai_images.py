"""Slice 1b part 4: free AI images with budget guards (FR-CAT-013, ADR-022)."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.test_auth import new_client, owner
from tests.test_catalog import item_body, signin, units
from tests.test_catalog import world as world
from tests.test_uploads import image_bytes

PROMPT = {"prompt": "bowl of bibimbap, top view, wooden table"}


def ai_settings(settings: Settings, tmp_path: Path, **extra: Any) -> Settings:
    values = {
        "upload_dir": str(tmp_path),
        "ai_cf_account_id": "0" * 32,
        "ai_cf_api_token": "test-token",
        "ai_tenant_daily_images": 2,
        **extra,
    }
    return settings.model_copy(update=values)


def client_for(app: FastAPI, sent: list[str], fail: bool = False) -> TestClient:
    async def fake(_settings: Settings, prompt: str) -> bytes:
        sent.append(prompt)
        if fail:
            raise RuntimeError("provider down")
        return image_bytes("PNG")

    app.state.ai_generate = fake
    return new_client(app)


@pytest.fixture(autouse=True)
def clean_counter() -> Iterator[None]:
    owner("DELETE FROM ai_usage_daily")
    yield
    owner("DELETE FROM ai_usage_daily")


def test_fr_cat_013_generate_accept_and_counter(
    settings: Settings, tmp_path: Path, world: dict[str, Any]
) -> None:
    sent: list[str] = []
    with client_for(create_app(ai_settings(settings, tmp_path)), sent) as client:
        h = signin(client, world["manager_a"])
        assert client.get("/api/v1/catalog/ai-images/usage").json()["remaining"] == 2
        made = client.post("/api/v1/catalog/ai-images", json=PROMPT, headers=h)
        assert made.status_code == 200, made.text
        assert sent == [PROMPT["prompt"]]  # only the typed prompt leaves the server
        assert made.json()["usage"]["remaining"] == 1
        item = client.post(
            "/api/v1/catalog/items", json=item_body(units(client)["g"]), headers=h
        ).json()
        image_id = made.json()["image"]["id"]
        accepted = client.put(f"/api/v1/catalog/items/{item['id']}/photo/{image_id}", headers=h)
        assert accepted.status_code == 200
        assert client.post("/api/v1/catalog/ai-images", json=PROMPT, headers=h).status_code == 200
        blocked = client.post("/api/v1/catalog/ai-images", json=PROMPT, headers=h)
        assert blocked.status_code == 429 and blocked.json()["code"] == "tenant_daily_limit"
        assert len(sent) == 2  # the blocked request never reached the provider


def test_platform_budget_blocks_before_the_free_limit(
    settings: Settings, tmp_path: Path, world: dict[str, Any]
) -> None:
    # 1,000 free neurons at 85% = 850; 400 per image: two fit, the third would pass 85%.
    tight = ai_settings(
        settings,
        tmp_path,
        ai_daily_free_neurons=1000,
        ai_neurons_per_image=400,
        ai_tenant_daily_images=10,
    )
    sent: list[str] = []
    with client_for(create_app(tight), sent) as client:
        ha = signin(client, world["manager_a"])
        assert client.post("/api/v1/catalog/ai-images", json=PROMPT, headers=ha).status_code == 200
        hb = signin(client, world["manager_b"])  # another tenant shares the free allowance
        assert client.post("/api/v1/catalog/ai-images", json=PROMPT, headers=hb).status_code == 200
        third = client.post("/api/v1/catalog/ai-images", json=PROMPT, headers=hb)
        assert third.status_code == 429 and third.json()["code"] == "platform_daily_limit"
        assert client.get("/api/v1/catalog/ai-images/usage").json()["remaining"] == 0
    assert len(sent) == 2


def test_failed_call_returns_the_budget_and_rules_apply(
    settings: Settings, tmp_path: Path, world: dict[str, Any]
) -> None:
    sent: list[str] = []
    with client_for(create_app(ai_settings(settings, tmp_path)), sent, fail=True) as client:
        h = signin(client, world["manager_a"])
        failed = client.post("/api/v1/catalog/ai-images", json=PROMPT, headers=h)
        assert failed.status_code == 500
        assert owner("SELECT coalesce(sum(neurons), 0) FROM ai_usage_daily")[0][0] == 0
        bad = client.post("/api/v1/catalog/ai-images", json={"prompt": "a\x00b"}, headers=h)
        assert bad.status_code == 422
        hc = signin(client, world["cashier_a"])
        assert client.post("/api/v1/catalog/ai-images", json=PROMPT, headers=hc).status_code == 403


def test_off_without_provider_keys(
    settings: Settings, tmp_path: Path, world: dict[str, Any]
) -> None:
    off = settings.model_copy(update={"upload_dir": str(tmp_path)})
    with client_for(create_app(off), []) as client:
        h = signin(client, world["manager_a"])
        assert client.get("/api/v1/catalog/ai-images/usage").json()["enabled"] is False
        made = client.post("/api/v1/catalog/ai-images", json=PROMPT, headers=h)
        assert made.status_code == 409 and made.json()["code"] == "ai_disabled"
