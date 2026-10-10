"""Store and read uploaded files (FR-CAT-001 photos; later waste photos and invoices).

Runs inside tenant_session. Pillow work and disk I/O run in a worker thread so a large photo
never blocks the event loop. Files are written to a temporary name and renamed into place, so
a reader never sees half a file. If the transaction later rolls back, the file is left
unreferenced; that costs a little disk and never exposes data (a cleanup job can sweep it)."""

import asyncio
import hashlib
import os
import uuid
from pathlib import Path

from fastapi import Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.config import Settings
from app.core.errors import AppError, NotFoundError
from app.core.uploads.images import clean_image
from app.core.uploads.models import Upload


class UploadTooLarge(AppError):
    status_code, code = 413, "upload_too_large"


async def read_body(request: Request, max_bytes: int) -> bytes:
    """Read the raw request body, stopping as soon as it passes the limit."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > max_bytes:
        raise UploadTooLarge(details={"max_bytes": max_bytes})
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > max_bytes:
            raise UploadTooLarge(details={"max_bytes": max_bytes})
        chunks.append(chunk)
    return b"".join(chunks)


def _path(settings: Settings, storage_key: str) -> Path:
    return Path(settings.upload_dir) / storage_key


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


async def store_image(
    db: AsyncSession,
    settings: Settings,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    purpose: str,
    raw: bytes,
) -> Upload:
    image = await asyncio.to_thread(clean_image, raw)
    digest = hashlib.sha256(image.data).hexdigest()
    existing = await db.scalar(
        select(Upload).where(Upload.purpose == purpose, Upload.sha256 == digest)
    )
    if existing is not None:
        return existing  # same picture uploaded again: reuse it
    upload_id = uuid.uuid4()
    key = f"{tenant_id}/{upload_id}.webp"  # random; the client's file name is never used
    await asyncio.to_thread(_write, _path(settings, key), image.data)
    row = Upload(
        id=upload_id,
        tenant_id=tenant_id,
        purpose=purpose,
        content_type=image.content_type,
        byte_size=len(image.data),
        width=image.width,
        height=image.height,
        sha256=digest,
        storage_key=key,
        created_by=user_id,
    )
    db.add(row)
    await db.flush()
    await audit.record(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="upload.create",
        target_type="upload",
        target_id=row.id,
        summary={"purpose": purpose, "bytes": row.byte_size},
    )
    return row


async def open_upload(
    db: AsyncSession, settings: Settings, upload_id: uuid.UUID
) -> tuple[Upload, Path]:
    """RLS limits the lookup to the caller's tenant, so another tenant's id is "not found"."""
    row = await db.get(Upload, upload_id)
    path = _path(settings, row.storage_key) if row else None
    if row is None or path is None or not path.is_file():
        raise NotFoundError("upload_not_found")
    return row, path


class UploadRef(BaseModel):
    id: uuid.UUID
    content_type: str
    width: int | None
    height: int | None
    byte_size: int
