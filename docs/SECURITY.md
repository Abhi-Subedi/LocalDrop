# Security

LocalDrop V1 is built for a **trusted home LAN**, not the hostile internet.
It is careful by default, but read this before exposing it further.

## Threat model (V1)

**In scope:** password storage (argon2id), session theft, cross-user access
(single owner today; object-level checks everywhere for tomorrow), path
traversal / symlink escape, malicious uploads (polyglot SVG/HTML served as
`attachment`, magic-byte sniffing beats client-declared types), share-link
guessing (130-bit tokens), brute force (login + unlock rate limits with
lockout), stale grants (revoked/expired shares 404 like unknown ones).

**Out of scope / your job:** network transport (use HTTPS past your LAN —
see below), host hardening, Docker daemon security, client device security,
denial of service by LAN peers (rate limits blunt, don't eliminate).

## Defaults that protect you

- Passwords: argon2id (64 MiB, t=3). Sessions: 256-bit tokens, sha256 at
  rest, HttpOnly + SameSite cookies, idle (7 d) + absolute (30 d) expiry,
  rotation at login; password change revokes other sessions.
- Every mutation under cookie auth requires the `X-Requested-With` header
  (CSRF); API tokens (PATs) are Bearer-scoped `read|write`.
- Filenames are validated server-side (no `/`, `\`, NUL, control chars,
  leading/trailing dots/spaces, 255-byte cap); storage paths are built from
  UUIDs/hashes only, with containment checks — `../` cannot escape `/data`.
- Uploads stream in 64 KiB chunks (bounded RAM), per-chunk sha256, size caps,
  offset-serialized; downloads stream with single-range resume only (the
  multi-range DoS class is sidestepped by design; Starlette is pinned past
  the GHSA-7f5h-v6xp-fcq8 fix regardless).
- Share downloads enforce limits with an atomic conditional `UPDATE`
  (no race past `max_downloads`); repeat downloads reuse one analytics row.
- Container: runs as uid 1000, `cap_drop: ALL`, `no-new-privileges`, no
  published database port, secrets via env (never baked into the image).

## Your hardening checklist

1. **Complete setup immediately** — pre-owner, whoever reaches the server
   first claims it. Don't leave a fresh install onboarding for days.
2. **Strong `SECRET_KEY` + `POSTGRES_PASSWORD`** (32+ random chars each).
3. **HTTPS for anything beyond your LAN.** Session cookies and share
   passwords travel over the wire; on plain HTTP your network can read them.
4. **Reverse proxies:** keep `TRUSTED_PROXIES=0` unless the proxy is the only
   direct client; a wrong value lets clients spoof IPs past rate limits.
5. **Backups:** see BACKUP.md. Ransomware encrypts always-on disks too —
   keep one offline/remote copy.
6. **Updates:** `git pull && docker compose up -d --build`; migrations run
   automatically with a pre-migration backup.

## Reporting a vulnerability

**Do not open a public issue.** Email the maintainer (see git log / README
contact) with steps to reproduce; expect acknowledgment within 7 days.
Supported: the latest minor release only.
