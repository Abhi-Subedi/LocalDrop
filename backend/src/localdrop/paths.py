"""One resolver for read-only bundled resources.

There used to be two, and they disagreed:

* ``launcher._bundled()`` resolved a frozen resource as ``sys._MEIPASS / rel``.
* ``main.SPA_DIST`` was ``Path(__file__).resolve().parent / "static"``.

In a PyInstaller build ``__file__`` for a bundled module is
``<bundle>/localdrop/main.py``, so the second one looked for
``<bundle>/localdrop/static`` while the files are shipped at ``<bundle>/static``.
``SPA_DIST.exists()`` was therefore always False in a frozen build, so
``create_app()`` never registered the SPA catch-all and ``GET /`` returned 404
- every published binary served the API and nothing else.

``localdrop --check`` could not catch it because it used the *first* resolver,
which was correct. A verifier and the code it verifies must agree by
construction, not by luck, so there is now exactly one implementation and both
callers use it.
"""

from __future__ import annotations

import sys
from pathlib import Path

#: The directory holding the ``localdrop`` package's own files.
PACKAGE_DIR = Path(__file__).resolve().parent


def is_frozen() -> bool:
    """True inside a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    """Where frozen read-only data lives.

    PyInstaller extracts a one-file bundle to a temporary directory and points
    ``sys._MEIPASS`` at it; for a one-directory build it points at ``_internal``.
    Data files are placed at its root, *not* inside a ``localdrop/`` subfolder.
    """
    return Path(getattr(sys, "_MEIPASS", "."))


def resource(rel: str) -> Path:
    """Resolve a read-only bundled resource such as ``static/index.html``.

    Frozen: ``<bundle>/rel``. Installed or running from source:
    ``<package>/rel``.
    """
    if is_frozen():
        return bundle_root() / rel
    return PACKAGE_DIR / rel


def spa_dist() -> Path:
    """The built single-page app.

    Returned whether or not it exists, so callers can report the real path in
    an error instead of silently degrading to a 404.
    """
    return resource("static")
