#!/usr/bin/env python3
"""Assert a built release archive contains what its consumers unpack.

Two shipped bugs were invisible to every existing gate, because both were about
archive *contents* and nothing looked:

1. `make_zip()` gated the payload walk on `exe.is_dir()`, which is never true
   because `exe` is a file in both build modes. The Windows zip shipped 3 entries
   instead of 803 and the binary died with
   `Failed to load Python DLL .../_internal/python312.dll`.
2. The archives did not carry LICENSE or README.md, so the Homebrew formula's
   `pkgshare.install "LICENSE"` aborted `brew install` outright.

Run it against whatever was just built:

    python scripts/check_archive_contents.py dist/release
    python scripts/check_archive_contents.py path/to/LocalDrop-1.2.0-linux-x64.tar.gz

Exits non-zero with a specific message naming what is missing. AGPL-3.0 requires
conveying the licence with the binary, so LICENSE is treated as mandatory, not
cosmetic.
"""

from __future__ import annotations

import sys
import tarfile
import zipfile
from pathlib import Path

#: Required in every archive, whatever the platform.
REQUIRED = ("LICENSE", "README.md")

#: The executable, per packaging/build-binary.py platform_slug().
EXECUTABLES = {
    "windows": ("localdrop.exe", "localdrop"),
    "linux": ("localdrop",),
    "macos": ("localdrop",),
}


#: PyInstaller scratch output that must never reach a user. It appears when the
#: one-file tarballs are built by packing the output directory instead of the
#: single executable, which is what 1.1.2 did. Matched against paths outside the
#: payload: `_internal/base_library.zip` is a legitimate part of a one-directory
#: build, so the same filename at a scratch location is not.
BUILD_JUNK = ("PYZ-00.pyz", "Analysis-", "BUNDLE-", "EXE-", "PKG-", "xref-", "warn-", ".toc")


def members(archive: Path) -> list[str]:
    """Archive member paths, with any single top-level directory stripped."""
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as z:
            names = z.namelist()
    else:
        with tarfile.open(archive) as t:
            names = t.getnames()

    roots = {n.split("/", 1)[0] for n in names if "/" in n}
    # A single root directory is the convention every consumer already assumes;
    # Homebrew strips it, install.ps1 expands into it, install.sh searches under it.
    prefix = roots.pop() + "/" if len(roots) == 1 else ""
    out = []
    for n in names:
        out.append(n[len(prefix):] if prefix and n.startswith(prefix) else n)
    return [n for n in out if n and not n.endswith("/")]


def platform_of(archive: Path) -> str:
    name = archive.name.lower()
    for plat in EXECUTABLES:
        if plat in name:
            return plat
    return "unknown"


def check_one(archive: Path) -> list[str]:
    problems: list[str] = []
    found = members(archive)

    for rel in REQUIRED:
        if rel not in found:
            problems.append(f"{archive.name}: missing {rel} (licence must travel with the binary)")

    plat = platform_of(archive)
    if plat == "unknown":
        problems.append(f"{archive.name}: cannot tell which platform this is for")
    elif not any(name in EXECUTABLES[plat] for name in found):
        problems.append(
            f"{archive.name}: no executable; expected one of {', '.join(EXECUTABLES[plat])}"
        )

    # A one-directory build must carry its payload. Detected rather than assumed
    # from the name: the marker is _internal/, which is exactly what the
    # missing-payload bug took away.
    onedir = any(n.startswith("_internal/") for n in found)
    if plat == "windows" and not onedir:
        problems.append(
            f"{archive.name}: the PyInstaller payload (_internal/) is missing - "
            "the binary will fail with 'Failed to load Python DLL'"
        )

    # static/ only exists as a directory in a one-directory build, where it sits
    # inside the payload. A one-file build embeds the SPA in the executable,
    # where no archive listing can see it - that case is covered by running
    # `localdrop --check`, which resolves the SPA through the server's own path
    # logic rather than a second copy of it.
    if onedir and not any(n.startswith("static/") or "/static/" in n for n in found):
        problems.append(
            f"{archive.name}: no static/ directory beside the payload - "
            "the web UI will 404"
        )

    junk = [
        n
        for n in found
        if not n.startswith("_internal/")
        and ("build/" in n or any(j in Path(n).name for j in BUILD_JUNK))
    ]
    if junk:
        problems.append(
            f"{archive.name}: ships {len(junk)} PyInstaller build file(s), "
            f"e.g. {', '.join(sorted({Path(j).name for j in junk})[:4])}"
        )

    if problems:
        return problems
    print(f"  ok  {archive.name}  ({len(found)} files)")
    return []


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print(__doc__)
        return 2

    archives: list[Path] = []
    for a in args:
        p = Path(a)
        if p.is_dir():
            archives.extend(sorted(p.iterdir()))
        else:
            archives.append(p)
    archives = [a for a in archives if a.is_file()]

    if not archives:
        print(f"check_archive_contents: no archives found in {args}", file=sys.stderr)
        return 2

    problems: list[str] = []
    for archive in archives:
        if archive.suffix not in (".zip", ".gz", ".tar"):
            continue
        try:
            problems += check_one(archive)
        except (tarfile.TarError, zipfile.BadZipFile) as exc:
            problems.append(f"{archive.name}: unreadable archive: {exc}")

    if problems:
        for p in problems:
            print(f"check_archive_contents: {p}", file=sys.stderr)
        print(
            f"check_archive_contents: FAILED with {len(problems)} problem(s). "
            "A consumer of this archive would get a broken install.",
            file=sys.stderr,
        )
        return 1
    print(f"check_archive_contents: OK - {len(archives)} archive(s) carry binary, payload and licence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())