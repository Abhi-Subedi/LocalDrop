"""Principal resolution + auth dependencies + CSRF middleware support.

AuthN: session cookie (ld_session) OR Authorization: Bearer <PAT>.
AuthZ: object-level owned-fetch helpers live in services (BC-10); this module
only authenticates.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .db import get_db
from .errors import Problem, forbidden, unauthenticated
from .models import AuthSession, PersonalAccessToken, User
from .security import hash_token

SESSION_COOKIE = "ld_session"
SHARE_COOKIE = "ld_share"


@dataclass
class Principal:
    user_id: uuid.UUID
    username: str
    role: str
    scopes: set[str]
    via: str  # session | pat
    session: AuthSession | None = None

    @property
    def can_write(self) -> bool:
        return "write" in self.scopes


async def _load_session_user(db: AsyncSession, token: str) -> tuple[AuthSession, User] | None:
    th = hash_token(token)
    row = (
        await db.execute(
            select(AuthSession).join(User, AuthSession.user_id == User.id).where(
                AuthSession.token_hash == th
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    now = datetime.now(UTC)
    if row.revoked_at is not None or now >= min(row.expires_at, row.absolute_expires_at):
        return None
    if not row.user.is_active:
        return None
    return row, row.user


async def _load_pat_user(db: AsyncSession, token: str) -> tuple[PersonalAccessToken, User] | None:
    th = hash_token(token)
    pat = (
        await db.execute(
            select(PersonalAccessToken).join(User, PersonalAccessToken.user_id == User.id).where(
                PersonalAccessToken.token_hash == th
            )
        )
    ).scalar_one_or_none()
    if pat is None:
        return None
    now = datetime.now(UTC)
    if pat.revoked_at is not None or (pat.expires_at and now >= pat.expires_at):
        return None
    if not pat.user.is_active:
        return None
    return pat, pat.user


async def resolve_principal(
    request: Request, db: AsyncSession = Depends(get_db)
) -> Principal:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        loaded = await _load_session_user(db, token)
        if loaded is not None:
            sess, user = loaded
            return Principal(
                user_id=user.id,
                username=user.username,
                role=user.role,
                scopes={"read", "write"},
                via="session",
                session=sess,
            )

    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        raw = auth[7:].strip()
        loaded = await _load_pat_user(db, raw)
        if loaded is not None:
            pat, user = loaded
            return Principal(
                user_id=user.id,
                username=user.username,
                role=user.role,
                scopes=set(pat.scopes.split(",")),
                via="pat",
            )

    raise unauthenticated()


async def require_write(p: Principal = Depends(resolve_principal)) -> Principal:
    if not p.can_write:
        raise forbidden(detail="This token lacks the 'write' scope.")
    return p


async def require_read(p: Principal = Depends(resolve_principal)) -> Principal:
    return p  # read is implied by any valid principal


def require_role(role: str):
    async def _dep(p: Principal = Depends(resolve_principal)) -> Principal:
        if p.role != role and p.role != "owner":
            raise forbidden()
        return p

    return _dep


def check_csrf(request: Request) -> None:
    """Cookie-auth unsafe methods must carry the custom header (spec 05 §1).

    Bearer-auth requests are exempt (no ambient credential).
    """
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        if request.headers.get("Authorization", "").startswith("Bearer "):
            return
        if request.headers.get("X-Requested-With") != "localdrop":
            raise Problem(403, "csrf", "CSRF check failed", "Missing X-Requested-With header.")


def settings_ok() -> None:
    get_settings()
