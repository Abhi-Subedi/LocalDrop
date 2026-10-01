"""Account services: onboarding, login, sessions, password change, PATs."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import audit
from ..auth import Principal
from ..config import get_settings
from ..errors import Problem, bad_credentials, not_found, validation
from ..models import AuthSession, File, PersonalAccessToken, Setting, User
from ..security import hash_password, hash_token, new_token, verify_password

SETUP_TOKEN_TTL_MINUTES = 15
SETUP_TOKEN_KEY = "setup_token"


async def onboarding_required(db: AsyncSession) -> bool:
    count = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    return count == 0


async def _issue_setup_token(db: AsyncSession) -> str:
    token = new_token(18)
    await db.merge(
        Setting(
            key=SETUP_TOKEN_KEY,
            value={
                "hash": hash_token(token),
                "expires": (
                    datetime.now(UTC) + timedelta(minutes=SETUP_TOKEN_TTL_MINUTES)
                ).isoformat(),
            },
        )
    )
    return token


async def get_or_issue_setup_token(db: AsyncSession) -> str | None:
    """Issue a fresh setup token. None if onboarding is done.

    Only ONE token is valid at a time: each issuance replaces the previous
    row, so the console print and the /setup/token endpoint share
    last-writer-wins semantics. Pre-owner the server has no other users, so
    whoever completes setup first (the installer) wins — complete setup
    immediately after first boot.
    """
    if not await onboarding_required(db):
        return None
    return await _issue_setup_token(db)


async def create_owner(db: AsyncSession, username: str, password: str, setup_token: str) -> User:
    if not await onboarding_required(db):
        raise Problem(410, "setup-done", "Onboarding Completed", "An owner already exists.")
    row = await db.get(Setting, SETUP_TOKEN_KEY)
    if row is None:
        raise Problem(410, "setup-expired", "Setup Token Invalid")
    expires = datetime.fromisoformat(row.value["expires"])
    if datetime.now(UTC) >= expires:
        raise Problem(
            410, "setup-expired", "Setup Token Expired", "Restart the server for a new token."
        )
    from ..security import constant_time_equals

    if not constant_time_equals(row.value["hash"], hash_token(setup_token)):
        raise Problem(410, "setup-expired", "Setup Token Invalid")

    user = User(
        username=username,
        password_hash=hash_password(password),
        role="owner",
    )
    db.add(user)
    await db.delete(row)
    await db.merge(Setting(key="onboarding_completed", value={"done": True}))
    await audit(db, "setup.completed", actor_id=None, details={"username": username})
    await db.flush()
    return user


async def login(
    db: AsyncSession, username: str, password: str, ip: str, user_agent: str
) -> tuple[User, str]:
    user = (
        await db.execute(select(User).where(func.lower(User.username) == username.lower().strip()))
    ).scalar_one_or_none()
    # Constant-shape: verify even when user missing (cheap random hash) to
    # avoid trivially-timed user enumeration.
    if user is None:
        hash_password("timing-equalizer")
        raise bad_credentials()
    if not user.is_active:
        raise bad_credentials()
    if not verify_password(user.password_hash, password):
        raise bad_credentials()

    s = get_settings()
    now = datetime.now(UTC)
    raw = new_token(32)
    sess = AuthSession(
        user_id=user.id,
        token_hash=hash_token(raw),
        last_seen_at=now,
        expires_at=now + timedelta(minutes=s.session_idle_minutes),
        absolute_expires_at=now + timedelta(minutes=s.session_absolute_minutes),
        ip=ip,
        user_agent=(user_agent or "")[:512],
    )
    db.add(sess)
    await audit(db, "auth.login", actor_id=str(user.id), actor_ip=ip)
    await db.flush()
    return user, raw


async def logout(db: AsyncSession, principal: Principal) -> None:
    if principal.session is not None:
        principal.session.revoked_at = datetime.now(UTC)
        await audit(db, "auth.logout", actor_id=str(principal.user_id))


async def touch_session(db: AsyncSession, principal: Principal) -> None:
    """Sliding idle expiry; called on authenticated requests."""
    if principal.session is None:
        return
    s = get_settings()
    now = datetime.now(UTC)
    new_expiry = now + timedelta(minutes=s.session_idle_minutes)
    cap = principal.session.absolute_expires_at
    principal.session.last_seen_at = now
    principal.session.expires_at = min(new_expiry, cap)


async def list_sessions(db: AsyncSession, principal: Principal) -> list[AuthSession]:
    rows = (
        (
            await db.execute(
                select(AuthSession)
                .where(AuthSession.user_id == principal.user_id, AuthSession.revoked_at.is_(None))
                .order_by(AuthSession.last_seen_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def revoke_session(db: AsyncSession, principal: Principal, session_id: uuid.UUID) -> None:
    row = (
        await db.execute(
            select(AuthSession).where(
                AuthSession.id == session_id, AuthSession.user_id == principal.user_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise not_found()
    row.revoked_at = datetime.now(UTC)
    await audit(db, "auth.session_revoked", actor_id=str(principal.user_id))


async def change_password(db: AsyncSession, principal: Principal, current: str, new: str) -> None:
    user = await db.get(User, principal.user_id)
    if user is None or not verify_password(user.password_hash, current):
        raise bad_credentials()
    user.password_hash = hash_password(new)
    # revoke all other sessions
    await db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    if principal.session is not None:
        await db.refresh(principal.session)
        principal.session.revoked_at = None
    await audit(db, "auth.password_changed", actor_id=str(user.id))


async def storage_used(db: AsyncSession, user_id: uuid.UUID) -> int:
    return int(
        (
            await db.execute(
                select(func.coalesce(func.sum(File.size), 0)).where(
                    File.uploader_id == user_id, File.deleted_at.is_(None)
                )
            )
        ).scalar_one()
    )


# ---- PATs ----


async def create_pat(
    db: AsyncSession, principal: Principal, name: str, scopes: str
) -> tuple[PersonalAccessToken, str]:
    raw = new_token(24)
    pat = PersonalAccessToken(
        user_id=principal.user_id, name=name, token_hash=hash_token(raw), scopes=scopes
    )
    db.add(pat)
    await audit(db, "auth.token_created", actor_id=str(principal.user_id), details={"name": name})
    await db.flush()
    return pat, raw


async def list_pats(db: AsyncSession, principal: Principal) -> list[PersonalAccessToken]:
    rows = (
        (
            await db.execute(
                select(PersonalAccessToken)
                .where(
                    PersonalAccessToken.user_id == principal.user_id,
                    PersonalAccessToken.revoked_at.is_(None),
                )
                .order_by(PersonalAccessToken.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def revoke_pat(db: AsyncSession, principal: Principal, pat_id: uuid.UUID) -> None:
    pat = (
        await db.execute(
            select(PersonalAccessToken).where(
                PersonalAccessToken.id == pat_id, PersonalAccessToken.user_id == principal.user_id
            )
        )
    ).scalar_one_or_none()
    if pat is None:
        raise not_found()
    pat.revoked_at = datetime.now(UTC)
    await audit(db, "auth.token_revoked", actor_id=str(principal.user_id))


def validate_username(username: str) -> str:
    if len(username) < 3 or len(username) > 32:
        raise validation("username must be 3-32 characters")
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789_.-")
    if not set(username) <= allowed:
        raise validation("username may only contain a-z, 0-9, dot, dash, underscore")
    return username
