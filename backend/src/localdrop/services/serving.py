"""Content-serving policy (spec 06 §4, BC-12): magic-byte sniffing + the
inline/attachment allowlist. Sniffed type wins over declared type.
Pure-python sniffing — no libmagic dependency.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..storage import Storage

# ---- safe-inline allowlist (FR-P1..P5; SVG and HTML are ALWAYS attachment) ----
INLINE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/avif",
    "video/mp4",
    "video/webm",
    "audio/mpeg",
    "audio/mp4",
    "audio/ogg",
    "audio/wav",
    "audio/webm",
    "audio/flac",
    "application/pdf",
    "text/plain",
    "text/csv",
    "application/json",
    "text/markdown",
}


@dataclass
class ServingDecision:
    content_type: str
    disposition: str  # "inline" | "attachment"
    safe_inline: bool


def decide_serving(declared_mime: str, sniffed_mime: str | None) -> ServingDecision:
    """Sniffed type wins when available (MIME spoofing defense)."""
    effective = (sniffed_mime or declared_mime or "application/octet-stream").split(";")[0].strip().lower()
    if effective in ("", "application/octet-stream") and declared_mime:
        effective = declared_mime.split(";")[0].strip().lower()
    safe = effective in INLINE_TYPES and not effective.startswith("image/svg")
    return ServingDecision(
        content_type=effective,
        disposition="inline" if safe else "attachment",
        safe_inline=safe,
    )


TEXT_SNIFF_LIMIT = 8192


def sniff_mime(storage: Storage, path) -> str | None:
    """Best-effort magic-byte detection for images, AV, pdf, zip, text."""
    try:
        fd = storage.open_read(path)
    except Exception:
        return None
    try:
        import os

        head = os.read(fd, TEXT_SNIFF_LIMIT)
    finally:
        import os as _os

        _os.close(fd)
    return sniff_bytes(head)


def sniff_bytes(head: bytes) -> str | None:
    if len(head) < 12:
        # short text-ish payloads
        return "text/plain" if _looks_text(head) else None
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
        return "image/gif"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "image/webp"
    if head[4:12] == b"ftypavif":
        return "image/avif"
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"isom", b"iso2", b"mp41", b"mp42", b"avc1", b"M4V ", b"dash"):
            return "video/mp4"
        if brand in (b"M4A ", b"mp42"):
            return "audio/mp4"
        return "video/mp4"
    if head.startswith(b"%PDF"):
        return "application/pdf"
    if head.startswith(b"PK\x03\x04"):
        return "application/zip"
    if head.startswith(b"ID3") or (head[0:2] == b"\xff\xfb" or head[0:2] == b"\xff\xf3"):
        return "audio/mpeg"
    if head.startswith(b"fLaC"):
        return "audio/flac"
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        return "audio/wav"
    if head.startswith(b"OggS"):
        return "audio/ogg"
    if head.startswith(b"{") or head.startswith(b"["):
        if _looks_text(head):
            return "application/json"
    if _looks_text(head):
        return "text/plain"
    return None


def _looks_text(head: bytes) -> bool:
    if b"\x00" in head:
        return False
    if not head:
        return False
    text_chars = bytes(range(0x20, 0x7F)) + b"\n\r\t\x0b\x0c"
    try:
        head.decode("utf-8")
        return True
    except UnicodeDecodeError:
        pass
    # treat high bytes conservatively: allow UTF-8 failure for latin-ish text
    printable = sum(1 for b in head if b in text_chars or b >= 0x80)
    return printable / max(len(head), 1) > 0.95


def content_disposition_value(decision: ServingDecision, filename: str) -> str:
    """RFC 5987 encoded filename."""
    from urllib.parse import quote

    fallback = filename.encode("ascii", "replace").decode("ascii").replace('"', "'")
    encoded = quote(filename, safe="")
    return f"{decision.disposition}; filename=\"{fallback}\"; filename*=UTF-8''{encoded}"
