# API reference (v1)

Base path: `/api/v1`. Errors are `application/problem+json`
(`{type, title, status, detail, request_id}`).

**Auth:** cookie session (`ld_session`) after `POST /auth/login`, or
`Authorization: Bearer <PAT>` (scopes `read|write`). Cookie mutations must
send `X-Requested-With: localdrop` (CSRF). Rate classes: `auth` 10/5 min per
IP+identity with lockout, `share` 120/min/IP, `content` 60/min/IP,
`api` 600/min.

## Setup & account

| Method & path | Notes |
|---|---|
| `GET /setup/status` | `{onboarding_required}` |
| `GET /setup/token` | Fresh single-use token while onboarding pending |
| `POST /setup/owner` `{username, password, setup_token}` | → `201` owner; `410` done/expired |
| `POST /auth/login` `{username, password}` | → `204` + cookie; `401`; `429` locked |
| `POST /auth/logout` | → `204` |
| `GET /auth/sessions` · `DELETE /auth/sessions/{id}` | List / revoke own sessions |
| `GET /me` | Profile + storage usage |
| `PUT /me/password` `{current, new}` | Revokes other sessions |
| `POST /me/tokens` `{name, scopes}` · `GET /me/tokens` · `DELETE /me/tokens/{id}` | PATs (token shown once) |

Password rule: min 8 chars. Username: 3–32 chars, `a-z 0-9 . - _`.

## Files & folders

Children listing supports `?type=file|folder`, `?q=` (substring search),
`?sort=name|-name|size|-size|created_at|-created_at`, cursor `?cursor=` +
`?limit=` (max 500) → `{items, next_cursor}`.

| Method & path | Notes |
|---|---|
| `POST /folders` `{parent_id\|null, name}` | `201`; `409` name collision (case-insensitive) |
| `PATCH /folders/{id}` `{name}` | Rename |
| `POST /folders/{id}/move` `{new_parent_id\|null}` | `null` = top level; `422` on cycles |
| `DELETE /folders/{id}` | Soft-delete subtree → `{deleted: n}` |
| `POST /folders/{id}/restore` | Restore (409 on name collision) |
| `GET /folders/{id}/path` | Breadcrumb chain |
| `GET /folders/root/children` · `GET /folders/{id}/children` | Listing |
| `PATCH /files/{id}` `{name}` | Rename |
| `POST /files/{id}/move` `{folder_id, overwrite=false}` | `409` unless overwrite |
| `POST /files/{id}/copy` `{folder_id}` | Zero-byte copy (same blob; auto-renames) → `201` |
| `DELETE /files/{id}` → `204` · `POST /files/{id}/restore` | Trash / restore |
| `GET /trash` · `POST /trash/purge` | List / empty trash |
| `GET /files/{id}/content` | Stream; `Range: bytes=a-b` → `206`; suffix ranges OK; multi-range degrades to `200`; `ETag`/`If-Range` resume |
| `GET /files/{id}/thumbnail` | WebP (404 until generated) |
| `GET /files/{id}/preview` | `{text, charset, truncated}` for text/JSON (≤ 256 KiB) |
| `GET /health/live` (no DB) · `GET /health/ready` (DB + storage) | Monitoring |

Content disposition: safe types (images, AV, PDF, plain text) render
`inline`; SVG/HTML/XML and anything unrecognized download as `attachment`
— declared type **and** sniffed bytes can each force attachment.

## Resumable uploads (tus 1.0.0 subset)

Extensions: `creation, expiration, termination, checksum` (sha256 per chunk).

```http
POST /uploads
  Upload-Length: <total bytes>
  Upload-Metadata: filename <b64>,folderId <b64>,filetype <b64>
→ 201, Location: /api/v1/uploads/<id>, Upload-Offset: 0

HEAD /uploads/<id>            → Upload-Offset, Upload-Length (resume here)
PATCH /uploads/<id>
  Upload-Offset: <must equal server offset or 460>
  Content-Type: application/offset+octet-stream
  Content-Length: <this chunk, 1..8 MiB>
  Upload-Checksum: sha256 <b64>   (optional but recommended; 460 + no advance on mismatch)
→ 204, Upload-Offset: <new>; X-Localdrop-File: <file id> when complete
DELETE /uploads/<id>          → cancel (204)
GET /uploads                  → active sessions
```

Rules: total ≤ max size (`413`), per-chunk ≤ 8 MiB (`460`), unknown session
→ `404`, offset mismatch → `460`. Finalize is automatic on the completing
chunk; hashing/dedup runs right after (status `pending` → `verified`).

`tus-js-client` works out of the box (the web UI uses it with
`Upload-Checksum`).

## Sharing

| Method & path | Notes |
|---|---|
| `POST /shares` `{file_id, expires_at?, max_downloads?, password?}` | → `201` `{id, token, url, qr_svg, …}` (26-char token) |
| `GET /shares` | Manage list |
| `PATCH /shares/{id}` | Update expiry/limit/password |
| `DELETE /shares/{id}` | Revoke → `204` |
| `GET /shares/{token}` | **Public.** Metadata (+ `requires_password`); unknown/revoked/expired → identical `404` |
| `POST /shares/{token}/unlock` `{password}` | → `204` + `ld_share` cookie (1 h) |
| `GET /shares/{token}/files/{fileId}/content` | **Public download.** `403 share-locked` / `403 share-limit-reached` |

The visitor page lives at `/s/{token}` (no account needed, mobile-first).
