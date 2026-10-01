"""Public demo mode: one throwaway account per visitor, deleted after a while.

LocalDrop's threat model is a trusted LAN, and its own SECURITY.md says not to
expose it to the open internet. A public demo is exactly that exposure, so demo
mode exists to make the exposure survivable rather than to wish it away:

* every visitor gets their **own** account, so one person cannot read or delete
  another person's files — a shared demo account would be a data leak waiting to
  be demonstrated;
* the account and its files are **deleted** after `demo_ttl_minutes` of
  inactivity, so nothing accumulates and a crawler's uploads do not become the
  host's storage bill;
* uploads are capped at `demo_max_upload_bytes`;
* sessions are short and the claim window closes, so the demo cannot be adopted
  as a permanent free host.

What demo mode deliberately does *not* do is pretend to be hardened. The
per-user model, the rate limits and the upload cap are the real defences; if
those are wrong, the demo is wrong. See ADR-011.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..errors import Problem
from ..models import AuthSession, Blob, File, Folder, PersonalAccessToken, User
from ..security import hash_password, hash_token, new_token

# Demo accounts are ordinary `user`-role rows, tagged by username prefix. A
# migration adding an is_demo column would be tidier, but a prefix is
# sufficient, is greppable with the other identifiers, and keeps the V1 schema
# frozen — the alternative is a schema change in a release whose headline is
# packaging.
DEMO_PREFIX = "guest-"
DEMO_CLAIMED_KEY = "demo_claimed_at"


def is_demo_user(user: User) -> bool:
    return user.username.startswith(DEMO_PREFIX)


async def claim_window_open(db: AsyncSession) -> bool:
    """True while a human may still claim the owner account over the tunnel.

    The demo workflow boots the stack and immediately opens a public tunnel. If
    the demo could hand out sessions instantly, a stranger's crawler could win
    the race and lock the real owner out. The operator claims the owner
    account during this window; afterwards the endpoint refuses.
    """
    from ..models import Setting

    s = get_settings()
    if not s.demo_mode:
        return True
    row = await db.get(Setting, DEMO_CLAIMED_KEY)
    if row is not None:
        return False
    # A pre-existing owner means the claim window is moot.
    return await _owner_exists(db)


async def mark_claimed(db: AsyncSession) -> None:
    """Called once the owner exists, so the demo stops accepting new visitors."""
    from ..models import Setting

    s = get_settings()
    if not s.demo_mode:
        return
    if await db.get(Setting, DEMO_CLAIMED_KEY) is None:
        db.add(Setting(key=DEMO_CLAIMED_KEY, value={"at": datetime.now(UTC).isoformat()}))


async def _owner_exists(db: AsyncSession) -> bool:
    count = (
        await db.execute(select(func.count()).select_from(User).where(User.role == "owner"))
    ).scalar_one()
    return bool(count)


async def live_demo_users(db: AsyncSession) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(User).where(User.username.like(f"{DEMO_PREFIX}%"))
        )
    ).scalar_one()


async def create_demo_session(
    db: AsyncSession, ip: str, user_agent: str
) -> tuple[User, str, datetime]:
    """Create a throwaway user and sign them in. Returns (user, raw token, expiry).

    The password is random and never disclosed: the demo has no password login,
    the cookie is the credential, and a disclosed password would be an
    invitation to enumerate throwaway accounts.
    """
    s = get_settings()
    if not s.demo_mode:
        raise Problem(404, "not-found", "Not Found", "This endpoint is not available.")

    if await live_demo_users(db) >= s.demo_max_users:
        raise Problem(
            503,
            "demo-full",
            "Demo Busy",
            "The demo is at capacity. Please try again in a few minutes.",
            headers={"Retry-After": "300"},
        )

    # 24 bits of entropy is plenty: these accounts hold nothing of value, and
    # they exist only to be deleted.
    username = f"{DEMO_PREFIX}{uuid.uuid4().hex[:10]}"
    now = datetime.now(UTC)
    user = User(
        username=username,
        password_hash=hash_password(new_token(24)),
        role="user",
    )
    db.add(user)
    await db.flush()

    raw = new_token(32)
    expires = now + timedelta(minutes=s.demo_ttl_minutes)
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=hash_token(raw),
            last_seen_at=now,
            # Sliding expiry is bounded by the demo TTL: a visitor who keeps
            # working is still reclaimed once they go quiet.
            expires_at=expires,
            absolute_expires_at=expires,
            ip=ip,
            user_agent=(user_agent or "")[:512],
        )
    )
    return user, raw, expires


async def purge_expired(db: AsyncSession) -> int:
    """Delete demo accounts idle for longer than the TTL, with their files.

    Returns the number of accounts removed.
    """
    s = get_settings()
    if not s.demo_mode:
        return 0

    cutoff = datetime.now(UTC) - timedelta(minutes=s.demo_ttl_minutes)
    stale = list(
        (
            await db.execute(
                select(User.id).where(
                    User.username.like(f"{DEMO_PREFIX}%"),
                    User.updated_at < cutoff,
                )
            )
        )
        .scalars()
        .all()
    )
    if not stale:
        return 0
    return await _delete_users(db, stale)


async def purge_all(db: AsyncSession) -> int:
    """Remove every demo account immediately. Used by the demo teardown step."""
    ids = list(
        (await db.execute(select(User.id).where(User.username.like(f"{DEMO_PREFIX}%"))))
        .scalars()
        .all()
    )
    if not ids:
        return 0
    return await _delete_users(db, ids)


async def _delete_users(db: AsyncSession, ids: list) -> int:
    """Delete users and everything they own, reclaiming now-orphaned blobs."""
    file_ids = list(
        (await db.execute(select(File.id).where(File.uploader_id.in_(ids)))).scalars().all()
    )
    blob_ids = set(
        (await db.execute(select(File.blob_id).where(File.uploader_id.in_(ids)))).scalars().all()
    )

    await _delete_shares_for_files(db, file_ids)
    await db.execute(delete(File).where(File.uploader_id.in_(ids)))
    await db.execute(delete(Folder).where(Folder.owner_id.in_(ids)))
    await db.execute(delete(PersonalAccessToken).where(PersonalAccessToken.user_id.in_(ids)))
    await db.execute(delete(AuthSession).where(AuthSession.user_id.in_(ids)))
    await db.execute(delete(User).where(User.id.in_(ids)))

    # A blob is content addressed, so a demo upload of a file some other user
    # also uploaded is the *same* row. Only reclaim when nothing else points at
    # it, or the demo would delete a real user's file.
    for blob_id in blob_ids:
        still_used = (
            await db.execute(
                select(func.count())
                .select_from(File)
                .join(Blob, File.blob_id == Blob.id)
                .where(Blob.id == blob_id, File.uploader_id.notin_(ids))
            )
        ).scalar_one()
        if not still_used:
            await db.execute(delete(Blob).where(Blob.id == blob_id))
    return len(ids)


async def _delete_shares_for_files(db: AsyncSession, file_ids: list) -> None:
    from ..models import Share, ShareDownload

    if not file_ids:
        return
    share_ids = list(
        (await db.execute(select(Share.id).where(Share.file_id.in_(file_ids)))).scalars().all()
    )
    if not share_ids:
        return
    await db.execute(delete(ShareDownload).where(ShareDownload.share_id.in_(share_ids)))
    await db.execute(delete(Share).where(Share.id.in_(share_ids)))


async def touch(db: AsyncSession, user: User) -> None:
    """Reset the idle clock so an active visitor is not purged mid-upload."""
    await db.execute(update(User).where(User.id == user.id).values(updated_at=datetime.now(UTC)))
