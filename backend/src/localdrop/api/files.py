"""Folder + file management endpoints (spec 05 §2.3, §2.4)."""

from __future__ import annotations

import uuid as uuid_mod

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import Principal, check_csrf, require_read, require_write
from ..db import get_db
from ..errors import Problem, not_found
from ..ratelimit import LIMITS
from ..schemas import (
    CopyRequest,
    EntryOut,
    EntryPage,
    FolderCreate,
    FolderRename,
    MoveRequest,
    PathEntry,
    TextPreview,
)
from ..services import tree
from ..services.jobs import generate_thumbnails
from ..services.serving import decide_serving
from ..storage import get_storage

router = APIRouter(tags=["files"])

# ---------- folders ----------


@router.post("/folders", response_model=EntryOut, status_code=201)
async def create_folder(
    body: FolderCreate,
    request: Request,
    p: Principal = Depends(require_write),
    db: AsyncSession = Depends(get_db),
) -> EntryOut:
    check_csrf(request)
    LIMITS.api.check(request.client.host if request.client else "0.0.0.0")
    parent_id = uuid_mod.UUID(str(body.parent_id)) if body.parent_id is not None else None
    folder = await tree.create_folder(db, p, parent_id, body.name)
    await db.commit()
    return EntryOut(
        id=folder.id,
        kind="folder",
        name=folder.name,
        size=0,
        created_at=folder.created_at,
        updated_at=folder.updated_at,
    )


@router.patch("/folders/{folder_id}", response_model=EntryOut)
async def rename_folder(
    folder_id: uuid_mod.UUID,
    body: FolderRename,
    request: Request,
    p: Principal = Depends(require_write),
    db: AsyncSession = Depends(get_db),
) -> EntryOut:
    check_csrf(request)
    folder = await tree.rename_folder(db, p, folder_id, body.name)
    await db.commit()
    return EntryOut(
        id=folder.id,
        kind="folder",
        name=folder.name,
        size=0,
        created_at=folder.created_at,
        updated_at=folder.updated_at,
    )


@router.post("/folders/{folder_id}/move", response_model=EntryOut)
async def move_folder(
    folder_id: uuid_mod.UUID,
    body: MoveRequest,
    request: Request,
    p: Principal = Depends(require_write),
    db: AsyncSession = Depends(get_db),
) -> EntryOut:
    check_csrf(request)
    new_parent = uuid_mod.UUID(str(body.new_parent_id)) if body.new_parent_id is not None else None
    folder = await tree.move_folder(db, p, folder_id, new_parent)
    await db.commit()
    return EntryOut(
        id=folder.id,
        kind="folder",
        name=folder.name,
        size=0,
        created_at=folder.created_at,
        updated_at=folder.updated_at,
    )


@router.delete("/folders/{folder_id}", status_code=200)
async def delete_folder(
    folder_id: uuid_mod.UUID,
    request: Request,
    p: Principal = Depends(require_write),
    db: AsyncSession = Depends(get_db),
) -> dict:
    check_csrf(request)
    n = await tree.delete_folder(db, p, folder_id)
    await db.commit()
    return {"deleted": n}


@router.post("/folders/{folder_id}/restore", response_model=EntryOut)
async def restore_folder(
    folder_id: uuid_mod.UUID,
    request: Request,
    p: Principal = Depends(require_write),
    db: AsyncSession = Depends(get_db),
) -> EntryOut:
    check_csrf(request)
    folder = await tree.restore_folder(db, p, folder_id)
    await db.commit()
    return EntryOut(
        id=folder.id,
        kind="folder",
        name=folder.name,
        size=0,
        created_at=folder.created_at,
        updated_at=folder.updated_at,
    )


@router.get("/folders/{folder_id}/path", response_model=list[PathEntry])
async def folder_path(
    folder_id: uuid_mod.UUID,
    p: Principal = Depends(require_read),
    db: AsyncSession = Depends(get_db),
) -> list[PathEntry]:
    chain = await tree.folder_path(db, p, folder_id)
    return [PathEntry(id=f.id, name=f.name) for f in chain]


@router.get("/folders/root/children", response_model=EntryPage)
async def root_children(
    type: str | None = Query(default=None, pattern="^(file|folder)$"),
    sort: str = Query(default="name", pattern="^-?(name|size|created_at)$"),
    q: str | None = Query(default=None, max_length=200),
    cursor: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=100, ge=1, le=500),
    p: Principal = Depends(require_read),
    db: AsyncSession = Depends(get_db),
) -> EntryPage:
    """Virtual root: all top-level folders + files uploaded without a folder.

    V1: files always live in a folder; the root shows the user's top folders.
    NOTE: registered before /folders/{folder_id}/children so "root" is not
    captured as a folder UUID.
    """
    after = (None, cursor) if cursor else None
    page, next_cursor = await tree.list_children(
        db, p, None, kind=type, sort=sort, q=q, after=after, limit=limit
    )
    await db.commit()
    return EntryPage(items=page, next_cursor=next_cursor)


@router.get("/folders/{folder_id}/children", response_model=EntryPage)
async def children(
    folder_id: uuid_mod.UUID,
    type: str | None = Query(default=None, pattern="^(file|folder)$"),
    sort: str = Query(default="name", pattern="^-?(name|size|created_at)$"),
    q: str | None = Query(default=None, max_length=200),
    cursor: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=100, ge=1, le=500),
    p: Principal = Depends(require_read),
    db: AsyncSession = Depends(get_db),
) -> EntryPage:
    after = (None, cursor) if cursor else None
    # Ownership of the parent itself: not-yours ≡ missing (BC-10).
    # (The listing query below only returns own rows, but the status code
    # must not distinguish either.)
    await tree.get_owned_folder(db, p, folder_id)
    page, next_cursor = await tree.list_children(
        db, p, folder_id, kind=type, sort=sort, q=q, after=after, limit=limit
    )
    await db.commit()
    return EntryPage(items=page, next_cursor=next_cursor)


# ---------- files ----------


@router.patch("/files/{file_id}", response_model=EntryOut)
async def rename_file(
    file_id: uuid_mod.UUID,
    body: FolderRename,
    request: Request,
    p: Principal = Depends(require_write),
    db: AsyncSession = Depends(get_db),
) -> EntryOut:
    check_csrf(request)
    f = await tree.rename_file(db, p, file_id, body.name)
    await db.commit()
    return EntryOut(
        id=f.id,
        kind="file",
        name=f.name,
        size=f.size,
        mime_type=f.mime_type,
        created_at=f.created_at,
        updated_at=f.updated_at,
    )


@router.post("/files/{file_id}/move", response_model=EntryOut)
async def move_file(
    file_id: uuid_mod.UUID,
    body: MoveRequest,
    request: Request,
    p: Principal = Depends(require_write),
    db: AsyncSession = Depends(get_db),
) -> EntryOut:
    check_csrf(request)
    if body.folder_id is None:
        raise not_found()
    f = await tree.move_file(db, p, file_id, uuid_mod.UUID(str(body.folder_id)), body.overwrite)
    await db.commit()
    return EntryOut(
        id=f.id,
        kind="file",
        name=f.name,
        size=f.size,
        mime_type=f.mime_type,
        created_at=f.created_at,
        updated_at=f.updated_at,
    )


@router.post("/files/{file_id}/copy", response_model=EntryOut, status_code=201)
async def copy_file(
    file_id: uuid_mod.UUID,
    body: CopyRequest,
    request: Request,
    p: Principal = Depends(require_write),
    db: AsyncSession = Depends(get_db),
) -> EntryOut:
    check_csrf(request)
    f = await tree.copy_file(db, p, file_id, uuid_mod.UUID(str(body.folder_id)))
    await db.commit()
    return EntryOut(
        id=f.id,
        kind="file",
        name=f.name,
        size=f.size,
        mime_type=f.mime_type,
        created_at=f.created_at,
        updated_at=f.updated_at,
    )


@router.delete("/files/{file_id}", status_code=204)
async def delete_file(
    file_id: uuid_mod.UUID,
    request: Request,
    p: Principal = Depends(require_write),
    db: AsyncSession = Depends(get_db),
) -> Response:
    check_csrf(request)
    await tree.delete_file(db, p, file_id)
    await db.commit()
    return Response(status_code=204)


@router.post("/files/{file_id}/restore", response_model=EntryOut)
async def restore_file(
    file_id: uuid_mod.UUID,
    request: Request,
    p: Principal = Depends(require_write),
    db: AsyncSession = Depends(get_db),
) -> EntryOut:
    check_csrf(request)
    f = await tree.restore_file(db, p, file_id)
    await db.commit()
    return EntryOut(
        id=f.id,
        kind="file",
        name=f.name,
        size=f.size,
        mime_type=f.mime_type,
        created_at=f.created_at,
        updated_at=f.updated_at,
    )


@router.get("/trash", response_model=list[EntryOut])
async def trash_ep(
    p: Principal = Depends(require_read), db: AsyncSession = Depends(get_db)
) -> list[EntryOut]:
    return await tree.list_trash(db, p)


@router.post("/trash/purge")
async def purge_ep(
    request: Request,
    p: Principal = Depends(require_write),
    db: AsyncSession = Depends(get_db),
) -> dict:
    check_csrf(request)
    n = await tree.purge_trash(db, p, get_storage())
    await db.commit()
    return {"purged": n}


# ---------- content, thumbnails, previews ----------


@router.get("/files/{file_id}/content")
async def content_ep(
    file_id: uuid_mod.UUID,
    request: Request,
    response: Response,
    p: Principal = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    ip = request.client.host if request.client else "0.0.0.0"
    LIMITS.content.check(ip)
    f = await tree.get_owned_file_with_blob(db, p, file_id)
    from ..services.downloads import blob_etag, file_response

    etag = await blob_etag(db, f.blob_id)
    await db.commit()  # touch session; no stream-loop writes
    return file_response(
        get_storage(), f, request.headers.get("Range"), request.headers.get("If-Range"), etag
    )


@router.get("/files/{file_id}/thumbnail")
async def thumbnail_ep(
    file_id: uuid_mod.UUID,
    size: int = Query(default=256),
    p: Principal = Depends(require_read),
    db: AsyncSession = Depends(get_db),
) -> Response:
    from pathlib import Path

    from fastapi.responses import FileResponse as StarletteFileResponse

    f = await tree.get_owned_file_with_blob(db, p, file_id)
    storage = get_storage()
    thumb = storage.thumb_path(str(f.id), 256 if size < 512 else 1024)
    if not thumb.exists():
        await generate_thumbnails(db, storage, f.id, max_n=1)
        await db.commit()
    if not thumb.exists():
        raise not_found("thumbnail not available")
    return StarletteFileResponse(Path(thumb), media_type="image/webp")


@router.get("/files/{file_id}/preview", response_model=TextPreview)
async def preview_ep(
    file_id: uuid_mod.UUID,
    p: Principal = Depends(require_read),
    db: AsyncSession = Depends(get_db),
) -> TextPreview:
    import os

    f = await tree.get_owned_file_with_blob(db, p, file_id)
    decision = decide_serving(f.mime_type, f.blob.mime_sniffed)
    if not decision.content_type.startswith("text/") and decision.content_type not in (
        "application/json",
        "application/pdf",
    ):
        raise not_found("no text preview for this type")
    if f.size > 256 * 1024:
        truncated = True
    else:
        truncated = False
    storage = get_storage()
    try:
        fd = storage.open_read(f.blob.storage_path)
    except (OSError, Problem):
        raise not_found("File data is not available on the server.") from None
    try:
        raw = os.read(fd, 256 * 1024)
    finally:
        os.close(fd)
    charset = "utf-8"
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
        charset = "latin-1"
    return TextPreview(text=text, charset=charset, truncated=truncated)
