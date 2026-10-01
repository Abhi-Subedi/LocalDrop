"""tus 1.0.0-subset upload engine (ADR-005 / BC-5).

Endpoints (routers call these services):
  POST   /api/v1/uploads        creation (tus-standard Upload-Metadata header)
  HEAD   /api/v1/uploads/{id}   offset query
  PATCH  /api/v1/uploads/{id}   chunk append (offset contiguity, sha256 checksum)
  DELETE /api/v1/uploads/{id}   cancel
  GET    /api/v1/uploads        own sessions (resume after reload)

Reliability rules (spec 03 §5):
  * offset contiguity enforced under row lock (SELECT ... FOR UPDATE)
  * append to staging file first, commit offset second
  * checksum verify BEFORE offset advance
  * finalize: fsync(file)+fsync(dir) → tx(blobs+files rows, session finalized)
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import uuid as uuid_mod
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import Request
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import audit
from ..auth import Principal
from ..config import get_settings
from ..errors import Problem, not_found, validation
from ..models import Blob, File, UploadSession
from ..schemas import _validate_name
from ..storage import Storage, get_storage
from .accounts import storage_used
from .tree import get_owned_folder

TUS_VERSION = "1.0.0"


def parse_upload_metadata(header: str | None) -> dict[str, str]:
    """tus-standard: comma-separated `key base64value` pairs."""
    out: dict[str, str] = {}
    if not header:
        return out
    for pair in header.split(","):
        pair = pair.strip()
        if not pair:
            continue
        parts = pair.split(" ", 1)
        key = parts[0].strip()
        if not key:
            continue
        if len(parts) == 1 or not parts[1].strip():
            out[key] = ""
            continue
        try:
            out[key] = base64.b64decode(parts[1].strip()).decode("utf-8", "replace")
        except (binascii.Error, ValueError):
            out[key] = ""
    return out


def parse_checksum_header(header: str | None) -> tuple[str, bytes] | None:
    """`sha256 <base64>` → (algorithm, digest)."""
    if not header:
        return None
    parts = header.strip().split(" ", 1)
    if len(parts) != 2:
        raise Problem(400, "checksum", "Bad Checksum Header")
    algo, value = parts[0].lower(), parts[1].strip()
    if algo != "sha256":
        raise Problem(400, "checksum-unsupported", "Unsupported Checksum Algorithm")
    try:
        return algo, base64.b64decode(value)
    except (binascii.Error, ValueError):
        raise Problem(400, "checksum", "Bad Checksum Header") from None


async def create_upload(
    db: AsyncSession,
    p: Principal,
    metadata: dict[str, str],
    folder_id: uuid_mod.UUID,
    total_size: int,
) -> tuple[UploadSession, str]:
    s = get_settings()
    st: Storage = get_storage()

    file_name = metadata.get("filename", "").strip()
    mime_type = (metadata.get("filetype") or "").strip() or "application/octet-stream"
    if not file_name:
        raise validation("Upload-Metadata must include 'filename'.")

    # Validate through the same name path as every other entry point (BC-11)
    try:
        file_name = _validate_name(file_name)
    except ValueError as e:
        raise validation(f"Invalid file name: {e}") from None

    if total_size < 0:
        raise validation("total size must be >= 0")
    if s.max_upload_bytes and total_size > s.max_upload_bytes:
        raise Problem(413, "too-large", "File Too Large")

    folder = await get_owned_folder(db, p, folder_id)

    # quota (single-owner: unlimited unless quota set)
    user_quota = None  # v1: owner has no quota
    if user_quota is not None:
        used = await storage_used(db, p.user_id)
        if used + total_size > user_quota:
            raise Problem(413, "quota-exceeded", "Storage Quota Exceeded")

    # free-space guard: content + overhead margin
    st.ensure_free(int(total_size * 1.02) + 1024 * 1024)

    active = (
        await db.execute(
            select(func.count())
            .select_from(UploadSession)
            .where(UploadSession.user_id == p.user_id, UploadSession.status == "active")
        )
    ).scalar_one()
    if active >= s.upload_sessions_max:
        raise Problem(429, "upload-sessions", "Too many active uploads; finish or cancel some.")

    session_id = uuid_mod.uuid4()
    path = st.create_staging(str(session_id))
    now = datetime.now(UTC)
    sess = UploadSession(
        id=session_id,
        user_id=p.user_id,
        folder_id=folder.id,
        file_name=file_name,
        mime_type=mime_type[:255],
        total_size=total_size,
        offset=0,
        status="active",
        staging_path=st.to_recorded(path),
        expires_at=now + timedelta(days=s.upload_ttl_days),
    )
    db.add(sess)
    await db.flush()
    return sess, mime_type


async def get_active_session(
    db: AsyncSession, p: Principal, session_id: uuid_mod.UUID
) -> UploadSession:
    sess = (
        await db.execute(
            select(UploadSession).where(
                UploadSession.id == session_id, UploadSession.user_id == p.user_id
            )
        )
    ).scalar_one_or_none()
    if sess is None or sess.status != "active":
        # expired/unknown indistinguishable
        raise not_found()
    return sess


async def head_offset(db: AsyncSession, p: Principal, session_id: uuid_mod.UUID) -> UploadSession:
    return await get_active_session(db, p, session_id)


async def append_chunk(
    db: AsyncSession, p: Principal, session_id: uuid_mod.UUID, request: Request
) -> int:
    """Append one chunk. Returns the new offset. Raises 460 on checksum/size
    mismatch WITHOUT advancing the persisted offset."""
    s = get_settings()
    st: Storage = get_storage()

    offset_hdr = request.headers.get("Upload-Offset")
    if offset_hdr is None:
        raise validation("Upload-Offset header required")
    try:
        client_offset = int(offset_hdr)
    except ValueError:
        raise validation("Upload-Offset must be an integer") from None

    content_type = request.headers.get("Content-Type", "")
    if content_type and "application/offset+octet-stream" not in content_type:
        raise Problem(415, "media-type", "Content-Type must be application/offset+octet-stream")

    # Row lock serializes concurrent PATCHes on one session (spec 09 §races)
    sess = (
        await db.execute(
            select(UploadSession)
            .where(
                UploadSession.id == session_id,
                UploadSession.user_id == p.user_id,
                UploadSession.status == "active",
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if sess is None:
        raise not_found()

    if client_offset != sess.offset:
        raise Problem(
            460,
            "offset-conflict",
            "Upload Offset Conflict",
            f"Expected offset {sess.offset}, got {client_offset}.",
        )

    declared_length = request.headers.get("Content-Length")
    if declared_length is None:
        raise Problem(411, "length-required", "Content-Length required")
    try:
        length = int(declared_length)
    except ValueError:
        raise validation("bad Content-Length") from None
    if length <= 0 or length > s.upload_chunk_max_bytes:
        raise Problem(
            460,
            "chunk-size",
            "Chunk Size Out Of Range",
            f"Chunk must be 1..{s.upload_chunk_max_bytes} bytes.",
        )
    if sess.offset + length > sess.total_size:
        raise Problem(460, "chunk-size", "Chunk exceeds declared total size")

    checksum = parse_checksum_header(request.headers.get("Upload-Checksum"))

    # Stream to disk in bounded reads (BC-6); verify checksum while writing.
    hasher = hashlib.sha256() if checksum else None
    written = 0
    fd = st.open_append(sess.staging_path)
    try:
        async for chunk in request.stream():
            if not chunk:
                continue
            written += len(chunk)
            if written > length:
                raise Problem(460, "chunk-size", "Body exceeds declared Content-Length")
            if hasher:
                hasher.update(chunk)
            os_write(fd, chunk)
        if written != length:
            raise Problem(
                460, "chunk-size", f"Body shorter than Content-Length ({written}/{length})"
            )
    finally:
        import os as _os

        _os.close(fd)

    if checksum and hasher is not None:
        if hasher.digest() != checksum[1]:
            # truncate the appended bytes back (offset not advanced)
            await _truncate_to(db, sess, sess.offset)
            raise Problem(
                460,
                "checksum-mismatch",
                "Checksum Mismatch",
                "Chunk checksum failed; retry the chunk.",
            )

    sess.offset += length
    # remember chunk hash for resume revalidation (capped)
    if hasher:
        ch = sess.chunk_hashes or []
        ch.append({"offset": sess.offset, "sha256": hasher.hexdigest()})
        sess.chunk_hashes = ch[-1000:]

    await db.flush()
    return sess.offset


def os_write(fd: int, data: bytes) -> None:
    import os

    os.write(fd, data)


async def _truncate_to(db: AsyncSession, sess: UploadSession, size: int) -> None:
    """Roll the staging file back to `size` bytes (checksum failure path)."""
    path = get_storage().from_recorded(sess.staging_path)
    with open(path, "r+b") as f:
        f.truncate(size)


async def cancel_upload(db: AsyncSession, p: Principal, session_id: uuid_mod.UUID) -> None:
    st: Storage = get_storage()
    sess = (
        await db.execute(
            select(UploadSession).where(
                UploadSession.id == session_id, UploadSession.user_id == p.user_id
            )
        )
    ).scalar_one_or_none()
    if sess is None:
        raise not_found()
    if sess.status == "active":
        sess.status = "cancelled"
        try:
            st.delete(Path(sess.staging_path))
        except Problem:
            pass
    await db.flush()


async def list_sessions(db: AsyncSession, p: Principal) -> list[UploadSession]:
    rows = (
        (
            await db.execute(
                select(UploadSession)
                .where(UploadSession.user_id == p.user_id, UploadSession.status == "active")
                .order_by(UploadSession.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def finalize(db: AsyncSession, p: Principal, session_id: uuid_mod.UUID) -> File:
    """Finalize an upload whose offset == total_size (called by PATCH completion
    or explicit POST). Storage-first, DB-second (BC-7)."""
    st: Storage = get_storage()
    sess = (
        await db.execute(
            select(UploadSession)
            .where(
                UploadSession.id == session_id,
                UploadSession.user_id == p.user_id,
                UploadSession.status == "active",
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if sess is None:
        raise not_found()
    if sess.offset != sess.total_size:
        raise Problem(400, "upload-incomplete", "Upload Incomplete")

    st.fsync_file(Path(sess.staging_path))
    st.fsync_dir(st.staging)

    blob = Blob(
        size=sess.total_size,
        status="pending",
        storage_path=sess.staging_path,
        mime_hint=sess.mime_type,
    )
    db.add(blob)
    await db.flush()
    f = File(
        folder_id=sess.folder_id,
        name=sess.file_name,
        blob_id=blob.id,
        mime_type=sess.mime_type or "application/octet-stream",
        size=sess.total_size,
        uploader_id=p.user_id,
    )
    db.add(f)
    sess.status = "finalized"
    await db.flush()
    await audit(
        db,
        "upload.finalize",
        actor_id=str(p.user_id),
        target_type="file",
        target_id=str(f.id),
        details={"size": sess.total_size},
    )
    return f


# ---- background: hash + dedup (U5) ----


async def hash_pending_blobs(db: AsyncSession, storage: Storage, max_n: int = 10) -> int:
    """Stream sha256 over pending blobs; verify size; move staging→blobs or
    dedup-link; set status verified. Idempotent (staging is source of truth
    until rename ack)."""
    rows = (
        (
            await db.execute(
                select(Blob).where(Blob.status == "pending").order_by(Blob.created_at).limit(max_n)
            )
        )
        .scalars()
        .all()
    )
    done = 0
    for blob in rows:
        src = Path(blob.storage_path)
        try:
            actual_size = storage.size_of(src)
        except (Problem, OSError):
            # staging file missing (e.g. crashed before fsync): mark dead
            await db.execute(update(Blob).where(Blob.id == blob.id).values(status="missing"))
            continue
        if actual_size != blob.size:
            await db.execute(update(Blob).where(Blob.id == blob.id).values(status="missing"))
            continue
        h = hashlib.sha256()
        fd = storage.open_read(src)
        try:
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                h.update(chunk)
        finally:
            os.close(fd)
        digest = h.digest()
        hexdigest = digest.hex()

        # sniff MIME (pure-python magic bytes) — serving policy input
        from .serving import sniff_mime

        mime = sniff_mime(storage, src)

        # dedup: does a verified blob with this hash already exist?
        existing = (
            await db.execute(select(Blob).where(Blob.sha256 == digest, Blob.status == "verified"))
        ).scalar_one_or_none()
        if existing is not None:
            # Self-healing: the canonical bytes may be gone (out-of-band
            # delete, moved data dir). Restore the bytes at the canonical
            # path and adopt the existing row — never mint a second row for
            # the same digest (unique index), so re-uploads can't 404 forever.
            try:
                canonical_ok = storage.size_of(existing.storage_path) == existing.size
            except (OSError, Problem):
                canonical_ok = False
            if not canonical_ok:
                dst = storage.blob_path(hexdigest)
                dst.parent.mkdir(parents=True, exist_ok=True)
                try:
                    storage.replace(src, dst)
                except OSError:
                    continue  # transient; retried next tick
                # Re-anchor the row to this data dir (heals legacy absolute
                # rows pointing elsewhere too).
                existing.storage_path = storage.to_recorded(dst)
                existing.size = blob.size
                await db.execute(
                    update(File).where(File.blob_id == blob.id).values(blob_id=existing.id)
                )
                await db.delete(blob)
                done += 1
                continue
            # point pending blob at existing content: adopt existing as canonical
            # (update referencing files to point at existing blob, delete pending row)
            await db.execute(
                update(File).where(File.blob_id == blob.id).values(blob_id=existing.id)
            )
            storage.delete(src)
            await db.delete(blob)
        else:
            dst = storage.blob_path(hexdigest)
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                storage.replace(src, dst)
            except OSError:
                continue  # transient; retried next tick
            blob.sha256 = digest
            blob.status = "verified"
            blob.storage_path = storage.to_recorded(dst)
            blob.mime_sniffed = mime
            try:
                async with db.begin_nested():
                    await db.flush()
            except IntegrityError:
                # Lost the dedup race: a concurrent worker verified identical
                # bytes first (unique index on verified sha256). The moved
                # file holds identical bytes, so just link our files to the
                # winner and drop the pending row.
                winners = (
                    (
                        await db.execute(
                            select(Blob).where(Blob.sha256 == digest, Blob.status == "verified")
                        )
                    )
                    .scalars()
                    .all()
                )
                winner = next((w for w in winners if w.id != blob.id), None)
                if winner is None:
                    continue  # vanished mid-race; next tick retries
                await db.execute(
                    update(File).where(File.blob_id == blob.id).values(blob_id=winner.id)
                )
                await db.delete(blob)
        done += 1
    if done:
        await db.flush()
    return done


async def expire_sessions(db: AsyncSession, storage: Storage) -> int:
    """GC expired/cancelled upload sessions + orphan staging files."""
    now = datetime.now(UTC)
    rows = (
        (
            await db.execute(
                select(UploadSession).where(
                    UploadSession.status == "active", UploadSession.expires_at < now
                )
            )
        )
        .scalars()
        .all()
    )
    n = 0
    for sess in rows:
        sess.status = "expired"
        try:
            storage.delete(Path(sess.staging_path))
        except Problem:
            pass
        n += 1
    # orphan .part files with no session row (crash between create and flush).
    # Compare as resolved absolutes: rows may be legacy-absolute or relative;
    # rows pointing outside this data dir are someone else's problem (skip).
    known: set[str] = set()
    for k in (
        (
            await db.execute(
                select(UploadSession.staging_path).where(UploadSession.status == "active")
            )
        )
        .scalars()
        .all()
    ):
        try:
            known.add(str(storage.from_recorded(k)))
        except Problem:
            continue
    for p in storage.staging.glob("*.part"):
        if str(p.resolve()) not in known:
            try:
                storage.delete(p)
                n += 1
            except Problem:
                pass
    if n:
        await db.flush()
    return n
