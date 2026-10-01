"""Rate limiting: in-process token buckets + progressive lockout (ADR-003).

Single-process accurate. Keyed by (class, client ip[/64 for IPv6], optional
identity) so login/unlock brute force locks the *account*, not just the IP.

Demo mode adds a second keying strategy. Behind a reverse proxy every visitor
shares one client IP, so the per-IP bucket would be a shared budget: one
person's failed logins would 429 everybody else, and the auth limit of 10 per
5 minutes would lock a shared proxy out of the demo entirely. In demo mode the
bucket is keyed by session identity instead, with the IP kept only as a
secondary key for the classes that are genuinely about the socket.
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
    # When True, the bucket is keyed by identity and the client IP is not
    # counted. Set this for limits that protect *content*, where the point is to
    # stop one visitor hogging the instance, not to inspect a socket. Login
    # keeps its IP key: there, the socket really is the signal.
    per_identity: bool = False

    def keys(self, ip: str, identity: str | None) -> list[str]:
        if self.per_identity and identity:
            # Behind a shared proxy the IP is the same for everybody, so a
            # per-IP budget here is a shared budget.
            return [f"{self.name}:id:{identity}"]
        out = [f"{self.name}:{_bucket_key(ip)}"]
        if identity is not None:
            out.append(f"{self.name}:id:{identity}:{_bucket_key(ip)}")
        return out

    def check(self, ip: str, identity: str | None = None) -> None:
        """Raise 429 if over limit. Records a hit otherwise."""
        now = time.monotonic()
        keys = self.keys(ip, identity)

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
    share: Limit = field(default_factory=lambda: Limit("share", 120, 60, per_identity=True))
    content: Limit = field(default_factory=lambda: Limit("content", 60, 60, per_identity=True))
    api: Limit = field(default_factory=lambda: Limit("api", 600, 60, per_identity=True))


LIMITS = Limits()


def identity_of(principal) -> str | None:  # noqa: ANN001 - avoids importing auth
    """The rate-limit identity for a request, or None when anonymous.

    Keeping this duck-typed avoids a circular import: auth imports this module.
    """
    return getattr(principal, "user_id", None) and str(principal.user_id) or None


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
