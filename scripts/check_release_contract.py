#!/usr/bin/env python3
"""Check that every consumer agrees on the release artefact names.

The release pipeline produces artefacts from `packaging/build-binary.py`, and
four separate places then hard-code the resulting file names:

  install.sh              what it downloads
  install.ps1             what it downloads
  packaging/homebrew/*.rb what brew fetches
  .github/workflows/release.yml  what it globs and what it greps for

Nothing in the toolchain connects them, so a rename on one side silently
publishes a release whose installers 404. This is the cheapest possible guard:
one dictionary, compared against the real strings.

    python scripts/check_release_contract.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent

# platform -> (arch, slug) as produced by build-binary.py platform_slug()
SLUGS = {
    "linux-x64": "linux/x64",
    "linux-arm64": "linux/arm64",
    "linux-armv7": "linux/armv7",
    "macos-x64": "macos/x64",
    "macos-arm64": "macos/arm64",
    "windows-x64": "windows/x64",
}

# Files that consume artefact names, and how each one spells them.
#   path -> (pattern, human description of how that consumer builds its name)
CONSUMERS: list[tuple[Path, str, str]] = [
    (ROOT / "packaging" / "homebrew" / "localdrop.rb", r"macos-(arm64|x64)\.tar\.gz",
     "the formula fetches a macOS tarball"),
    (ROOT / ".github" / "workflows" / "release.yml", r"asset:\s*(\S+)",
     "the matrix selects one runner per slug"),
]

# Spellings that have been wrong before. Each is a slug that appears somewhere
# but is not produced by the build script.
BANNED = {
    "macos-x86_64": "the build script emits `macos-x64`",
    "darwin-x64": "the build script emits `macos-x64`, not `darwin-*`",
    "win-x64": "the build script emits `windows-x64`",
    "macos-x86-64": "hyphens in the arch segment break the glob",
    "linux-aarch64": "the build script emits `linux-arm64`",
}


def check_shell_installer() -> list[str]:
    """install.sh composes the name at runtime, so match its parts, not a slug."""
    path = ROOT / "install.sh"
    if not path.exists():
        return ["install.sh does not exist"]
    text = path.read_text(encoding="utf-8")
    problems: list[str] = []

    # The platform half must come from uname, and only these two are shipped.
    if not re.search(r'Linux\)\s*PLATFORM="linux"', text):
        problems.append("install.sh does not map uname Linux to PLATFORM=linux")
    if not re.search(r'Darwin\)\s*PLATFORM="macos"', text):
        problems.append("install.sh does not map uname Darwin to PLATFORM=macos")

    # The arch half must be produced by detect_arch.
    m = re.search(r"detect_arch\(\)\s*\{(.*?)\n\}", text, re.S)
    if not m:
        problems.append("install.sh has no detect_arch function")
    else:
        for arch in ("x64", "arm64", "armv7"):
            if f'echo "{arch}"' not in m.group(1):
                problems.append(f"install.sh detect_arch never returns {arch}")

    # And the two must be interpolated into the asset name.
    if not re.search(r'ASSET="localdrop-\$\{VERSION\}-\$\{PLATFORM\}-\$\{ARCH\}\.tar\.gz"', text):
        problems.append(
            "install.sh does not compose ASSET from VERSION/PLATFORM/ARCH, so it may "
            "not match the published name"
        )
    return problems


def check_powershell_installer() -> list[str]:
    path = ROOT / "install.ps1"
    if not path.exists():
        return ["install.ps1 does not exist"]
    text = path.read_text(encoding="utf-8")
    problems: list[str] = []
    if 'LocalDrop-$Version-windows-$arch.zip' not in text:
        problems.append(
            "install.ps1 does not name the archive LocalDrop-<version>-windows-<arch>.zip"
        )
    if "$arch = " not in text or "'x64'" not in text:
        problems.append("install.ps1 does not define an $arch of 'x64'")
    return problems


def check_slugs_are_producible() -> list[str]:
    """Every slug the release matrix builds must be one platform_slug() returns."""
    build = (ROOT / "packaging" / "build-binary.py").read_text(encoding="utf-8")
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    produced = set(re.findall(r'"((?:linux|macos|windows)-(?:x64|arm64|armv7))"', build))
    problems: list[str] = []
    for slug in sorted(set(re.findall(r"asset:\s*(\S+)", release))):
        if slug not in produced:
            problems.append(
                f"release.yml builds `{slug}`, but build-binary.py platform_slug() "
                f"never returns it (it returns: {', '.join(sorted(produced))})"
            )
    for slug in sorted(produced - set(SLUGS)):
        problems.append(f"build-binary.py produces `{slug}`, which is not in this script's list")
    return problems


def main() -> int:
    problems: list[str] = []

    for path, pattern, why in CONSUMERS:
        if not path.exists():
            problems.append(f"{path.relative_to(ROOT).as_posix()} does not exist")
            continue
        found = sorted(set(re.findall(pattern, path.read_text(encoding="utf-8"))))
        if not found:
            problems.append(f"{path.relative_to(ROOT).as_posix()}: no artefact name found ({why})")
        else:
            print(f"  {path.relative_to(ROOT).as_posix():42} {', '.join(found)}")

    problems += check_shell_installer()
    problems += check_powershell_installer()
    problems += check_slugs_are_producible()

    # Nothing anywhere may name an artefact the build script cannot produce.
    for path in [
        ROOT / "install.sh",
        ROOT / "install.ps1",
        ROOT / "uninstall.sh",
        ROOT / "packaging" / "homebrew" / "localdrop.rb",
        ROOT / ".github" / "workflows" / "release.yml",
        ROOT / "packaging" / "build-binary.py",
    ]:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for bad, why in BANNED.items():
            if bad in text:
                problems.append(
                    f"{path.relative_to(ROOT).as_posix()}: names `{bad}`, but {why}"
                )

    print(f"\n  build-binary.py produces: {', '.join(sorted(SLUGS))}")
    if problems:
        for p in problems:
            print(f"check_release_contract: {p}", file=sys.stderr)
        print(
            f"check_release_contract: FAILED with {len(problems)} problem(s). "
            "An installer would download a file that does not exist.",
            file=sys.stderr,
        )
        return 1
    print("check_release_contract: OK — installers, formula and pipeline agree on the names")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
