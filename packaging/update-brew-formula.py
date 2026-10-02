#!/usr/bin/env python3
"""Rewrite the Homebrew formula for a specific release.

Keeps the formula in step with the published artefacts: substitutes the version
and the per-architecture SHA-256 taken from the release's SHA256SUMS. Called by
.github/workflows/release.yml after the checksums are computed.

    python packaging/update-brew-formula.py --version 1.1.0 \
        --sha256-arm64 <hex> --sha256-x64 <hex>

    # validate without writing
    python packaging/update-brew-formula.py --version 1.1.0 --check-only

Placeholders in the committed template are the tell that a real release has not
happened yet, which is exactly what `--check-only` is for.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

FORMULA = Path(__file__).resolve().parent / "homebrew" / "localdrop.rb"
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def render(template: str, version: str, arm: str, x64: str) -> str:
    out = template.replace("LOCALDROP_VERSION_PLACEHOLDER", version)
    out = out.replace("LOCALDROP_SHA256_ARM64_PLACEHOLDER", arm)
    out = out.replace("LOCALDROP_SHA256_X64_PLACEHOLDER", x64)
    return out


def substitute(text: str, version: str, arm: str, x64: str) -> str:
    """Rewrite a *released* formula, not just the template's placeholders.

    The template is only rendered on a fresh release. Once a real version has
    been substituted the placeholders are gone, so a later release has to
    rewrite the literal values instead. Doing only the first half is why the
    committed formula stayed stuck on whatever version it first reached.
    """
    out = text.replace("LOCALDROP_VERSION_PLACEHOLDER", version)
    out = out.replace("LOCALDROP_SHA256_ARM64_PLACEHOLDER", arm)
    out = out.replace("LOCALDROP_SHA256_X64_PLACEHOLDER", x64)
    out = re.sub(r'(?m)^(\s*version\s+")[^"]*(")', rf'\g<1>{version}\g<2>', out)

    # The two sha256 lines belong to the arm64 branch and the x64 branch, in
    # that order. This has to be one pass: a second re.sub would match the line
    # the first one just rewrote and both would end up with the x64 digest.
    digests = iter((arm, x64))

    def _sha(match: re.Match[str]) -> str:
        return f'{match.group(1)}{next(digests, x64)}{match.group(2)}'

    out = re.sub(r'(?m)^(\s*sha256\s+")[^"]*(")', _sha, out)

    # The download URLs embed the version twice each, once per architecture.
    # The leading whitespace must be captured and re-emitted: matching with
    # `^\s*` and returning a bare `url ...` silently de-indents the line, which
    # is harmless to Ruby but rewrites the file on every release and breaks
    # anything that matches on indentation.
    def _url(match: re.Match[str]) -> str:
        indent = match.group(1)
        arch = "arm64" if "macos-arm64" in match.group(0) else "x64"
        return (
            f'{indent}url "https://github.com/Abhi-Subedi/LocalDrop/releases/'
            f'download/v{version}/localdrop-{version}-macos-{arch}.tar.gz"'
        )

    out = re.sub(
        r'(?m)^([ \t]*)url "https://github\.com/[^"]*\.tar\.gz"[ \t]*$',
        _url,
        out,
    )
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", required=True, help="release version, e.g. 1.1.0")
    ap.add_argument("--sha256-arm64", default="", help="sha256 of the macos-arm64 tarball")
    ap.add_argument("--sha256-x64", default="", help="sha256 of the macos-x86_64 tarball")
    ap.add_argument("--check-only", action="store_true", help="validate, do not write")
    ap.add_argument(
        "--formula",
        type=Path,
        help="formula to operate on (default: the one next to this script). The "
        "homebrew-localdrop tap passes its own Formula/localdrop.rb so there is "
        "one substitution implementation instead of two.",
    )
    args = ap.parse_args(argv)

    formula = args.formula if args.formula else FORMULA
    if not formula.is_file():
        print(f"update-brew-formula: {formula} does not exist", file=sys.stderr)
        return 2

    if not re.match(r"^\d+\.\d+\.\d+(-[\w.]+)?$", args.version):
        print(f"update-brew-formula: bad version {args.version!r}", file=sys.stderr)
        return 2

    template = formula.read_text(encoding="utf-8")
    if args.check_only:
        # A committed formula with placeholders has never been released. This is
        # the check CI runs, so it must not demand the digests it is about to
        # discard - otherwise it exits before saying anything useful and the
        # caller is forced to ignore it.
        leftovers = sorted(set(re.findall(r"LOCALDROP_[A-Z0-9_]*PLACEHOLDER", template)))
        if leftovers:
            print(f"update-brew-formula: {formula.name} still contains {', '.join(leftovers)}",
                  file=sys.stderr)
            return 1
        m = re.search(r'version "([^"]+)"', template)
        pinned = m.group(1) if m else "?"
        if pinned != args.version:
            print(f"update-brew-formula: {formula.name} is pinned at {pinned}, "
                  f"not {args.version}", file=sys.stderr)
            return 1
        print(f"update-brew-formula: {formula.name} is pinned at {pinned}")
        return 0

    # Digests are only required when actually rewriting the file.
    for name, digest in (("arm64", args.sha256_arm64), ("x64", args.sha256_x64)):
        if not HEX64.match(digest or ""):
            print(
                f"update-brew-formula: --sha256-{name} must be a 64-char hex digest",
                file=sys.stderr,
            )
            return 2

    formula.write_text(
        substitute(template, args.version, args.sha256_arm64.lower(), args.sha256_x64.lower()),
        encoding="utf-8",
    )
    print(f"update-brew-formula: {formula.name} -> {args.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
