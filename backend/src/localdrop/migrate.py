"""Programmatic database migrations.

Every install method funnels through `upgrade()`: the launcher, the Docker
entrypoint, the systemd unit, the launchd plist and the PyInstaller binary.
Calling Alembic programmatically (rather than shelling out to `alembic
upgrade head` and relying on a CWD-relative alembic.ini) is what makes the
frozen binary and a pip-installed wheel work from any working directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent


def migrations_dir() -> Path:
    """Absolute path to the packaged Alembic environment."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", ".")) / "migrations"
    return _PACKAGE_DIR / "migrations"


def make_config() -> object:
    """Build an Alembic Config pointing at the packaged migrations."""
    from alembic.config import Config as AlembicConfig

    cfg = AlembicConfig()
    cfg.set_main_option("script_location", str(migrations_dir()))
    return cfg


def upgrade(revision: str = "head") -> None:
    """Apply migrations up to `revision` (default: head)."""
    from alembic import command

    command.upgrade(make_config(), revision)  # type: ignore[arg-type]


def current() -> None:
    """Print the database's current revision — used by `localdrop-migrate`."""
    from alembic import command

    command.current(make_config())  # type: ignore[arg-type]


def main(argv: list[str] | None = None) -> int:
    """Console entrypoint: `localdrop-migrate [head|<revision>]`."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("-h", "--help"):
        print(
            "usage: localdrop-migrate [head|<revision>]\n\n"
            "Applies LocalDrop database migrations. Defaults to `head`."
        )
        return 0
    target = argv[0] if argv else "head"
    try:
        upgrade(target)
    except Exception as exc:  # noqa: BLE001 - surfaced verbatim to the operator
        print(f"localdrop-migrate: FAILED at '{target}': {exc}", file=sys.stderr)
        return 1
    print(f"localdrop-migrate: schema is at '{target}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
