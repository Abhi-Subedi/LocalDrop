"""Setup + auth + account endpoints (spec 05 §2.2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import audit
from ..auth import (
    SESSION_COOKIE,
    Principal,
    check_csrf,
    resolve_principal,
)
from ..db import get_db
from ..errors import unauthenticated
from ..ratelimit import LIMITS, client_ip_from_headers
from ..schemas import (
    LoginRequest,
    OwnerCreate,
    PasswordChange,
    PATCreate,
    SessionOut,
    SetupStatus,
    TokenCreated,
    TokenOut,
    UserOut,
)
from ..security import hash_token, new_token
from ..services import accounts

router = APIRouter(tags=["auth"])


def _client_ip(request: Request) -> str:
    s = request.app.state.settings
    return client_ip_from_headers(
        request.client.host if request.client else "0.0.0.0",
        request.headers.get("X-Forwarded-For"),
        s.trusted_proxies,
    )


def _secure_cookie(request: Request) -> bool:
    proto = request.headers.get("X-Forwarded-Proto", "")
    return request.url.scheme == "https" or proto == "https"


@router.get("/setup/status", response_model=SetupStatus)
async def setup_status_ep(db: AsyncSession = Depends(get_db)) -> SetupStatus:
    return SetupStatus(onboarding_required=await accounts.onboarding_required(db))


@router.get("/setup/token")
async def setup_token_ep(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """Returns the setup token ONLY while onboarding is pending.

    V1 posture: on a trusted LAN, first-run onboarding is open to whoever
    reaches the server first (documented in INSTALLATION). The console also
    prints the token at startup; both consume the same single-use value.
    """
    needed = await accounts.onboarding_required(db)
    if not needed:
        return {"onboarding_required": False, "token_available": False}
    token = await accounts.get_or_issue_setup_token(db)
    return {"onboarding_required": True, "token_available": token is not None, "token": token}


@router.post("/setup/owner", status_code=201)
async def setup_owner_ep(
    body: OwnerCreate, request: Request, db: AsyncSession = Depends(get_db)
) -> UserOut:
    LIMITS.auth.check(_client_ip(request))
    check_csrf(request)
    username = accounts.validate_username(body.username)
    user = await accounts.create_owner(db, username, body.password, body.setup_token)
    await db.commit()
    return UserOut(
        id=user.id, username=user.username, role=user.role,
        storage_used=0, storage_quota=None,
    )


@router.post("/auth/login", status_code=204)
async def login_ep(
    body: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> Response:
    ip = _client_ip(request)
    LIMITS.auth.check(ip, identity=body.username)
    check_csrf(request)
    user, raw = await accounts.login(db, body.username, body.password, ip, request.headers.get("User-Agent", ""))
    await db.commit()
    response.set_cookie(
        SESSION_COOKIE,
        raw,
        httponly=True,
        samesite="lax",
        secure=_secure_cookie(request),
        max_age=request.app.state.settings.session_absolute_minutes * 60,
        path="/",
    )
    response.status_code = 204
    return response


@router.post("/auth/logout", status_code=204)
async def logout_ep(
    request: Request,
    response: Response,
    p: Principal = Depends(resolve_principal),
    db: AsyncSession = Depends(get_db),
) -> Response:
    check_csrf(request)
    await accounts.logout(db, p)
    await db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.status_code = 204
    return response


@router.get("/auth/sessions", response_model=list[SessionOut])
async def sessions_ep(
    p: Principal = Depends(resolve_principal), db: AsyncSession = Depends(get_db)
) -> list[SessionOut]:
    rows = await accounts.list_sessions(db, p)
    return [
        SessionOut(
            id=s.id,
            created_at=s.last_seen_at,
            last_seen_at=s.last_seen_at,
            ip=s.ip,
            user_agent=s.user_agent,
            current=(p.session is not None and s.id == p.session.id),
        )
        for s in rows
    ]


@router.delete("/auth/sessions/{session_id}", status_code=204)
async def revoke_session_ep(
    session_id, request: Request,
    p: Principal = Depends(resolve_principal), db: AsyncSession = Depends(get_db),
) -> Response:
    import uuid as uuid_mod

    check_csrf(request)
    await accounts.revoke_session(db, p, uuid_mod.UUID(str(session_id)))
    await db.commit()
    return Response(status_code=204)


@router.get("/me", response_model=UserOut)
async def me_ep(
    p: Principal = Depends(resolve_principal), db: AsyncSession = Depends(get_db)
) -> UserOut:
    used = await accounts.storage_used(db, p.user_id)
    return UserOut(
        id=p.user_id, username=p.username, role=p.role,
        storage_used=used, storage_quota=None,
    )


@router.put("/me/password", status_code=204)
async def password_ep(
    body: PasswordChange,
    request: Request,
    response: Response,
    p: Principal = Depends(resolve_principal),
    db: AsyncSession = Depends(get_db),
) -> Response:
    check_csrf(request)
    await accounts.change_password(db, p, body.current, body.new)
    await db.commit()
    # keep the caller logged in: rotate to a fresh session
    raw = new_token(32)
    from ..models import AuthSession
    from datetime import UTC, datetime, timedelta

    s = request.app.state.settings
    now = datetime.now(UTC)
    sess = AuthSession(
        user_id=p.user_id,
        token_hash=hash_token(raw),
        last_seen_at=now,
        expires_at=now + timedelta(minutes=s.session_idle_minutes),
        absolute_expires_at=now + timedelta(minutes=s.session_absolute_minutes),
        ip=_client_ip(request),
        user_agent=(request.headers.get("User-Agent") or "")[:512],
    )
    db.add(sess)
    await db.commit()
    response.set_cookie(
        SESSION_COOKIE, raw, httponly=True, samesite="lax",
        secure=_secure_cookie(request), max_age=s.session_absolute_minutes * 60, path="/",
    )
    response.status_code = 204
    return response


@router.post("/me/tokens", response_model=TokenCreated, status_code=201)
async def create_token_ep(
    body: PATCreate,
    request: Request,
    p: Principal = Depends(resolve_principal),
    db: AsyncSession = Depends(get_db),
) -> TokenCreated:
    check_csrf(request)
    pat, raw = await accounts.create_pat(db, p, body.name, body.scopes)
    await db.commit()
    return TokenCreated(
        id=pat.id, name=pat.name, scopes=pat.scopes, created_at=pat.created_at,
        last_used_at=None, token=raw,
    )


@router.get("/me/tokens", response_model=list[TokenOut])
async def list_tokens_ep(
    p: Principal = Depends(resolve_principal), db: AsyncSession = Depends(get_db)
) -> list[TokenOut]:
    rows = await accounts.list_pats(db, p)
    return [
        TokenOut(id=t.id, name=t.name, scopes=t.scopes, created_at=t.created_at, last_used_at=t.last_used_at)
        for t in rows
    ]


@router.delete("/me/tokens/{token_id}", status_code=204)
async def revoke_token_ep(
    token_id, request: Request,
    p: Principal = Depends(resolve_principal), db: AsyncSession = Depends(get_db),
) -> Response:
    import uuid as uuid_mod

    check_csrf(request)
    await accounts.revoke_pat(db, p, uuid_mod.UUID(str(token_id)))
    await db.commit()
    return Response(status_code=204)
