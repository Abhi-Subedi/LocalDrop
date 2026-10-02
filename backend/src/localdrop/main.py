"""LocalDrop application factory (BC-1: one process serves API + SPA + jobs)."""

from __future__ import annotations

import asyncio
import contextlib
import socket
import sys
import uuid as uuid_mod
from contextlib import asynccontextmanager

# Windows dev only: psycopg async requires the selector event loop. Linux
# (production) is unaffected.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from . import errors as err
from .__about__ import __version__
from .config import Settings, get_settings
from .db import dispose_engine, init_engine  # noqa: F401 (init used below)
from .logging import bind_request_id, get_logger, setup_logging
from .paths import spa_dist
from .storage import Storage, set_storage

log = get_logger(__name__)

# The built SPA. Resolved through paths.spa_dist() rather than
# `Path(__file__).parent / "static"`: inside a PyInstaller bundle __file__ is
# <bundle>/localdrop/main.py, so that expression pointed at
# <bundle>/localdrop/static while the files ship at <bundle>/static. The result
# was SPA_DIST.exists() == False in every published binary, so the catch-all
# route was never registered and GET / returned 404 - the API worked and the
# web UI did not. `localdrop --check` missed it because it already used the
# correct resolver; there is now only one.
SPA_DIST = spa_dist()


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Request id + CSRF + security headers (spec 06, BC-12 headers)."""

    SECURITY_HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "same-origin",
        "X-Frame-Options": "DENY",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    }

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or f"req_{uuid_mod.uuid4().hex[:16]}"
        bind_request_id(request_id)
        request.state.request_id = request_id

        response = await call_next(request)
        for k, v in self.SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        if request.url.path.startswith(("/api/", "/metrics")):
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'none'; frame-ancestors 'none'",
            )
        response.headers["X-Request-ID"] = request_id
        return response


async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    rid = getattr(request.state, "request_id", "unknown")
    detail = "; ".join(
        f"{'.'.join(str(x) for x in e['loc'][1:])}: {e['msg']}" for e in exc.errors()[:5]
    )
    return JSONResponse(
        {
            "type": "https://localdrop.dev/errors/validation",
            "title": "Validation Error",
            "status": 422,
            "detail": detail,
            "request_id": rid,
        },
        status_code=422,
        media_type="application/problem+json",
    )


async def generic_handler(request: Request, exc: Exception) -> JSONResponse:
    rid = getattr(request.state, "request_id", None)
    log.error(
        "unhandled_exception", error=str(exc), type=type(exc).__name__, request_id=rid, exc_info=exc
    )
    return err.problem_response(500, "internal", "Internal Server Error", None, rid)


# ---- background job loop (ADR-003: in-process scheduler) ----


async def job_loop(app: FastAPI) -> None:

    from .db import SessionFactory
    from .services.jobs import cleanup_pass, generate_thumbnails
    from .services.uploads import hash_pending_blobs
    from .storage import get_storage

    s = get_settings()
    tick = 0
    while True:
        try:
            await asyncio.sleep(10)
            if SessionFactory is None:
                continue
            storage: Storage = get_storage()
            async with SessionFactory() as db:
                await hash_pending_blobs(db, storage, max_n=5)
                if tick % 3 == 0:  # every 30s
                    await generate_thumbnails(db, storage, file_id=None, max_n=4)
                if tick % 6 == 0 and s.demo_mode:  # every minute
                    from .services import demo

                    removed = await demo.purge_expired(db)
                    if removed:
                        log.info("demo_purged", accounts=removed)
                if tick % 60 == 0:  # every 10 min
                    await cleanup_pass(db, storage)
                await db.commit()
            tick += 1
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.error("job_loop_error", error=str(e), type=type(e).__name__)


def detect_lan_ips() -> list[str]:
    """Enumerate plausible LAN IPv4s (best effort; spec 03 §7)."""
    ips: set[str] = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = str(info[4][0])
            if not ip.startswith("127."):
                ips.add(ip)
    except OSError:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("10.254.254.254", 1))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return sorted(ips)


def print_lan_banner(settings: Settings, port: int) -> None:
    ips = detect_lan_ips()
    urls = [f"http://{ip}:{port}" for ip in ips] or [f"http://localhost:{port}"]
    try:
        import qrcode

        qr = qrcode.QRCode(border=1)
        qr.add_data(urls[0])
        qr.print_ascii(invert=True)
    except Exception as exc:
        # A missing/broken qrcode install must never stop the server booting;
        # the URL is printed on the next line regardless.
        log.debug("qr_banner_unavailable", error=str(exc))
    log.info("localdrop_ready", urls=urls, data_dir=str(settings.data_dir))
    print("\n  LocalDrop is running:")
    for u in urls:
        print(f"    {u}")
    print("  Scan the QR above from your phone, or open a URL.\n")


async def maybe_print_setup_token() -> None:
    """First-run onboarding: print the single-use setup token to stdout so
    headless installs (docker logs) can complete onboarding. Shares its value
    with GET /api/v1/setup/token — whichever issues first wins."""
    try:
        from .db import SessionFactory
        from .services import accounts

        if SessionFactory is None:
            return
        async with SessionFactory() as db:
            if not await accounts.onboarding_required(db):
                return
            token = await accounts.get_or_issue_setup_token(db)
            await db.commit()
        if token:
            print("\n  First-run setup token (valid 15 min, single use):")
            print(f"    {token}")
            print("  Open the web UI and enter it to create your owner account.\n")
    except Exception as e:
        log.warning("setup_token_unavailable", error=str(e), type=type(e).__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or get_settings()
    setup_logging()
    set_storage(Storage(s.data_dir))
    init_engine()  # before lifespan so module-level importers see a ready factory

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = s
        task = asyncio.create_task(job_loop(app))
        if not s.dev_mode:
            print_lan_banner(s, s.port)
        await maybe_print_setup_token()
        yield
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await dispose_engine()

    app = FastAPI(
        title="LocalDrop",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs" if s.dev_mode else None,
        openapi_url="/api/openapi.json" if s.dev_mode else None,
        redirect_slashes=False,
    )
    app.state.settings = s

    # routers
    from .api import auth as auth_api
    from .api import files as files_api
    from .api import shares as shares_api
    from .api import system as system_api
    from .api import uploads as uploads_api

    app.include_router(system_api.router, prefix="/api/v1")
    api = system_api.router
    api.include_router(auth_api.router, prefix="/api/v1")
    api.include_router(files_api.router, prefix="/api/v1")
    api.include_router(uploads_api.router, prefix="/api/v1")
    api.include_router(shares_api.router, prefix="/api/v1")
    api.include_router(shares_api.public, prefix="/api/v1")
    app.include_router(api)  # inner includes already carry /api/v1

    if s.demo_mode:
        # Only mounted in demo mode, so a normal deployment has no demo surface
        # at all rather than a 404 that advertises one.
        from .api import demo as demo_api

        app.include_router(demo_api.router, prefix="/api/v1")
        log.info(
            "demo_mode_enabled",
            ttl_minutes=s.demo_ttl_minutes,
            max_upload_bytes=s.effective_max_upload_bytes(),
        )

    # metrics: authenticated only (spec 05 §2.1 admin-only; V1 single owner).
    # Health probes stay public; point Prometheus at a PAT Bearer token.
    from fastapi import Depends
    from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest

    from .auth import Principal, resolve_principal

    @app.get("/metrics")
    async def metrics(p: Principal = Depends(resolve_principal)) -> JSONResponse:
        return JSONResponse(
            content=generate_latest(REGISTRY).decode(),
            media_type=CONTENT_TYPE_LATEST,
        )

    # error handlers
    app.add_exception_handler(err.Problem, err.problem_handler)  # type: ignore[arg-type]
    # Starlette types add_exception_handler as taking a handler for `Exception`;
    # RequestValidationError is a subclass, so the narrower annotation is fine.
    app.add_exception_handler(RequestValidationError, validation_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, generic_handler)

    app.add_middleware(RequestContextMiddleware)

    # CORS (dev mode only)
    if s.dev_mode and s.cors_origins:
        from fastapi.middleware.cors import CORSMiddleware

        app.add_middleware(
            CORSMiddleware,
            allow_origins=s.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID", "Upload-Offset", "Location"],
        )

    # SPA serving (BC-9): /api/* and /metrics untouched; everything else → SPA
    spa = SPA_DIST
    if not (spa / "index.html").is_file():
        # Previously this was `if spa.exists()`, and a wrong path therefore
        # degraded silently: no catch-all, no /assets mount, and every
        # non-API URL a bare 404 while the API worked fine. A packaging mistake
        # should be loud at startup, not invisible until someone opens the page.
        log.error(
            "the web UI is missing from this build: expected %s. "
            "This is a packaging fault, not a configuration one - the API will "
            "run but the browser interface will 404.",
            spa / "index.html",
        )
    else:
        assets = spa / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str):
            if full_path.startswith("api/") or full_path == "metrics":
                raise err.not_found()
            candidate = (spa / full_path).resolve()
            if candidate.is_file() and candidate.is_relative_to(spa.resolve()):
                return FileResponse(candidate)
            return FileResponse(spa / "index.html")

    return app
