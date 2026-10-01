# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the frozen LocalDrop server.

One spec, three platforms. PyInstaller cannot cross-compile, so CI runs this
file on a native runner per target (see .github/workflows/release.yml):

    Linux   x86_64 / aarch64   -> onefile  dist/localdrop
    macOS   x86_64 / arm64     -> onefile  dist/localdrop   (+ .app bundle wrapper)
    Windows x86_64             -> onedir   dist/localdrop/localdrop.exe

Why onefile on Unix and onedir on Windows:

* onefile  - a single self-extracting file is what `curl | sh`, the tarball and
             the Homebrew formula want. Startup cost (~1 s) is irrelevant for a
             server that stays up.
* onedir   - a onefile Windows build unpacks to %TEMP% on *every* start, which
             antivirus software flags and which makes the Inno Setup installer
             slow and fragile. A server that runs continuously should not pay a
             per-boot penalty, so Windows ships a directory (zipped for portable
             use, wrapped by the installer for normal use).

Set LOCALDROP_ONEFILE=1 to force onefile everywhere, LOCALDROP_ONEDIR=1 to force
onedir. Nothing else should need editing — the version is read from __about__.py.
"""

import os
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

# spec files execute with CWD == the directory holding this file
PACKAGING_DIR = Path(os.path.abspath(SPECPATH))  # noqa: F821
REPO_ROOT = PACKAGING_DIR.parent.parent
BACKEND = REPO_ROOT / "backend"
PKG = BACKEND / "src" / "localdrop"

# --- version, straight from the single source of truth ---------------------
_about = (PKG / "__about__.py").read_text(encoding="utf-8")
VERSION = re.search(r'^__version__\s*=\s*"([^"]+)"', _about, re.M).group(1)
APP_NAME = re.search(r'^APP_NAME\s*=\s*"([^"]+)"', _about, re.M).group(1)
HOMEPAGE = re.search(r'^HOMEPAGE\s*=\s*"([^"]+)"', _about, re.M).group(1)

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"

# One dir on Windows unless explicitly overridden; one file everywhere else.
if os.environ.get("LOCALDROP_ONEDIR") == "1":
    ONEFILE = False
elif os.environ.get("LOCALDROP_ONEFILE") == "1":
    ONEFILE = True
else:
    ONEFILE = not IS_WINDOWS

# --- read-only assets that must ship inside the bundle ---------------------
# Both live inside the package now, so `pip install` and the frozen binary
# resolve them through the same code path (launcher._bundled).
datas = [
    (str(PKG / "static"), "static"),
    (str(PKG / "migrations"), "migrations"),
]

# --- imports PyInstaller's static analysis cannot see ----------------------
hiddenimports: list[str] = [
    # console entrypoints are resolved dynamically by the launcher
    "localdrop.launcher",
    "localdrop.migrate",
    "localdrop.embedded_pg",    # uvicorn picks loop/protocol classes through a Config string
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    # alembic resolves the env.py / script.py.mako templates at runtime
    "alembic.runtime.migration",
    "alembic.op",
    # structlog ships optional processors selected by string name
    "structlog.processors",
    "structlog.dev",
    "structlog.stdlib",
]
# Pillow loads backends by name; qrcode picks a writer by feature check.
for _pkg in ("PIL", "qrcode", "qrcode.image.pil"):
    hiddenimports += collect_submodules(_pkg)
# prometheus_client ships collectors for frameworks that may not be installed;
# collecting the whole tree emits a warning per absent framework.
hiddenimports += [
    m
    for m in collect_submodules("prometheus_client")
    if not m.endswith((".twisted", ".tornado", ".sanic", ".aiohttp", ".asgi", ".flask", ".django"))
]

binaries = []
# psycopg 3 "binary" and argon2-cffi are compiled extensions behind ctypes/import.
for _pkg in ("psycopg_binary", "argon2"):
    binaries += collect_dynamic_libs(_pkg)
# psycopg ships a pure-python .pyi/data bundle too.
datas += collect_data_files("psycopg", include_py_files=False)

a = Analysis(
    [str(PACKAGING_DIR / "entrypoint.py")],
    pathex=[str(BACKEND / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # Nothing in the build environment should leak in: the bundle must run on
    # a clean host with only a compatible libc (musl/gnu) available.
    excludes=[
        "tkinter",
        "unittest",
        "pydoc_data",
        "test",
        # dev/test tooling that is present in the build venv but must never
        # reach a user install (mypy alone is ~0.7 MiB of dead weight)
        "pytest",
        "pytest_asyncio",
        "httpx",
        "asgi_lifespan",
        "mypy",
        "mypy_extensions",
        "ruff",
        "PyInstaller",
        "IPython",
        "notebook",
        "matplotlib",
        "watchfiles",  # uvicorn's --reload dependency, unused in production
        "numpy",  # Pillow is used for thumbnailing only, not for arrays
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)  # noqa: F821

exe_common = {
    "console": True,  # it is a server: stdout/stderr are the log
    "disable_windowed_traceback": False,
    "name": "localdrop",
    "debug": False,
    "bootloader_ignore_signals": False,
    "strip": IS_MACOS,
    "upx": False,  # UPX-packed binaries trip many antivirus heuristics
    "version": None,
    "icon": None,
    "env": {"LOCALDROP_VERSION_PLACEHOLDER": VERSION},
}

if ONEFILE:
    exe = EXE(  # noqa: F821
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        runtime_runtime_dependencies=False if hasattr(sys, "frozen") else None,
        **exe_common,
        runtime_tmpdir=None,
    )
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **exe_common)
    coll = COLLECT(  # noqa: F821
        exe,
        a.binaries,
        a.datas,
        strip=IS_MACOS,
        upx=False,
        name="localdrop",
    )

# macOS: emit a .app bundle so double-clicking works and the window/icon are
# sane. The binary inside is still a plain CLI server.
if IS_MACOS and ONEFILE:
    app = BUNDLE(  # noqa: F821
        exe,
        name=f"{APP_NAME}.app",
        icon=None,
        bundle_identifier="io.github.abhisubedi.localdrop",
        version=VERSION,
        info_plist={
            "CFBundleName": APP_NAME,
            "CFBundleDisplayName": APP_NAME,
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
