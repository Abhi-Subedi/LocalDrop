"""Streaming downloads with single-range support (BC-6, spec 03 §6, §12).

Range policy: single range only; multi-range headers are degraded to a full
response (sidesteps the GHSA-7f5h-v6xp-fcq8 DoS class entirely).
No DB writes inside the streaming loop.
"""

from __future__ import annotations

import re
from typing import AsyncIterator

from starlette.responses import StreamingResponse

from ..errors import Problem
from ..models import File
from ..services.serving import content_disposition_value, decide_serving
from ..storage import Storage

READ_SIZE = 256 * 1024
RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


def parse_single_range(range_header: str, size: int) -> tuple[int, int] | None:
    """Return (start, end) inclusive, or None for full-body / unsatisfiable→raise.
    Multi-range or malformed → None (serve 200 full body)."""
    if not range_header:
        return None
    if "," in range_header:  # multi-range: degrade to full response
        return None
    m = RANGE_RE.match(range_header.strip())
    if not m:
        return None
    start_s, end_s = m.groups()
    if start_s == "" and end_s == "":
        return None
    if start_s == "":
        # suffix range: last N bytes
        n = int(end_s)
        if n == 0:
            raise Problem(416, "range", "Range Not Satisfiable")
        start = max(0, size - n)
        end = size - 1
    else:
        start = int(start_s)
        end = int(end_s) if end_s else size - 1
    if start >= size:
        raise Problem(416, "range", "Range Not Satisfiable")
    end = min(end, size - 1)
    if start > end:
        raise Problem(416, "range", "Range Not Satisfiable")
    return start, end


async def file_stream(storage: Storage, path, start: int, length: int) -> AsyncIterator[bytes]:
    fd = storage.open_read(path)
    try:
        import os

        if start:
            os.lseek(fd, start, os.SEEK_SET)
        remaining = length
        while remaining > 0:
            chunk = os.read(fd, min(READ_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk
    finally:
        import os

        os.close(fd)


def file_response(
    storage: Storage,
    f: File,
    range_header: str | None,
    if_range: str | None,
    etag: str | None,
) -> StreamingResponse:
    """Build the streaming response for a file's blob."""
    import os

    size = f.size
    # Fail cleanly BEFORE streaming starts: unreadable blob data (missing
    # file, or a legacy absolute row pointing outside this data dir) is a
    # 404, never a mid-stream connection abort or a 500.
    try:
        storage.size_of(f.blob.storage_path)
    except (OSError, Problem):
        from ..errors import not_found as _not_found

        raise _not_found("File data is not available on the server.") from None
    decision = decide_serving(f.mime_type, f.blob.mime_sniffed if f.blob else None)

    # If-Range: only honor range when ETag matches (else full body)
    effective_range = range_header
    if range_header and if_range and etag and if_range.strip() != f'"{etag}"':
        effective_range = None

    headers = {
        "Accept-Ranges": "bytes",
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": content_disposition_value(decision, f.name),
    }
    if decision.safe_inline and decision.content_type == "application/pdf":
        headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
    if etag:
        headers["ETag"] = f'"{etag}"'

    if effective_range:
        rng = parse_single_range(effective_range, size)
        if rng is None:
            start, body_len, status, extra = 0, size, 200, {}
        else:
            start, end = rng
            body_len = end - start + 1
            status = 206
            extra = {"Content-Range": f"bytes {start}-{end}/{size}"}
        headers.update(extra)
        return StreamingResponse(
            file_stream(storage, f.blob.storage_path, start, body_len),
            status_code=status,
            media_type=decision.content_type,
            headers=headers,
        )

    return StreamingResponse(
        file_stream(storage, f.blob.storage_path, 0, size),
        status_code=200,
        media_type=decision.content_type,
        headers=headers,
    )


async def blob_etag(db, blob_id) -> str | None:
    """Strong ETag = sha256 hex when verified; else row id (weak-ish but stable
    enough for V1 while hash is pending)."""
    from sqlalchemy import select

    from ..models import Blob

    blob = (await db.execute(select(Blob).where(Blob.id == blob_id))).scalar_one_or_none()
    if blob is None:
        return None
    return blob.sha256.hex() if blob.sha256 else f"pending-{blob.id}"
