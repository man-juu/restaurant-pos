"""Slice 1b part 3: upload engine and item photos (FR-CAT-001, docs/06 file uploads)."""

import io
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.core.uploads.images import MAX_SIDE, InvalidImage, clean_image
from app.main import create_app
from tests.test_auth import new_client
from tests.test_catalog import item_body, signin, units
from tests.test_catalog import world as world


def image_bytes(fmt: str = "JPEG", size: tuple[int, int] = (64, 48), **save: Any) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (200, 80, 40)).save(buffer, fmt, **save)
    return buffer.getvalue()


# --- Image checks ---------------------------------------------------------------------------


def test_reencodes_to_webp_and_strips_metadata() -> None:
    exif = Image.Exif()
    exif[0x8825] = {2: (6.0, 10.0, 0.0)}  # GPS info: must not survive
    exif[0x010F] = "PhoneMaker"
    out = clean_image(image_bytes(exif=exif.tobytes()))
    with Image.open(io.BytesIO(out.data)) as img:
        assert img.format == "WEBP"
        assert not img.getexif()
        assert img.info.get("exif") is None


def test_large_images_are_resized() -> None:
    out = clean_image(image_bytes("PNG", (4000, 1000)))
    assert (out.width, out.height) == (MAX_SIDE, MAX_SIDE // 4)


@pytest.mark.parametrize(
    "raw",
    [
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        b"%PDF-1.7 not an image",
        image_bytes("GIF"),  # valid image, but not on the allow-list
        image_bytes()[:200],  # truncated JPEG
    ],
)
def test_rejects_non_images_and_disallowed_types(raw: bytes) -> None:
    with pytest.raises(InvalidImage):
        clean_image(raw)


def test_rejects_decompression_bombs() -> None:
    bomb = io.BytesIO()
    Image.new("1", (12_000, 12_000)).save(bomb, "PNG")  # tiny file, 144 megapixels
    assert len(bomb.getvalue()) < 100_000
    with pytest.raises(InvalidImage):
        clean_image(bomb.getvalue())


# --- API ------------------------------------------------------------------------------------


@pytest.fixture
def client(settings: Settings, tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(settings.model_copy(update={"upload_dir": str(tmp_path)}))
    with new_client(app) as c:
        yield c


def _item(client: TestClient, h: dict[str, str]) -> str:
    created = client.post("/api/v1/catalog/items", json=item_body(units(client)["g"]), headers=h)
    return str(created.json()["id"])


def put_photo(client: TestClient, h: dict[str, str], item_id: str, raw: bytes) -> Any:
    return client.put(
        f"/api/v1/catalog/items/{item_id}/photo",
        content=raw,
        headers={**h, "Content-Type": "application/octet-stream"},
    )


def test_fr_cat_001_photo_upload_serve_and_dedupe(
    client: TestClient, world: dict[str, Any], tmp_path: Path
) -> None:
    h = signin(client, world["manager_a"])
    item_id = _item(client, h)
    first = put_photo(client, h, item_id, image_bytes())
    assert first.status_code == 200, first.text
    photo = first.json()["id"]
    assert client.get(f"/api/v1/catalog/items/{item_id}").json()["photo_upload_id"] == photo
    served = client.get(f"/api/v1/uploads/{photo}")
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/webp"
    assert served.headers["x-content-type-options"] == "nosniff"
    assert put_photo(client, h, item_id, image_bytes()).json()["id"] == photo  # same file
    assert len(list(tmp_path.rglob("*.webp"))) == 1
    assert client.delete(f"/api/v1/catalog/items/{item_id}/photo", headers=h).status_code == 204
    assert client.get(f"/api/v1/catalog/items/{item_id}").json()["photo_upload_id"] is None


def test_upload_rules_permissions_size_and_isolation(
    client: TestClient, world: dict[str, Any], settings: Settings
) -> None:
    h = signin(client, world["manager_a"])
    item_id = _item(client, h)
    photo = put_photo(client, h, item_id, image_bytes()).json()["id"]
    bad = put_photo(client, h, item_id, b"<svg/>")
    assert bad.status_code == 422 and bad.json()["code"] == "invalid_image"
    huge = put_photo(client, h, item_id, b"\0" * (settings.upload_max_bytes + 1))
    assert huge.status_code == 413
    hc = signin(client, world["cashier_a"])
    assert client.get(f"/api/v1/uploads/{photo}").status_code == 200  # staff can see photos
    assert put_photo(client, hc, item_id, image_bytes()).status_code == 403
    signin(client, world["manager_b"])
    assert client.get(f"/api/v1/uploads/{photo}").status_code == 404  # other tenant
