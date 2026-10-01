#!/usr/bin/env python3
"""Fail if the app version is declared inconsistently anywhere in the repo.

`backend/src/localdrop/__about__.py` is the single source of truth; pyproject
reads it dynamically. Two kinds of file are checked:

* **Synced copies** — files whose format demands a literal version (npm's
  `package.json`, a human-readable CHANGELOG heading). These must *equal* the
  canonical version. `npm version` and the release script keep them in step.
* **Derived files** — Docker/compose/packaging files, which must contain *no*
  version literal at all, because the release tooling substitutes a placeholder
  or the file reads its tag from the environment. A literal here is how version
  drift starts.

Run directly (`python scripts/check_version.py`) or in CI; exit 1 on drift.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ABOUT = ROOT / "backend" / "src" / "localdrop" / "__about__.py"
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def canonical_version() -> str:
    m = re.search(
        r'^__version__\s*=\s*"([^"]+)"', ABOUT.read_text(encoding="utf-8"), re.M
    )
    if not m:
        sys.exit(f"check_version: no __version__ in {ABOUT}")
    return m.group(1)


def _code_lines(path: Path) -> list[tuple[int, str]]:
    """(lineno, line) for non-comment lines, honouring #, // and /* */ blocks."""
    comment_starts = ("#", "//", "--", ";")
    out: list[tuple[int, str]] = []
    in_block = False
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw
        if in_block:
            if "*/" in line:
                in_block = False
                line = line.split("*/", 1)[1]
            else:
                continue
        while "/*" in line:
            head, _, tail = line.partition("/*")
            if "*/" in tail:
                line = head + tail.split("*/", 1)[1]
            else:
                in_block = True
                line = head
        if line.lstrip().startswith(comment_starts):
            continue
        # Strip a trailing comment that cannot be inside a URL or a string we
        # care about: good enough for the narrow patterns used below.
        for marker in ("  #", "\t#", " //", " --"):
            idx = line.find(marker)
            if idx != -1:
                line = line[:idx]
        if line.strip():
            out.append((lineno, line))
    return out


def check_synced(version: str) -> list[str]:
    problems: list[str] = []

    changelog = ROOT / "CHANGELOG.md"
    newest = re.search(r"^## \[(\d+\.\d+\.\d+)\]", changelog.read_text(encoding="utf-8"), re.M)
    if not newest:
        problems.append("CHANGELOG.md has no `## [x.y.z]` release heading")
    elif newest.group(1) != version:
        problems.append(
            f"CHANGELOG.md: newest released heading is {newest.group(1)}, "
            f"but __about__ says {version} — write the {version} release notes"
        )

    pkg_path = ROOT / "frontend" / "package.json"
    pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    if pkg.get("name") != "localdrop-frontend":
        problems.append(
            f"frontend/package.json name is {pkg.get('name')!r}, expected 'localdrop-frontend'"
        )
    if pkg.get("version") != version:
        problems.append(
            f"frontend/package.json version is {pkg.get('version')!r}, expected {version!r} "
            "(run `npm version` in frontend/ or packaging/release.py)"
        )
    return problems


def check_no_literals(version: str) -> list[str]:
    """A literal *app* version in a derived file is the drift this prevents.

    Scoped deliberately: dependency pins (`sqlalchemy>=2.0.40`) and prose
    examples in comments are legitimate, so each file type gets a pattern that
    matches only the shapes a stale app version actually takes, and comment
    lines are skipped entirely.
    """
    problems: list[str] = []
    semver = r"\d+\.\d+\.\d+"

    # (path, regex) — regex must identify an app-version reference, not a dep pin.
    rules: list[tuple[Path, re.Pattern[str]]] = [
        # A pinned LocalDrop image tag, or a build arg pre-set to a version.
        (ROOT / "docker-compose.yml", re.compile(rf"localdrop:{semver}|LOCALDROP_VERSION\s*[=:?]\s*{semver}")),
        (ROOT / "docker" / "Dockerfile", re.compile(rf"localdrop:{semver}|LOCALDROP_VERSION=\d")),
        # A literal [project] version defeats the dynamic hatchling hook.
        (ROOT / "backend" / "pyproject.toml", re.compile(r'^\s*version\s*=\s*["\']')),
        # FastAPI metadata / argparse defaults.
        (ROOT / "backend" / "src" / "localdrop" / "main.py",
         re.compile(rf'version\s*=\s*["\'][v]?{semver}["\']')),
        (ROOT / "backend" / "src" / "localdrop" / "launcher.py",
         re.compile(rf"LOCALDROP_VERSION[\"']\s*,\s*[\"']v?{semver}|v?{semver}['\"]\s*\)?\s*help")),
        (ROOT / "backend" / "src" / "localdrop" / "migrate.py",
         re.compile(rf"[\"']v?{semver}[\"']")),
    ]
    for path, pattern in rules:
        if not path.exists():
            continue
        for lineno, line in _code_lines(path):
            if "LOCALDROP_VERSION_PLACEHOLDER" in line:
                continue  # substituted at release time
            if pattern.search(line):
                problems.append(
                    f"{path.relative_to(ROOT).as_posix()}:{lineno}: hard-coded app version "
                    f"in a derived file (canonical {version!r}) — derive it from __about__.py"
                )

    # Frontend: only a *displayed* version literal is a problem. A semver that
    # belongs to a dependency (e.g. a comment about lucide-react 1.49.0) is not.
    frontend = ROOT / "frontend" / "src"
    display = re.compile(rf"[\"'`]v?{semver}[\"'`]|version[=:]\s*[\"']v?{semver}")
    for path in sorted(frontend.rglob("*.ts*")):
        for lineno, line in _code_lines(path):
            if "lucide-react" in line or "import" in line or "from '" in line:
                continue
            if display.search(line):
                problems.append(
                    f"{path.relative_to(ROOT).as_posix()}:{lineno}: hard-coded app version "
                    f"in the UI (canonical {version!r}) — read it from GET /api/v1/version"
                )
    return problems


def main() -> int:
    version = canonical_version()
    if not SEMVER.match(version):
        print(f"check_version: {version!r} is not plain SemVer", file=sys.stderr)
        return 1
    print(f"check_version: canonical version = {version} "
          f"({ABOUT.relative_to(ROOT).as_posix()})")

    problems = check_synced(version) + check_no_literals(version)
    for p in problems:
        print(f"check_version: {p}", file=sys.stderr)
    if problems:
        print(f"check_version: FAILED with {len(problems)} problem(s)", file=sys.stderr)
        return 1
    print("check_version: OK — single source of truth, no drift")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
