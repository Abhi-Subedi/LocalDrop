"""Folder/file tree services. ALL object access flows through owned-fetch
helpers (BC-10): "not yours" and "missing" are indistinguishable 404s."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import audit
from ..auth import Principal
from ..errors import Problem, conflict, not_found, validation
from ..models import Blob, File, Folder
from ..schemas import EntryOut

PAGE_SIZE_DEFAULT = 100
PAGE_SIZE_MAX = 500


# ---- owned-fetch helpers (the ONLY way services load objects) ----


async def get_owned_folder(db: AsyncSession, p: Principal, folder_id: uuid.UUID) -> Folder:
    row = (
        await db.execute(
            select(Folder).where(Folder.id == folder_id, Folder.owner_id == p.user_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise not_found()
    return row


async def get_owned_file(db: AsyncSession, p: Principal, file_id: uuid.UUID) -> File:
    row = (
        await db.execute(select(File).where(File.id == file_id, File.uploader_id == p.user_id))
    ).scalar_one_or_none()
    if row is None:
        raise not_found()
    return row


async def get_owned_file_with_blob(db: AsyncSession, p: Principal, file_id: uuid.UUID) -> File:
    row = (
        await db.execute(
            select(File).join(Blob, File.blob_id == Blob.id).where(
                File.id == file_id, File.uploader_id == p.user_id
            )
        )
    ).unique().scalar_one_or_none()
    if row is None:
        raise not_found()
    return row


# ---- folders ----


async def create_folder(db: AsyncSession, p: Principal, parent_id: uuid.UUID | None, name: str) -> Folder:
    if parent_id is not None:
        parent = await get_owned_folder(db, p, parent_id)
        if parent.deleted_at is not None:
            raise not_found()
    await _check_name_free(db, p, parent_id, name, None)
    folder = Folder(name=name, owner_id=p.user_id, parent_id=parent_id)
    db.add(folder)
    await db.flush()
    return folder


async def _check_name_free(
    db: AsyncSession, p: Principal, parent_id: uuid.UUID, name: str, exclude: uuid.UUID | None
) -> None:
    q = select(Folder.id).where(
        Folder.parent_id.is_(None) if parent_id is None else Folder.parent_id == parent_id,
        func.lower(Folder.name) == name.lower(),
        Folder.deleted_at.is_(None),
    )
    if exclude:
        q = q.where(Folder.id != exclude)
    if (await db.execute(q)).scalar_one_or_none() is not None:
        raise conflict("name-collision", f"A folder named '{name}' already exists here.")
    qf = select(File.id).where(
        File.folder_id == parent_id,
        func.lower(File.name) == name.lower(),
        File.deleted_at.is_(None),
    )
    if (await db.execute(qf)).scalar_one_or_none() is not None:
        raise conflict("name-collision", f"A file named '{name}' already exists here.")


async def rename_folder(db: AsyncSession, p: Principal, folder_id: uuid.UUID, name: str) -> Folder:
    folder = await get_owned_folder(db, p, folder_id)
    if folder.deleted_at is not None or folder.parent_id is None:
        raise not_found()
    await _check_name_free(db, p, folder.parent_id, name, exclude=folder.id)
    folder.name = name
    await db.flush()
    return folder


async def _is_descendant(db: AsyncSession, candidate: uuid.UUID, ancestor: uuid.UUID) -> bool:
    """Cycle guard: is `candidate` equal to or below `ancestor`?"""
    current: uuid.UUID | None = candidate
    seen = 0
    while current is not None and seen < 100:
        if current == ancestor:
            return True
        row = (
            await db.execute(select(Folder.parent_id).where(Folder.id == current))
        ).scalar_one_or_none()
        current = row
        seen += 1
    return False


async def move_folder(
    db: AsyncSession, p: Principal, folder_id: uuid.UUID, new_parent_id: uuid.UUID
) -> Folder:
    folder = await get_owned_folder(db, p, folder_id)
    new_parent = await get_owned_folder(db, p, new_parent_id)
    if folder.deleted_at or new_parent.deleted_at or folder.parent_id is None:
        raise not_found()
    if folder.id == new_parent.id or await _is_descendant(db, new_parent.id, folder.id):
        raise Problem(422, "cycle", "Cannot move a folder into itself or its descendants.")
    await _check_name_free(db, p, new_parent.id, folder.name, exclude=folder.id)
    folder.parent_id = new_parent.id
    await db.flush()
    return folder


async def delete_folder(db: AsyncSession, p: Principal, folder_id: uuid.UUID) -> int:
    """Soft-delete the subtree (single UPDATE over descendant ids)."""
    folder = await get_owned_folder(db, p, folder_id)
    if folder.deleted_at is not None:
        raise not_found()
    if folder.parent_id is None:
        raise validation("cannot delete the virtual root")
    # Collect subtree ids (iterative CTE walk).
    ids: list[uuid.UUID] = [folder.id]
    frontier = [folder.id]
    while frontier:
        rows = (
            await db.execute(
                select(Folder.id).where(Folder.parent_id.in_(frontier), Folder.deleted_at.is_(None))
            )
        ).scalars().all()
        ids.extend(rows)
        frontier = list(rows)
    now = datetime.now(UTC)
    await db.execute(
        update(Folder).where(Folder.id.in_(ids)).values(deleted_at=now)
    )
    await db.execute(
        update(File).where(File.folder_id.in_(ids), File.deleted_at.is_(None)).values(deleted_at=now)
    )
    await audit(db, "folder.delete", actor_id=str(p.user_id), target_type="folder", target_id=str(folder.id), details={"count": len(ids)})
    await db.flush()
    return len(ids)


async def restore_folder(db: AsyncSession, p: Principal, folder_id: uuid.UUID) -> Folder:
    folder = await get_owned_folder(db, p, folder_id)
    if folder.deleted_at is None:
        raise not_found()
    # Check destination is live
    if folder.parent_id is not None:
        parent = await get_owned_folder(db, p, folder.parent_id)
        if parent.deleted_at is not None:
            raise conflict("parent-in-trash", "Restore the parent folder first.")
    await _check_name_free(db, p, folder.parent_id, folder.name, exclude=folder.id)
    # Restore subtree
    ids: list[uuid.UUID] = [folder.id]
    frontier = [folder.id]
    while frontier:
        rows = (
            await db.execute(select(Folder.id).where(Folder.parent_id.in_(frontier)))
        ).scalars().all()
        ids.extend(rows)
        frontier = list(rows)
    now = datetime.now(UTC)
    await db.execute(update(Folder).where(Folder.id.in_(ids)).values(deleted_at=None))
    await db.execute(
        update(File).where(File.folder_id.in_(ids)).values(deleted_at=None, updated_at=now)
    )
    await db.flush()
    return folder


async def folder_path(db: AsyncSession, p: Principal, folder_id: uuid.UUID | None) -> list[Folder]:
    """Breadcrumb chain from root to folder (virtual root = id None)."""
    chain: list[Folder] = []
    current = folder_id
    seen = 0
    while current is not None and seen < 100:
        folder = await get_owned_folder(db, p, current)
        chain.append(folder)
        current = folder.parent_id
        seen += 1
    chain.reverse()
    return chain


# ---- listing ----


async def list_children(
    db: AsyncSession,
    p: Principal,
    parent_id: uuid.UUID | None,
    *,
    kind: str | None = None,
    sort: str = "name",
    q: str | None = None,
    after: tuple[str, str] | None = None,  # (sort_value, id) cursor
    limit: int = PAGE_SIZE_DEFAULT,
) -> tuple[list[EntryOut], str | None]:
    limit = min(max(limit, 1), PAGE_SIZE_MAX)
    entries: list[EntryOut] = []

    if kind in (None, "folder"):
        qf = select(Folder).where(
            Folder.owner_id == p.user_id, Folder.deleted_at.is_(None)
        )
        if parent_id is None:
            qf = qf.where(Folder.parent_id.is_(None))
        else:
            qf = qf.where(Folder.parent_id == parent_id)
        if q:
            qf = qf.where(Folder.name.ilike(f"%{_escape_like(q)}%"))
        rows = (await db.execute(qf)).scalars().all()
        entries.extend(
            EntryOut(
                id=r.id, kind="folder", name=r.name, size=0, mime_type=None,
                created_at=r.created_at, updated_at=r.updated_at,
            )
            for r in rows
        )

    if kind in (None, "file"):
        qf = (
            select(File)
            .join(Folder, File.folder_id == Folder.id)
            .where(Folder.owner_id == p.user_id, File.deleted_at.is_(None), Folder.deleted_at.is_(None))
        )
        if parent_id is not None:
            qf = qf.where(File.folder_id == parent_id)
        if q:
            qf = qf.where(File.name.ilike(f"%{_escape_like(q)}%"))
        rows = (await db.execute(qf)).unique().scalars().all()
        entries.extend(
            EntryOut(
                id=r.id, kind="file", name=r.name, size=r.size, mime_type=r.mime_type,
                hash_status=r.blob.status, created_at=r.created_at, updated_at=r.updated_at,
            )
            for r in rows
        )

    # sort + cursor (name|size|created_at, asc only for V1 simplicity of cursor)
    reverse = sort.startswith("-")
    key = sort.lstrip("-")
    if key not in ("name", "size", "created_at"):
        key = "name"
    entries.sort(key=lambda e: (str(getattr(e, key) or ""), str(e.id)), reverse=reverse)

    start = 0
    if after:
        val, last_id = after
        try:
            start = next(i for i, e in enumerate(entries) if str(e.id) == last_id) + 1
        except StopIteration:
            start = 0
    page = entries[start : start + limit]
    next_cursor = str(page[-1].id) if len(entries) > start + limit else None
    return page, next_cursor


def _escape_like(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ---- files ----


async def rename_file(db: AsyncSession, p: Principal, file_id: uuid.UUID, name: str) -> File:
    f = await get_owned_file(db, p, file_id)
    if f.deleted_at is not None:
        raise not_found()
    q = select(File.id).where(
        File.folder_id == f.folder_id,
        func.lower(File.name) == name.lower(),
        File.deleted_at.is_(None),
        File.id != f.id,
    )
    qf = select(Folder.id).where(
        Folder.parent_id == f.folder_id,
        func.lower(Folder.name) == name.lower(),
        Folder.deleted_at.is_(None),
    )
    if (await db.execute(q)).scalar_one_or_none() or (await db.execute(qf)).scalar_one_or_none():
        raise conflict("name-collision", f"'{name}' already exists here.")
    f.name = name
    await db.flush()
    return f


async def move_file(
    db: AsyncSession, p: Principal, file_id: uuid.UUID, folder_id: uuid.UUID, overwrite: bool
) -> File:
    f = await get_owned_file(db, p, file_id)
    target = await get_owned_folder(db, p, folder_id)
    if f.deleted_at or target.deleted_at:
        raise not_found()
    existing = (
        await db.execute(
            select(File).where(
                File.folder_id == folder_id,
                func.lower(File.name) == f.name.lower(),
                File.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if not overwrite:
            raise conflict("name-collision", f"A file named '{f.name}' already exists there.")
        existing.deleted_at = datetime.now(UTC)  # overwritten file goes to trash
    f.folder_id = folder_id
    await db.flush()
    return f


async def copy_file(
    db: AsyncSession, p: Principal, file_id: uuid.UUID, folder_id: uuid.UUID
) -> File:
    """Copy = new DB row, same blob. Zero bytes moved (ADR-004)."""
    f = await get_owned_file(db, p, file_id)
    target = await get_owned_folder(db, p, folder_id)
    if f.deleted_at or target.deleted_at:
        raise not_found()
    name = f.name
    existing = (
        await db.execute(
            select(File.name).where(
                File.folder_id == folder_id, File.deleted_at.is_(None),
                func.lower(File.name) == name.lower(),
            )
        )
    ).scalars().all()
    if existing:
        base, dot, ext = name.rpartition(".")
        stem = base if dot else name
        suffix = ext if dot else ""
        n = 2
        while f"{stem} ({n}){('.' + suffix) if suffix else ''}".lower() in {e.lower() for e in existing}:
            n += 1
        name = f"{stem} ({n}){('.' + suffix) if suffix else ''}"
    copy = File(
        folder_id=folder_id,
        name=name,
        blob_id=f.blob_id,
        mime_type=f.mime_type,
        size=f.size,
        uploader_id=p.user_id,
    )
    db.add(copy)
    await db.flush()
    return copy


async def delete_file(db: AsyncSession, p: Principal, file_id: uuid.UUID) -> File:
    f = await get_owned_file(db, p, file_id)
    if f.deleted_at is not None:
        raise not_found()
    f.deleted_at = datetime.now(UTC)
    await audit(db, "file.delete", actor_id=str(p.user_id), target_type="file", target_id=str(f.id))
    await db.flush()
    return f


async def restore_file(db: AsyncSession, p: Principal, file_id: uuid.UUID) -> File:
    f = await get_owned_file(db, p, file_id)
    if f.deleted_at is None:
        raise not_found()
    folder = await get_owned_folder(db, p, f.folder_id)
    if folder.deleted_at is not None:
        raise conflict("parent-in-trash", "The folder is in the trash; restore it first.")
    q = select(File.id).where(
        File.folder_id == f.folder_id,
        func.lower(File.name) == f.name.lower(),
        File.deleted_at.is_(None),
        File.id != f.id,
    )
    if (await db.execute(q)).scalar_one_or_none():
        raise conflict("name-collision", f"'{f.name}' already exists here.")
    f.deleted_at = None
    await db.flush()
    return f


async def list_trash(db: AsyncSession, p: Principal) -> list[EntryOut]:
    files = (
        await db.execute(
            select(File).where(File.uploader_id == p.user_id, File.deleted_at.is_not_null())
        )
    ).scalars().all()
    return [
        EntryOut(
            id=f.id, kind="file", name=f.name, size=f.size, mime_type=f.mime_type,
            created_at=f.created_at, deleted_at=f.deleted_at,
        )
        for f in sorted(files, key=lambda x: x.deleted_at or x.created_at, reverse=True)
    ]


async def purge_trash(db: AsyncSession, p: Principal, storage) -> int:
    """Hard-delete trash contents; blob GC happens in cleanup job."""
    files = (
        await db.execute(
            select(File).where(File.uploader_id == p.user_id, File.deleted_at.is_not_null())
        )
    ).scalars().all()
    n = len(files)
    if n:
        await db.execute(
            delete_files_by_ids([f.id for f in files])
        )
    await audit(db, "trash.purge", actor_id=str(p.user_id), details={"count": n})
    await db.flush()
    return n


def delete_files_by_ids(ids: list[uuid.UUID]):
    from sqlalchemy import delete as _del

    return _del(File).where(File.id.in_(ids))


async def user_root_usage(db: AsyncSession, user_id: uuid.UUID) -> int:
    return await storage_used(db, user_id)
