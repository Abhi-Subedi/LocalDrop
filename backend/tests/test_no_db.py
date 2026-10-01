"""Tests that need no database.

Everything here is a pure function or a route that answers without touching
PostgreSQL, so the whole file runs anywhere:

    python -m pytest tests/test_no_db.py -q

They are not a substitute for `test_v1_critical.py`; they cover the parts of
the server that must be correct even when the database is down, which is
exactly when an operator is trying to diagnose something.
"""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

# Point at a port nothing is listening on: these tests must pass *because* they
# do not need a database, and a hang would mean that assumption is wrong.
DEAD_DB = "postgresql+psycopg://nobody@127.0.0.1:1/nothing"


# ---- FR-O1: health endpoints ---------------------------------------------
@pytest.mark.asyncio
async def test_health_live_is_public_and_never_touches_the_database(monkeypatch, tmp_path):
    """FR-O1: liveness answers while the database is unreachable.

    A readiness probe that hangs when PostgreSQL is down is useless during an
    incident, and a liveness probe that depends on the database will restart a
    perfectly healthy process.
    """
    monkeypatch.setenv("LOCALDROP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LOCALDROP_SECRET_KEY", "x" * 40)
    monkeypatch.setenv("LOCALDROP_DATABASE_URL", DEAD_DB)
    monkeypatch.setenv("LOCALDROP_DEV_MODE", "true")

    from localdrop.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/v1/health/live")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_ready_reports_degraded_instead_of_crashing(monkeypatch, tmp_path):
    """FR-O1: readiness degrades to 503 with a named reason, never a 500.

    A probe that raises gives an operator nothing to act on. Naming the failing
    subsystem is the entire point of a readiness check.
    """
    monkeypatch.setenv("LOCALDROP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LOCALDROP_SECRET_KEY", "x" * 40)
    monkeypatch.setenv("LOCALDROP_DATABASE_URL", DEAD_DB)
    monkeypatch.setenv("LOCALDROP_DEV_MODE", "true")

    from localdrop.config import get_settings
    from localdrop.main import create_app

    get_settings.cache_clear()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        import time

        started = time.monotonic()
        r = await c.get("/api/v1/health/ready")
        elapsed = time.monotonic() - started
        assert r.status_code == 503, r.text
        body = r.json()
        assert body["status"] == "degraded"
        # The failing subsystem must be named, not just reported as "error".
        assert "database" in body["checks"]
        assert body["checks"]["database"] != "ok"
        # Docker probes with --timeout=5s and most orchestrators give a probe
        # ~30s. libpq's default connect timeout is ~2 minutes, which would
        # make this endpoint useless exactly when it is needed. Regression
        # guard: a missing connect_timeout in db.make_engine() shows up here.
        assert elapsed < 10, f"readiness took {elapsed:.1f}s against a dead database"
    get_settings.cache_clear()


# ---- FR-O2: every response carries a request id --------------------------
@pytest.mark.asyncio
async def test_every_response_carries_a_request_id(monkeypatch, tmp_path):
    """FR-O2: a request id is generated, echoed, and logged.

    Without it there is no way to correlate a user's report ("it failed at
    14:03") with a line in the log.
    """
    monkeypatch.setenv("LOCALDROP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LOCALDROP_SECRET_KEY", "x" * 40)
    monkeypatch.setenv("LOCALDROP_DATABASE_URL", DEAD_DB)
    monkeypatch.setenv("LOCALDROP_DEV_MODE", "true")

    from localdrop.config import get_settings
    from localdrop.main import create_app

    get_settings.cache_clear()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        first = await c.get("/api/v1/health/live")
        second = await c.get("/api/v1/health/live")
        assert first.headers.get("x-request-id")
        assert second.headers.get("x-request-id")
        # Two requests must not collide, or the log correlation is worthless.
        assert first.headers["x-request-id"] != second.headers["x-request-id"]

        # A client-supplied id is honoured, so a reverse proxy can stitch traces.
        supplied = "req-from-the-proxy-123"
        third = await c.get("/api/v1/health/live", headers={"X-Request-ID": supplied})
        assert third.headers.get("x-request-id") == supplied
    get_settings.cache_clear()


# ---- security headers (spec 06 / BC-12) ----------------------------------
@pytest.mark.asyncio
async def test_security_headers_are_present(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALDROP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LOCALDROP_SECRET_KEY", "x" * 40)
    monkeypatch.setenv("LOCALDROP_DATABASE_URL", DEAD_DB)
    monkeypatch.setenv("LOCALDROP_DEV_MODE", "true")

    from localdrop.config import get_settings
    from localdrop.main import create_app

    get_settings.cache_clear()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/v1/health/live")
        h = {k.lower() for k in r.headers}
        assert "x-content-type-options" in h
        assert "referrer-policy" in h
        assert r.headers.get("x-content-type-options") == "nosniff"
        # The API must never be framed or sniffed by a browser.
        assert r.headers.get("x-frame-options", "DENY") in {"DENY", "SAMEORIGIN"}
    get_settings.cache_clear()


# ---- FR-O2: unknown API paths are problem+json, not HTML ------------------
@pytest.mark.asyncio
async def test_unknown_api_path_is_problem_json_not_the_spa(monkeypatch, tmp_path):
    """A 404 under /api must not fall through to index.html.

    Returning the SPA for an unknown API route turns a client bug into a
    confusing HTML parse error instead of a clear 404.
    """
    monkeypatch.setenv("LOCALDROP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LOCALDROP_SECRET_KEY", "x" * 40)
    monkeypatch.setenv("LOCALDROP_DATABASE_URL", DEAD_DB)
    monkeypatch.setenv("LOCALDROP_DEV_MODE", "true")

    from localdrop.config import get_settings
    from localdrop.main import create_app

    get_settings.cache_clear()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/v1/definitely-not-a-route")
        assert r.status_code == 404
        assert "application/problem+json" in r.headers["content-type"]
        assert r.json()["type"]
    get_settings.cache_clear()


# ---- FR-L1: LAN address discovery ----------------------------------------
def test_detect_lan_ips_excludes_loopback_and_returns_strings():
    """FR-L1: LAN discovery yields printable addresses, never 127.0.0.1.

    The banner is what tells a user which URL to open on their phone, and
    "http://127.0.0.1:8080" on a phone is a dead end.
    """
    from localdrop.main import detect_lan_ips

    ips = detect_lan_ips()
    assert isinstance(ips, list)
    for ip in ips:
        assert isinstance(ip, str), f"{ip!r} is not a string"
        assert not ip.startswith("127."), "loopback must never be advertised"
        # A non-string here would blow up the f-string in the banner.
        assert ip.count(".") == 3, f"{ip!r} is not dotted-quad IPv4"
    assert len(ips) == len(set(ips)), "duplicate addresses"


def test_lan_banner_urls_are_well_formed(capsys, monkeypatch, tmp_path):
    """FR-L1: every advertised URL is parseable and carries the port."""
    from localdrop.config import Settings, get_settings
    from localdrop.main import print_lan_banner

    monkeypatch.setenv("LOCALDROP_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    s = Settings(data_dir=tmp_path, port=9123, dev_mode=True)
    print_lan_banner(s, 9123)
    out = capsys.readouterr().out

    assert "LocalDrop is running" in out
    urls = [line.strip() for line in out.splitlines() if line.strip().startswith("http://")]
    assert urls, "the banner printed no URLs at all"
    for url in urls:
        assert url.startswith("http://")
        assert url.endswith(":9123"), f"{url!r} is missing the port"
    get_settings.cache_clear()


# ---- version reporting (single source of truth) ---------------------------
def test_version_endpoint_reports_the_canonical_version(monkeypatch, tmp_path):
    """GET /api/v1/version must agree with localdrop.__version__.

    This is what the Settings "About" panel shows and what a user pastes into
    a bug report, so a stale value here misdirects every future triage.
    """
    monkeypatch.setenv("LOCALDROP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LOCALDROP_SECRET_KEY", "x" * 40)
    monkeypatch.setenv("LOCALDROP_DATABASE_URL", DEAD_DB)
    monkeypatch.setenv("LOCALDROP_DEV_MODE", "true")

    from localdrop import __version__
    from localdrop.config import get_settings
    from localdrop.main import create_app

    get_settings.cache_clear()
    app = create_app()

    async def _go():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            return (await c.get("/api/v1/version")).json()

    body = asyncio.run(_go())
    assert body["version"] == __version__
    assert body["name"] == "LocalDrop"
    # Must not leak deployment detail.
    assert not any(k in body for k in ("database_url", "data_dir", "secret_key"))
    get_settings.cache_clear()


# ---- packaging invariants -------------------------------------------------
def test_packaged_resources_exist_outside_a_frozen_build():
    """The SPA and the migrations must be importable from a plain install.

    A wheel that installs but cannot find its own migrations is the failure
    mode that moved both directories into the package; this is the guard.
    """
    from localdrop.main import SPA_DIST
    from localdrop.migrate import migrations_dir

    assert (SPA_DIST / "index.html").is_file(), f"no SPA at {SPA_DIST}"
    md = migrations_dir()
    assert (md / "env.py").is_file(), f"no alembic env.py at {md}"
    assert (md / "script.py.mako").is_file(), f"no alembic template at {md}"
    assert list((md / "versions").glob("*.py")), f"no migration revisions in {md}"


def test_every_documented_setting_exists():
    """Every setting the docs promise must be a real Settings field.

    Pairs with scripts/check_config_docs.py, which does the same for CI. This
    version is fast enough to run in the ordinary suite. Field names are bare;
    Settings supplies the LOCALDROP_ prefix via env_prefix.
    """
    from localdrop.config import Settings

    fields = set(Settings.model_fields)
    assert Settings.model_config["env_prefix"] == "LOCALDROP_"
    for name in (
        "secret_key",
        "data_dir",
        "database_url",
        "port",
        "public_url",
        "trusted_proxies",
        "max_upload_bytes",
        "trash_retention_days",
        "session_idle_minutes",
        "session_absolute_minutes",
        "log_level",
        "log_format",
        "dev_mode",
        "rate_auth_limit",
        "upload_ttl_days",
    ):
        assert name in fields, f"{name} is not a setting, but the docs list it"

    # A secret key shorter than 32 chars must be rejected in production mode.
    from localdrop.config import Settings as S

    with pytest.raises(RuntimeError, match="32 characters"):
        S(secret_key="too-short", dev_mode=False).ensure_secure()
    # ...and quietly defaulted in dev mode, so iteration "just works".
    dev = S(secret_key="", dev_mode=True)
    dev.ensure_secure()
    assert len(dev.secret_key) >= 32
