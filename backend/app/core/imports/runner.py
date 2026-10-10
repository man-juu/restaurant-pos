"""Shared check-then-commit flow for every import (FR-IMP-001, 002).

The check runs the real save inside a savepoint and rolls it back, so "check" and "import"
apply exactly the same rules (no second copy of the validation that could drift). Every row
problem is collected; any problem means nothing is saved."""

import hashlib
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.errors import ConflictError, NotFoundError
from app.core.imports.models import ImportBatch
from app.core.tabular import InvalidTable, read_table


@dataclass
class Outcome:
    created: list[uuid.UUID] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)


# (db, rows) -> outcome; rows are dicts from read_table, numbered from 2 (row 1 is the header).
Builder = Callable[[AsyncSession, list[dict[str, str]]], Awaitable[Outcome]]


class _DryRun(Exception):
    pass


def rows_of(raw: bytes, file_name: str, required: tuple[str, ...]) -> list[dict[str, str]]:
    rows = read_table(raw, file_name)
    missing = [c for c in required if rows and c not in rows[0]]
    if missing:
        raise InvalidTable("missing_columns", details={"columns": missing})
    return rows


async def check(db: AsyncSession, rows: list[dict[str, str]], build: Builder) -> Outcome:
    result = Outcome()
    try:
        async with db.begin_nested():
            result = await build(db, rows)
            raise _DryRun  # always roll the savepoint back
    except _DryRun:
        pass
    return result


async def commit(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    kind: str,
    raw: bytes,
    file_name: str,
    rows: list[dict[str, str]],
    build: Builder,
) -> ImportBatch:
    digest = hashlib.sha256(raw).hexdigest()
    done = await db.scalar(
        select(ImportBatch).where(ImportBatch.kind == kind, ImportBatch.file_sha256 == digest)
    )
    if done is not None:
        raise ConflictError("already_imported", details={"batch_id": str(done.id)})
    outcome = await check(db, rows, build)
    if outcome.errors:
        raise InvalidTable("rows_invalid", details={"errors": outcome.errors[:200]})
    outcome = await build(db, rows)
    batch = ImportBatch(
        tenant_id=tenant_id,
        kind=kind,
        file_sha256=digest,
        file_name=file_name[:200],
        row_count=len(rows),
        created_ids=[str(i) for i in outcome.created],
        created_by=user_id,
    )
    db.add(batch)
    await db.flush()
    await audit.record(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action=f"import.{kind}.commit",
        target_type="import_batch",
        target_id=batch.id,
        summary={"rows": len(rows), "created": len(outcome.created), "file": file_name[:200]},
    )
    return batch


async def open_for_revert(db: AsyncSession, batch_id: uuid.UUID, kinds: set[str]) -> ImportBatch:
    """Lock a committed batch of one of `kinds` (each module undoes only its own imports)."""
    batch = await db.get(ImportBatch, batch_id, with_for_update=True)
    if batch is None or batch.kind not in kinds:
        raise NotFoundError("import_not_found")
    if batch.status != "committed":
        raise ConflictError("already_reverted")
    return batch


async def mark_reverted(
    db: AsyncSession,
    batch: ImportBatch,
    *,
    user_id: uuid.UUID,
    summary: dict[str, Any],
) -> ImportBatch:
    batch.status, batch.reverted_at = "reverted", func.now()
    await audit.record(
        db,
        tenant_id=batch.tenant_id,
        user_id=user_id,
        action=f"import.{batch.kind}.revert",
        target_type="import_batch",
        target_id=batch.id,
        summary=summary,
    )
    await db.flush()
    await db.refresh(batch)
    return batch
