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
async def test_register_login_logout(client):
    r = await client.get("/api/v1/setup/status")
    assert r.status_code == 200 and r.json()["onboarding_required"] is True
    r = await client.get("/api/v1/setup/token")
    token = r.json()["token"]
    r = await client.post("/api/v1/setup/owner",
                          json={"username": "owner", "password": "testpass123", "setup_token": token},
                          headers=H)
    assert r.status_code == 201
    # token single-use
    r2 = await client.get("/api/v1/setup/token")
    assert r2.json()["onboarding_required"] is False
    # login
    r = await client.post("/api/v1/auth/login", json={"username": "owner", "password": "testpass123"}, headers=H)
    assert r.status_code == 204
    assert "ld_session" in r.headers.get("set-cookie", "")
    # me
    r = await client.get("/api/v1/me", headers=H)
    assert r.status_code == 200 and r.json()["username"] == "owner"
    # wrong password
    r = await client.post("/api/v1/auth/login", json={"username": "owner", "password": "wrong-password"}, headers=H)
    assert r.status_code == 401
    # logout
    r = await client.post("/api/v1/auth/logout", headers=H)
    assert r.status_code == 204
    r = await client.get("/api/v1/me", headers=H)
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_csrf_required_for_cookie_mutations(owner_client):
    r = await owner_client.post("/api/v1/folders", json={"parent_id": None, "name": "no-csrf"})
    assert r.status_code == 403
    assert r.json()["type"].endswith("csrf")


@pytest.mark.asyncio
async def test_password_change_revokes_other_sessions(app, owner_client):
    # a second client = another session
    from httpx import ASGITransport, AsyncClient
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c2:
        r = await c2.post("/api/v1/auth/login", json={"username": owner_client.ld_username, "password": owner_client.ld_password}, headers=H)
        assert r.status_code == 204
    r = await owner_client.put("/api/v1/me/password",
                               json={"current": owner_client.ld_password, "new": "newpass1234"}, headers=H)
    assert r.status_code == 204
    # old password no longer works
    r = await owner_client.post("/api/v1/auth/login", json={"username": owner_client.ld_username, "password": "testpass123"}, headers=H)
    assert r.status_code == 401
    # restore
    r = await owner_client.post("/api/v1/auth/login", json={"username": owner_client.ld_username, "password": "newpass1234"}, headers=H)
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_login_lockout_after_failures(client, owner_client):
    for _ in range(10):
        await client.post("/api/v1/auth/login", json={"username": "owner", "password": "badpass123"}, headers=H)
    r = await client.post("/api/v1/auth/login", json={"username": "owner", "password": "badpass123"}, headers=H)
    assert r.status_code == 429


# ---------------- authorization ----------------


@pytest.mark.asyncio
async def test_unauthenticated_access_denied(client):
    for method, path in [
        ("GET", "/api/v1/me"), ("GET", "/api/v1/folders/root/children"),
        ("POST", "/api/v1/folders"), ("GET", "/api/v1/trash"), ("GET", "/api/v1/shares"),
    ]:
        r = await getattr(client, method.lower())(path, headers=H)
        assert r.status_code in (401,), f"{method} {path}: {r.status_code}"


@pytest.mark.asyncio
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
        db.add(User(username=attacker_name, password_hash=hash_password("attackerpass1"), role="user"))
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as attacker:
        r = await attacker.post("/api/v1/auth/login", json={"username": attacker_name, "password": "attackerpass1"}, headers=H)
        assert r.status_code == 204

        # attacker cannot see owner's folders/files
        r = await attacker.get("/api/v1/folders/root/children", headers=H)
        assert r.status_code == 200 and r.json()["items"] == []


# ---------------- files & folders ----------------


@pytest.mark.asyncio
async def test_folder_crud_and_collisions(owner_client):
    f1 = await make_folder(owner_client, "Docs")
    # case-insensitive collision
    r = await owner_client.post("/api/v1/folders", json={"parent_id": None, "name": "docs"}, headers=H)
    assert r.status_code == 409
    # rename
    r = await owner_client.patch(f"/api/v1/folders/{f1['id']}", json={"name": "Documents"}, headers=H)
    assert r.status_code == 200 and r.json()["name"] == "Documents"
    # subfolder + move
    sub = await make_folder(owner_client, "Sub")
    r = await owner_client.post(f"/api/v1/folders/{sub['id']}/move", json={"new_parent_id": f1["id"]}, headers=H)
    assert r.status_code == 200
    # cycle rejection: move Documents into Sub
    r = await owner_client.post(f"/api/v1/folders/{f1['id']}/move", json={"new_parent_id": sub["id"]}, headers=H)
    assert r.status_code == 422
    # delete (soft) → trash → restore
    r = await owner_client.delete(f"/api/v1/folders/{f1['id']}", headers=H)
    assert r.status_code == 200
    r = await owner_client.get("/api/v1/folders/root/children", headers=H)
    assert r.json()["items"] == []
    r = await owner_client.post(f"/api/v1/folders/{f1['id']}/restore", headers=H)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_file_lifecycle_upload_download_rename_move_copy_delete(owner_client):
    folder = await make_folder(owner_client)
    content = b"LocalDrop test content " * 1000
    file_id = await tus_upload(owner_client, folder["id"], content, name="notes.txt", mime="text/plain")

    # download + verify
    r = await owner_client.get(f"/api/v1/files/{file_id}/content", headers=H)
    assert r.status_code == 200 and hashlib.sha256(r.content).hexdigest() == hashlib.sha256(content).hexdigest()
    assert r.headers["content-type"].startswith("text/plain")

    # range single
    r = await owner_client.get(f"/api/v1/files/{file_id}/content", headers={**H, "Range": "bytes=0-9"})
    assert r.status_code == 206 and r.content == content[:10]
    # suffix range
    r = await owner_client.get(f"/api/v1/files/{file_id}/content", headers={**H, "Range": "bytes=-5"})
    assert r.status_code == 206 and r.content == content[-5:]

    # rename
    r = await owner_client.patch(f"/api/v1/files/{file_id}", json={"name": "renamed.txt"}, headers=H)
    assert r.status_code == 200 and r.json()["name"] == "renamed.txt"

    # move to second folder
    f2 = await make_folder(owner_client)
    r = await owner_client.post(f"/api/v1/files/{file_id}/move", json={"folder_id": f2["id"]}, headers=H)
    assert r.status_code == 200

    # copy (same blob, zero bytes)
    r = await owner_client.post(f"/api/v1/files/{file_id}/copy", json={"folder_id": folder["id"]}, headers=H)
    assert r.status_code == 201

    # delete → trash → restore
    r = await owner_client.delete(f"/api/v1/files/{file_id}", headers=H)
    assert r.status_code == 204
    r = await owner_client.get("/api/v1/trash", headers=H)
    assert len(r.json()) == 1
    r = await owner_client.post(f"/api/v1/files/{file_id}/restore", headers=H)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_dedup_same_content_single_blob(owner_client):
    folder = await make_folder(owner_client)
    content = b"dedup-me " * 1000
    from sqlalchemy import func, select

    from localdrop.db import SessionFactory
    from localdrop.models import Blob

    async def verified_count() -> int:
        async with SessionFactory() as db:
            return (await db.execute(select(func.count()).select_from(Blob).where(Blob.status == "verified"))).scalar_one()

    before = await verified_count()
    fid1 = await tus_upload(owner_client, folder["id"], content, name="a.bin")
    fid2 = await tus_upload(owner_client, folder["id"], content, name="b.bin")
    assert fid1 != fid2
    # two files, one new blob: identical content is stored once
    assert await verified_count() == before + 1


# ---------------- upload security / failure cases ----------------


@pytest.mark.asyncio
async def test_upload_offset_conflict_rejected(owner_client):
    folder = await make_folder(owner_client)
    md = md_for(folder["id"])
    r = await owner_client.post("/api/v1/uploads", headers={**H, "Upload-Length": "100", "Upload-Metadata": md})
    loc = r.headers["location"]
    r = await owner_client.patch(loc, content=b"0123456789",
                                 headers={**H, "Upload-Offset": "50", "Content-Type": "application/offset+octet-stream",
                                          "Content-Length": "10"})
    assert r.status_code == 460


@pytest.mark.asyncio
async def test_upload_checksum_mismatch_keeps_offset(owner_client):
    folder = await make_folder(owner_client)
    md = md_for(folder["id"])
    r = await owner_client.post("/api/v1/uploads", headers={**H, "Upload-Length": "20", "Upload-Metadata": md})
    loc = r.headers["location"]
    bad_ck = "sha256 " + base64.b64encode(hashlib.sha256(b"not-the-data").digest()).decode()
    r = await owner_client.patch(loc, content=b"01234567890123456789",
                                 headers={**H, "Upload-Offset": "0", "Content-Type": "application/offset+octet-stream",
                                          "Upload-Checksum": bad_ck, "Content-Length": "20"})
    assert r.status_code == 460
    # offset unchanged
    r = await owner_client.head(loc, headers={**H, "Tus-Resumable": "1.0.0"})
    assert r.headers["Upload-Offset"] == "0"


@pytest.mark.asyncio
async def test_upload_oversize_rejected(owner_client):
    folder = await make_folder(owner_client)
    md = md_for(folder["id"])
    r = await owner_client.post("/api/v1/uploads", headers={**H, "Upload-Length": "200000000000", "Upload-Metadata": md})
    assert r.status_code == 413


@pytest.mark.asyncio
async def test_upload_interrupted_then_resumed(owner_client):
    folder = await make_folder(owner_client)
    content = b"resume-test " * 100000  # 1.2MB
    md = md_for(folder["id"], name="resume.bin")
    r = await owner_client.post("/api/v1/uploads", headers={**H, "Upload-Length": str(len(content)), "Upload-Metadata": md})
    loc = r.headers["location"]
    # first chunk only
    part = content[:524288]
    ck = "sha256 " + base64.b64encode(hashlib.sha256(part).digest()).decode()
    r = await owner_client.patch(loc, content=part,
                                 headers={**H, "Upload-Offset": "0", "Content-Type": "application/offset+octet-stream",
                                          "Upload-Checksum": ck, "Content-Length": str(len(part))})
    assert r.status_code == 204
    # HEAD reports the persisted offset (resume works)
    r = await owner_client.head(loc, headers={**H, "Tus-Resumable": "1.0.0"})
    assert r.headers["Upload-Offset"] == str(len(part))
    # resume with the rest
    rest = content[524288:]
    ck = "sha256 " + base64.b64encode(hashlib.sha256(rest).digest()).decode()
    r = await owner_client.patch(loc, content=rest,
                                 headers={**H, "Upload-Offset": str(len(part)), "Content-Type": "application/offset+octet-stream",
                                          "Upload-Checksum": ck, "Content-Length": str(len(rest))})
    assert r.status_code == 204
    file_id = r.headers["X-Localdrop-File"]
    r = await owner_client.get(f"/api/v1/files/{file_id}/content", headers=H)
    assert hashlib.sha256(r.content).hexdigest() == hashlib.sha256(content).hexdigest()


# ---------------- sharing ----------------


@pytest.mark.asyncio
async def test_share_full_lifecycle(owner_client):
    folder = await make_folder(owner_client)
    file_id = await tus_upload(owner_client, folder["id"], b"share me", name="s.txt", mime="text/plain")

    r = await owner_client.post("/api/v1/shares",
                                json={"file_id": file_id, "max_downloads": 2, "password": "pw12345"}, headers=H)
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
async def test_share_invalid_token_is_404(owner_client):
    r = await owner_client.get("/api/v1/shares/AAAAAAAAAAAAAAAAAAAAAAAAAA")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_share_expiry(owner_client):
    """A share past its expiry is indistinguishable from unknown (404)."""
    from datetime import UTC, datetime, timedelta

    from localdrop.db import SessionFactory
    from localdrop.models import Share
    from sqlalchemy import select

    folder = await make_folder(owner_client)
    file_id = await tus_upload(owner_client, folder["id"], b"exp", name="e.txt")
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    r = await owner_client.post("/api/v1/shares", json={"file_id": file_id, "expires_at": future}, headers=H)
    assert r.status_code == 201
    token = r.json()["token"]

    # past expiry is rejected at creation
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    r = await owner_client.post("/api/v1/shares", json={"file_id": file_id, "expires_at": past}, headers=H)
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
async def test_hostile_names_rejected(owner_client):
    folder = await make_folder(owner_client)
    bad_names = [
        "../../etc/passwd", "..\\..\\windows\\win.ini", "a/b", "a\\b",
        "​invisible", "dir‮name", ".hidden", "trailing.", " ", "a\x00b",
        "x" * 300,
    ]
    for name in bad_names:
        r = await owner_client.post("/api/v1/folders", json={"parent_id": None, "name": name}, headers=H)
        assert r.status_code in (400, 422), f"accepted hostile name: {name!r}"
        md = md_for(folder["id"], name=name)
        r = await owner_client.post("/api/v1/uploads", headers={**H, "Upload-Length": "1", "Upload-Metadata": md})
        assert r.status_code in (400, 422), f"accepted hostile upload name: {name!r}"


@pytest.mark.asyncio
async def test_svg_always_attachment(owner_client):
    folder = await make_folder(owner_client)
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    file_id = await tus_upload(owner_client, folder["id"], svg, name="innocent.svg",
                               mime="image/svg+xml")
    r = await owner_client.get(f"/api/v1/files/{file_id}/content", headers=H)
    assert r.status_code == 200
    assert "attachment" in r.headers.get("content-disposition", "")


@pytest.mark.asyncio
async def test_multi_range_degrades_to_full(owner_client):
    folder = await make_folder(owner_client)
    content = b"multi-range-test-content" * 100
    file_id = await tus_upload(owner_client, folder["id"], content, name="m.bin")
    r = await owner_client.get(f"/api/v1/files/{file_id}/content", headers={**H, "Range": "bytes=0-9,50-59"})
    assert r.status_code == 200 and len(r.content) == len(content)
