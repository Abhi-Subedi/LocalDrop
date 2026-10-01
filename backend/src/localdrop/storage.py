"""Content-addressed storage layer (ADR-004 / BC-3, BC-6, BC-7).

Rules enforced here:
  * Paths are composed ONLY from server-generated UUIDs / hex hashes.
  * Every open resolves the path and verifies containment in the data dir
    (symlink defense, layer 2 of 3).
  * O_NOFOLLOW + O_CREAT|O_EXCL where applicable (layer 3).
  * append-first / db-second is the caller's responsibility; we provide
    atomic replace + fsync helpers.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from .config import get_settings
from .errors import Problem

_OPEN_FLAGS_READ = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
# Windows CRT fds default to TEXT mode (\n <-> \r\n translation, 0x1A = EOF).
# Every open in this module must force binary mode; Linux O_BINARY == 0 (no-op).
_OPEN_FLAGS_WRITE_NEW = (
    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
)
_OPEN_FLAGS_APPEND = (
    os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
)
_OPEN_FLAGS_RDWR = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)


class Storage:
    """The only module allowed to touch LOCALDROP_DATA_DIR."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = (data_dir or get_settings().data_dir).resolve()
        self.blobs = self.data_dir / "blobs"
        self.staging = self.data_dir / "staging"
        self.thumbs = self.data_dir / "thumbs"
        self.tmp = self.data_dir / "tmp"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        for d in (self.blobs, self.staging, self.thumbs, self.tmp):
            d.mkdir(parents=True, exist_ok=True)

    # ---- path safety ----

    def _safe(self, path: Path | str) -> Path:
        """Containment check (defense layer 2). Raises 500-class problem."""
        resolved = Path(path).resolve()
        if not resolved.is_relative_to(self.data_dir):
            raise Problem(500, "storage-containment", "Internal storage error")
        return resolved

    # ---- recorded paths (what the DB stores) ----

    def to_recorded(self, path: Path | str) -> str:
        """Persist paths RELATIVE to the data dir.

        Absolute paths break the moment a data volume moves (backup restore
        to a new path, changed mount). Relative rows stay valid anywhere.
        Stored POSIX-style so rows are portable across OSes too.
        """
        return Path(path).resolve().relative_to(self.data_dir).as_posix()

    def from_recorded(self, recorded: Path | str) -> Path:
        """Resolve a DB path back to an absolute, containment-checked Path.

        Accepts legacy absolute rows (grandfathered if inside the data dir)
        and current relative rows.
        """
        p = Path(recorded)
        if p.is_absolute():
            return self._safe(p)
        return self._safe(self.data_dir / p)

    def _resolve(self, path: Path | str) -> Path:
        return self.from_recorded(str(path))

    def blob_path(self, sha256_hex: str) -> Path:
        if len(sha256_hex) != 64 or any(c not in "0123456789abcdef" for c in sha256_hex):
            raise Problem(500, "storage-blob-path", "Internal storage error")
        return self._safe(self.blobs / sha256_hex[:2] / sha256_hex[2:4] / sha256_hex)

    def staging_path(self, session_id: str) -> Path:
        return self._safe(self.staging / f"{session_id}.part")

    def thumb_path(self, file_id: str, size: int) -> Path:
        return self._safe(self.thumbs / file_id / f"{size}.webp")

    # ---- lifecycle ----

    def create_staging(self, session_id: str) -> Path:
        """Exclusive creation of a .part file (defense layer 3)."""
        path = self.staging_path(session_id)
        fd = os.open(path, _OPEN_FLAGS_WRITE_NEW, 0o600)
        os.close(fd)
        return path

    def open_append(self, path: Path | str) -> int:
        return os.open(self._resolve(path), _OPEN_FLAGS_APPEND)

    def open_read(self, path: Path | str) -> int:
        return os.open(self._resolve(path), _OPEN_FLAGS_READ)

    def delete(self, path: Path | str, missing_ok: bool = True) -> None:
        p = self._resolve(path)
        try:
            p.unlink()
        except FileNotFoundError:
            if not missing_ok:
                raise

    def replace(self, src: Path, dst: Path) -> None:
        """Atomic move within the data dir (same filesystem)."""
        os.replace(self._resolve(src), self._resolve(dst))

    def fsync_file(self, path: Path | str) -> None:
        # O_RDWR: Windows fsync requires a writable handle (EBADF on O_RDONLY).
        fd = os.open(self._resolve(path), _OPEN_FLAGS_RDWR)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def fsync_dir(self, path: Path | str) -> None:
        """Durability nicety for POSIX; Windows cannot open directories — no-op."""
        try:
            fd = os.open(self._resolve(path), _OPEN_FLAGS_READ)
        except (PermissionError, OSError):
            return
        try:
            os.fsync(fd)
        except OSError:
            pass
        finally:
            os.close(fd)

    def size_of(self, path: Path | str) -> int:
        return self._resolve(path).stat().st_size

    def free_bytes(self) -> int:
        return shutil.disk_usage(self.data_dir).free

    def ensure_free(self, needed: int) -> None:
        if self.free_bytes() < needed:
            raise Problem(
                423,
                "storage-full",
                "Storage Full",
                "Not enough free space to complete this operation.",
            )

    def make_thumb_dir(self, file_id: str) -> Path:
        d = self._safe(self.thumbs / file_id)
        d.mkdir(parents=True, exist_ok=True)
        return d


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        _storage = Storage()
    return _storage


def set_storage(s: Storage) -> None:
    global _storage
    _storage = s
