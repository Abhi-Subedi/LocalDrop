"""Demo mode endpoints: hand each visitor an isolated throwaway account.

Only mounted when LOCALDROP_DEMO_MODE=true. Everything else about the instance
is unchanged — the demo uses the real upload, browse, preview and share paths,
so what a visitor tries is what they would get on their own server.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import SESSION_COOKIE, check_csrf
from ..config import get_settings
from ..db import get_db
from ..errors import Problem
from ..ratelimit import LIMITS, client_ip_from_headers
from ..services import demo

router = APIRouter(tags=["demo"])


def _client_ip(request: Request) -> str:
    s = request.app.state.settings
    return client_ip_from_headers(
        request.client.host if request.client else "0.0.0.0",
        request.headers.get("X-Forwarded-For"),
        s.trusted_proxies,
    )


def _require_demo(request: Request) -> None:
    if not request.app.state.settings.demo_mode:
        raise Problem(404, "not-found", "Not Found", "This endpoint is not available.")


@router.get("/demo/status")
async def demo_status(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """What the SPA needs to decide whether to offer the demo path.

    Degrades instead of raising: if the database is unreachable the demo is not
    working whatever we report, and a 500 here would leave the SPA spinning on a
    request that can never succeed. `accepting_visitors: false` sends the
    visitor to the login page, which fails with something they can read.
    """
    _require_demo(request)
    s = get_settings()
    try:
        accepting = await demo.claim_window_open(db)
    except Exception:
        accepting = False
    return {
        "demo_mode": True,
        # The SPA skips onboarding and login entirely when this is true.
        "accepting_visitors": accepting,
        "max_upload_bytes": s.effective_max_upload_bytes(),
        "ttl_minutes": s.demo_ttl_minutes,
        "notice": s.demo_notice,
    }


@router.post("/demo/session", status_code=201)
async def create_demo_session_ep(
    request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> dict:
    """Create a throwaway account and sign the visitor in.

    No body and no credentials: a visitor gets an account by asking, which is
    the whole point. There is nothing here to guess, and nothing worth stealing,
    because the account is deleted shortly.
    """
    _require_demo(request)
    check_csrf(request)
    ip = _client_ip(request)
    # Per-IP, because this endpoint creates a database row: a crawler must not
    # be able to mint thousands of accounts from one address.
    LIMITS.auth.check(ip)

    if not await demo.claim_window_open(db):
        raise Problem(
            503,
            "demo-closed",
            "Demo Closed",
            "This demo is not accepting new visitors right now.",
            headers={"Retry-After": "3600"},
        )

    user, raw, expires = await demo.create_demo_session(
        db, ip, request.headers.get("user-agent", "")
    )
    await db.commit()

    # Same cookie policy as a real login. Over the demo tunnel the request is
    # https, so Secure is set; over plain http on a LAN it is not, which is why
    # this mirrors _secure_cookie in the auth router rather than hard-coding.
    proto = request.headers.get("X-Forwarded-Proto", "")
    secure = request.url.scheme == "https" or proto == "https"
    response.set_cookie(
        SESSION_COOKIE,
        raw,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
        max_age=max(0, int((expires - datetime.now(UTC)).total_seconds())),
    )
    return {
        "username": user.username,
        "expires_at": expires.isoformat(),
        "max_upload_bytes": get_settings().effective_max_upload_bytes(),
    }
