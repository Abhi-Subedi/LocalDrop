# 06 — Security Model & Privacy Model

*Status: Proposed. The threat model below is the contract security testing implements
(08 §testing L4). Rule from the spec: authentication existing is never the argument
that the system is secure — every threat below is analyzed as if auth partially fails.*

---

## 1. Trust boundaries

```text
┌─ Untrusted ───────────────────────────────────────────┐
│  Any LAN/remote HTTP client                           │
│  Public share-link visitors (anonymous)               │
│  Uploaded file *contents* (forever untrusted)         │
├─ Boundary 1: HTTP layer (authn, rate limits) ─────────┤
│  Authenticated principal (session or PAT)             │
├─ Boundary 2: Service layer (authz per object) ────────┤
│  Owner (v1: sole role)                                │
├─ Boundary 3: Storage layer ───────────────────────────┤
│  Filesystem blob store (paths from server data only)  │
├─ Boundary 4: Container ───────────────────────────────┤
│  Host (volume mount, docker socket — NOT mounted)     │
└───────────────────────────────────────────────────────┘
```

Deployment assumption tiers (documented, not enforced): **T1 isolated LAN** (default
posture), **T2 LAN with hostile devices** (coffee-shop-class Wi-Fi — HTTP is
plaintext; docs mandate TLS via reverse proxy), **T3 internet-exposed** (docs mandate
TLS + optionally VPN/tailscale; LocalDrop's own posture must survive T3).

---

## 2. Threat model

Format: **Attack → Defense → Where the defense lives.**

### 2.1 Path traversal & filename attacks

- **Attack:** `fileName = "../../../../etc/passwd"` or `"..\..\windows\win.ini"` on
  upload; crafted folder names; unicode tricks (`ﬁ` ligatures, RTL overrides, `..%2f`
  after decoding) aiming at filesystem paths or at URL joins.
- **Defense:**
  1. **User strings never reach filesystem paths** — paths are built only from UUIDs
     and hex hashes (03 §4.2 rule 1). This is the primary control.
  2. Names are validated at the schema layer: NFC normalization, no `/`, no `\`,
     no NUL/control chars, no leading/trailing whitespace/dot, 1–255 **bytes**;
     RTL-override and zero-width characters stripped (rendering attack on the *UI*
     list, e.g. spoofing `invoice.pdf`).
  3. A canary integration test feeds the full malicious-name corpus through every
     endpoint accepting a name.
- **Where:** Pydantic schemas (`NameStr` type, reused everywhere) + integration test
  corpus + storage layer (defense in depth: it also rejects any constructed path
  outside the data dir via `Path.resolve()` + prefix check).

### 2.2 Unauthorized file access / broken access control

- **Attack:** ID enumeration (`/api/v1/files/{uuid}` guesses — uuidv7s are
  time-ordered, lowering entropy slightly); accessing another user's files (Phase 2);
  share-link token brute force; accessing trash; `folder_id` cross-reference in
  move/copy to someone else's folder.
- **Defense:**
  1. Every object-touching service call takes an explicit `Principal` and performs
     an **object-level** check (`owner_id == principal.user_id`; Phase 2: folder-ACL
     walk) — route-level auth is never sufficient. Standardized check functions are
     the only way rows are fetched (`get_owned_file(...)`, never `session.get(File, id)`).
  2. Share tokens: 130 bits CSPRNG (base32) — brute force at `share` rate limit
     (120/min/IP) ≈ 10³⁰ years; unknown vs. revoked vs. expired tokens all return
     identical `404`/`403` bodies crafted to prevent oracle behavior (validity
     distinguishable only by the token holder — password-protected shares reveal
     `requires_password: true` *only after* the token is proven valid, which the
     holder already knows).
  3. Trash and staging are behind the same checks (soft-deleted ≠ accessible).
  4. Authorization test matrix (L4): for every endpoint × every principal type ×
     every object-ownership combination, assert allow/deny — **the matrix is
     generated from the route table**, so new endpoints must join it.
- **Where:** services layer + generated test suite.

### 2.3 Session theft & fixation

- **Attack:** XSS or network sniffing yields the session cookie; attacker rides the
  session; fixation by planting a token.
- **Defense:**
  1. Cookies: `HttpOnly` (no JS read), `Secure` (auto when TLS), `SameSite=Lax`,
     server-side opaque token (256-bit) stored **hashed**; DB theft ≠ usable tokens.
  2. Rotation: session id regenerated at login; idle (7 d) + absolute (30 d) expiry;
     password change revokes everything else; session list UI enables
     self-audit ("that's not my device" ⇒ revoke).
  3. Sniffing on plain HTTP is acknowledged (T2): docs state LAN-HTTP is acceptable
     *only* on trusted networks, and the onboarding UI shows a persistent
     "unencrypted connection" notice when the request is not TLS.
- **Where:** auth service + middleware + UI notice.

### 2.4 CSRF

- **Attack:** malicious webpage in the victim's browser issues state-changing
  requests to `http://localdrop.local/...` riding the ambient cookie.
- **Defense:** `SameSite=Lax` blocks cross-site POST/PATCH from subresources/foreign
  origins; additionally all unsafe methods require the non-simple header
  `X-Requested-With: localdrop` (cannot be attached by HTML forms or plain `fetch()`
  cross-origin without CORS preflight approval, which the API never grants).
  `Lax` top-level GET navigation is safe (all mutations are non-GET).
- **Where:** middleware (rejected before routing) — single enforcement point, tested.

### 2.5 XSS

- **Attack:** stored XSS via filenames/share names rendering in the file list;
  reflected XSS via error details; DOM XSS in the SPA (URL params into innerHTML);
  XSS via **file content** (SVG upload served inline).
- **Defense:**
  1. React's escaping by default + ESLint rule banning `dangerouslySetInnerHTML`
     (allowlist: none in v1).
  2. **Serving policy table (§4):** only a fixed allowlist of types gets
     `Content-Disposition: inline` + a restrictive `Content-Security-Policy` sandbox
     header on content responses; **SVG and HTML are always `attachment`** (SVG is
     script-capable). Text previews render server-sanitized-charset text into a
     `<pre>`, never an iframe of raw bytes.
  3. Tight global CSP for the SPA itself: `default-src 'self'; frame-ancestors 'none';
     object-src 'none'; img-src 'self' data:` — no inline scripts (Vite hashes),
     making even an injected-string bug harder to leverage.
  4. Filename rendering: display exactly what's stored (already normalized/stripped
     §2.1) with `text-overflow` CSS — no HTML construction from names.
- **Where:** serving policy (download router) + CSP headers + frontend lint rules.

### 2.6 SQL injection

- **Defense:** SQLAlchemy bound parameters exclusively; **no f-string/SQL-text
  interpolation rule enforced by lint** (`ruff` custom check / `bandit` S608);
  `pg_trgm` search uses parameterized `ILIKE` with escaped wildcards. Reviewer
  checklist item for any raw SQL (rare, must justify).
- **Where:** data-access layer + CI.

### 2.7 SSRF

- **Attack:** features that fetch remote URLs (link previews, remote import) turning
  the server into a proxy into the LAN (router admin pages, cloud metadata).
- **Defense (architectural):** **LocalDrop v1 has zero URL-fetching features** — the
  offline rule (NFR-12) forbids outbound HTTP at runtime, enforced by a test that
  fails if any code path performs an outbound connection during the full test suite.
  If URL-fetching features arrive later (favicon fetch etc.), they require a new ADR
  with egress allowlist + IP-range blocking — noted in the Build Contract.
- **Where:** architecture rule + test `test_no_outbound_connections`.

### 2.8 Malicious uploads (content attacks)

- **Attack:** malware hosting (localdrop as C2 drop); polyglot files
  (JPEG/PHP, PDF/JS); stashed content later served inline; **SVG with embedded
  scripts**; **ZIP bombs** (nested/quadratic zip awaiting extraction — we don't
  extract); huge decompression via preview pipeline.
- **Defense:**
  1. Storage is inert: content-addressed blobs with no execution (no PHP interpret
     anywhere; static file serving never executes).
  2. **Magic-byte sniffing at finalize** (`libmagic`/`python-magic`): recorded
     `detected_type`; if it contradicts declared `mime_type`, the *serving* type is
     the sniffed one and UI shows it (MIME spoofing defense, §2.9).
  3. Serving policy allowlist (§4) means even polyglots download as `attachment`
     unless the sniffed type is on the safe-inline list.
  4. No archive extraction ever in v1; zip download is *generation*, not extraction
     (Phase 3), and streamed with entry-count/size caps.
  5. Thumbnails decode images with Pillow inside the sandboxed process pool; decode
     bombs (decompression bomb JPEGs/PNGs) mitigated by Pillow's
     `ImageFile.MAXBLOCK`/pixel caps: images over 80 MP (configurable) are not
     thumbnailed — icon only. `[NEEDS VALIDATION: exact Pillow cap behavior per format]`
  6. Virus scanning is **not in v1**; optional ClamAV sidecar is Phase 4 — the
     schema (`blobs.scan_status`) and job seam exist so it's additive.
- **Where:** finalize service + serving policy + thumbnail job.

### 2.9 MIME spoofing

- Covered by §2.8(2): sniffed type wins for serving decisions; declared type is
  display metadata. `X-Content-Type-Options: nosniff` on every response.

### 2.10 Huge-file / resource-exhaustion abuse

- **Attack:** many concurrent uploads filling the disk; 10⁶ tiny files bloating DB;
  one 100 GB upload with 1-byte chunks (DB offset-write storm); slowloris-style
  drip-feeding PATCH bodies; share-link scraping.
- **Defense:** max upload size config (default 100 GiB, `413` beyond); **free-space
  guard** (423) at session create *and* re-checked every 1 GiB appended; per-user
  session cap (20); minimum chunk size 64 KiB (below → `400`, kills the write-storm
  economics); per-chunk max 64 MiB; uvicorn `--limit-concurrency` backpressure;
  listing/search results capped by cursor pagination; per-IP `share` and `content`
  rate limits; slow-body timeouts (upload PATCH read timeout 60 s).
- **Where:** upload service + uvicorn config + rate limiter.

### 2.11 Rate-limit bypass

- **Attack:** rotating source IPs (IPv6 /64 spray), header spoofing (`X-Forwarded-For`
  forgery to reset buckets), distributed brute force on login/share passwords.
- **Defense:**
  1. `X-Forwarded-For` is trusted **only** from configured proxy hops
     (`LOCALDROP_TRUSTED_PROXIES` count, default 0) — by default the socket peer is
     the client.
  2. IPv6 keys bucket by /64, not /128.
  3. Brute-force-sensitive buckets key on **(IP + target identity)** for login and
     (share-token) for unlock — spraying across IPs still locks the *account/share*
     with progressive backoff (5 attempts → 15 min lock on the identity, logged +
     audited, surfaced to the owner in the admin audit feed).
  4. Limits are conservative defaults documented as tunable; per-process accuracy
     acknowledged (single-process v1 makes them exact).
- **Where:** rate-limit service.

### 2.12 Share-link abuse

- **Attack:** link forwarded beyond intent (mitigated by expiry/password/limits —
  user controls); crawler finds link (token entropy §2.2); password brute force
  (§2.11(3)); link content served to third parties who *do* hold the password
  (accepted risk — bearer semantics, documented); abusing unlimited downloads for
  bandwidth DoS (content rate class).
- **Defense:** already-stated controls + share creation defaults that nudge safety:
  UI defaults expiry to 7 days (user can clear); audit events on
  create/unlock-failure/limit-reached visible to owner.
- **Where:** share service + UI defaults.

### 2.13 Symlink attacks

- **Attack:** if the data dir is manipulated locally (or a malicious "restore" zip
  contains symlinks), blob reads could escape via symlinked paths; an upload's
  staging path replaced by a symlink to `/etc/shadow` → appended to.
- **Defense:** storage layer opens staging/blobs with `O_NOFOLLOW` (and on Linux,
  `O_CREAT|O_EXCL` for creation); `Path.resolve()` containment check on every open
  (§2.1(3)); the documented restore procedure never extracts archives as root into
  the data dir. Multi-host NFS subtleties documented as unsupported in v1.
- **Where:** storage layer.

### 2.14 Docker/container risks

- **Threats:** container escape via excessive privileges; docker-socket mount;
  root-owned volume data complicating host access; image supply chain; secret leakage
  via env in logs.
- **Defense:**
  1. Container runs **non-root** (`uid 1000 localdrop`), read-only rootfs (only
     `/data` and `/tmp` writable), `cap_drop: ALL` + `no-new-privileges`, no docker
     socket, no host PID/NET (except opt-in mDNS host-network profile, clearly
     flagged as reducing isolation).
  2. Secrets: `LOCALDROP_SECRET_KEY` via compose secrets/env_file (0755-file warning
     in docs); **logs never print full env** (startup logs a redacted config dump).
  3. Supply chain: base images pinned by digest (python:3.12-slim, postgres:16);
     dependabot; CI builds attest with SBOM (syft) `[Phase 1 lightweight]`;
     trivy scan on every release; releases signed with cosign `[Phase 4]`.
  4. Postgres container: internal compose network only, never publishes a port by
     default, strong generated password in a volume-persisted env file.
- **Where:** docker/ compose + CI.

### 2.15 Information disclosure

- Logs contain request paths (with ids), IPs, usernames — **never** share tokens
  (logged truncated), session tokens, passwords, or file content. Error responses
  echo `request_id` only. `Server` header minimized; no framework banners.

### 2.16 Container of containers — PostgreSQL

- Postgres runs with `POSTGRES_INITDB_ARGS` tuned small; superuser password is
  random-generated per install (entrypoint writes `pg.env` with 0600); app DB user
  has only `localdrop` database rights. Backup docs use the app role (least privilege).

---

## 3. Authentication & authorization design (summary)

- **AuthN:** argon2id (memory 64 MiB, t=3, p=4 — OWASP 2024-class parameters,
  re-evaluated at release `[NEEDS VALIDATION: benchmark on Pi 4 so login stays < 1 s]`);
  opaque sessions (§2.3); PATs (scoped, hashed, last-used tracking).
- **AuthZ:** role enum `owner > admin > user > viewer` defined in v1 schema; v1
  runtime has exactly one `owner`. Authorization is **object-level checks in
  services** (§2.2) — Phase 2 folder ACLs extend the check function, not the call
  sites. Share access is a separate capability path (token + optional password +
  expiry + count), never entangled with user authz.
- **Onboarding:** first-run prints a 12-char setup token to console (the only
  privileged channel a fresh install has); `POST /setup/owner` consumes it (single
  use, 15 min TTL). Until consumed, every other endpoint returns `503 setup-pending`.

---

## 4. Content-serving policy table (MIME + disposition)

| Sniffed type | Disposition | Preview path |
|---|---|---|
| image/jpeg, png, webp, gif, avif | `inline` | thumbnail + lightbox |
| image/svg+xml | **`attachment`** | icon only (script-capable) |
| video/* , audio/* (mp4/webm/m4a/mp3/ogg/opus/flac) | `inline` | native player |
| application/pdf | `inline` (with `CSP: sandbox`) | embedded viewer |
| text/* (plain, code, csv, markdown) | `inline` as `text/plain` | server-capped text preview |
| application/json, xml | `inline` as text | text preview |
| **everything else** | **`attachment`** | icon only |

Every content response: `X-Content-Type-Options: nosniff`,
`Content-Security-Policy: default-src 'none'; sandbox` (top-level navigations to
inline content are allowed to render *nothing* active), `Content-Disposition` with
RFC 5987 filename encoding.

---

## 5. Security release checklist (gates for v1.0)

- [ ] All L4 security suites green: authorization matrix, malicious-name corpus,
      traversal corpus, CSRF negative, session-fixation, share-token entropy audit.
- [ ] `test_no_outbound_connections` green (NFR-12).
- [ ] Dependency scan (pip-audit, pnpm audit) with no untriaged highs.
- [ ] Container config audit against §2.14 (non-root, caps dropped, RO rootfs).
- [ ] Argon2 params benchmarked on Raspberry Pi 4.
- [ ] Manual review pass of the serving-policy table vs. an adversarial corpus
      (polyglots, SVG, RFC-violating content types).
- [ ] SECURITY.md published with a private reporting channel.

---

## 6. Privacy model (the whole truth)

**What the server records** (this list is exhaustive and CI-tested — a test fails if
a new table/column lacks an entry here):

| Data | Where | Lifetime | Rationale |
|---|---|---|---|
| Account row (username, optional email, argon2 hash) | `users` | until deletion | authentication |
| Session rows (hashed token, last IP, UA, timestamps) | `sessions` | ≤ 30 d idle-bound | login function + user-visible security self-audit |
| PATs (hashed, label, last_used) | `personal_access_tokens` | until revoked | API access |
| File/folder metadata (names, sizes, types, timestamps) | `files`, `folders` | until deleted + trash retention | the product |
| Blob hashes + sizes | `blobs` | with files | integrity, dedup |
| Upload session records | `upload_sessions` | ≤ 7 d after activity | resumability |
| Share definitions + anonymous access counters | `shares`, `share_downloads` | until revoked + 30 d | share limits/stats |
| Security audit events (login, share unlock failures, deletions, config changes) | `audit_events` | 180 d default | attack detection for the owner |
| Request logs (IP, path, status, request id) | container stdout | operator's log rotation (docs: 14 d JSON suggestion) | debugging; no tokens/content |

**Telemetry: none.** No analytics, crash reports, version pings, or update checks.
The egress test (§2.7) enforces it mechanically, not rhetorically.

**Offline: fully.** Fonts/icons/CSP'd assets are bundled; QR generation is in-process.

**What the admin sees:** v1 owner sees everything above (they run the box). From
Phase 2: admins see metadata + audit events of their instance but UI never previews
file content without an explicit open action (which is itself audited).

**What users see about themselves:** session list (MVP); audit self-history (Phase 2).

**Deletion honesty:** account/file deletion ⇒ soft-delete → trash → purge → blob GC;
docs describe the disk-level story honestly (purged blobs are unlinked; the DB no
longer references them; we do not overwrite flash media — documented).

---

*Next: [07 — Frontend, design system, accessibility](07-frontend-design.md).*
