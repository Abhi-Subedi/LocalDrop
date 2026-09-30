# 09 — Architecture Diagrams (Mermaid)

*Status: Proposed. These render on GitHub. Keep them in sync — a diagram that
disagrees with ADRs loses to ADRs.*

---

## 1. System architecture

```mermaid
flowchart LR
    subgraph clients["Clients (any device on LAN / remote via proxy)"]
        B["Browser SPA<br/>(React, served by backend)"]
        C["curl / scripts / future CLI<br/>(PAT auth)"]
        P["Anonymous share visitor"]
    end

    subgraph app["localdrop container — single FastAPI process"]
        API["REST API /api/v1"]
        SSE["SSE /events"]
        SPA["Static SPA serving"]
        SVC["Services:<br/>auth · files · shares ·<br/>upload engine · thumbnails"]
        JOBS["Job scheduler:<br/>hash · thumbs · GC"]
        BUS["EventBus (in-process)"]
    end

    DB[("PostgreSQL 16<br/>users · sessions · folders · files<br/>blobs · upload_sessions · shares · audit")]
    FS[("Data volume<br/>blobs/ · staging/ · thumbs/")]

    B --> SPA
    B --> API
    B <-.->|SSE push| SSE
    C --> API
    P --> API
    API --> SVC
    SVC --> DB
    SVC --> FS
    JOBS --> FS
    JOBS --> DB
    SVC --> BUS
    BUS --> SSE
```

---

## 2. Authentication flow (login)

```mermaid
sequenceDiagram
    participant U as Browser
    participant A as API
    participant DB as PostgreSQL

    U->>A: POST /api/v1/auth/login {username, password}
    A->>A: rate-limit check (IP + username bucket)
    A->>DB: fetch user by username
    A->>A: argon2id verify (constant-time)
    alt invalid
        A-->>U: 401 problem+json
        A->>DB: audit auth.login_failed
    else valid
        A->>DB: insert session (sha256(token), expiry)
        A-->>U: 200 + Set-Cookie ld_session (HttpOnly, SameSite=Lax)
        A->>DB: audit auth.login
        U->>A: GET /api/v1/me (cookie)
        A-->>U: 200 profile
    end
```

Onboarding pre-step: first run prints a one-time setup token in the container
console; `POST /setup/owner` consumes it and creates the owner (06 §3).

---

## 3. File upload flow (tus resumable)

```mermaid
sequenceDiagram
    participant C as Client (tus-js)
    participant A as API
    participant S as Staging (data dir)
    participant DB as PostgreSQL
    participant J as Hash job

    C->>A: POST /api/v1/uploads {fileName, folderId, totalSize}
    A->>A: authz + size limit + free-space ≥ 102%
    A->>DB: insert upload_sessions (offset=0)
    A->>S: create <uuid>.part
    A-->>C: 201 + Location: /uploads/{id}

    loop per 8 MiB chunk (retryable)
        C->>A: PATCH /uploads/{id}  Upload-Offset: N  [Upload-Checksum: sha256]
        A->>A: offset contiguity + chunk checksum verify
        A->>S: append (64 KiB stream loop — RAM bounded)
        A->>DB: update offset
    end

    C->>A: PATCH final chunk (offset == totalSize)
    A->>S: fsync + fsync(dir)
    A->>DB: tx: blobs(pending) + files row, session=finalized
    A-->>C: 201 file resource (hash_status=pending)

    J->>S: stream read → sha256
    J->>S: os.replace staging → blobs/ab/cd/<sha256>  (or dedup-link existing)
    J->>DB: blobs.status=verified
    J-->>C: SSE file.created (UI clears "verifying" badge)
```

Failure handling for every step is specified in 03 §5.3 (crash, corruption,
disk-full, restart — all resume or GC).

---

## 4. File download flow (streaming + range)

```mermaid
sequenceDiagram
    participant C as Client
    participant A as API
    participant DB as PostgreSQL
    participant S as Blobs

    C->>A: GET /files/{id}/content  [Range: bytes=N-]
    A->>DB: load file + blob (owner check — object-level authz)
    A->>A: ETag match? If-Range handling
    alt range request
        A->>S: open at offset N
        A-->>C: 206 Partial Content (streamed 256 KiB reads)
    else full
        A-->>C: 200 + Content-Length + ETag "<sha256>" (stream)
    end
    Note over A,C: public share path (/shares/{token}/files/{id}/content)<br/>adds: token validity → password session → expiry/limit check → count row
```

---

## 5. Share-link flow (public)

```mermaid
sequenceDiagram
    participant O as Owner (browser)
    participant A as API
    participant V as Visitor (anonymous)
    participant DB as PostgreSQL

    O->>A: POST /shares {fileId, expiresAt?, password?, maxDownloads?}
    A->>DB: insert share (130-bit base32 token)
    A-->>O: {token, url, qrSvg}

    V->>A: GET /shares/{token}
    A->>DB: validity check (revoked? expired? limit?)
    A-->>V: metadata + requiresPassword
    opt password set
        V->>A: POST /shares/{token}/unlock {password}
        A->>A: progressive backoff on failures (audit)
        A-->>V: ld_share cookie (1 h)
    end
    V->>A: GET /shares/{token}/files/{id}/content [Range…]
    A->>DB: re-check + upsert share_downloads(session_key)
    A-->>V: streamed bytes
    Note over A,DB: download_count == maxDownloads ⇒ next request 403 share-limit-reached
```

---

## 6. Database relationships (ERD)

```mermaid
erDiagram
    users ||--o{ sessions : "has"
    users ||--o{ personal_access_tokens : "has"
    users ||--o{ folders : "owns"
    users ||--o{ files : "uploaded"
    users ||--o{ upload_sessions : "started"
    users ||--o{ shares : "created"
    users ||--o{ audit_events : "acted"
    folders ||--o{ folders : "parent of"
    folders ||--o{ files : "contains"
    blobs ||--o{ files : "backed by (dedup: N files → 1 blob)"
    shares }o--|| files : "target (v1)"
    shares }o--|| folders : "target (Ph2)"
    shares ||--o{ share_downloads : "counted by"

    users { uuid id PK  text username UK  citext email  text password_hash  text role  bool is_active }
    sessions { uuid id PK  uuid user_id FK  text token_hash UK  timestamptz expires_at }
    folders { uuid id PK  uuid parent_id FK  text name  uuid owner_id FK  timestamptz deleted_at }
    blobs { uuid id PK  bytea sha256 UK  bigint size  text status }
    files { uuid id PK  uuid folder_id FK  uuid blob_id FK  text name  bigint size  timestamptz deleted_at }
    upload_sessions { uuid id PK  uuid user_id FK  bigint offset  bigint total_size  text status }
    shares { uuid id PK  text token UK  text target_type  timestamptz expires_at  int max_downloads  text password_hash }
    audit_events { uuid id PK  uuid actor_id FK  text action  jsonb details }
```

---

## 7. Docker deployment

```mermaid
flowchart TB
    subgraph host["Docker host (Linux server / Pi / NAS / VPS)"]
        subgraph net["bridge network: localdrop (internal)"]
            APP["localdrop app<br/>ghcr.io/localdrop/localdrop:stable<br/>uid 1000 · ro-rootfs · caps dropped<br/>:8080 published"]
            PG["postgres:16<br/>random pw · not published"]
        end
        VOL1[("volume: localdrop-data<br/>→ /data blobs+staging+thumbs")]
        VOL2[("volume: pgdata")]
    end
    LAN["LAN devices<br/>QR / localdrop.local / IP:8080"]
    NET["Internet (optional)"]

    LAN -->|http :8080| APP
    NET -->|TLS via deployer's reverse proxy / tailscale| APP
    APP --> PG
    APP --- VOL1
    PG --- VOL2
```

---

## 8. Local-network discovery

```mermaid
flowchart LR
    subgraph boot["Container startup"]
        DET["Detect LAN IPv4s<br/>(filter docker/virt bridges)"]
        QR["Print URLs + QR<br/>(console + onboarding page)"]
        MDNS["mDNS announce<br/>_localdrop._http._tcp.local<br/>(opt-in, host-network profile)"]
    end
    DET --> QR
    DET --> MDNS

    PHONE["📱 Phone camera<br/>(works everywhere)"]
    MAC["macOS / iOS<br/>.local resolves natively"]
    WIN["Windows 10/11<br/>.local usually resolves"]
    AND["Android<br/>.local unreliable → QR"]
    LNX["Linux desktop<br/].local if nss-mdns"]

    PHONE -->|scan| QR
    MAC -->|bonjour| MDNS
    WIN -->|native mDNS| MDNS
    AND -->|primary path| QR
    LNX -->|avahi| MDNS
```

Honesty matrix with caveats: 03 §7.

---

## 9. Real-time communication (SSE)

```mermaid
flowchart LR
    subgraph server
        SVC["services mutate<br/>(file/share/job)"]
        BUS["EventBus<br/>bounded per-subscriber queues"]
        EP["GET /api/v1/events<br/>(text/event-stream, session auth)"]
        HB["heartbeat every 20 s"]
    end
    subgraph browser
        ES["EventSource"]
        Q["TanStack Query cache"]
        POLL["30 s polling fallback<br/>(correctness never depends on SSE)"]
    end
    SVC --> BUS --> EP
    HB --> EP
    EP -->|file.created, folder.changed, share.updated, job.progress| ES
    ES -->|invalidate| Q
    POLL -->|refetch| Q
```

---

*Next: [10 — Risks & open questions](10-risks-open-questions.md).*
