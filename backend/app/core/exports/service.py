"""Build a tenant's data export (FR-TEN-010): one ZIP with a JSON Lines file per table and a
manifest. Every table with a tenant_id is read inside the tenant's RLS context, so another
tenant's rows cannot leak in. Secrets never leave: columns holding password or PIN hashes,
2FA secrets, tokens or keys are dropped, and session and idempotency tables are skipped."""

import asyncio
import json
import uuid
import zipfile
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import Table, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.config import Settings
from app.core.errors import ConflictError
from app.core.exports.models import DataExport
from app.core.models import Base

KEEP_DAYS = 7
SKIP_TABLES = frozenset(
    {"idempotency_keys", "sessions", "user_pins", "impersonation_sessions", "data_exports"}
)
SECRET_MARKS = ("password", "hash", "secret", "token", "totp", "recovery", "key_enc", "pin_")
MAX_QUEUED = 1
MAX_PER_DAY = 3


def secret_column(name: str) -> bool:
    return any(mark in name for mark in SECRET_MARKS) and name != "storage_key"


def tenant_tables() -> list[Table]:
    return [
        t for t in Base.metadata.sorted_tables if "tenant_id" in t.c and t.name not in SKIP_TABLES
    ]


async def readable(db: AsyncSession, tables: list[Table]) -> list[Table]:
    """Only tables the app role may read: platform tables (job failures, restore requests)
    carry a tenant_id but belong to the platform admin."""
    names = [t.name for t in tables]
    rows = await db.execute(
        text(
            "SELECT t FROM unnest(CAST(:names AS text[])) t WHERE has_table_privilege(t, 'SELECT')"
        ),
        {"names": names},
    )
    allowed = {r[0] for r in rows}
    return [t for t in tables if t.name in allowed]


def _plain(value: Any) -> Any:
    if isinstance(value, (uuid.UUID, Decimal)):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (bytes, memoryview)):
        return None
    return value


async def _table_lines(db: AsyncSession, table: Table) -> list[str]:
    cols = [c for c in table.c if not secret_column(c.name)]
    rows = await db.execute(select(*cols))
    return [json.dumps({c.name: _plain(v) for c, v in zip(cols, r, strict=True)}) for r in rows]


def _write_zip(path: Path, files: dict[str, list[str]], manifest: dict[str, Any]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, indent=2))
        for name, lines in files.items():
            z.writestr(f"{name}.jsonl", "\n".join(lines) + ("\n" if lines else ""))
    tmp.replace(path)
    return path.stat().st_size


def export_path(settings: Settings, key: str) -> Path:
    return Path(settings.upload_dir) / key


async def build(db: AsyncSession, settings: Settings, row: DataExport) -> None:
    files = {t.name: await _table_lines(db, t) for t in await readable(db, tenant_tables())}
    manifest = {
        "tenant_id": str(row.tenant_id),
        "export_id": str(row.id),
        "created_at": datetime.now(UTC).isoformat(),
        "format": "one JSON object per line; money in minor units; quantities as strings",
        "tables": {name: len(lines) for name, lines in files.items()},
        "left_out": "password and PIN hashes, 2FA secrets, tokens, sessions",
    }
    key = f"exports/{row.tenant_id}/{row.id}.zip"
    size = await asyncio.to_thread(_write_zip, export_path(settings, key), files, manifest)
    now = datetime.now(UTC)
    row.status, row.file_key, row.byte_size = "ready", key, size
    row.finished_at, row.expires_at = now, now + timedelta(days=KEEP_DAYS)
    await db.flush()


async def request_export(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> DataExport:
    """Owner asks for an export; at most one waiting and three a day (they are heavy)."""
    since = datetime.now(UTC) - timedelta(days=1)
    recent = list(await db.scalars(select(DataExport).where(DataExport.created_at >= since)))
    if sum(r.status == "queued" for r in recent) >= MAX_QUEUED:
        raise ConflictError("export_already_queued")
    if len(recent) >= MAX_PER_DAY:
        raise ConflictError("export_limit", details={"per_day": MAX_PER_DAY})
    row = DataExport(tenant_id=tenant_id, requested_by=user_id, status="queued")
    db.add(row)
    await db.flush()
    await audit.record(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="tenant.export.request",
        target_type="data_export",
        target_id=row.id,
        summary={},
    )
    return row


async def run_queued(db: AsyncSession, tenant_id: uuid.UUID, settings: Settings) -> int:
    """Periodic task: build this tenant's queued exports. A failure is recorded on the row
    (exception type only) and does not stop the job."""
    queued = list(await db.scalars(select(DataExport).where(DataExport.status == "queued")))
    for row in queued:
        try:
            async with db.begin_nested():
                await build(db, settings, row)
        except Exception as err:
            row.status, row.error = "failed", type(err).__name__
            row.finished_at = datetime.now(UTC)
    await db.flush()
    return len(queued)
