"""HTTP pieces shared by every module's import and export endpoints."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import Query, Response
from pydantic import BaseModel

from app.core.tabular import write_csv, write_xlsx

FileName = Annotated[str, Query(min_length=1, max_length=200, pattern=r"^[^/\\]+\.(csv|xlsx)$")]
Format = Literal["csv", "xlsx"]
MAX_FILE = 5 * 1024 * 1024
_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class ImportCheckOut(BaseModel):
    rows_ok: int
    errors: list[dict[str, Any]]
    new_categories: list[str] = []


class ImportBatchOut(BaseModel):
    id: uuid.UUID
    kind: str
    file_name: str
    status: str
    row_count: int
    created_at: datetime
    reverted_at: datetime | None


def table_file(fmt: Format, name: str, header: tuple[str, ...], rows: list[list[Any]]) -> Response:
    data = write_xlsx(header, rows) if fmt == "xlsx" else write_csv(header, rows)
    return Response(
        data,
        media_type=_TYPES[fmt],
        headers={"Content-Disposition": f'attachment; filename="{name}.{fmt}"'},
    )
