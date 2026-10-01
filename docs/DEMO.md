# Public demo

LocalDrop ships a **demo mode** and a GitHub Actions workflow that publishes a
live, interactive instance so a visitor can try it without installing anything.

```bash
gh workflow run demo.yml
```

The URL appears in the job summary. The instance lives as long as the job.

## What a visitor gets

They open the URL and are **signed in automatically** — a throwaway account is
created for them, with an empty file tree of their own. Everything the app does
normally, it does: drag-and-drop uploads, folders, search, previews, share
links with expiry and passwords, trash, and resumable uploads of a few
megabytes.

Nothing is asked of them up front. The first click is theirs, which is the
whole point of a demo: no setup token to find in a console log, no password to
invent.

Above the file list, a banner tells them the truth: this is a public demo,
uploads are capped at 25 MB, and everything they upload is deleted after the
TTL.

## Why demo mode exists rather than just a tunnel

Pointing a reverse proxy at a normal LocalDrop instance does not produce a
working public demo. Three things break, and all three are fixed in the app
rather than worked around in the infrastructure:

**1. Every visitor shares one IP.** Rate limits are per-IP. Behind a proxy,
`trusted_proxies=1` means all traffic arrives from one address, so the auth
limit of 10 attempts per 5 minutes becomes a *shared* budget — one person
fumbling a login locks out everyone. In demo mode the `share`, `content` and
`api` limits key on the session instead of the socket. The `auth` limit stays
per-IP on purpose: there, the socket really is the signal.

**2. There is one owner account.** On a first-run server, whoever reaches the
setup token first becomes the owner. A public URL means a stranger's crawler
wins that race, and then every visitor shares one account and can read or
delete everyone else's files. Demo mode instead mints an isolated `user`-role
account per visitor, and opens a **claim window** so the maintainer can take the
owner account before strangers arrive.

**3. Nothing gets cleaned up.** A demo accumulates uploads forever. In demo mode
each account and its files are deleted after `LOCALDROP_DEMO_TTL_MINUTES` of
inactivity, on a background job, with blobs reclaimed only when no other user
still references them.

## What it is not

Demo mode does **not** make LocalDrop safe to run on the open internet. It makes
one narrow, supervised thing survivable: a public demo where strangers upload
throwaway files that are deleted shortly. It does not add TLS, it does not fix
the fact that the app is built for a trusted LAN, and it is not a substitute for
the hardening in [`SECURITY.md`](../SECURITY.md).

The workflow's own lifetime is part of the safety model: the tunnel closes and
the volumes are deleted when the job ends, so there is no permanent target and
one visitor's upload is never the next visitor's problem.

## The claim window

For the first `LOCALDROP_DEMO_CLAIM_WINDOW_MINUTES` after boot — until someone
creates an owner — the demo hands out sessions to anyone. That is deliberate:
a live demo is worthless if a crawler locked it before you could look at it.

Claim the owner account as soon as the tunnel is up:

```bash
bash scripts/demo-claim.sh https://something.trycloudflare.com
```

It refuses to touch anything that is not a demo instance, and creating the owner
closes the window: `/api/v1/demo/session` then returns `503` and no new visitors
are served. Existing throwaway accounts still expire on their own TTL.

To re-open the demo, delete the volume and start again:

```bash
docker compose -f docker-compose.demo.yml down -v
docker compose -f docker-compose.demo.yml up -d
```

## Running a demo yourself

The stack is ordinary Compose with demo mode on:

```bash
export LOCALDROP_SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))')
export DEMO_POSTGRES_PASSWORD=$(python3 -c 'import secrets;print(secrets.token_urlsafe(24))')
docker compose -f docker-compose.demo.yml up -d
```

`docker-compose.demo.yml` is a **separate file** from `docker-compose.yml` on
purpose. The production stack should not be one environment variable away from
being a public demo.

To put it on the internet yourself, add a tunnel in front of `127.0.0.1:8080`
(Cloudflare `cloudflared tunnel --url`, Tailscale Funnel, or ngrok). The demo
compose file binds the port to loopback specifically so the tunnel process is
the only thing that can reach it.

## Configuration

Every setting, with defaults, is in
[`CONFIGURATION.md`](CONFIGURATION.md#public-demo-mode). The short version:

| Setting | Default | Why |
|---|---|---|
| `LOCALDROP_DEMO_MODE` | `false` | Off by default. The demo endpoints are not mounted at all when it is off — not a 404 that advertises them. |
| `LOCALDROP_DEMO_TTL_MINUTES` | `60` | How long a visitor's files survive after they stop. |
| `LOCALDROP_DEMO_MAX_UPLOAD_BYTES` | `25 MiB` | A demo does not need 100 GiB, and a runner has 14 GB. |
| `LOCALDROP_DEMO_MAX_USERS` | `200` | A crawler cannot fill the users table. Surplus visitors get `503` and a `Retry-After`. |
| `LOCALDROP_DEMO_CLAIM_WINDOW_MINUTES` | `30` | How long the maintainer has to take the owner account. |
| `LOCALDROP_DEMO_NOTICE` | *(a sentence)* | The banner text. Say what is true about your instance. |

## Costs and limits

- **A GitHub-hosted runner is a bad long-term host.** 14 GB of disk, 2 cores, an
  IP range that is heavily abused, and jobs capped at 6 hours. The workflow
  defaults to holding the tunnel for 4 hours, which is the honest ceiling.
- **`trycloudflare.com` URLs are ephemeral** and change on every run. A quick
  tunnel is fine for a demo; it is not a hostname.
- **The runner sleeps** when idle, so the first request after a quiet period can
  take a few seconds.
- **A persistent URL needs a real host** — a small VPS, a NAS, or a home server.
  Nothing in the app changes; you would swap the tunnel for Caddy and point it at
  the same compose file.

## See also

- [`CONFIGURATION.md`](CONFIGURATION.md#public-demo-mode) — every demo setting
- [`SECURITY.md`](../SECURITY.md) — the threat model, and why this is a demo, not
  a deployment
- [`DEVELOPMENT.md`](DEVELOPMENT.md) — the rest of the CI setup
