"""Password hashing (argon2id), token generation and hashing."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import string

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from .config import get_settings

ALPHABET = string.ascii_letters + string.digits

_hasher: PasswordHasher | None = None


def _ph() -> PasswordHasher:
    global _hasher
    if _hasher is None:
        s = get_settings()
        _hasher = PasswordHasher(
            time_cost=s.argon2_time_cost,
            memory_cost=s.argon2_memory_cost,
            parallelism=s.argon2_parallelism,
            hash_len=32,
            salt_len=16,
        )
    return _hasher


def hash_password(password: str) -> str:
    return _ph().hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph().verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def new_token(nbytes: int = 32) -> str:
    """CSPRNG opaque token, URL-safe."""
    return secrets.token_urlsafe(nbytes)


def share_token() -> str:
    """26-char base32 = 130 bits of entropy (spec 04 §3.8)."""
    raw = secrets.token_bytes(17)  # 136 bits → 27.2 base32 chars; trim to 26
    alphabet = string.ascii_uppercase + "234567"
    value = int.from_bytes(raw, "big")
    out = []
    while value and len(out) < 26:
        value, rem = divmod(value, 32)
        out.append(alphabet[rem])
    return "".join(out)


def hash_token(token: str) -> str:
    """SHA-256 hex of the opaque token — raw tokens are never stored."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
