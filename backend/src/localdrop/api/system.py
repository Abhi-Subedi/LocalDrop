"""System: health, version and build-info endpoints (spec 05 §2.1)."""

from __future__ import annotations

import platform
import sys
from typing import Any

from fastapi import APIRouter, Response
from sqlalchemy import text

from ..__about__ import APP_NAME, __version__
from ..db import get_db  # noqa: F401
from ..storage import get_storage

router = APIRouter(tags=["system"])


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/version")
async def version() -> dict[str, Any]:
    """Public build metadata.

    Intentionally unauthenticated and free of any deployment detail (no data
    dir, no host, no database URL): the Settings "About" panel and support
    requests both need it before a user is signed in.
    """
    return {
        "name": APP_NAME,
        "version": __version__,
        "python": platform.python_version(),
        "platform": sys.platform,
        "frozen": bool(getattr(sys, "frozen", False)),
    }


@router.get("/health/ready")
async def ready() -> Response:

    from fastapi.responses import JSONResponse

    checks: dict[str, Any] = {}
    ok = True
    # DB probe
    from ..db import SessionFactory

    if SessionFactory is None:
        checks["database"] = "not-initialised"
        ok = False
    else:
        try:
            async with SessionFactory() as db:
                await db.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as e:
            checks["database"] = f"error: {type(e).__name__}"
            ok = False
    # storage probe
    try:
        st = get_storage()
        probe = st.tmp / ".probe"
        probe.write_text("ok")
        probe.unlink()
        checks["storage"] = "ok"
    except Exception as e:
        checks["storage"] = f"error: {type(e).__name__}"
        ok = False

    return JSONResponse(
        {"status": "ok" if ok else "degraded", "checks": checks},
        status_code=200 if ok else 503,
    )
