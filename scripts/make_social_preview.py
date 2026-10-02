"""Generate GitHub's social preview image (1280x640) from the brand assets.

This is the banner GitHub shows on the repository card, on the owner's profile,
in search results, and in every social preview of a link to the repo. It is the
single highest-leverage visual on the page, and GitHub's default (a blurry crop
of the README) looks like an accident.

Run from the repo root:
    python scripts/make_social_preview.py
    python scripts/make_social_preview.py --out somewhere/else.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent

W, H = 1280, 640

# The palette from frontend/src/index.css: emerald accent on near-black.
BG_TOP = (10, 10, 10)
BG_BOTTOM = (16, 20, 18)
EMERALD = (34, 197, 94)
EMERALD_DIM = (21, 128, 61)
TEXT = (244, 244, 245)
MUTED = (160, 168, 164)

FONT_CANDIDATES_BOLD = [
    "C:/Windows/Fonts/seguisb.ttf",   # Segoe UI Semibold
    "C:/Windows/Fonts/segoeuib.ttf",  # Segoe UI Bold
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]
FONT_CANDIDATES = [
    "C:/Windows/Fonts/segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont:
    for c in candidates:
        p = Path(c)
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size)
            except OSError:
                continue
    return ImageFont.load_default(size)


def background() -> Image.Image:
    """A near-black field with a soft emerald glow, matching the app's dark theme."""
    img = Image.new("RGB", (W, H), BG_TOP)
    draw = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        draw.line(
            [(0, y), (W, y)],
            fill=tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)),
        )

    # Two blurred emerald pools so the flat background has some depth without
    # looking like a gradient template.
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([-260, -320, 560, 300], fill=EMERALD_DIM)
    gd.ellipse([W - 520, H - 360, W + 220, H + 240], fill=(16, 90, 48))
    glow = glow.filter(ImageFilter.GaussianBlur(150))
    return Image.blend(img, glow, 0.22)


def load_mark(size: int) -> Image.Image | None:
    """The leaf mark, recoloured white so it reads on the dark field."""
    for rel in ("frontend/public/mark-on-light.png",
                 "frontend/public/icon-512.png",
                 "frontend/public/logo-on-light.png"):
        src = ROOT / rel
        if not src.exists():
            continue
        mark = Image.open(src).convert("RGBA")
        # Make the mark a single tone; the source is monochrome on transparency.
        alpha = mark.split()[-1]
        tint = Image.new("RGBA", mark.size, (255, 255, 255, 0))
        tint.putalpha(alpha)
        mark = tint.resize((size, size), Image.LANCZOS)
        bbox = mark.split()[-1].getbbox()
        if bbox:
            mark = mark.crop(bbox)
            scale = size / max(mark.width, mark.height)
            mark = mark.resize(
                (max(1, int(mark.width * scale)), max(1, int(mark.height * scale))),
                Image.LANCZOS,
            )
        return mark
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT / ".github" / "social-preview.png")
    args = ap.parse_args()

    img = background()

    mark = load_mark(150)
    left = 96
    top = 150
    if mark is not None:
        img.paste(mark, (left, top), mark)
    else:
        print("warning: no brand mark found; the preview will have no logo",
              file=sys.stderr)

    draw = ImageDraw.Draw(img)
    f_title = font(FONT_CANDIDATES_BOLD, 82)
    f_sub = font(FONT_CANDIDATES, 33)
    f_pill = font(FONT_CANDIDATES_BOLD, 22)

    x = left
    draw.text((x, top + 205), "LocalDrop", font=f_title, fill=TEXT)
    draw.text((x + 3, top + 310),
              "Self-hosted file sharing on your own network.",
              font=f_sub, fill=MUTED)

    # A row of install chips. These are the words a visitor scans for, so they
    # earn their place rather than being decoration.
    #
    # anchor="lm" draws the text from its left-middle, and the box is centred on
    # that same baseline: measuring a box off the text's top-left is what makes
    # small labels look clipped at the bottom.
    chips = ["curl | sh", "Docker", "Homebrew", "Windows", "AGPL-3.0"]
    cx, cy = x, top + 400
    pad_x, pad_y = 20, 13
    for chip in chips:
        tw = draw.textlength(chip, font=f_pill)
        draw.rounded_rectangle(
            (cx, cy - pad_y, cx + tw + pad_x * 2, cy + pad_y),
            radius=(pad_y * 2) // 2 + 4,
            fill=(22, 27, 25),
            outline=EMERALD,
            width=2,
        )
        draw.text((cx + pad_x, cy), chip, font=f_pill, fill=TEXT, anchor="lm")
        cx += tw + pad_x * 2 + 14

    draw.line([(0, H - 6), (W, H - 6)], fill=EMERALD, width=6)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    # RGB, not RGBA: GitHub rejects transparency in a social preview.
    img.convert("RGB").save(args.out, "PNG", optimize=True)
    kb = args.out.stat().st_size / 1024
    print(f"wrote {args.out.relative_to(ROOT)}  ({img.width}x{img.height}, {kb:.0f} KiB)")
    if kb > 1024:
        print("warning: over 1 MiB; GitHub prefers smaller", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
