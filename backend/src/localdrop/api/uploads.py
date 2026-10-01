"""tus upload endpoints (spec 05 §2.5). After every PATCH, if the upload is
complete, finalize immediately and run opportunistic hashing."""

from __future__ import annotations

import uuid as uuid_mod
from datetime import timezone
from email.utils import format_datetime

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import Principal, check_csrf, require_write
from ..config import get_settings
from ..db import get_db
from ..errors import Problem, validation
from ..models import UploadSession
from ..schemas import UploadOut
from ..services import uploads
from ..services.uploads import hash_pending_blobs
from ..storage import get_storage

router = APIRouter(tags=["uploads"])

TUS_RESUMABLE = "1.0.0"


def _tus_headers(response: Response, offset: int | None = None, expires=None) -> None:
    response.headers["Tus-Resumable"] = TUS_RESUMABLE
    response.headers["Tus-Version"] = TUS_RESUMABLE
    response.headers["Tus-Max-Size"] = str(get_settings().max_upload_bytes)
    if offset is not None:
        response.headers["Upload-Offset"] = str(offset)
    if expires is not None:
        # TIMESTAMPTZ values come back in the DB session timezone (not
        # necessarily UTC) or naive; the wire format needs UTC.
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        else:
            expires = expires.astimezone(timezone.utc)
        response.headers["Upload-Expires"] = format_datetime(expires, usegmt=True)


@router.options("/uploads")
async def options_ep(response: Response) -> Response:
    response.headers["Tus-Resumable"] = TUS_RESUMABLE
    response.headers["Tus-Version"] = TUS_RESUMABLE
    response.headers["Tus-Max-Size"] = str(get_settings().max_upload_bytes)
    response.headers["Tus-Extension"] = "creation,expiration,checksum"
    response.status_code = 204
    return response


@router.post("/uploads", status_code=201)
async def create_ep(
    request: Request,
    response: Response,
    p: Principal = Depends(require_write),
    db: AsyncSession = Depends(get_db),
) -> Response:
    check_csrf(request)
    # tus-standard creation: metadata + size in headers (tus-js-client compatible)
    metadata = uploads.parse_upload_metadata(request.headers.get("Upload-Metadata"))
    length_hdr = request.headers.get("Upload-Length")
    if length_hdr is None:
        raise Problem(400, "length", "Upload-Length header required")
    try:
        total = int(length_hdr)
    except ValueError:
        raise validation("Upload-Length must be an integer") from None

    folder_hdr = metadata.get("folderId", "").strip()
    if not folder_hdr:
        raise validation("Upload-Metadata must include 'folderId'")
    try:
        folder_id = uuid_mod.UUID(folder_hdr)
    except ValueError:
        raise validation("folderId must be a UUID") from None

    sess, _ = await uploads.create_upload(db, p, metadata, folder_id, total)
    await db.commit()
    _tus_headers(response, offset=0, expires=sess.expires_at)
    response.headers["Location"] = f"/api/v1/uploads/{sess.id}"
    response.status_code = 201
    return response


@router.head("/uploads/{session_id}")
async def head_ep(
    session_id: uuid_mod.UUID,
    response: Response,
    p: Principal = Depends(require_write),
    db: AsyncSession = Depends(get_db),
) -> Response:
    sess = await uploads.head_offset(db, p, session_id)
    _tus_headers(response, offset=sess.offset, expires=sess.expires_at)
    response.headers["Upload-Length"] = str(sess.total_size)
    response.headers["Cache-Control"] = "no-store"
    response.status_code = 200
    return response


@router.patch("/uploads/{session_id}")
async def patch_ep(
    session_id: uuid_mod.UUID,
    request: Request,
    response: Response,
    p: Principal = Depends(require_write),
    db: AsyncSession = Depends(get_db),
) -> Response:
    check_csrf(request)
    new_offset = await uploads.append_chunk(db, p, session_id, request)

    file_id: str | None = None
    row = (
        await db.execute(select(UploadSession).where(UploadSession.id == session_id))
    ).scalar_one_or_none()
    if row is not None and row.offset == row.total_size:
        f = await uploads.finalize(db, p, session_id)
        file_id = str(f.id)

    await hash_pending_blobs(db, get_storage(), max_n=3)
    await db.commit()

    _tus_headers(response, offset=new_offset)
    if file_id:
        response.headers["X-Localdrop-File"] = file_id
    response.status_code = 204
    return response


@router.delete("/uploads/{session_id}", status_code=204)
async def cancel_ep(
    session_id: uuid_mod.UUID,
    request: Request,
    p: Principal = Depends(require_write),
    db: AsyncSession = Depends(get_db),
) -> Response:
    check_csrf(request)
    await uploads.cancel_upload(db, p, session_id)
    await db.commit()
    return Response(status_code=204)


@router.get("/uploads", response_model=list[UploadOut])
async def list_ep(
    p: Principal = Depends(require_write), db: AsyncSession = Depends(get_db)
) -> list[UploadOut]:
    rows = await uploads.list_sessions(db, p)
    await db.commit()
    return [
        UploadOut(
            id=r.id, file_name=r.file_name, total_size=r.total_size,
            offset=r.offset, status=r.status, expires_at=r.expires_at,
        )
        for r in rows
    ]
