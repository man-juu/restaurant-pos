"""Free AI images for item photos (FR-CAT-013, ADR-022). The user types a prompt, gets one
image to accept (it becomes the item photo) or discard. Only the prompt leaves our server."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, StringConstraints

from app.core import audit
from app.core.access.policy import Principal, require
from app.core.ai import provider
from app.core.ai import service as ai
from app.core.tenancy import tenant_session
from app.core.uploads import service as uploads
from app.modules.catalog import permissions as perm

router = APIRouter(prefix="/api/v1/catalog/ai-images", tags=["catalog"])

Update = Annotated[Principal, Depends(require(perm.ITEM_UPDATE))]

# Printable text only: no control characters reach the provider or the log.
Prompt = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=3, max_length=300, pattern=r"^[^\x00-\x1f\x7f]+$"
    ),
]


class GenerateIn(BaseModel):
    prompt: Prompt


class GenerateOut(BaseModel):
    image: uploads.UploadRef
    usage: ai.AiUsage


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


@router.get("/usage", response_model=ai.AiUsage)
async def get_usage(request: Request, p: Update) -> ai.AiUsage:
    async with _db(request, p) as db:
        return await ai.usage(db, request.app.state.settings)


@router.post("", response_model=GenerateOut)
async def generate(body: GenerateIn, request: Request, p: Update) -> GenerateOut:
    settings = request.app.state.settings
    async with _db(request, p) as db:  # committed before the slow call: the slot is taken
        reservation = await ai.reserve(
            db, settings, tenant_id=p.tenant_id, user_id=p.user_id, prompt=body.prompt
        )
    make = getattr(request.app.state, "ai_generate", provider.generate)
    try:
        raw = await make(settings, body.prompt)
    except Exception:
        async with _db(request, p) as db:
            await ai.finish(db, reservation, upload_id=None)
        raise
    async with _db(request, p) as db:
        row = await uploads.store_image(
            db, settings, tenant_id=p.tenant_id, user_id=p.user_id, purpose="item_photo", raw=raw
        )
        await ai.finish(db, reservation, upload_id=row.id)
        await audit.record(
            db,
            tenant_id=p.tenant_id,
            user_id=p.user_id,
            action="catalog.ai_image.generate",
            target_type="upload",
            target_id=row.id,
            summary={"prompt": body.prompt},
        )
        image = uploads.UploadRef.model_validate(row, from_attributes=True)
        return GenerateOut(image=image, usage=await ai.usage(db, settings))
