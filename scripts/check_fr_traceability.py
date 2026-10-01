#!/usr/bin/env python3
"""Fail if a functional requirement in the spec has no test referencing its id.

The gate the engineering spec asks for (docs/spec/08-engineering.md §5) is not
"coverage" but accountability: every FR-M in docs/spec/02-requirements.md must
be traceable to a test, so a feature cannot be declared done and then quietly
regressed.

    python scripts/check_fr_traceability.py            # check
    python scripts/check_fr_traceability.py --list     # the id -> test map
    python scripts/check_fr_traceability.py --strict   # also fail on orphans

A test claims an id by mentioning it in its name or docstring:

    async def test_tus_resume_after_interruption_FR_T_3(): ...

The result is written to `.coverage-fr.json` so the mapping is a reviewable
artefact rather than a claim.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "docs" / "spec" / "02-requirements.md"
TESTS = ROOT / "backend" / "tests"
OUT = ROOT / ".coverage-fr.json"

FR_ID = re.compile(r"\bFR-[A-Z]+\d+\b")
# The spec lists requirements as table rows, with the priority in the last cell:
#   | FR-A1 | First-run onboarding creates the owner account … | M |
# Priorities: M (must, in scope for 1.x), a number (a later minor), or a
# `[FUTURE]` marker. Only `M` is a release commitment, so only `M` is gated.
FR_ROW = re.compile(
    r"^\|\s*(FR-[A-Z]+\d+)\s*\|([^|]*)\|([^|]*)\|\s*$", re.M
)
# Headings are also accepted, for requirements added outside a table.
FR_HEADING = re.compile(r"^\s*#{2,4}\s*\**(FR-[A-Z]+\d+)\**", re.M)


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Must-have requirements with no automated test, and why. This is a register of
# known debt, not an escape hatch: the check fails on any gap NOT listed here,
# so the set can only shrink. Remove an entry when its test lands — the script
# will then tell you the entry is stale.
KNOWN_GAPS: dict[str, str] = {
    "FR-F4": "bulk move/delete reuse the single-item endpoints already covered by "
             "FR-F3; download-as-zip is a phase-3 feature. The multi-select UI "
             "itself has no automated coverage yet.",
    "FR-F5": "list/search/sort is implemented in services/tree.py but has no test "
             "that pins the ordering and cursor behaviour.",
    "FR-L2": "not implemented. LOCALDROP_MDNS_ENABLED is a reserved setting; "
             "discovery is URL + QR (FR-L1). The spec row should be re-prioritised.",
    "FR-L3": "a documentation deliverable (a per-platform matrix in "
             "docs/spec/03-architecture.md §7), not something a test can assert.",
    "FR-P1": "thumbnailing is best-effort background work with no failure path "
             "asserted yet; the served bytes are FR-P5's concern.",
    "FR-P2": "PDF is decided by the same magic-byte sniffing path FR-P5 covers; "
             "only the PDF branch is unasserted.",
    "FR-P3": "text preview caps at 256 KiB with charset detection; the cap is "
             "unasserted.",
    "FR-P4": "audio/video metadata relies on browser-native <video>/<audio>; "
             "there is no server behaviour left to assert beyond FR-P5.",
    "FR-S4": "the share response already carries qr_svg (exercised manually by "
             "backend/scripts/smoke_flow.py) but no test asserts its shape.",
}


def required_ids(must_only: bool = True) -> dict[str, str]:
    """{FR id: one-line description} for the requirements we gate on.

    With `must_only` (the default) this returns just the `M` rows: those are the
    release commitments. Numbered and `[FUTURE]` rows describe work that is
    deliberately not in 1.x, and gating on them would be theatre.
    """
    if not SPEC.exists():
        sys.exit(f"check_fr_traceability: {SPEC} does not exist")
    text = SPEC.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for m in FR_ROW.finditer(text):
        fr, desc, priority = m.group(1), m.group(2).strip(), m.group(3).strip()
        is_must = priority.startswith("M")
        if must_only and not is_must:
            continue
        out[fr] = f"{desc[:70]} [priority {priority}]"
    for m in FR_HEADING.finditer(text):
        out.setdefault(m.group(1), m.group(0).strip().lstrip("#* ").strip())
    return out


def test_claims() -> dict[str, list[str]]:
    """{FR id: ["tests/file.py::test_name", ...]}"""
    claims: dict[str, list[str]] = {}
    for path in sorted(TESTS.rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for fr in FR_ID.findall(line):
                claims.setdefault(fr, []).append(f"{path.relative_to(ROOT).as_posix()}:{lineno}")
    return claims


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--strict", action="store_true", help="also fail on ids no spec lists")
    ap.add_argument("--all", action="store_true", help="gate every priority, not just M")
    ap.add_argument("--no-write", action="store_true", help="do not write the json map")
    args = ap.parse_args(argv)

    required = required_ids(must_only=not args.all)
    claimed = test_claims()
    if not required:
        sys.exit("check_fr_traceability: no FR rows found in the spec")

    if args.list:
        for fr in sorted(set(required) | set(claimed)):
            mark = "ok " if fr in required and claimed.get(fr) else ("GAP" if fr in required else "?? ")
            where = ", ".join(claimed.get(fr, [])) or "-"
            print(f" {mark} {fr:8} {required.get(fr, '(not in the spec)')[:58]:58} {where}")
        return 0

    # A gap is acceptable only if it is registered in KNOWN_GAPS, and only for
    # as long as it stays there.
    missing = sorted(f for f in required if not claimed.get(f))
    unregistered = [f for f in missing if f not in KNOWN_GAPS]
    stale = sorted(f for f in KNOWN_GAPS if claimed.get(f))
    unknown = sorted(f for f in KNOWN_GAPS if f not in required)
    orphans = sorted(f for f in claimed if f not in required)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    if not args.no_write:
        OUT.write_text(
            json.dumps(
                {
                    "required": len(required),
                    "covered": len(required) - len(missing),
                    "uncovered": missing,
                    "known_gaps": {k: v for k, v in sorted(KNOWN_GAPS.items())},
                    "orphaned": orphans,
                    "map": {k: v for k, v in sorted(claimed.items())},
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    problems = [f"{fr} — {required[fr]}" for fr in unregistered]
    if args.strict:
        problems += [f"{fr} is referenced by a test but not in the spec" for fr in orphans]
    problems += [
        f"{fr} is in KNOWN_GAPS but is now covered by a test - remove the entry"
        for fr in stale
    ]
    problems += [f"{fr} is in KNOWN_GAPS but is not a Must-have requirement" for fr in unknown]

    if problems:
        for p in problems:
            print(f"check_fr_traceability: {p}", file=sys.stderr)
        print(
            f"check_fr_traceability: FAILED. Either add a test that names the id, "
            f"or register it in KNOWN_GAPS with a reason.",
            file=sys.stderr,
        )
        return 1

    print(
        f"check_fr_traceability: OK — {len(required) - len(missing)}/{len(required)} "
        f"Must-have requirements covered by tests"
    )
    for fr in missing:
        print(f"  known gap {fr}: {KNOWN_GAPS[fr].splitlines()[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
