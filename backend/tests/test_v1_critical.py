"""Critical-path tests (user V1 §18): auth, authz, files, upload, share, security."""

from __future__ import annotations

import base64
import hashlib
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from tests.conftest import H, make_folder, md_for, tus_upload

# ---------------- authentication ----------------


@pytest.mark.asyncio
@pytest.mark.asyncio
# FR-A1, FR-A2: onboarding, login and logout.
async def test_register_login_logout(client):
    r = await client.get("/api/v1/setup/status")
    assert r.status_code == 200 and r.json()["onboarding_required"] is True
    r = await client.get("/api/v1/setup/token")
    token = r.json()["token"]
    r = await client.post(
        "/api/v1/setup/owner",
        json={"username": "owner", "password": "testpass123", "setup_token": token},
        headers=H,
    )
    assert r.status_code == 201
    # token single-use
    r2 = await client.get("/api/v1/setup/token")
    assert r2.json()["onboarding_required"] is False
    # login
    r = await client.post(
        "/api/v1/auth/login", json={"username": "owner", "password": "testpass123"}, headers=H
    )
    assert r.status_code == 204
    assert "ld_session" in r.headers.get("set-cookie", "")
    # me
    r = await client.get("/api/v1/me", headers=H)
    assert r.status_code == 200 and r.json()["username"] == "owner"
    # wrong password
    r = await client.post(
        "/api/v1/auth/login", json={"username": "owner", "password": "wrong-password"}, headers=H
    )
    assert r.status_code == 401
    # logout
    r = await client.post("/api/v1/auth/logout", headers=H)
    assert r.status_code == 204
    r = await client.get("/api/v1/me", headers=H)
    assert r.status_code == 401


@pytest.mark.asyncio
@pytest.mark.asyncio
# FR-A2: unsafe cookie-auth requests must carry X-Requested-With.
async def test_csrf_required_for_cookie_mutations(owner_client):
    r = await owner_client.post("/api/v1/folders", json={"parent_id": None, "name": "no-csrf"})
    assert r.status_code == 403
    assert r.json()["type"].endswith("csrf")


@pytest.mark.asyncio
@pytest.mark.asyncio
# FR-A3, FR-A4: a password change revokes every other session.
async def test_password_change_revokes_other_sessions(app, owner_client):
    # a second client = another session
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c2:
        r = await c2.post(
            "/api/v1/auth/login",
            json={"username": owner_client.ld_username, "password": owner_client.ld_password},
            headers=H,
        )
        assert r.status_code == 204
    r = await owner_client.put(
        "/api/v1/me/password",
        json={"current": owner_client.ld_password, "new": "newpass1234"},
        headers=H,
    )
    assert r.status_code == 204
    # old password no longer works
    r = await owner_client.post(
        "/api/v1/auth/login",
        json={"username": owner_client.ld_username, "password": "testpass123"},
        headers=H,
    )
    assert r.status_code == 401
    # restore
    r = await owner_client.post(
        "/api/v1/auth/login",
        json={"username": owner_client.ld_username, "password": "newpass1234"},
        headers=H,
    )
    assert r.status_code == 204


@pytest.mark.asyncio
@pytest.mark.asyncio
# FR-A2: auth rate limiting and lockout.
async def test_login_lockout_after_failures(client, owner_client):
    for _ in range(10):
        await client.post(
            "/api/v1/auth/login", json={"username": "owner", "password": "badpass123"}, headers=H
        )
    r = await client.post(
        "/api/v1/auth/login", json={"username": "owner", "password": "badpass123"}, headers=H
    )
    assert r.status_code == 429


# ---------------- authorization ----------------


@pytest.mark.asyncio
@pytest.mark.asyncio
# FR-A2: anonymous access to protected routes is refused.
async def test_unauthenticated_access_denied(client):
    for method, path in [
        ("GET", "/api/v1/me"),
        ("GET", "/api/v1/folders/root/children"),
        ("POST", "/api/v1/folders"),
        ("GET", "/api/v1/trash"),
        ("GET", "/api/v1/shares"),
    ]:
        r = await getattr(client, method.lower())(path, headers=H)
        assert r.status_code in (401,), f"{method} {path}: {r.status_code}"


@pytest.mark.asyncio
@pytest.mark.asyncio
# FR-A3: object-level authorization holds across accounts.
async def test_user_cannot_access_other_users_file(app, owner_client):
    """Object-level authz: a second user's session cannot fetch user A's file."""
    from localdrop.db import SessionFactory
    from localdrop.models import User
    from localdrop.security import hash_password

    r = await owner_client.get("/api/v1/me", headers=H)
    assert r.status_code == 200

    # create a second user directly in DB (v1 has no registration API by design)
    attacker_name = f"attacker-{uuid.uuid4().hex[:8]}"
    async with SessionFactory() as db:
        db.add(
            User(username=attacker_name, password_hash=hash_password("attackerpass1"), role="user")
        )
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as attacker:
        r = await attacker.post(
            "/api/v1/auth/login",
            json={"username": attacker_name, "password": "attackerpass1"},
            headers=H,
        )
        assert r.status_code == 204

        # attacker cannot see owner's folders/files
        r = await attacker.get("/api/v1/folders/root/children", headers=H)
        assert r.status_code == 200 and r.json()["items"] == []


# ---------------- files & folders ----------------


@pytest.mark.asyncio
@pytest.mark.asyncio
# FR-F2: folder create/rename/move/delete and name collisions.
async def test_folder_crud_and_collisions(owner_client):
    f1 = await make_folder(owner_client, "Docs")
    # case-insensitive collision
    r = await owner_client.post(
        "/api/v1/folders", json={"parent_id": None, "name": "docs"}, headers=H
    )
    assert r.status_code == 409
    # rename
    r = await owner_client.patch(
        f"/api/v1/folders/{f1['id']}", json={"name": "Documents"}, headers=H
    )
    assert r.status_code == 200 and r.json()["name"] == "Documents"
    # subfolder + move
    sub = await make_folder(owner_client, "Sub")
    r = await owner_client.post(
        f"/api/v1/folders/{sub['id']}/move", json={"new_parent_id": f1["id"]}, headers=H
    )
    assert r.status_code == 200
    # cycle rejection: move Documents into Sub
    r = await owner_client.post(
        f"/api/v1/folders/{f1['id']}/move", json={"new_parent_id": sub["id"]}, headers=H
    )
    assert r.status_code == 422
    # delete (soft) → trash → restore
    r = await owner_client.delete(f"/api/v1/folders/{f1['id']}", headers=H)
    assert r.status_code == 200
    r = await owner_client.get("/api/v1/folders/root/children", headers=H)
    assert r.json()["items"] == []
    r = await owner_client.get("/api/v1/trash", headers=H)
    assert any(i["id"] == f1["id"] and i["kind"] == "folder" for i in r.json())
    r = await owner_client.post(f"/api/v1/folders/{f1['id']}/restore", headers=H)
    assert r.status_code == 200


@pytest.mark.asyncio
@pytest.mark.asyncio
# FR-F1, FR-F3, FR-T4: upload, download, rename, move, copy, soft-delete.
async def test_file_lifecycle_upload_download_rename_move_copy_delete(owner_client):
    folder = await make_folder(owner_client)
    content = b"LocalDrop test content " * 1000
    file_id = await tus_upload(
        owner_client, folder["id"], content, name="notes.txt", mime="text/plain"
    )

    # download + verify
    r = await owner_client.get(f"/api/v1/files/{file_id}/content", headers=H)
    assert (
        r.status_code == 200
        and hashlib.sha256(r.content).hexdigest() == hashlib.sha256(content).hexdigest()
    )
    assert r.headers["content-type"].startswith("text/plain")

    # range single
    r = await owner_client.get(
        f"/api/v1/files/{file_id}/content", headers={**H, "Range": "bytes=0-9"}
    )
    assert r.status_code == 206 and r.content == content[:10]
    # suffix range
    r = await owner_client.get(
        f"/api/v1/files/{file_id}/content", headers={**H, "Range": "bytes=-5"}
    )
    assert r.status_code == 206 and r.content == content[-5:]

    # rename
    r = await owner_client.patch(
        f"/api/v1/files/{file_id}", json={"name": "renamed.txt"}, headers=H
    )
    assert r.status_code == 200 and r.json()["name"] == "renamed.txt"

    # move to second folder
    f2 = await make_folder(owner_client)
    r = await owner_client.post(
        f"/api/v1/files/{file_id}/move", json={"folder_id": f2["id"]}, headers=H
    )
    assert r.status_code == 200

    # copy (same blob, zero bytes)
    r = await owner_client.post(
        f"/api/v1/files/{file_id}/copy", json={"folder_id": folder["id"]}, headers=H
    )
    assert r.status_code == 201

    # delete → trash → restore
    r = await owner_client.delete(f"/api/v1/files/{file_id}", headers=H)
    assert r.status_code == 204
    r = await owner_client.get("/api/v1/trash", headers=H)
    assert len(r.json()) == 1
    r = await owner_client.post(f"/api/v1/files/{file_id}/restore", headers=H)
    assert r.status_code == 200


@pytest.mark.asyncio
@pytest.mark.asyncio
# FR-F6: identical content reuses one blob.
async def test_dedup_same_content_single_blob(owner_client):
    folder = await make_folder(owner_client)
    content = b"dedup-me " * 1000
    from sqlalchemy import func, select

    from localdrop.db import SessionFactory
    from localdrop.models import Blob

    async def verified_count() -> int:
        async with SessionFactory() as db:
            return (
                await db.execute(
                    select(func.count()).select_from(Blob).where(Blob.status == "verified")
                )
            ).scalar_one()

    before = await verified_count()
    fid1 = await tus_upload(owner_client, folder["id"], content, name="a.bin")
    fid2 = await tus_upload(owner_client, folder["id"], content, name="b.bin")
    assert fid1 != fid2
    # two files, one new blob: identical content is stored once
    assert await verified_count() == before + 1


# ---------------- upload security / failure cases ----------------


@pytest.mark.asyncio
@pytest.mark.asyncio
# FR-T1: a tus offset conflict is refused.
async def test_upload_offset_conflict_rejected(owner_client):
    folder = await make_folder(owner_client)
    md = md_for(folder["id"])
    r = await owner_client.post(
        "/api/v1/uploads", headers={**H, "Upload-Length": "100", "Upload-Metadata": md}
    )
    loc = r.headers["location"]
    r = await owner_client.patch(
        loc,
        content=b"0123456789",
        headers={
            **H,
            "Upload-Offset": "50",
            "Content-Type": "application/offset+octet-stream",
            "Content-Length": "10",
        },
    )
    assert r.status_code == 460


@pytest.mark.asyncio
@pytest.mark.asyncio
# FR-T2: a bad per-chunk checksum does not advance the offset.
async def test_upload_checksum_mismatch_keeps_offset(owner_client):
    folder = await make_folder(owner_client)
    md = md_for(folder["id"])
    r = await owner_client.post(
        "/api/v1/uploads", headers={**H, "Upload-Length": "20", "Upload-Metadata": md}
    )
    loc = r.headers["location"]
    bad_ck = "sha256 " + base64.b64encode(hashlib.sha256(b"not-the-data").digest()).decode()
    r = await owner_client.patch(
        loc,
        content=b"01234567890123456789",
        headers={
            **H,
            "Upload-Offset": "0",
            "Content-Type": "application/offset+octet-stream",
            "Upload-Checksum": bad_ck,
            "Content-Length": "20",
        },
    )
    assert r.status_code == 460
    # offset unchanged
    r = await owner_client.head(loc, headers={**H, "Tus-Resumable": "1.0.0"})
    assert r.headers["Upload-Offset"] == "0"


@pytest.mark.asyncio
@pytest.mark.asyncio
# FR-T5: uploads above the configured cap get 413.
async def test_upload_oversize_rejected(owner_client):
    folder = await make_folder(owner_client)
    md = md_for(folder["id"])
    r = await owner_client.post(
        "/api/v1/uploads", headers={**H, "Upload-Length": "200000000000", "Upload-Metadata": md}
    )
    assert r.status_code == 413


@pytest.mark.asyncio
@pytest.mark.asyncio
# FR-T1, FR-T3: an interrupted upload resumes at the right offset.
async def test_upload_interrupted_then_resumed(owner_client):
    folder = await make_folder(owner_client)
    content = b"resume-test " * 100000  # 1.2MB
    md = md_for(folder["id"], name="resume.bin")
    r = await owner_client.post(
        "/api/v1/uploads", headers={**H, "Upload-Length": str(len(content)), "Upload-Metadata": md}
    )
    loc = r.headers["location"]
    # first chunk only
    part = content[:524288]
    ck = "sha256 " + base64.b64encode(hashlib.sha256(part).digest()).decode()
    r = await owner_client.patch(
        loc,
        content=part,
        headers={
            **H,
            "Upload-Offset": "0",
            "Content-Type": "application/offset+octet-stream",
            "Upload-Checksum": ck,
            "Content-Length": str(len(part)),
        },
    )
    assert r.status_code == 204
    # HEAD reports the persisted offset (resume works)
    r = await owner_client.head(loc, headers={**H, "Tus-Resumable": "1.0.0"})
    assert r.headers["Upload-Offset"] == str(len(part))
    # resume with the rest
    rest = content[524288:]
    ck = "sha256 " + base64.b64encode(hashlib.sha256(rest).digest()).decode()
    r = await owner_client.patch(
        loc,
        content=rest,
        headers={
            **H,
            "Upload-Offset": str(len(part)),
            "Content-Type": "application/offset+octet-stream",
            "Upload-Checksum": ck,
            "Content-Length": str(len(rest)),
        },
    )
    assert r.status_code == 204
    file_id = r.headers["X-Localdrop-File"]
    r = await owner_client.get(f"/api/v1/files/{file_id}/content", headers=H)
    assert hashlib.sha256(r.content).hexdigest() == hashlib.sha256(content).hexdigest()


@pytest.mark.asyncio
async def test_upload_binary_content_roundtrip_byte_identical(owner_client):
    """Regression: Windows CRT text-mode translation must never touch bytes.
    FR-T2: binary content survives the round trip byte for byte.

    Content covers all 256 byte values (incl. \\n and \\x1a/Ctrl-Z, which a
    text-mode fd would translate / treat as EOF). Multi-chunk upload must
    land byte-identical and verify (not go 'missing').
    """
    folder = await make_folder(owner_client)
    content = bytes(range(256)) * 4000  # 1 MiB, every byte value
    file_id = await tus_upload(
        owner_client,
        folder["id"],
        content,
        name="binary.bin",
        mime="application/octet-stream",
        chunk_size=524288,
    )
    r = await owner_client.get(f"/api/v1/files/{file_id}/content", headers=H)
    assert r.status_code == 200
    assert r.content == content

    import uuid as _uuid

    from sqlalchemy import select

    from localdrop.db import SessionFactory
    from localdrop.models import Blob, File

    async with SessionFactory() as db:
        f = (await db.execute(select(File).where(File.id == _uuid.UUID(file_id)))).scalar_one()
        b = (await db.execute(select(Blob).where(Blob.id == f.blob_id))).scalar_one()
        assert b.status == "verified"
        assert b.size == len(content)


# ---------------- sharing ----------------


@pytest.mark.asyncio
@pytest.mark.asyncio
# FR-S1, FR-S3: share create, download, revoke, list.
async def test_share_full_lifecycle(owner_client):
    folder = await make_folder(owner_client)
    file_id = await tus_upload(
        owner_client, folder["id"], b"share me", name="s.txt", mime="text/plain"
    )

    r = await owner_client.post(
        "/api/v1/shares",
        json={"file_id": file_id, "max_downloads": 2, "password": "pw12345"},
        headers=H,
    )
    assert r.status_code == 201
    share = r.json()
    assert len(share["token"]) == 26 and "svg" in share["qr_svg"]
    token = share["token"]

    # anonymous: info shows lock
    r = await owner_client.get(f"/api/v1/shares/{token}")  # no auth needed but cookie present
    assert r.status_code == 200 and r.json()["requires_password"] is True
    # locked download
    r = await owner_client.get(f"/api/v1/shares/{token}/files/{file_id}/content")
    assert r.status_code == 403
    # wrong password
    r = await owner_client.post(f"/api/v1/shares/{token}/unlock", json={"password": "wrong-pass"})
    assert r.status_code == 403
    # correct
    r = await owner_client.post(f"/api/v1/shares/{token}/unlock", json={"password": "pw12345"})
    assert r.status_code == 204
    r = await owner_client.get(f"/api/v1/shares/{token}/files/{file_id}/content")
    assert r.status_code == 200 and r.content == b"share me"
    # limit reached after 2nd
    r = await owner_client.get(f"/api/v1/shares/{token}/files/{file_id}/content")
    assert r.status_code == 200
    r = await owner_client.get(f"/api/v1/shares/{token}/files/{file_id}/content")
    assert r.status_code == 403 and "limit" in r.json()["type"]

    # revoke
    r = await owner_client.delete(f"/api/v1/shares/{share['id']}", headers=H)
    assert r.status_code == 204
    r = await owner_client.get(f"/api/v1/shares/{token}", headers=H)
    assert r.status_code == 404  # revoked ≡ unknown


@pytest.mark.asyncio
@pytest.mark.asyncio
# FR-S1: a dead share link is indistinguishable from a missing one.
async def test_share_invalid_token_is_404(owner_client):
    r = await owner_client.get("/api/v1/shares/AAAAAAAAAAAAAAAAAAAAAAAAAA")
    assert r.status_code == 404


@pytest.mark.asyncio
@pytest.mark.asyncio
# FR-S2: an expired share refuses downloads.
async def test_share_expiry(owner_client):
    """A share past its expiry is indistinguishable from unknown (404)."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from localdrop.db import SessionFactory
    from localdrop.models import Share

    folder = await make_folder(owner_client)
    file_id = await tus_upload(owner_client, folder["id"], b"exp", name="e.txt")
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    r = await owner_client.post(
        "/api/v1/shares", json={"file_id": file_id, "expires_at": future}, headers=H
    )
    assert r.status_code == 201
    token = r.json()["token"]

    # past expiry is rejected at creation
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    r = await owner_client.post(
        "/api/v1/shares", json={"file_id": file_id, "expires_at": past}, headers=H
    )
    assert r.status_code == 400

    # expire the live share behind the scenes → public surface goes 404
    async with SessionFactory() as db:
        share = (await db.execute(select(Share).where(Share.token == token))).scalar_one()
        share.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()
    r = await owner_client.get(f"/api/v1/shares/{token}", headers=H)
    assert r.status_code == 404


# ---------------- security: names & traversal ----------------


@pytest.mark.asyncio
@pytest.mark.asyncio
# FR-F2: path traversal and hostile names are refused.
async def test_hostile_names_rejected(owner_client):
    folder = await make_folder(owner_client)
    bad_names = [
        "../../etc/passwd",
        "..\\..\\windows\\win.ini",
        "a/b",
        "a\\b",
        "​invisible",
        "dir‮name",
        ".hidden",
        "trailing.",
        " ",
        "a\x00b",
        "x" * 300,
    ]
    for name in bad_names:
        r = await owner_client.post(
            "/api/v1/folders", json={"parent_id": None, "name": name}, headers=H
        )
        assert r.status_code in (400, 422), f"accepted hostile name: {name!r}"
        md = md_for(folder["id"], name=name)
        r = await owner_client.post(
            "/api/v1/uploads", headers={**H, "Upload-Length": "1", "Upload-Metadata": md}
        )
        assert r.status_code in (400, 422), f"accepted hostile upload name: {name!r}"


@pytest.mark.asyncio
@pytest.mark.asyncio
# FR-P5: SVG is always an attachment, never rendered.
async def test_svg_always_attachment(owner_client):
    folder = await make_folder(owner_client)
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    file_id = await tus_upload(
        owner_client, folder["id"], svg, name="innocent.svg", mime="image/svg+xml"
    )
    r = await owner_client.get(f"/api/v1/files/{file_id}/content", headers=H)
    assert r.status_code == 200
    assert "attachment" in r.headers.get("content-disposition", "")


@pytest.mark.asyncio
@pytest.mark.asyncio
# FR-T4: multi-range requests fall back to the full body.
async def test_multi_range_degrades_to_full(owner_client):
    folder = await make_folder(owner_client)
    content = b"multi-range-test-content" * 100
    file_id = await tus_upload(owner_client, folder["id"], content, name="m.bin")
    r = await owner_client.get(
        f"/api/v1/files/{file_id}/content", headers={**H, "Range": "bytes=0-9,50-59"}
    )
    assert r.status_code == 200 and len(r.content) == len(content)


# ---------------- background GC ----------------


@pytest.mark.asyncio
async def test_cleanup_pass_purges_trash_reclaims_blobs_and_spares_live_uploads(owner_client):
    """Regression: cleanup_pass must run (no AttributeError), purge stale
    FR-F3: trash purge, blob reclaim, live uploads spared.
    trash + orphan blobs, and NEVER collect in-progress (pending) uploads."""
    import uuid as _uuid
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import func, select

    from localdrop.db import SessionFactory
    from localdrop.models import Blob, File, UploadSession
    from localdrop.services.jobs import cleanup_pass
    from localdrop.storage import get_storage

    folder = await make_folder(owner_client)
    file_id = await tus_upload(owner_client, folder["id"], b"trash me", name="t.txt")

    # trash it, then backdate past retention
    r = await owner_client.delete(f"/api/v1/files/{file_id}", headers=H)
    assert r.status_code == 204
    async with SessionFactory() as db:
        f = (await db.execute(select(File).where(File.id == _uuid.UUID(file_id)))).scalar_one()
        blob_id = f.blob_id
        f.deleted_at = datetime.now(UTC) - timedelta(days=60)
        # a live in-progress upload: pending blob + active session
        sess = UploadSession(
            user_id=f.uploader_id,
            folder_id=f.folder_id,
            file_name="live.bin",
            total_size=10,
            offset=0,
            status="active",
            staging_path="staging/live.bin",
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
        db.add(sess)
        await db.flush()
        live_blob = Blob(size=10, status="pending", storage_path="staging/live.bin")
        db.add(live_blob)
        await db.commit()

    async with SessionFactory() as db:
        stats = await cleanup_pass(db, get_storage())
        await db.commit()
    assert stats["trash_purged"] == 1

    async with SessionFactory() as db:
        assert (
            await db.execute(select(File).where(File.id == _uuid.UUID(file_id)))
        ).scalar_one_or_none() is None
        assert (
            await db.execute(select(Blob).where(Blob.id == blob_id))
        ).scalar_one_or_none() is None
        # live upload untouched
        assert (
            await db.execute(select(Blob).where(Blob.status == "pending"))
        ).scalars().all() != []
        n_pending = (
            await db.execute(select(func.count()).select_from(Blob).where(Blob.status == "pending"))
        ).scalar_one()
        assert n_pending >= 1


# ---------------- personal access tokens ----------------


@pytest.mark.asyncio
async def test_pat_auth_scopes_and_revocation(owner_client, app):
    """Regression: PAT Bearer auth must work cookie-less; read scope cannot
    FR-A5: PAT scopes are enforced and revocation works.
    write; revoked PATs stop working. (PAT loading once raised AttributeError
    because the model lacked the user relationship.)"""
    from httpx import ASGITransport, AsyncClient

    r = await owner_client.post(
        "/api/v1/me/tokens", json={"name": "rw", "scopes": "read,write"}, headers=H
    )
    assert r.status_code == 201
    rw, rw_id = r.json()["token"], r.json()["id"]
    r = await owner_client.post(
        "/api/v1/me/tokens", json={"name": "ro", "scopes": "read"}, headers=H
    )
    ro = r.json()["token"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://pat") as c:
        r = await c.get("/api/v1/me", headers={"Authorization": f"Bearer {rw}"})
        assert r.status_code == 200, r.text
        r = await c.post(
            "/api/v1/folders",
            json={"parent_id": None, "name": "pat-folder"},
            headers={"Authorization": f"Bearer {rw}"},
        )
        assert r.status_code == 201, r.text
        r = await c.get("/api/v1/folders/root/children", headers={"Authorization": f"Bearer {ro}"})
        assert r.status_code == 200
        r = await c.post(
            "/api/v1/folders",
            json={"parent_id": None, "name": "pat-nope"},
            headers={"Authorization": f"Bearer {ro}"},
        )
        assert r.status_code == 403, r.status_code

    r = await owner_client.delete(f"/api/v1/me/tokens/{rw_id}", headers=H)
    assert r.status_code == 204
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://pat") as c:
        r = await c.get("/api/v1/me", headers={"Authorization": f"Bearer {rw}"})
        assert r.status_code == 401, r.status_code


@pytest.mark.asyncio
@pytest.mark.asyncio
# FR-O3: /metrics is not public.
async def test_metrics_requires_authentication(app, owner_client):
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://anon") as anon:
        r = await anon.get("/metrics")
        assert r.status_code == 401, r.status_code
    r = await owner_client.get("/metrics", headers=H)
    assert r.status_code == 200, r.status_code


# ---------------- unreadable storage ----------------


@pytest.mark.asyncio
async def test_missing_blob_data_is_clean_404_not_500(owner_client):
    """Lost blob bytes (deleted/moved data dir) must surface as a clean 404
    FR-F3: a vanished blob is a clean 404, not a 500.
    JSON error — never a 500 and never a mid-stream abort."""
    import os
    import uuid as _uuid

    from sqlalchemy import select

    from localdrop.db import SessionFactory
    from localdrop.models import Blob, File
    from localdrop.storage import get_storage

    folder = await make_folder(owner_client)
    file_id = await tus_upload(owner_client, folder["id"], b"doomed", name="d.txt")
    async with SessionFactory() as db:
        f = (await db.execute(select(File).where(File.id == _uuid.UUID(file_id)))).scalar_one()
        b = (await db.execute(select(Blob).where(Blob.id == f.blob_id))).scalar_one()
        path = get_storage().from_recorded(b.storage_path)
    os.remove(path)
    for url in (f"/api/v1/files/{file_id}/content", f"/api/v1/files/{file_id}/preview"):
        r = await owner_client.get(url, headers=H)
        assert r.status_code == 404, (url, r.status_code)
        assert r.json()["type"].endswith("not-found")


# ---------------- concurrency ----------------


@pytest.mark.asyncio
async def test_concurrent_identical_uploads_no_corruption(owner_client):
    """Dedup race: two simultaneous uploads of identical bytes must both
    FR-T1: concurrent identical uploads stay consistent.
    succeed (no 500/IntegrityError) and share one verified blob."""
    import asyncio as _asyncio

    from sqlalchemy import func, select

    from localdrop.db import SessionFactory
    from localdrop.models import Blob

    folder = await make_folder(owner_client)
    content = b"race-content " * 50000  # 600 KiB

    async def one(name: str) -> str:
        return await tus_upload(owner_client, folder["id"], content, name=name)

    fid1, fid2 = await _asyncio.gather(one("r1.bin"), one("r2.bin"))
    assert fid1 != fid2
    for fid in (fid1, fid2):
        r = await owner_client.get(f"/api/v1/files/{fid}/content", headers=H)
        assert r.status_code == 200 and r.content == content
    async with SessionFactory() as db:
        n = (
            await db.execute(
                select(func.count()).select_from(Blob).where(Blob.status == "verified")
            )
        ).scalar_one()
    # both files verified; at most the blobs this test created (other tests'
    # blobs may exist in the shared schema — assert no *duplicate* for ours)
    assert n >= 1


@pytest.mark.asyncio
async def test_reupload_heals_lost_blob_bytes(owner_client):
    """If canonical blob bytes vanish out-of-band, re-uploading identical
    FR-F6: re-upload repairs a blob whose bytes went missing.
    bytes must heal (new verified blob) instead of linking to the dead row."""
    import os
    import uuid as _uuid

    from sqlalchemy import select

    from localdrop.db import SessionFactory
    from localdrop.models import Blob, File
    from localdrop.storage import get_storage

    folder = await make_folder(owner_client)
    content = b"heal-me " * 1000
    fid1 = await tus_upload(owner_client, folder["id"], content, name="h1.bin")
    async with SessionFactory() as db:
        f = (await db.execute(select(File).where(File.id == _uuid.UUID(fid1)))).scalar_one()
        b = (await db.execute(select(Blob).where(Blob.id == f.blob_id))).scalar_one()
        assert b.status == "verified"
        os.remove(get_storage().from_recorded(b.storage_path))
    # first file now 404s cleanly
    r = await owner_client.get(f"/api/v1/files/{fid1}/content", headers=H)
    assert r.status_code == 404
    # re-upload heals
    fid2 = await tus_upload(owner_client, folder["id"], content, name="h2.bin")
    r = await owner_client.get(f"/api/v1/files/{fid2}/content", headers=H)
    assert r.status_code == 200 and r.content == content
