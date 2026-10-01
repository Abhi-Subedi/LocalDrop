# Security Policy

## Reporting a vulnerability

**Do not open a public issue.** Use
[GitHub's private vulnerability reporting](https://github.com/Abhi-Subedi/LocalDrop/security/advisories/new).

That opens a private thread visible only to you and the maintainer. You will get
an acknowledgement within 7 days. If the report is actionable you will get a fix
or a mitigation plan before it is published anywhere.

If private reporting is unavailable to you, email the maintainer at the address
on [the repository profile](https://github.com/Abhi-Subedi) and say "security
report" in the subject.

Please include, where you can:

- the LocalDrop version (`curl -s http://<host>/api/v1/version`, or the About
  panel in Settings)
- how it was installed (Docker, native binary, Homebrew, source)
- reproduction steps, ideally a `curl` script
- what an attacker gains

**Please do not test against other people's deployments.** Use a local
instance, or one you have permission to test. Rate-limit yourself to avoid
taking a service down. `docs/SECURITY.md` has the threat model if you want to
know what is already defended.

## What gets a fast response

| Class | Examples | Target |
|---|---|---|
| Critical | Auth bypass, RCE, path traversal out of the data dir, secret disclosure, SQL injection reachable without auth | Patch within 7 days |
| High | Stored XSS served to an authenticated owner, share-token bypass, DoS with a few requests | Patch within 14 days |
| Medium | Information leak without secrets, missing hardening on a documented path | Next release |
| Low | Defense-in-depth gaps, hardening suggestions | Triaged, not scheduled |

Out of scope, and not a vulnerability: LocalDrop has one owner account by
design, so the owner can read and delete everything. That is the product.

## Supported versions

Only the latest minor release receives fixes. When a security fix lands for
1.1.x, the 1.1.4 release is the one to run.

| Version | Supported |
|---|---|
| 1.1.x | Yes |
| 1.0.x | No — upgrade |
| < 1.0 | No |

## Hardening your own deployment

LocalDrop is built for a trusted LAN, not for the open internet. If you expose
it beyond your network, you are changing the threat model — read this first.

1. **Serve it over HTTPS.** Everything is plain HTTP by default, including your
   session cookie. Put Caddy, nginx or Tailscale in front and terminate TLS
   there. Never port-forward LocalDrop straight to the internet.
2. **Complete setup immediately.** The first-run setup token creates the owner
   account; anyone who reaches an un-onboarded instance can claim it.
3. **Keep `LOCALDROP_TRUSTED_PROXIES=0`** unless a proxy is genuinely the only
   path in. Each trusted hop lets the previous hop forge a client IP, which
   defeats per-IP rate limiting.
4. **Set a strong `LOCALDROP_SECRET_KEY`** (32+ characters). It signs sessions.
   The installers generate one for you.
5. **Turn up the reverse proxy's read timeout** for large transfers
   (`proxy_read_timeout 3600s`, `proxy_buffering off`).
6. **Restrict who can reach the port** — a firewall rule or a VPN is worth more
   than any amount of application hardening.
7. **Keep it updated.** `docker compose pull && docker compose up -d`, or
   re-run the installer.

The full threat model, the defences already in place, and the known limits are
in [`docs/SECURITY.md`](docs/SECURITY.md).

## A note on disclosure

Reporters are credited unless they ask not to be. There is no bug bounty; this
is a volunteer project. If a report turns out to be a hardening suggestion
rather than a vulnerability, that is still worth telling us about.
