from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from resume_matching.api.deps import ContainerDep

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", summary="Liveness probe")
async def live() -> dict:
    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe (database + taxonomy)")
async def ready(container: ContainerDep) -> JSONResponse:
    checks: dict[str, str] = {}
    try:
        async with container.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {type(exc).__name__}"
    checks["taxonomy"] = (
        f"ok ({len(container.taxonomy)} skills)" if len(container.taxonomy) else "empty"
    )
    healthy = all(v.startswith("ok") for v in checks.values())
    return JSONResponse(
        {"status": "ok" if healthy else "unavailable", "checks": checks},
        status_code=200 if healthy else 503,
    )
