#!/usr/bin/env python3
"""Fail if docs/CONFIGURATION.md and backend/src/localdrop/config.py disagree.

`config.py` is the single source of truth for configuration (its own docstring
says so). This script keeps the reference table honest:

1. every `LOCALDROP_*` field on Settings must appear in the table;
2. every `LOCALDROP_*` in the table must exist on Settings;
3. a `default:` in config.py must match the default documented in the table.

It runs in CI (`.github/workflows/ci.yml` job `docs-sync`) and standalone:

    python scripts/check_config_docs.py          # check
    python scripts/check_config_docs.py --list   # show what it sees
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

# The docs contain arrows and typographic characters; a cp1252 console (the
# default on Windows) must not turn a passing check into a UnicodeEncodeError.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PY = ROOT / "backend" / "src" / "localdrop" / "config.py"
DOC = ROOT / "docs" / "CONFIGURATION.md"

# Documented in the second table, "read by the packaging": these are consumed by
# the launcher, the compose file, the entrypoint or the installer rather than by
# the Settings class.
ENVFILE_ONLY = {
    "LOCALDROP_HOST",
    "LOCALDROP_PG_PORT",
    "LOCALDROP_VERSION",
    "LOCALDROP_BACKUP_BEFORE_MIGRATE",
    "LOCALDROP_HOST_PORT",
    "LOCALDROP_IMAGE_TAG",
    "POSTGRES_PASSWORD",
}

# Backends the settings loader understands; anything else in the table is
# either a real bug or something we have to document deliberately.
SQL_PREFIX = "postgresql"


def settings_fields() -> dict[str, str | None]:
    """{LOCALDROP_NAME: documented default} straight from the AST of config.py."""
    tree = ast.parse(CONFIG_PY.read_text(encoding="utf-8"))
    cls = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef) and n.name == "Settings"
    )
    out: dict[str, str | None] = {}
    for stmt in cls.body:
        if not isinstance(stmt, ast.AnnAssign) or not isinstance(stmt.target, ast.Name):
            continue
        name = f"LOCALDROP_{stmt.target.id.upper()}"
        default: str | None = None
        if isinstance(stmt.value, ast.Call):  # Field(default=...)
            for kw in stmt.value.keywords:
                if kw.arg == "default":
                    default = ast.unparse(kw.value)
        elif stmt.value is not None:
            default = ast.unparse(stmt.value)
        out[name] = default
    return out


def evaluate(expr: str) -> str | None:
    """Reduce a config.py default to a comparable literal.

    Settings use readable arithmetic for byte and minute constants
    (`8 * 1024 ** 2`), so `7 * 24 * 60` has to become `10080` before it can be
    compared with the documented value. Only literals, arithmetic and `Path()`
    are evaluated, and anything unexpected returns None.
    """
    try:
        node = ast.parse(expr, mode="eval").body
    except SyntaxError:
        return None
    try:
        value = eval(  # noqa: S307 - AST is parsed above from our own source file
            compile(ast.Expression(node), "<default>", "eval"),
            {"__builtins__": {"Path": lambda p: str(p)}},
        )
    except Exception:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return value
    return None


def documented() -> dict[str, str]:
    """{NAME: the Default cell of its row in CONFIGURATION.md}."""
    if not DOC.exists():
        sys.exit(f"check_config_docs: {DOC} does not exist")
    names: dict[str, str] = {}
    # | `NAME` | default | what |
    row = re.compile(
        r"^\|\s*`([A-Z][A-Z0-9_]{3,})`\s*\|([^|]*)\|", re.M
    )
    for m in row.finditer(DOC.read_text(encoding="utf-8")):
        names[m.group(1)] = m.group(2).strip()
    return names


def normalise(value: str) -> str | None:
    """Make a value and a markdown cell comparable, or give up.

    Returns None when the cell is prose rather than a value ("compose default",
    "*(required)*", "…"), in which case the caller skips the comparison: the
    script checks that a default is *documented*, not that prose matches.
    """
    v = value.strip().strip("`").strip().strip("*").strip()
    v = v.replace("`", "").replace('"', "").replace("'", "").strip()
    if not v or v in {"-", "…", "..."} or "(" in v:
        return None
    if v.startswith(("compose", "see ", "generated", "empty", "unset", "n/a", "sqlalchemy")):
        return None
    # A leading numeric literal is the value; trailing "(100 GiB)" is commentary.
    m = re.match(r"^([0-9][0-9_.]*(?:[kmgt]i?b)?)\b", v.lower())
    if m:
        return m.group(1).replace("_", "")
    low = v.lower().replace("_", "").replace("-", "")
    aliases = {"": "none", "none": "none", "null": "none", "true": "true", "false": "false"}
    if low in aliases:
        return aliases[low]
    return low


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="print both sets and exit")
    args = ap.parse_args(argv)

    code = settings_fields()
    docs = documented()
    if args.list:
        print(f"{len(code)} field(s) in config.py, {len(docs)} row(s) in the docs\n")
        for k in sorted(set(code) | set(docs)):
            mark = " " if (k in code and k in docs) else ("<" if k in code else ">")
            print(f" {mark} {k:38} code={str(code.get(k)):22} docs={docs.get(k, '-')}")
        return 0

    problems: list[str] = []
    for name in sorted(set(code) - set(docs)):
        problems.append(f"{name} is a Settings field but is not documented")
    for name in sorted(set(docs) - set(code) - ENVFILE_ONLY):
        problems.append(f"{name} is documented but is not a Settings field")
    for name in sorted(ENVFILE_ONLY & set(code)):
        problems.append(
            f"{name} is a Settings field but is filed under the packaging table"
        )

    for name in sorted(set(code) & set(docs)):
        code_default, doc_default = code[name], docs[name]
        if code_default is None:
            continue
        a = normalise(evaluate(code_default) or code_default)
        b = normalise(doc_default)
        if a is None or b is None:
            continue  # prose cell: presence is documented, value is not claimed
        if a != b:
            problems.append(
                f"{name}: config.py default evaluates to {a!r} but the docs say {b!r}"
            )

    if problems:
        for p in problems:
            print(f"check_config_docs: {p}", file=sys.stderr)
        print(
            f"check_config_docs: FAILED with {len(problems)} problem(s). "
            f"Update {DOC.relative_to(ROOT).as_posix()}.",
            file=sys.stderr,
        )
        return 1
    print(
        f"check_config_docs: OK — {len(code)} settings in config.py, "
        f"{len(set(docs) - set(code))} packaging variables, all documented"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
