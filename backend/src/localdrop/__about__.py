"""Canonical version metadata for LocalDrop.

This file is the single source of truth for the application version.
`backend/pyproject.toml` reads it via hatchling's dynamic version hook, so the
wheel, the `localdrop` console script, the PyInstaller binary, the FastAPI app
metadata, the `/api/v1/system/version` response, the Settings "About" panel and
the release tooling all agree by construction.

To cut a release: edit `__version__` below, then run
`python scripts/release.py --tag` (or bump it by hand and open a PR). CI's
`version-check` job fails if any other place disagrees.
"""

from __future__ import annotations

__all__ = ["__version__", "VERSION", "APP_NAME", "APP_SLUG", "APP_ID", "HOMEPAGE", "USER_AGENT"]

__version__ = "1.1.0"

#: Numeric form, e.g. "1.1.0" -> (1, 1, 0). Kept derived so it can never drift.
VERSION: tuple[int, ...] = tuple(int(p) for p in __version__.split("."))

APP_NAME = "LocalDrop"
APP_SLUG = "localdrop"
#: Reverse-DNS identifier used for macOS launchd labels and Windows install paths.
APP_ID = "io.github.abhisubedi.localdrop"

HOMEPAGE = "https://github.com/Abhi-Subedi/LocalDrop"
ISSUES = "https://github.com/Abhi-Subedi/LocalDrop/issues"
SECURITY = "https://github.com/Abhi-Subedi/LocalDrop/security/advisories"

USER_AGENT = f"{APP_SLUG}/{__version__} (+{HOMEPAGE})"
