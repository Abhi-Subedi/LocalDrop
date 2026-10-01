"""Universal LocalDrop entrypoint: `localdrop` / `python -m localdrop.launcher`.

Used by every install method (Windows exe, pip install, systemd, launchd,
Homebrew). Responsibilities, in order:

1. Resolve and create the data dir (default: per-OS user data location).
2. Generate and persist a secret key on first run.
3. If LOCALDROP_DATABASE_URL is not configured, start an embedded PostgreSQL
   cluster inside the data dir (embedded_pg.py).
4. Run database migrations.
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


def _default_data_dir() -> Path:
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
    return Path(__file__).resolve().parents[2] / rel


def _ensure_secret(data_dir: Path) -> str:
    key_file = data_dir / "secret.key"
    if not key_file.exists():
        key_file.write_text(secrets.token_hex(32), encoding="ascii")
        try:
            os.chmod(key_file, 0o600)
        except OSError:
            pass
    return key_file.read_text(encoding="ascii").strip()


def _migrate() -> None:
    from alembic import command
    from alembic.config import Config as AlembicConfig

    cfg = AlembicConfig()
    cfg.set_main_option("script_location", str(_bundled("migrations")))
    command.upgrade(cfg, "head")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="localdrop", description="Run the LocalDrop server.")
    parser.add_argument("--port", type=int, default=int(os.environ.get("LOCALDROP_PORT", "8080")))
    parser.add_argument("--data-dir", default=os.environ.get("LOCALDROP_DATA_DIR"))
    parser.add_argument("--pg-port", type=int, default=5439,
                        help="port for the embedded PostgreSQL cluster (if used)")
    parser.add_argument("--no-browser", action="store_true", help="do not open the web UI on start")
    parser.add_argument("--version", action="version", version=f"LocalDrop {os.environ.get('LOCALDROP_VERSION', '1.1.0')}")
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir or _default_data_dir()).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ["LOCALDROP_DATA_DIR"] = str(data_dir)
    os.environ.setdefault("LOCALDROP_SECRET_KEY", _ensure_secret(data_dir))
    os.environ.setdefault("LOCALDROP_LOG_FORMAT", "dev")
    os.environ["LOCALDROP_PORT"] = str(args.port)

    pg = None
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

    from localdrop.main import create_app

    import uvicorn

    settings_port = args.port
    app = create_app()
    if not args.no_browser:
        threading.Timer(2.0, webbrowser.open, [f"http://127.0.0.1:{settings_port}"]).start()

    server = uvicorn.Server(uvicorn.Config(
        app, host="0.0.0.0", port=settings_port, loop="asyncio", access_log=False,
    ))
    if sys.platform == "win32":
        # psycopg async requires the selector loop; pin it explicitly rather
        # than relying on the deprecated policy mechanism.
        asyncio.run(server.serve(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(server.serve())


if __name__ == "__main__":
    main()
