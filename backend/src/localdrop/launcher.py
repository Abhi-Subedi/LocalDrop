"""Universal LocalDrop entrypoint: `localdrop` / `python -m localdrop.launcher`.

Used by every install method (Windows exe, pip, systemd, launchd, Homebrew).
Responsibilities, in order:

1. Resolve and create the data dir (default: per-OS user data location).
2. Generate and persist a secret key on first run.
3. If LOCALDROP_DATABASE_URL is not configured, start an embedded PostgreSQL
   cluster inside the data dir (embedded_pg.py).
4. Run database migrations (migrate.py).
5. Serve API + SPA on 0.0.0.0 and print LAN URLs + the first-run setup token.

Existing deployments (Docker, systemd with their own Postgres) just set
LOCALDROP_DATABASE_URL and the embedded cluster is never touched.
"""

from __future__ import annotations

import argparse
import asyncio
import atexit
import os
import secrets
import sys
import threading
import webbrowser
from pathlib import Path

from .__about__ import __version__

#: Frozen builds ship read-only data next to the executable inside _MEIPASS.
#: Installed builds (wheel/venv) have it inside the package directory. Both are
#: the same place now, so this is just a dev-convenience fallback.
_PACKAGE_DIR = Path(__file__).resolve().parent


def _default_data_dir() -> Path:
    """Where files and metadata live when LOCALDROP_DATA_DIR is not set.

    Native service installs (systemd unit, launchd plist, the Windows service)
    set LOCALDROP_DATA_DIR explicitly to /var/lib/localdrop or the platform
    equivalent. This default is for the "just run the binary" case: it must
    resolve to a path the *invoking* user can write.
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "LocalDrop"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "LocalDrop"
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "localdrop"


def _bundled(rel: str) -> Path:
    """Locate read-only resources (static/, migrations/) in dev and frozen builds."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", ".")) / rel
    return _PACKAGE_DIR / rel


def _ensure_secret(data_dir: Path) -> str:
    key_file = data_dir / "secret.key"
    if not key_file.exists():
        key_file.write_text(secrets.token_hex(32), encoding="ascii")
        try:
            os.chmod(key_file, 0o600)
        except OSError:
            pass
    return key_file.read_text(encoding="ascii").strip()


_ENV_TEMPLATE = """\
# LocalDrop configuration.
# Generated on first run. Full reference: docs/CONFIGURATION.md
# This file is read by launchd on macOS; on other platforms export these as
# environment variables or use the service unit's own configuration file.

LOCALDROP_SECRET_KEY={secret}
LOCALDROP_PORT={port}
LOCALDROP_HOST=0.0.0.0
LOCALDROP_LOG_FORMAT=console
LOCALDROP_LOG_LEVEL=INFO

# The address other devices on your LAN use, so share links and the QR code
# point somewhere real. Leave empty to derive it per request.
# LOCALDROP_PUBLIC_URL=http://192.168.1.20:{port}

# Uncomment ONLY if you run your own PostgreSQL. When unset, LocalDrop manages
# an embedded cluster inside the data directory.
# LOCALDROP_DATABASE_URL=postgresql+psycopg://localdrop:secret@127.0.0.1:5432/localdrop
"""


def _load_env_file(env_file: Path) -> None:
    """Apply KEY=VALUE pairs from a localdrop.env, never overwriting the real
    environment. Lets `localdrop` be configured the same way on every platform
    instead of only through a service manager's EnvironmentFile directive."""

    def _read_env_file_inner() -> None:
        if not env_file.is_file():
            return
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            if key.startswith("LOCALDROP_") and value and key not in os.environ:
                os.environ[key] = value

    _read_env_file_inner()


def _write_default_env(data_dir: Path, port: int = 8080) -> Path:
    """Create a commented localdrop.env next to the data, with a fresh key."""
    env_file = data_dir / "localdrop.env"
    if env_file.exists():
        return env_file
    env_file.write_text(
        _ENV_TEMPLATE.format(secret=_ensure_secret(data_dir), port=port), encoding="utf-8"
    )
    try:
        os.chmod(env_file, 0o600)  # it holds the secret key
    except OSError:
        pass
    return env_file


def _migrate() -> None:
    from .migrate import upgrade

    upgrade()


def _self_check() -> int:
    """Verify a build is self-sufficient, then exit. No database, no data dir.

    Run against the frozen binary before publishing a release, and available to
    users as `localdrop --check` to answer "is my install broken?" without
    waiting on a database that may itself be the thing that is broken.
    """
    import importlib

    problems: list[str] = []
    frozen = bool(getattr(sys, "frozen", False))
    bundle = str(Path(getattr(sys, "_MEIPASS", "."))) if frozen else str(_PACKAGE_DIR)

    print(f"  LocalDrop {__version__}  (python {sys.version.split()[0]}, {sys.platform})")
    print(f"  frozen={frozen}  bundle={bundle}")

    for rel in ("static/index.html", "migrations/env.py", "migrations/script.py.mako"):
        path = _bundled(rel)
        ok = path.is_file()
        print(f"  {'ok  ' if ok else 'FAIL'}  {rel}")
        if not ok:
            problems.append(f"missing bundled resource: {rel} (looked in {path})")

    versions_dir = _bundled("migrations") / "versions"
    revisions = sorted(p.name for p in versions_dir.glob("*.py")) if versions_dir.is_dir() else []
    print(f"  {'ok  ' if revisions else 'FAIL'}  migrations: {len(revisions)} revision(s)")
    if not revisions:
        problems.append("no migration revisions found in the bundle")

    for mod in ("fastapi", "uvicorn", "sqlalchemy", "psycopg", "alembic", "argon2", "PIL"):
        try:
            importlib.import_module(mod)
            print(f"  ok    import {mod}")
        except Exception as exc:
            print(f"  FAIL  import {mod}: {exc}")
            problems.append(f"cannot import {mod}: {exc}")

    try:
        from .main import create_app

        print(f"  ok    app factory ({create_app.__name__}) importable")
    except Exception as exc:
        print(f"  FAIL  app factory: {exc}")
        problems.append(f"cannot import the app factory: {exc}")

    if problems:
        print(f"\n  FAILED: {len(problems)} problem(s)")
        return 1
    print("\n  All checks passed.")
    return 0


def _print_setup_token() -> int:
    """Print (or re-issue) the one-time setup token and exit.

    A headless install cannot see the server's console: it is a systemd unit,
    a launchd job, or a service on Windows. This gives an operator a way to
    finish onboarding without digging through logs, and it re-issues the token
    if the previous one expired (they are single-use and last 15 minutes).
    """
    import asyncio

    from .db import SessionFactory, dispose_engine, init_engine
    from .services import accounts

    init_engine()
    if SessionFactory is None:
        print("  No database configured; set LOCALDROP_DATABASE_URL or start the server once.")
        return 1

    async def _run() -> str | None:
        try:
            async with SessionFactory() as db:
                if not await accounts.onboarding_required(db):
                    return None
                token = await accounts.get_or_issue_setup_token(db)
                await db.commit()
                return token
        finally:
            await dispose_engine()

    try:
        token = asyncio.run(_run())
    except Exception as exc:
        print(f"  Could not reach the database: {exc}")
        return 1

    if not token:
        print("  Onboarding is already complete - no setup token needed.")
        print("  Sign in normally, or reset the owner password from the server console.")
        return 0
    print("\n  First-run setup token (valid 15 min, single use):")
    print(f"    {token}")
    print("\n  Open the web UI and paste it in to create your owner account.\n")
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="localdrop",
        description="Run the LocalDrop server.",
        epilog=(
            "First run: the server prints a one-time setup token. Open the printed "
            "URL, paste the token, and create your owner account."
        ),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("LOCALDROP_PORT", "8080")),
        help="TCP port to listen on (default: 8080)",
    )
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("LOCALDROP_DATA_DIR"),
        help=f"storage + embedded database directory (default: {_default_data_dir()})",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("LOCALDROP_HOST", "0.0.0.0"),
        help="bind address; 0.0.0.0 serves the LAN (default), 127.0.0.1 is loopback-only",
    )
    parser.add_argument(
        "--pg-port",
        type=int,
        default=int(os.environ.get("LOCALDROP_PG_PORT", "5439")),
        help="port for the embedded PostgreSQL cluster (if used)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="do not open the web UI on start",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify this install is self-sufficient, then exit (needs no database)",
    )
    parser.add_argument(
        "--setup-token",
        action="store_true",
        help="print the one-time setup token for first-run onboarding, then exit",
    )
    parser.add_argument(
        "--install-service",
        action="store_true",
        help="start LocalDrop at login (macOS LaunchAgent) and exit",
    )
    parser.add_argument(
        "--uninstall-service",
        action="store_true",
        help="remove the login service and exit",
    )
    parser.add_argument(
        "--service-status",
        action="store_true",
        help="report whether the login service is installed and loaded",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"LocalDrop {__version__}",
    )
    args = parser.parse_args(argv)

    if args.check:
        raise SystemExit(_self_check())

    if args.install_service or args.uninstall_service or args.service_status:
        from . import service

        if args.install_service:
            data_dir = Path(args.data_dir or _default_data_dir()).resolve()
            data_dir.mkdir(parents=True, exist_ok=True)
            env_file = data_dir / "localdrop.env"
            if not env_file.exists():
                _write_default_env(data_dir)
            print(f"  {service.install(service.executable_path(), data_dir, env_file)}")
            print(f"  Logs: {data_dir / 'localdrop.log'}")
            raise SystemExit(0)
        if args.uninstall_service:
            print(f"  {service.uninstall()}")
            raise SystemExit(0)
        state = "loaded" if service.loaded() else "installed, not loaded"
        print(f"  {service.LAUNCHD_LABEL}: {'not installed' if service.uninstalled() else state}")
        raise SystemExit(0)

    if args.setup_token:
        data_dir = Path(args.data_dir or _default_data_dir()).resolve()
        data_dir.mkdir(parents=True, exist_ok=True)
        os.environ["LOCALDROP_DATA_DIR"] = str(data_dir)
        _load_env_file(data_dir / "localdrop.env")
        os.environ.setdefault("LOCALDROP_SECRET_KEY", _ensure_secret(data_dir))
        os.environ.setdefault("LOCALDROP_LOG_FORMAT", "console")
        if not os.environ.get("LOCALDROP_DATABASE_URL"):
            from .embedded_pg import EmbeddedPostgres

            pg = EmbeddedPostgres(data_dir / "pg", port=args.pg_port)
            pg.ensure_binaries()
            pg.start()
            atexit.register(pg.stop)
            os.environ["LOCALDROP_DATABASE_URL"] = pg.url()
        raise SystemExit(_print_setup_token())

    data_dir = Path(args.data_dir or _default_data_dir()).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ["LOCALDROP_DATA_DIR"] = str(data_dir)
    # A localdrop.env beside the data lets native installs be configured without
    # editing a service unit. Real environment variables always win, so a
    # systemd/launchd EnvironmentFile still overrides this file.
    _load_env_file(data_dir / "localdrop.env")
    os.environ.setdefault("LOCALDROP_SECRET_KEY", _ensure_secret(data_dir))
    os.environ.setdefault("LOCALDROP_LOG_FORMAT", "console")
    os.environ["LOCALDROP_PORT"] = str(args.port)

    if not os.environ.get("LOCALDROP_DATABASE_URL"):
        from .embedded_pg import EmbeddedPostgres

        pg = EmbeddedPostgres(data_dir / "pg", port=args.pg_port)
        print(f"  No LOCALDROP_DATABASE_URL set — using embedded PostgreSQL in {data_dir / 'pg'}")
        pg.ensure_binaries()
        pg.start()
        atexit.register(pg.stop)
        os.environ["LOCALDROP_DATABASE_URL"] = pg.url()

    print("  Running database migrations…")
    _migrate()

    import uvicorn

    from .main import create_app

    app = create_app()
    if not args.no_browser:
        threading.Timer(2.0, webbrowser.open, [f"http://127.0.0.1:{args.port}"]).start()

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=args.host,
            port=args.port,
            loop="asyncio",
            access_log=False,
        )
    )
    if sys.platform == "win32":
        # psycopg async requires the selector loop; pin it explicitly rather
        # than relying on the deprecated policy mechanism.
        asyncio.run(server.serve(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(server.serve())


if __name__ == "__main__":
    main()
