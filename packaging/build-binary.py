#!/usr/bin/env python3
"""Build the frozen LocalDrop binary for the *current* platform.

PyInstaller cannot cross-compile: this script builds for whatever host it runs
on, and .github/workflows/release.yml runs it on one runner per target. For a
local smoke build:

    python packaging/build-binary.py                # default layout for this OS
    python packaging/build-binary.py --onefile      # force a single file
    python packaging/build-binary.py --outdir dist  # somewhere else

It verifies the artefact afterwards (see verify_artifact) so a build that
produces a binary which cannot find its SPA or its migrations fails here rather
than in a user's install directory.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND = REPO_ROOT / "backend"
PKG = BACKEND / "src" / "localdrop"
SPEC = REPO_ROOT / "packaging" / "pyinstaller" / "localdrop.spec"
RELEASE_DIST = REPO_ROOT / "dist"


def canonical_version() -> str:
    m = re.search(
        r'^__version__\s*=\s*"([^"]+)"',
        (PKG / "__about__.py").read_text(encoding="utf-8"),
        re.M,
    )
    if not m:
        sys.exit("build-binary: no __version__ found")
    return m.group(1)


def ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("build-binary: installing PyInstaller…", flush=True)
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "pyinstaller>=6.10"]
        )


def platform_slug() -> str:
    import platform

    machine = platform.machine().lower()
    if sys.platform == "win32":
        return "windows-x64" if machine in ("amd64", "x86_64") else f"windows-{machine}"
    if sys.platform == "darwin":
        return "macos-arm64" if machine in ("arm64", "aarch64") else "macos-x64"
    if machine in ("aarch64", "arm64"):
        return "linux-arm64"
    if machine.startswith("armv7"):
        return "linux-armv7"
    return "linux-x64"


def build(outdir: Path, onefile: bool | None) -> Path:
    ensure_pyinstaller()
    version = canonical_version()
    if not (PKG / "static" / "index.html").exists():
        sys.exit(
            "build-binary: backend/src/localdrop/static/index.html is missing.\n"
            "               Build the web UI first:  cd frontend && npm ci && npm run build"
        )

    env = dict(os.environ)
    env.pop("LOCALDROP_ONEFILE", None)
    env.pop("LOCALDROP_ONEDIR", None)
    if onefile is True:
        env["LOCALDROP_ONEFILE"] = "1"
    elif onefile is False:
        env["LOCALDROP_ONEDIR"] = "1"

    workdir = outdir / "build"
    if workdir.exists():
        shutil.rmtree(workdir)
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"build-binary: {platform_slug()} v{version} -> {outdir}", flush=True)
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--distpath",
            str(outdir),
            "--workpath",
            str(workdir),
            str(SPEC),
        ],
        env=env,
        cwd=str(BACKEND),
    )
    return outdir


def verify_artifact(outdir: Path, version: str) -> Path:
    """Prove the artefact is self-sufficient before it is published.

    A PyInstaller bundle that is missing its SPA or migrations still *runs* --
    it just serves a broken app and crashes on first migration. Catching that
    here is the difference between a bad release and a bad afternoon.
    """
    if sys.platform == "win32":
        exe = outdir / "localdrop" / "localdrop.exe"
    elif sys.platform == "darwin":
        exe = outdir / "localdrop"
    else:
        exe = outdir / "localdrop"
    if not exe.exists():
        candidates = sorted(outdir.glob("**/localdrop*"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            sys.exit(f"build-binary: no artefact produced in {outdir}")
        exe = candidates[0]

    print(f"build-binary: verifying {exe.relative_to(outdir)} …", flush=True)
    # `--check` exercises interpreter start-up, every bundled resource, the
    # heavy C-extension imports (psycopg, argon2, Pillow) and the app factory —
    # all without a database or a data dir. `--version` alone would only prove
    # the bootloader works.
    probe = subprocess.run([str(exe), "--check"], capture_output=True, text=True, timeout=300)
    output = (probe.stdout + probe.stderr).strip()
    if probe.returncode != 0 or version not in output:
        sys.exit(
            f"build-binary: self-check failed (rc={probe.returncode}), expected {version!r}\n"
            f"               output: {output[-1500:]}"
        )
    failures = [line for line in output.splitlines() if "FAIL" in line]
    if failures:
        sys.exit("build-binary: self-check reported failures:\n  " + "\n  ".join(failures))
    print(f"build-binary: OK — self-check passed ({version})", flush=True)
    return exe


def make_zip(exe: Path, outdir: Path, version: str, slug: str) -> Path:
    """Portable archive: a .zip on Windows, a .tar.gz everywhere else."""
    if slug.startswith("windows"):
        target = outdir / f"LocalDrop-{version}-{slug}.zip"
        if target.exists():
            target.unlink()
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(exe.parent.rglob("*")):
                if p.is_file() and "__pycache__" not in p.parts:
                    z.write(p, Path(exe.parent.name) / p.relative_to(exe.parent))
    else:
        import tarfile

        target = outdir / f"localdrop-{version}-{slug}.tar.gz"
        if target.exists():
            target.unlink()
        root = exe.parent if exe.is_dir() else None
        with tarfile.open(target, "w:gz") as t:
            if root is not None:
                for p in sorted(root.rglob("*")):
                    if p.is_file():
                        t.add(p, arcname=f"localdrop-{version}/{p.relative_to(root)}")
            else:
                t.add(exe, arcname=f"localdrop-{version}/{exe.name}")
    print(f"build-binary: archive {target.name} ({target.stat().st_size // 1024} KiB)", flush=True)
    return target


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the LocalDrop server binary.")
    ap.add_argument("--outdir", type=Path, default=None, help="output dir (default: dist/release)")
    ap.add_argument("--onefile", action="store_true", help="force a single-file bundle")
    ap.add_argument("--onedir", action="store_true", help="force a directory bundle")
    ap.add_argument("--zip", action="store_true", help="also emit a portable archive")
    ap.add_argument("--skip-verify", action="store_true", help="do not smoke-test the artefact")
    args = ap.parse_args(argv)
    if args.onefile and args.onedir:
        ap.error("--onefile and --onedir are mutually exclusive")

    version = canonical_version()
    slug = platform_slug()
    outdir = (args.outdir or (RELEASE_DIST / "release")).resolve()

    outdir = build(outdir, True if args.onefile else (False if args.onedir else None))
    exe = verify_artifact(outdir, version) if not args.skip_verify else None
    if args.zip and exe is not None:
        make_zip(exe, outdir, version, slug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
