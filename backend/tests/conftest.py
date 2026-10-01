"""Test fixtures: isolated app instance per session, test DB, auth clients."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import sys
import tempfile
import uuid

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

os.environ["LOCALDROP_DATA_DIR"] = tempfile.mkdtemp(prefix="localdrop-test-")
# Honour an externally supplied test database, because the default only works on
# a developer machine with a trust-auth cluster on :5433. CI runs PostgreSQL with
# a password, and a hard-coded passwordless URL fails there with
# "fe_sendauth: no password supplied" — which is a confusing way to learn that
# the suite is not actually pointed at the database CI created.
#
#   LOCALDROP_TEST_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/db
#
# Or set the parts: LOCALDROP_TEST_PG{,_USER,_PASSWORD,_DB}.
_TEST_URL = os.environ.get("LOCALDROP_TEST_DATABASE_URL")
if not _TEST_URL:
    _pg_host = os.environ.get("LOCALDROP_TEST_PG", "127.0.0.1")
    _pg_port = os.environ.get("LOCALDROP_TEST_PG_PORT", "5433")
    _pg_user = os.environ.get("LOCALDROP_TEST_PG_USER", "postgres")
    _pg_pass = os.environ.get("LOCALDROP_TEST_PG_PASSWORD")
    _pg_db = os.environ.get("LOCALDROP_TEST_PG_DB", "localdrop_test")
    _auth = f"{_pg_user}:{_pg_pass}" if _pg_pass else _pg_user
    _TEST_URL = f"postgresql+psycopg://{_auth}@{_pg_host}:{_pg_port}/{_pg_db}"
os.environ["LOCALDROP_DATABASE_URL"] = _TEST_URL
os.environ["LOCALDROP_SECRET_KEY"] = "test-secret-key-0123456789abcdef0123456789abcdef"
os.environ["LOCALDROP_DEV_MODE"] = "true"

from localdrop.main import create_app  # noqa: E402

H = {"X-Requested-With": "localdrop"}


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """Isolate tests from the in-process rate limiter (one shared IP in tests)."""
    from localdrop.ratelimit import reset_limits

    reset_limits()
    yield
    reset_limits()


@pytest_asyncio.fixture(scope="session")
async def app():
    app = create_app()
    # fresh schema per session
    from sqlalchemy import text

    from localdrop.db import engine

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))

    # Apply migrations in-process, in a worker thread: Alembic's API is sync, and
    # the Windows selector loop cannot spawn subprocesses.
    #
    # Deliberately calls localdrop.migrate rather than building an AlembicConfig
    # here. Hand-rolling it meant this file kept a hard-coded path to
    # alembic.ini, which broke silently when the file moved into the package.
    from localdrop.migrate import upgrade as _upgrade

    await asyncio.to_thread(_upgrade)
    async with LifespanManager(app):
        yield app


@pytest_asyncio.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def owner_client(app, client):
    """Self-contained authenticated client with a dedicated user (test-isolated)."""
    from sqlalchemy import select

    from localdrop.db import SessionFactory
    from localdrop.models import User
    from localdrop.security import hash_password

    uname = f"owner-{uuid.uuid4().hex[:8]}"
    async with SessionFactory() as db:
        user = (await db.execute(select(User).where(User.username == uname))).scalars().first()
        if user is None:
            db.add(User(username=uname, password_hash=hash_password("testpass123"), role="owner"))
            await db.commit()
    r = await client.post(
        "/api/v1/auth/login", json={"username": uname, "password": "testpass123"}, headers=H
    )
    assert r.status_code == 204, r.text
    client.ld_username = uname  # tests read this instead of hardcoding
    client.ld_password = "testpass123"
    yield client


async def make_folder(client: AsyncClient, name: str | None = None) -> dict:
    name = name or f"folder-{uuid.uuid4().hex[:8]}"
    r = await client.post("/api/v1/folders", json={"parent_id": None, "name": name}, headers=H)
    assert r.status_code == 201, r.text
    return r.json()


async def tus_upload(
    client: AsyncClient,
    folder_id: str,
    content: bytes,
    name: str = "file.bin",
    mime: str = "application/octet-stream",
    chunk_size: int = 524288,
) -> str:
    """Run the full tus cycle; returns the file id."""
    md = (
        "filename "
        + base64.b64encode(name.encode()).decode()
        + ",folderId "
        + base64.b64encode(folder_id.encode()).decode()
        + ",filetype "
        + base64.b64encode(mime.encode()).decode()
    )
    r = await client.post(
        "/api/v1/uploads",
        headers={
            **H,
            "Upload-Length": str(len(content)),
            "Upload-Metadata": md,
            "Tus-Resumable": "1.0.0",
        },
    )
    assert r.status_code == 201, r.text
    loc = r.headers["location"]
    off = 0
    file_id = ""
    while off < len(content):
        chunk = content[off : off + chunk_size]
        ck = "sha256 " + base64.b64encode(hashlib.sha256(chunk).digest()).decode()
        r = await client.patch(
            loc,
            content=chunk,
            headers={
                **H,
                "Upload-Offset": str(off),
                "Content-Type": "application/offset+octet-stream",
                "Upload-Checksum": ck,
                "Content-Length": str(len(chunk)),
            },
        )
        assert r.status_code == 204, r.text
        off = int(r.headers["Upload-Offset"])
        file_id = r.headers.get("X-Localdrop-File", file_id)
    return file_id


def md_for(folder_id: str, name: str = "x.bin", mime: str = "application/octet-stream") -> str:
    return (
        "filename "
        + base64.b64encode(name.encode()).decode()
        + ",folderId "
        + base64.b64encode(folder_id.encode()).decode()
        + ",filetype "
        + base64.b64encode(mime.encode()).decode()
    )
