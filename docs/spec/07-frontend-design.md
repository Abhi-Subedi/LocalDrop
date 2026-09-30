# 07 — Frontend Architecture, Design System & Accessibility

*Status: Proposed. Stack decided in [ADR-008](../adr/ADR-008-frontend.md):
React 18 + TypeScript + Vite SPA · TanStack Router · TanStack Query · Tailwind CSS ·
Radix primitives. The visual language target: **modern, technical, trustworthy, calm.**
No third-party look-alike; LocalDrop's own system.*

---

## 1. Application structure

```text
frontend/src/
├── routes/            # TanStack Router file-routes (typed)
├── features/          # one folder per domain: files, uploads, shares,
│                      #   auth, settings, admin, publicShare
├── components/ui/     # design-system primitives (§3)
├── components/icons/  # bundled SVG icon set (file types, actions)
├── api/               # typed client generated from OpenAPI (CI)
├── stores/            # zustand for the few client-global states
│                      #   (upload manager, selection, toasts)
├── hooks/             # a11y focus utils, SSE→Query bridge
└── styles/            # tokens, tailwind config
```

**State policy:** server state lives in TanStack Query only (invalidated by SSE +
polling fallback, 03 §8); client state (selection, upload queue, modals) in zustand;
URL is the source of truth for navigation state (folder path, filters, selection
where shareable). A reload never loses your place or your upload queue (queue
persisted in IndexedDB → resume works after crash, FR-T1).

### Routes / pages

| Route | Page | Notes |
|---|---|---|
| `/setup` | First-run owner creation | Only while onboarding pending; shows setup-token field |
| `/login` | Login | Single card, no distractions |
| `/` | Dashboard | Quick actions: upload dropzone, recent files, storage summary, active shares — a launchpad, not a wall of widgets |
| `/files/…` | **File browser** (the core screen) | §2 |
| `/files/{id}` | Details drawer/page | Metadata, hashes, shares of this file, actions |
| `/uploads` | Upload manager | Global bottom-sheet + dedicated page; per-file progress, pause/resume/cancel/retry |
| `/shares` | My shares | Table: target, created, expiry, downloads/limit, status; edit/revoke |
| `/trash` | Trash | Restore / purge |
| `/settings/account` | Account | Password, sessions list, PATs |
| `/settings/admin` | Admin *(v1 minimal)* | Stats + audit feed (Phase 2 grows) |
| `/s/{token}` | **Public share page** | Zero-chrome download page; password gate; works logged-out; fully responsive |
| `*` | 404 | — |

### Responsive strategy

Three real layouts, one component tree (container queries, not device sniffing):

- **Mobile (< 640 px):** single-column list; bottom tab bar (Files / Uploads /
  Shares / Settings); details become full-screen sheets; actions behind long-press →
  action sheet; the upload button is a FAB. Touch targets ≥ 44 px.
- **Tablet (640–1024 px):** list + side details pane (select to preview);
  toolbar collapses to icon-only.
- **Desktop (> 1024 px):** sidebar navigation + main pane + persistent details
  drawer; grid/list toggle; full keyboard operation (§4).

---

## 2. File browser (the contract screen)

The file browser carries most of the product; it is specified most tightly.

- **Header:** breadcrumb path (clickable segments, overflow to "…" menu), search
  field (debounced 200 ms, searches current subtree), sort/filter control,
  view toggle, upload button.
- **Body:** virtualized grid or list (TanStack Virtual) — must hold 10⁵ rows.
  Grid card: icon/thumbnail, name (truncate middle, not end — keeps extensions
  visible), size, relative time. List row: name, size, type, modified, shares badge.
- **Selection model:** click/tap selects (single), ctrl/cmd multi, shift range,
  select-all; a selection action bar docks to the bottom (download `[Ph 3]`, move,
  copy, rename *(single)*, share *(single/multi→multi-share `[Ph 2]`)*, delete).
  Mobile: long-press enters selection mode.
- **Drag & drop:** drop anywhere on the page → upload with folder-visibility
  ("N files → Upload to *Photos*"); folder drags move items (with modifier for copy);
  cross-tab HTML5 drags accepted as file uploads.
- **Empty states:** each has a purpose — empty folder ("Drop files here" + upload
  CTA), no search results (query echo + clear), empty trash, empty shares.
- **Optimistic updates** for rename/move/create; failures roll back with a toast
  carrying the problem+json detail.

---

## 3. Design system (tokens & primitives)

**Foundations**

- **Type:** system font stack with `Inter var` bundled as progressive enhancement
  (self-hosted, no Google Fonts). Scale (rem): 12 / 14 (body) / 16 / 20 / 24 / 32;
  mono (`ui-monospace`) for hashes, sizes, paths — *technical* signal.
- **Space:** 4 px base grid; radii 4/8/12; 1 px hairline borders.
- **Color (semantic tokens, light + dark from day one):**
  - Neutrals: calm slate ramp (canvas `#fafafa`/dark `#0f1115`, surfaces, hairlines).
  - Accent: **deep teal** (`#0d7d8c` light / `#35c4d4` dark) — trustworthy-technical,
    4.6:1+ on canvas; used for primary actions, focus, links — never decoration.
  - Status: green (done), amber (verifying/expiring), red (error/destructive).
  - Contrast rule: text ≥ 4.5:1, large text/UI ≥ 3:1 (WCAG 1.4.3/1.4.11) — token
    values are chosen to pass, CI lighthouse/axe verifies.
- **Motion:** 120–200 ms ease-out micro-transitions only; full `prefers-reduced-motion`
  respect (§4). No parallax, no confetti.

**Primitives (all Radix-based where interactive — bought a11y, not built it)**

| Primitive | Rules |
|---|---|
| Button | Variants: primary (teal), secondary (outline), ghost, destructive. Sizes sm/md/lg; icon buttons always `aria-label`; loading state keeps width. |
| Input / Select | Label always visible (no placeholder-as-label); error text linked via `aria-describedby`; prefix/suffix slots (search icon, unit). |
| Card | Surface + hairline + 8 radius; hover raises hairline only. File card is a specialization (§2). |
| Dialog / Sheet | Radix Dialog; focus trap + restore; `Esc` closes; destructive confirmations require typing nothing extra (see Confirmation) — modal over sheet on mobile. |
| Dropdown menu | Radix; keyboard navigable; destructive items grouped with separator + red. |
| Toast | Bottom-right (bottom-center mobile); `aria-live="polite"`; errors offer "Details" → problem+json `detail`; never auto-dismiss errors. |
| Table | Used for shares/sessions/settings; sticky header; row actions in an overflow menu; horizontal scroll on mobile with shadow affordance. |
| File icon set | Bundled SVGs: image, video, audio, pdf, text/code, archive, generic + shared-badge, hash-pending badge. Monoline 1.5 px, 20/24 px. |
| Loading | Skeletons for lists (never spinners for structural loads); inline spinners for actions; upload rows show live byte progress + speed + ETA. |
| Empty / Error states | Illustration-optional, always: title, one-line explanation, one action. Error states include request id for bug reports. |
| Confirmation | Destructive single-item: dialog naming the item. Bulk delete: dialog with count. Trash purge (irreversible): requires typing `PURGE`. |

---

## 4. Accessibility (WCAG 2.2 AA target)

- **Keyboard:** full task completion without a pointer — navigation, browse,
  multiselect (ctrl/shift), context actions (menu key / `Shift+F10`), upload,
  share management. Visible focus ring (2 px accent offset) on every interactive
  element; roving `tabindex` in the file grid (arrows move, `Enter` opens,
  `Space` selects, `Escape` clears); skip-to-content link.
- **Screen readers:** semantic landmarks (`nav/main`), `aria-current` for location,
  live-region announcements for upload completion/toasts, descriptive labels on
  icon-only controls, file rows exposed as `role="option"` within a listbox-style
  composite in grid mode.
- **Focus management:** route changes move focus to the page `h1` (announced);
  dialogs trap and restore; destructive flows never strand focus.
- **Color & contrast:** tokens pre-validated (§3); information never encoded by
  color alone (badges carry text).
- **Motion:** `prefers-reduced-motion` collapses transitions to opacity-only/instant.
- **Targets:** ≥ 44 px on touch; WCAG 2.2 `2.5.8` satisfied by spacing, `2.4.11`
  focus-not-obscured by drawer placement.
- **Testing:** axe-core in component tests + Playwright a11y scan on core pages as a
  release gate; manual NVDA/VoiceOver pass documented per release (checklist in repo).

---

## 5. Internationalization

- **MVP:** all UI strings behind `t()` from day one (i18next, namespace per feature);
  English ships; locale from `Accept-Language`, override in settings.
- **Formatting:** dates (relative + absolute tooltip), numbers, byte units, and RTL
  mirroring via logical CSS properties — so **Arabic/Hebrew layout works** even
  before translations exist.
- **Phase 2:** translation files (fr/de/es priority by early-user demand signal
  `[DECISION REQUIRED: which locales ship]`), translator guide in CONTRIBUTING.
- Content (file names) is never translated or transformed.

---

## 6. Frontend performance budget

- Initial route ≤ 150 KB gzip JS (code-split per route; vendor chunk split);
  Lighthouse mobile ≥ 90 on the file browser with 10k files virtualized.
- Thumbnails lazy-load with `loading="lazy"` + intrinsic-size reservations (no CLS).
- Upload manager offloads hashing-free work (no client full-file hashing in v1 —
  per-chunk checksums only), so a 20 GB upload costs the tab no meaningful memory.

---

*Next: [08 — Engineering: repo, dev env, config, testing, CI/CD, releases](08-engineering.md).*
