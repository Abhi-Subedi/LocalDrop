"""Thumbnails (Pillow, thread pool — off the event loop) + cleanup jobs."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete as sa_delete
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..errors import Problem
from ..models import AuthSession, Blob, File, Setting
from ..storage import Storage

THUMB_SIZES = (256, 1024)
MAX_PIXELS = 80_000_000  # decompression-bomb cap (FR-P1, spec 06 §2.8)
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="localdrop-job")


async def run_in_pool(fn, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, fn, *args)


def _make_thumb_sync(storage: Storage, src: Path, dst_dir: Path, size: int) -> bool:
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        with Image.open(src) as im:
            im = im.convert("RGB")
            im.thumbnail((size, size))
            dst_dir.mkdir(parents=True, exist_ok=True)
            im.save(dst_dir / f"{size}.webp", "WEBP", quality=80)
        return True
    except Exception:
        return False


async def generate_thumbnails(db: AsyncSession, storage: Storage, file_id, max_n: int = 5) -> int:
    """Best-effort thumbs for verified image blobs."""
    from ..services.serving import sniff_mime

    rows = (
        await db.execute(
            select(File).join(Blob, File.blob_id == Blob.id).where(
                Blob.status == "verified",
                File.deleted_at.is_(None),
                File.mime_type.in_(("image/jpeg", "image/png", "image/webp", "image/gif", "image/avif")),
            )
            .order_by(File.created_at.desc())
            .limit(max_n)
        )
    ).scalars().all()
    made = 0
    for f in rows:
        if f.blob.sha256 is None:
            continue
        thumb_dir = storage.thumbs / str(f.id)
        if all((thumb_dir / f"{s}.webp").exists() for s in THUMB_SIZES):
            continue
        try:
            src = storage.from_recorded(f.blob.storage_path)
        except Problem:
            continue  # blob data lives outside this data dir; nothing to thumb
        if not src.exists():
            continue
        head_mime = sniff_mime(storage, src)
        if head_mime is None or not head_mime.startswith("image/"):
            continue
        ok = await run_in_pool(_make_thumb_sync, storage, src, thumb_dir, THUMB_SIZES[0])
        if ok:
            await run_in_pool(_make_thumb_sync, storage, src, thumb_dir, THUMB_SIZES[1])
            made += 1
    return made


async def cleanup_pass(db: AsyncSession, storage: Storage) -> dict[str, int]:
    """One GC sweep: uploads, trash purge + blob GC, sessions."""
    s = get_settings()
    now = datetime.now(UTC)
    stats: dict[str, int] = {}

    # 1. expired upload sessions + orphan staging
    from ..services.uploads import expire_sessions

    stats["uploads"] = await expire_sessions(db, storage)

    # 2. trash purge past retention → hard delete files, then blob GC
    cutoff = now - timedelta(days=s.trash_retention_days)
    stale = (
        await db.execute(
            select(File).where(File.deleted_at.is_not(None), File.deleted_at < cutoff)
        )
    ).scalars().all()
    if stale:
        await db.execute(sa_delete(File).where(File.id.in_([f.id for f in stale])))
    stats["trash_purged"] = len(stale)

    # blobs with no referencing file rows → delete row + unlink.
    # Only blobs no upload can still claim (verified/missing): pending blobs
    # belong to live upload sessions and are handled by expire_sessions —
    # collecting them here would eat in-progress uploads.
    orphan_blobs = (
        await db.execute(
            select(Blob).where(
                Blob.status.in_(("verified", "missing")),
                Blob.id.not_in(select(File.blob_id)),
            )
        )
    ).scalars().all()
    reclaimed = 0
    for b in orphan_blobs:
        try:
            p = storage.from_recorded(b.storage_path)
        except Problem:
            p = None
        if p is not None:
            try:
                storage.delete(p)
                reclaimed += b.size
            except Problem:
                pass
        await db.delete(b)
    stats["blobs_removed"] = len(orphan_blobs)
    stats["bytes_reclaimed"] = reclaimed

    # 3. expired auth sessions: revoked-and-old, idle-expired, absolute-expired
    await db.execute(
        sa_delete(AuthSession).where(
            AuthSession.expires_at < now - timedelta(days=1),
            AuthSession.revoked_at.is_not(None),
        )
    )
    await db.execute(sa_delete(AuthSession).where(AuthSession.expires_at < now - timedelta(days=1)))
    await db.execute(sa_delete(AuthSession).where(AuthSession.absolute_expires_at < now - timedelta(days=7)))

    # 4. download_count reconciliation drift logging (spec 04 §5.7)
    await db.flush()
    return stats


async def get_setting(db: AsyncSession, key: str) -> dict | None:
    row = await db.get(Setting, key)
    return row.value if row else None


async def set_setting(db: AsyncSession, key: str, value: dict) -> None:
    await db.merge(Setting(key=key, value=value))
