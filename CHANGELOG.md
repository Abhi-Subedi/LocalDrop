# Changelog

All notable changes to LocalDrop are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) ·
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] — 2026-10-01

First usable release: a single-owner, self-hosted file drop box.

### Added

- **Auth:** first-run setup token (console + `/setup/token`, last-writer-wins),
  owner onboarding, login/logout, DB sessions (idle 7 d + absolute 30 d,
  rotation, per-device list/revoke), password change (revokes others), personal
  access tokens (`read|write` scopes), login rate limiting with lockout.
- **Files:** folders (create/rename/move incl. top level/delete/restore,
  cycle guard, case-insensitive collisions), file rename/move/copy/delete,
  trash with restore + purge, search, six sort orders, paginated listings.
- **Uploads:** native tus 1.0.0 subset (create/offset/append/cancel), per-chunk
  sha256, interrupt + HEAD resume, streaming bounded-RAM writes, dedup by
  content hash, `O_BINARY`-safe byte handling on all platforms.
- **Downloads:** streaming, single-range resume (`206`), suffix ranges,
  `ETag`/`If-Range`, magic-byte sniffing with an inline/attachment policy
  (SVG/HTML/XML always download, never render).
- **Sharing:** 26-char secure tokens, expiry, download limits (atomic,
  race-free), passwords (argon2id + HMAC cookie), revocation, QR codes,
  anonymous `/s/{token}` page, indistinguishable 404s for dead links.
- **UI:** React SPA — file browser (breadcrumbs, drag-drop, selection,
  context menus, previews, upload sheet with progress), shares manager,
  trash, settings (password, sessions, PATs), public share page;
  mobile-first, keyboard accessible, dark-mode aware.
- **Deploy:** multi-stage Docker image (non-root, `cap_drop ALL`,
  healthchecks), 2-service Compose stack, entrypoint with DB wait +
  pre-migration `pg_dump` valve + auto-migrate, `backup.sh`/`restore.sh`.
- **Docs:** README, INSTALLATION, CONFIGURATION, BACKUP, SECURITY, API,
  DEVELOPMENT, CONTRIBUTING, Code of Conduct.
- **Tests:** 20-test critical-path suite (auth, authz isolation, file +
  share lifecycles, tus failure modes, hostile names, binary byte-identity).

### Security

- See `docs/SECURITY.md` for the threat model and hardening checklist.
- Serve past your LAN only over HTTPS; complete setup immediately.

### Known limitations (V1)

- Single owner account; no multi-user sharing (use public links).
- Files live in folders (no top-level files); no folder/zip download.
- No live cross-device refresh yet (no SSE): the UI refreshes after your own
  actions; another device's changes appear on reload. SSE arrives in v1.1.
- LAN discovery is URL + QR (no mDNS advertisement yet).
- LAN discovery is URL + QR (no mDNS advertisement yet).

## [Unreleased]

### Fixed

- **Production builds shipped without any CSS.** `index.css` was never
  imported by the app entry, so the built SPA rendered unstyled; the stylesheet
  now emits and loads correctly (`assets/index-*.css`).

### Added

- **Restraint pass (anti-cliché audit):** removed decorative shadows from
  buttons/inputs/cards, icon-in-colored-tile empty states, backdrop blur,
  non-functional entrance animations, and pill-shaped action buttons; toolbar
  Folder/Upload buttons now appear only on mobile (the sidebar New menu covers
  desktop); radii unified at 8px for controls, 12px for surfaces.
- **New brand identity:** leaf logo + wordmark assets replace the teal mark;
  emerald-green (`#22C55E`) accent, near-black dark theme and neutral light
  theme per the visual spec, self-hosted Inter font (works offline on LAN),
  regenerated favicons/PWA icons/manifest, service-worker cache bumped.
- **Drive-style app layout:** top bar with global search + theme toggle +
  account menu, sidebar with "New" (upload/new folder) menu and pill
  navigation, file browser as a table with Name/Size/Modified columns
  (compact two-line rows on mobile), big page titles with breadcrumbs.
- **Theme system wired end to end:** system/light/dark picker in Settings,
  `ThemeProvider` mounted app-wide, persisted in localStorage, applied as
  `data-theme` on `<html>`.
- **Visual polish pass:** branded auth screens (Login/Setup), app shell with
  storage meter + avatar + active nav, grid view for the file browser
  (persisted per user), refined tokens/typography/focus states, skeleton
  loaders and composed empty states across screens, upload panel with live
  transfer speed, branded public share page.
- Tests: 26-test critical-path suite (adds blob self-healing, dedup race,
  cleanup-vs-live-uploads, metrics auth, missing-blob 404, multi-range).

### Added

- Master Specification (Phase 0): product vision, requirements, architecture,
  database, API, security/privacy threat model, frontend design system,
  engineering delivery docs, diagrams, risks register, Build Contract (BC-1…24),
  and Architecture Decision Records ADR-001…010 — `docs/`.
- Implementation Plan: 14-phase execution roadmap, vertical slices, 31 tracked
  issues (LD-001…031), 7 milestones, Definition of Done, AI coding agent rules —
  `IMPLEMENTATION_PLAN.md`.

### Notes

- `0.x` versions cover MVP development; the API stability promises of the spec
  begin at `1.0.0` (see `docs/spec/08-engineering.md` §9).
- Licensed under **AGPL-3.0** — ratified 2026-10-01 (ADR-010 Accepted, `LICENSE`
  added to the repo root).
