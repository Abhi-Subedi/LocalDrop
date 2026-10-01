"""End-to-end smoke flow (dev): onboarding → tus upload → download → share.

Run: backend/.venv/Scripts/python scripts/smoke_flow.py
"""

import asyncio
import base64
import hashlib
import sys
import time
import warnings

sys.path.insert(0, "src")
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
warnings.filterwarnings("ignore")

from asgi_lifespan import LifespanManager  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

B = "http://test/api/v1"
H = {"X-Requested-With": "localdrop"}


async def onboard(c: AsyncClient) -> None:
    r = await c.get(f"{B}/setup/status")
    if not r.json()["onboarding_required"]:
        return
    r = await c.get(f"{B}/setup/token")
    token = r.json().get("token")
    if not token:
        print("dev-mode token unavailable; check .env")
        sys.exit(1)
    r = await c.post(
        f"{B}/setup/owner",
        json={"username": "owner", "password": "devpassword1", "setup_token": token},
        headers=H,
    )
    print("owner:", r.status_code)


async def main() -> None:
    from localdrop.main import create_app

    app = create_app()
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            await onboard(c)
            r = await c.post(
                f"{B}/auth/login", json={"username": "owner", "password": "devpassword1"}, headers=H
            )
            assert r.status_code == 204, r.text
            print("login: 204")

            UNIQ = f"Pictures-{int(time.time())}"
            r = await c.post(f"{B}/folders", json={"parent_id": None, "name": UNIQ}, headers=H)
            print("create folder:", r.status_code)
            fid = r.json()["id"]

            r = await c.post(
                f"{B}/folders", json={"parent_id": None, "name": UNIQ.lower()}, headers=H
            )
            print("collision 409:", r.status_code)

            content = b"hello localdrop " * 100000  # 1.6 MB
            md = (
                "filename "
                + base64.b64encode(b"photo.bin").decode()
                + ",folderId "
                + base64.b64encode(str(fid).encode()).decode()
                + ",filetype "
                + base64.b64encode(b"application/octet-stream").decode()
            )
            r = await c.post(
                f"{B}/uploads",
                headers={
                    **H,
                    "Upload-Length": str(len(content)),
                    "Upload-Metadata": md,
                    "Tus-Resumable": "1.0.0",
                },
            )
            print("tus create:", r.status_code)
            loc = r.headers["location"]

            off = 0
            file_id = ""
            while off < len(content):
                chunk = content[off : off + 524288]
                ck = "sha256 " + base64.b64encode(hashlib.sha256(chunk).digest()).decode()
                r = await c.patch(
                    f"{loc}",
                    content=chunk,
                    headers={
                        **H,
                        "Upload-Offset": str(off),
                        "Content-Type": "application/offset+octet-stream",
                        "Upload-Checksum": ck,
                        "Content-Length": str(len(chunk)),
                    },
                )
                assert r.status_code == 204, (r.status_code, r.text)
                off = int(r.headers["Upload-Offset"])
                file_id = r.headers.get("X-Localdrop-File", file_id)
            print("tus upload complete:", off, "file:", file_id)

            r = await c.get(f"{B}/files/{file_id}/content", headers=H)
            match = hashlib.sha256(r.content).hexdigest() == hashlib.sha256(content).hexdigest()
            print("download:", r.status_code, "len:", len(r.content), "sha match:", match)

            r = await c.get(f"{B}/files/{file_id}/content", headers={**H, "Range": "bytes=0-99"})
            print("range:", r.status_code, len(r.content), r.headers.get("content-range"))

            r = await c.get(f"{B}/folders/{fid}/children", headers=H)
            items = r.json()["items"]
            print("children:", [(i["name"], i["size"], i["hash_status"]) for i in items])

            # rename
            r = await c.patch(f"{B}/files/{file_id}", json={"name": "renamed.bin"}, headers=H)
            print("rename:", r.status_code, r.json().get("name"))

            # share
            r = await c.post(
                f"{B}/shares",
                json={"file_id": file_id, "max_downloads": 2, "password": "pw12345"},
                headers=H,
            )
            print("share:", r.status_code, "qr:", "svg" in r.json().get("qr_svg", "")[:100])
            share = r.json()
            url = share["url"]
            token = share["token"]
            print("share url:", url)

            # anonymous access (locked)
            r = await c.get(f"{B}/shares/{token}", headers=H)
            print("public info (locked):", r.status_code, r.json()["requires_password"])
            r = await c.get(f"{B}/shares/{token}/files/{file_id}/content")
            print("locked download (expect 403):", r.status_code)
            # unlock wrong + right
            r = await c.post(f"{B}/shares/{token}/unlock", json={"password": "wrong"})
            print("wrong pw (expect 403):", r.status_code)
            r = await c.post(f"{B}/shares/{token}/unlock", json={"password": "pw12345"})
            print("unlock:", r.status_code)
            r = await c.get(f"{B}/shares/{token}/files/{file_id}/content")
            print("shared download:", r.status_code, len(r.content))
            # limit 2 reached on next
            r = await c.get(f"{B}/shares/{token}/files/{file_id}/content")
            print("second download:", r.status_code)
            r = await c.get(f"{B}/shares/{token}/files/{file_id}/content")
            print("limit reached (expect 403):", r.status_code)
            # revoke
            r = await c.delete(f"{B}/shares/{share['id']}", headers=H)
            print("revoke:", r.status_code)
            r = await c.get(f"{B}/shares/{token}", headers=H)
            print("revoked info (expect 404):", r.status_code)


asyncio.run(main())
