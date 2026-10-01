"""Share services: 130-bit tokens, expiry, password, atomic download limits.

Limit enforcement is TOCTOU-free: the increment happens via a conditional
UPDATE ... WHERE download_count < max_downloads RETURNING (spec 04 §5.7).
Unknown / revoked / expired states are indistinguishable to non-holders.
"""

from __future__ import annotations

import uuid as uuid_mod
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import audit
from ..auth import Principal
from ..config import get_settings
from ..errors import forbidden, not_found, validation
from ..models import File, Share, ShareDownload, UploadSession  # noqa: F401 (UploadSession unused)
from ..security import hash_password, share_token, verify_password
from .tree import get_owned_file

BACKOFF = {"n": 0}


async def create_share(
    db: AsyncSession,
    p: Principal,
    file_id: uuid_mod.UUID,
    expires_at: datetime | None,
    max_downloads: int | None,
    password: str | None,
    base_url: str,
) -> tuple[Share, str]:
    f = await get_owned_file(db, p, file_id)  # ownership + 404 semantics
    if f.deleted_at is not None:
        raise not_found()
    if password is not None and len(password) < 1:
        raise validation("password must not be empty")
    if expires_at is not None and expires_at <= datetime.now(UTC):
        raise validation("expiry must be in the future")
    share = Share(
        token=share_token(),
        target_type="file",
        file_id=f.id,
        created_by=p.user_id,
        expires_at=expires_at,
        max_downloads=max_downloads,
        password_hash=hash_password(password) if password else None,
    )
    db.add(share)
    await audit(
        db,
        "share.create",
        actor_id=str(p.user_id),
        target_type="file",
        target_id=str(f.id),
        details={"has_password": bool(password), "max_downloads": max_downloads},
    )
    await db.flush()
    return share, f"{base_url}/s/{share.token}"


async def get_share_qr_svg(url: str) -> str:
    import io

    import qrcode.image.svg

    img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=12)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode("utf-8")


async def list_shares(db: AsyncSession, p: Principal) -> list[Share]:
    rows = (
        (
            await db.execute(
                select(Share).where(Share.created_by == p.user_id).order_by(Share.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def get_owned_share(db: AsyncSession, p: Principal, share_id: uuid_mod.UUID) -> Share:
    row = (
        await db.execute(select(Share).where(Share.id == share_id, Share.created_by == p.user_id))
    ).scalar_one_or_none()
    if row is None:
        raise not_found()
    return row


async def update_share(
    db: AsyncSession,
    p: Principal,
    share_id: uuid_mod.UUID,
    *,
    expires_at: datetime | None = None,
    max_downloads: int | None = None,
    password: str | None = None,
    clear_password: bool = False,
    clear_expiry: bool = False,
) -> Share:
    share = await get_owned_share(db, p, share_id)
    if clear_expiry:
        share.expires_at = None
    elif expires_at is not None:
        if expires_at <= datetime.now(UTC):
            raise validation("expiry must be in the future")
        share.expires_at = expires_at
    if max_downloads is not None:
        share.max_downloads = max_downloads
    if clear_password:
        share.password_hash = None
    elif password:
        share.password_hash = hash_password(password)
    await audit(
        db, "share.update", actor_id=str(p.user_id), target_type="share", target_id=str(share.id)
    )
    await db.flush()
    return share


async def revoke_share(db: AsyncSession, p: Principal, share_id: uuid_mod.UUID) -> Share:
    share = await get_owned_share(db, p, share_id)
    share.revoked_at = datetime.now(UTC)
    await audit(
        db, "share.revoke", actor_id=str(p.user_id), target_type="share", target_id=str(share.id)
    )
    await db.flush()
    return share


# ---- public (anonymous) surface ----


def _valid(share: Share) -> bool:
    """Identity validity: revoked/expired shares don't exist (404, no oracle).

    NOTE: download-count exhaustion is NOT checked here on purpose — an
    exhausted link reports 403 `share-limit-reached` from the download path
    so holders get a truthful message. The limit itself is still enforced
    atomically by increment_download_atomic.
    """
    now = datetime.now(UTC)
    if share.revoked_at is not None:
        return False
    if share.expires_at is not None and now >= share.expires_at:
        return False
    return True


async def get_public_share(db: AsyncSession, token: str) -> Share:
    """Load by token; ALL invalid states → identical 404 (no oracle)."""
    share = (await db.execute(select(Share).where(Share.token == token))).scalar_one_or_none()
    if share is None or not _valid(share):
        raise not_found()
    return share


async def unlock_share(db: AsyncSession, ip: str, token: str, password: str) -> str:
    """Verify password → return a share-session key (cookie value).
    The key is an HMAC of the token under the server secret: stateless,
    bound to this share, and impossible to derive without the secret."""
    import hashlib
    import hmac as hmac_mod

    from ..ratelimit import LIMITS

    LIMITS.auth.check(ip, identity=f"unlock:{token}")
    share = (await db.execute(select(Share).where(Share.token == token))).scalar_one_or_none()
    if share is None or not _valid(share) or share.password_hash is None:
        raise not_found()
    if not verify_password(share.password_hash, password):
        await audit(
            db, "share.password_failed", actor_ip=ip, target_type="share", target_id=str(share.id)
        )
        raise forbidden("share-locked", "Incorrect password.")
    await audit(db, "share.unlocked", actor_ip=ip, target_type="share", target_id=str(share.id))
    secret = get_settings().secret_key.encode()
    return hmac_mod.new(secret, f"share-unlock:{token}".encode(), hashlib.sha256).hexdigest()[:32]


def expected_share_key(token: str) -> str:
    import hashlib
    import hmac as hmac_mod

    secret = get_settings().secret_key.encode()
    return hmac_mod.new(secret, f"share-unlock:{token}".encode(), hashlib.sha256).hexdigest()[:32]


async def increment_download_atomic(db: AsyncSession, share: Share) -> bool:
    """TOCTOU-free limit enforcement. False means limit reached."""
    if share.max_downloads is None:
        share.download_count += 1
        return True
    res = await db.execute(
        update(Share)
        .where(
            Share.id == share.id,
            Share.revoked_at.is_(None),
            (Share.expires_at.is_(None) | (Share.expires_at > datetime.now(UTC))),
            Share.download_count < Share.max_downloads,
        )
        .values(download_count=Share.download_count + 1)
    )
    # The conditional UPDATE is the lock: exactly one row matches per allowed
    # download, so rowcount==1 means the counter moved and the share is live.
    rowcount = getattr(res, "rowcount", 0)
    return rowcount == 1


async def record_download(
    db: AsyncSession,
    share: Share,
    file_id: uuid_mod.UUID,
    session_key: str,
    ip: str,
    user_agent: str,
) -> None:
    """One analytics row per (share, viewer session). Repeat downloads from
    the same session update nothing here — the counter in `shares` is the
    authority for limits (increment_download_atomic)."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    stmt = (
        pg_insert(ShareDownload)
        .values(
            share_id=share.id,
            session_key=session_key,
            file_id=file_id,
            ip=ip,
            user_agent=(user_agent or "")[:512],
        )
        # uq_share_downloads_human is a unique *index* (not a constraint),
        # so target it by columns.
        .on_conflict_do_nothing(index_elements=["share_id", "session_key"])
    )
    await db.execute(stmt)


async def share_file(share: Share) -> File:
    if share.file is None or share.file.deleted_at is not None:
        raise not_found()
    return share.file
