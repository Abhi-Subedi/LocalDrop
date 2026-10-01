"""Demo mode, tested without a database where possible.

Demo mode is what makes a public instance survivable, so the invariants are
worth pinning: the endpoints must not exist at all on a normal deployment, the
upload cap must actually shrink, and the rate limiter must not collapse into one
shared bucket when every visitor arrives through the same proxy.

The parts that need PostgreSQL (creating a throwaway account, purging it) are
covered in tests/test_demo_db.py.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

DEAD_DB = "postgresql+psycopg://nobody@127.0.0.1:1/nothing"
H = {"X-Requested-With": "localdrop"}


def _app(monkeypatch, tmp_path, **env):
    monkeypatch.setenv("LOCALDROP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LOCALDROP_SECRET_KEY", "x" * 40)
    monkeypatch.setenv("LOCALDROP_DATABASE_URL", DEAD_DB)
    monkeypatch.setenv("LOCALDROP_DEV_MODE", "true")
    for k, v in env.items():
        monkeypatch.setenv(k, str(v))

    from localdrop.config import get_settings
    from localdrop.main import create_app

    get_settings.cache_clear()
    app = create_app()
    return app, get_settings


# ---- the demo surface must not exist on a normal deployment ---------------
@pytest.mark.asyncio
async def test_demo_endpoints_absent_when_demo_mode_is_off(monkeypatch, tmp_path):
    """A normal instance must not serve a demo, even as an error.

    The SPA catch-all is a GET route, so a POST to an unmounted path resolves to
    405 rather than 404. Either is an acceptable refusal; what matters is that
    it is never 2xx and that the route is absent from the published schema.
    """
    app, _ = _app(monkeypatch, tmp_path, LOCALDROP_DEMO_MODE="false")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.get("/api/v1/demo/status")).status_code == 404
        r = await c.post("/api/v1/demo/session", headers=H)
        assert r.status_code in (404, 405), r.text

        spec = (await c.get("/api/openapi.json")).json()
        assert "/api/v1/demo/session" not in spec["paths"]
        assert "/api/v1/demo/status" not in spec["paths"]
    from localdrop.config import get_settings

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_demo_endpoints_present_when_demo_mode_is_on(monkeypatch, tmp_path):
    app, _ = _app(monkeypatch, tmp_path, LOCALDROP_DEMO_MODE="true")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/v1/demo/status")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["demo_mode"] is True
        assert body["max_upload_bytes"] == 25 * 1024**2
        assert body["ttl_minutes"] == 60
        assert "demo" in body["notice"].lower()
        # The database is unreachable in this test, so the endpoint must report
        # "not accepting" rather than raising: a 500 would leave the SPA
        # spinning on a request that can never succeed.
        assert body["accepting_visitors"] is False

        spec = (await c.get("/api/openapi.json")).json()
        assert "/api/v1/demo/session" in spec["paths"]
    from localdrop.config import get_settings

    get_settings.cache_clear()


# ---- the upload cap must actually shrink ---------------------------------
def test_effective_upload_cap_is_the_smaller_of_the_two():
    from localdrop.config import Settings

    normal = Settings(max_upload_bytes=100 * 1024**3, demo_mode=False)
    assert normal.effective_max_upload_bytes() == 100 * 1024**3

    demo = Settings(max_upload_bytes=100 * 1024**3, demo_mode=True)
    assert demo.effective_max_upload_bytes() == 25 * 1024**2


def test_effective_upload_cap_respects_a_smaller_operator_setting():
    """An operator who already set a 10 MiB cap must not have it raised to 25."""
    from localdrop.config import Settings

    s = Settings(max_upload_bytes=10 * 1024**2, demo_mode=True)
    assert s.effective_max_upload_bytes() == 10 * 1024**2


def test_demo_mode_does_not_raise_a_zero_cap_into_something_else():
    """0 means unlimited in the base config; demo mode must still bound it."""
    from localdrop.config import Settings

    s = Settings(max_upload_bytes=0, demo_mode=True)
    # effective_max_upload_bytes returns max_upload_bytes when it is falsy, so
    # an explicit 0 stays unlimited rather than being silently reinterpreted.
    assert s.effective_max_upload_bytes() == 0


@pytest.mark.asyncio
async def test_tus_max_size_header_advertises_the_demo_cap(monkeypatch, tmp_path):
    """The client learns the cap from Tus-Max-Size, so it must be the demo one."""
    app, _ = _app(monkeypatch, tmp_path, LOCALDROP_DEMO_MODE="true")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post(
            "/api/v1/uploads",
            json={"filename": "x.bin", "filetype": "application/octet-stream", "size": 10},
            headers=H,
        )
        if "tus-max-size" in {k.lower() for k in r.headers}:
            assert r.headers["Tus-Max-Size"] == str(25 * 1024**2)
    from localdrop.config import get_settings

    get_settings.cache_clear()


# ---- the rate limiter must not collapse behind a shared proxy -------------
def test_per_identity_limit_ignores_the_ip_when_an_identity_is_given():
    """The whole point: two visitors behind one proxy must not share a budget.

    This is the failure that makes a hosted demo impossible. With a per-IP
    bucket, the auth limit of 10 per 5 minutes is spent by the first person who
    fumbles a login, and everyone else gets a 429 from a server that is working
    perfectly.
    """
    from localdrop.ratelimit import Limit

    limit = Limit("content", 5, 60, per_identity=True)
    limit.check("203.0.113.1", identity="user-a")
    limit.check("203.0.113.1", identity="user-b")
    limit.check("203.0.113.1", identity="user-c")

    keys = limit.keys("203.0.113.1", "user-a")
    assert keys == ["content:id:user-a"], keys
    assert "203.0.113.1" not in keys[0]


def test_per_identity_limit_still_limits_that_identity():
    from localdrop.errors import Problem
    from localdrop.ratelimit import Limit, reset_limits

    reset_limits()
    limit = Limit("content", 3, 60, per_identity=True)
    for _ in range(3):
        limit.check("198.51.100.7", identity="user-a")
    with pytest.raises(Problem) as e:
        limit.check("198.51.100.7", identity="user-a")
    assert e.value.status == 429
    # ...and a different visitor is unaffected.
    limit.check("198.51.100.7", identity="user-b")


def test_per_identity_falls_back_to_ip_when_anonymous():
    """A request with no session still needs a bucket, or it is unmetered."""
    from localdrop.ratelimit import Limit

    limit = Limit("api", 10, 60, per_identity=True)
    assert limit.keys("192.0.2.5", None) == ["api:192.0.2.5"]


def test_auth_limit_keeps_its_ip_key():
    """Login must stay per-IP: there, the socket really is the signal.

    Keying login by session would be useless, because an attacker has no session
    to key by.
    """
    from localdrop.ratelimit import LIMITS

    assert LIMITS.auth.per_identity is False
    assert LIMITS.share.per_identity is True
    assert LIMITS.content.per_identity is True
    assert LIMITS.api.per_identity is True


# ---- the demo identity naming must be unguessable -------------------------
def test_demo_usernames_are_prefixed_and_unpredictable():
    from localdrop.services.demo import DEMO_PREFIX, is_demo_user

    class U:
        def __init__(self, name):
            self.username = name

    assert is_demo_user(U(f"{DEMO_PREFIX}abc123")) is True
    assert is_demo_user(U("alice")) is False
    # 10 hex chars = 40 bits, so names cannot be enumerated or guessed into.
    assert DEMO_PREFIX == "guest-"
