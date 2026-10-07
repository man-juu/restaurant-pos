"""Serve uploaded files to signed-in members of the owning tenant (docs/06: separate path,
fixed content type, no sniffing, never executed)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse

from app.core.access.policy import Principal, require
from app.core.tenancy import tenant_session
from app.core.uploads import service

router = APIRouter(prefix="/api/v1/uploads", tags=["uploads"])

Member = Annotated[Principal, Depends(require("tenant.outlet.view"))]


@router.get("/{upload_id}", response_class=FileResponse)
async def get_upload(upload_id: uuid.UUID, request: Request, p: Member) -> FileResponse:
    settings = request.app.state.settings
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        row, path = await service.open_upload(db, settings, upload_id)
    return FileResponse(
        path,
        media_type=row.content_type,
        headers={
            "Content-Disposition": f'inline; filename="{row.id}.webp"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=86400, immutable",  # ids never change content
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )
