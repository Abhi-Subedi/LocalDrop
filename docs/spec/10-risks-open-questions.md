# 10 — Risks, Open Questions & Decision Log

*Status: living document. Nothing on this page may be silently resolved — a resolved
item moves to an ADR and gets struck through here.*

---

## 1. [NEEDS VALIDATION] — assumptions to test empirically (Phase 1 spikes)

| # | Assumption | Test |
|---|---|---|
| V1 | Starlette `FileResponse` range/If-Range behavior is correct & fast enough for multi-GB, incl. behind common proxies | L5 harness: correctness fuzz (random ranges) + throughput vs. manual streaming |
| V2 | mDNS from the container: zeroconf under `network_mode: host` on Linux works reliably; confirm Docker Desktop (mac/ win) cannot (expected: no) | Spike on Pi 4 + Ubuntu host; document matrix |
| V3 | Android Chrome `.local` resolution status across OEM builds in 2026 | Physical/manual test or crowd-sourced docs issue |
| V4 | Argon2id (64 MiB) login latency on Raspberry Pi 4 class hardware stays under ~1 s | Benchmark on Pi 4 |
| V5 | Per-chunk DB offset commits sustain 8 MiB-chunk 1 GbE streams (125 chunks/s aggregate) without write latency wall | L5 concurrent-stream test; fallback design: commit every N MiB (journal in .part footer) |
| V6 | Pillow decompression-bomb caps behave as expected across formats | Adversarial image corpus |
| V7 | `chunk_hashes` jsonb history stays sane for huge uploads (100k chunks) | Cap + tail-re-read fallback design (04 §3.7) |
| V8 | SSE through the documented proxy snippets (nginx buffering off, Caddy, Traefik) holds 24 h with heartbeats | Nightly soak job |

---

## 2. [DECISION REQUIRED] — maintainer decisions blocking or shaping work

| # | Question | Recommendation on the table | Needed by |
|---|---|---|---|
| D1 | **License** (ADR-010) | AGPL-3.0 | Phase 0 exit — repo can't go public without it |
| D2 | Phase 2 translation locales | en + top 2 by early community demand | Phase 2 planning |
| D3 | Email's role when SMTP unset (admin-console reset only? skip verification?) | console reset; verification off by default | Phase 2 design |
| D4 | Multi-volume storage model (Phase 4): per-folder placement vs. pool/span | per-folder placement flag | Phase 4 |
| D5 | CLI implementation language (Phase 5) | Rust | Phase 5 |

---

## 3. Open questions (non-blocking, tracked)

- OAuth/OIDC provider scope for Phase 5 (generic authorize-code only? device flow for CLI?).
- Plugin trust model (Phase 5): in-process Python plugins are an arbitrary-code-execution surface by definition — sandbox story needed before any plugin system exists.
- E2EE vault mode: fundamentally conflicts with server-side previews/shares/dedup; would be a separate mode, not a feature. Parked indefinitely unless a contributor owns it.
- S3 backend (Phase 5): which of tus-over-S3 multipart vs. proxy-through-app; affects ADR-004's Storage protocol shape (keep protocol minimal until decided).
- Public registration flag (Phase 2): default off — but decide whether "off" also hides UI hints.
- Trash UX: retention vs. size cap (both?) — data point needed from real usage.

---

## 4. Risk register

| ID | Risk | L | I | Mitigation |
|---|---|---|---|---|
| R1 | **Scope creep kills the MVP** (the master prompt lists ~everything; teams like ours build half of it badly) | H | H | MVP gates in 02 §5; "designed-for, not built" discipline; roadmap reviews prune |
| R2 | **Security incident on an exposed instance** damages the project permanently | M | H | Threat model before code (06); L4 suites in CI; SECURITY.md + fast patch process; conservative defaults |
| R3 | **tus implementation bugs** corrupt uploads | M | H | The L2 lifecycle suite is exhaustive (kill -9 at every step); checksum headers; hash-verify before `verified` |
| R4 | **Bus factor = 1** early on | H | M | Documentation-first (this repo); boring stack choices maximizing contributor overlap; ADRs make decisions re-learnable |
| R5 | Docker networking breaks the flagship LAN experience (mDNS impossible on bridge) | M | M | QR-first posture; honest matrix (03 §7); opt-in host-network profile |
| R6 | Postgres major upgrades bite long-lived deployments | M | M | Pin majors in compose; upgrade docs per major; pre-migrate pg_dump valve |
| R7 | Supply-chain compromise of a dependency | L | H | Pinned digests, lockfiles, dependabot, pip-audit/pnpm-audit CI, SBOMs, minimal dep policy (every new dep needs a sentence in the PR) |
| R8 | Reverse-proxy misconfig breaks SSE/streaming (buffering, timeouts) | M | M | Documented copy-paste snippets incl. the non-default settings; polling fallback; E2E runs behind a proxy |
| R9 | Large-file edge cases on exotic filesystems (FAT 4 GiB, network mounts) | M | L | Docs: ext4/btrfs/ntfs/xfs supported; free-space + 423 guard; FAQ |
| R10 | Performance regressions land silently | M | M | Nightly L5 with numeric gates posted as artifacts |
| R11 | Name-collision semantics anger users (case-insensitive uniqueness) | L | L | Documented day one; escape hatch `[FUTURE: per-instance case-sensitive flag]` |
| R12 | AGPL hesitation suppresses corporate adoption & contributions | M | M | Honest ADR-010 analysis; decision is the founder's, not the spec's |

(L = likelihood, I = impact, H/M/L.)

---

## 5. Decision log (spec-time, superseded questions)

- ~~Frontend framework~~ → ADR-008 (Vite SPA over Next.js).
- ~~WebSocket vs SSE~~ → ADR-006 (SSE).
- ~~Redis in v1~~ → ADR-003 (no).
- ~~SQLite as default~~ → ADR-002 (Postgres default; SQLite = future single-binary mode).
- ~~tus vs custom protocol~~ → ADR-005 (tus subset).
- ~~Storage layout~~ → ADR-004 (content-addressed).

---

*Next: [11 — Build Contract](11-build-contract.md).*
