"""Rate limiting: in-process token buckets + progressive lockout (ADR-003).

Single-process accurate. Keyed by (class, client ip[/64 for IPv6], optional
identity) so login/unlock brute force locks the *account*, not just the IP.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from ipaddress import ip_address

from .errors import Problem

_table: dict[str, list[float]] = {}
_lockouts: dict[str, float] = {}


def _bucket_key(ip: str) -> str:
    try:
        addr = ip_address(ip)
    except ValueError:
        return ip
    if addr.version == 6:
        return f"{addr.exploded.split(':')[0:4]}/64"
    return str(addr)


@dataclass
class Limit:
    name: str
    limit: int
    window: int  # seconds
    lockout: int = 0  # seconds, applied to identity+ip on breach

    def check(self, ip: str, identity: str | None = None) -> None:
        """Raise 429 if over limit. Records a hit otherwise."""
        now = time.monotonic()
        keys = [f"{self.name}:{_bucket_key(ip)}"]
        if identity is not None:
            keys.append(f"{self.name}:id:{identity}:{_bucket_key(ip)}")

        for key in keys:
            if self.lockout:
                until = _lockouts.get(key, 0)
                if now < until:
                    raise Problem(
                        429,
                        "rate-limited",
                        "Too Many Requests",
                        "Try again later.",
                        headers={
                            "Retry-After": str(int(until - now)),
                            "RateLimit-Limit": str(self.limit),
                        },
                    )

        for key in keys:
            hits = _table.setdefault(key, [])
            cutoff = now - self.window
            hits[:] = [t for t in hits if t > cutoff]
            hits.append(now)
            if len(hits) > self.limit:
                if self.lockout:
                    _lockouts[key] = now + self.lockout
                raise Problem(
                    429,
                    "rate-limited",
                    "Too Many Requests",
                    "Rate limit exceeded. Try again later.",
                    headers={"Retry-After": str(self.window)},
                )


@dataclass
class Limits:
    auth: Limit = field(default_factory=lambda: Limit("auth", 10, 300, lockout=900))
    share: Limit = field(default_factory=lambda: Limit("share", 120, 60))
    content: Limit = field(default_factory=lambda: Limit("content", 60, 60))
    api: Limit = field(default_factory=lambda: Limit("api", 600, 60))


LIMITS = Limits()


def client_ip_from_headers(request_ip: str, xff: str | None, trusted_proxies: int) -> str:
    """XFF trusted only from configured proxy hops (default: socket peer)."""
    if trusted_proxies <= 0 or not xff:
        return request_ip
    parts = [p.strip() for p in xff.split(",")]
    # take the client as the (N+1)-th from the right
    idx = len(parts) - 1 - trusted_proxies
    if idx < 0:
        return request_ip
    return parts[idx]


def reset_limits() -> None:
    """Test helper."""
    _table.clear()
    _lockouts.clear()
