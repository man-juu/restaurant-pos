from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.db import ping

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> JSONResponse:
    """Liveness plus database status (NFR-010). 503 lets uptime checks and Docker see an outage."""
    db_ok = await ping(request.app.state.engine)
    return JSONResponse(
        {"status": "ok" if db_ok else "degraded", "database": "ok" if db_ok else "unavailable"},
        status_code=200 if db_ok else 503,
    )
