"""LocalDrop configuration.

All configuration arrives via LOCALDROP_* environment variables (12-factor).
This module is the single source of truth; docs/config reference is checked
against it (see scripts/check_config_docs.py).
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LOCALDROP_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- required (production) ---
    database_url: str = Field(default="postgresql+psycopg://postgres@127.0.0.1:5433/localdrop")
    secret_key: str = Field(default="")  # validated in ensure_secure(): >= 32 chars

    # --- storage ---
    data_dir: Path = Field(default=Path("/var/lib/localdrop"))
    max_upload_bytes: int = 100 * 1024**3  # 100 GiB; 0 = unlimited
    upload_chunk_max_bytes: int = 8 * 1024**2  # 8 MiB, hard cap 64 MiB
    upload_chunk_min_bytes: int = 64 * 1024
    upload_sessions_max: int = 20  # per user, active sessions
    upload_ttl_days: int = 7
    trash_retention_days: int = 30

    # --- sessions ---
    session_idle_minutes: int = 7 * 24 * 60  # 7 days
    session_absolute_minutes: int = 30 * 24 * 60  # 30 days

    # --- rate limits (requests per window seconds) ---
    rate_auth_limit: int = 10
    rate_auth_window: int = 300
    rate_auth_lockout: int = 15  # minutes after limit
    rate_share_limit: int = 120
    rate_share_window: int = 60
    rate_content_limit: int = 60
    rate_content_window: int = 60
    rate_api_limit: int = 600
    rate_api_window: int = 60

    # --- network ---
    port: int = 8080
    public_url: str = ""  # e.g. http://192.168.1.10:8080; empty = derive per-request
    trusted_proxies: int = 0  # number of trusted proxy hops in X-Forwarded-For chain
    mdns_enabled: bool = False

    # --- database connection behaviour ---
    # Seconds to wait for a TCP connect to PostgreSQL. Kept short on purpose:
    # /health/ready is probed with a 5 s timeout by Docker and most
    # orchestrators, so a dead database has to be reported in seconds, not the
    # ~2 minutes libpq waits by default.
    db_connect_timeout: int = 5
    # Idle seconds before a keepalive probe; three missed probes close the
    # connection so a half-open socket cannot pin a pool slot.
    db_keepalive_seconds: int = 30

    # --- auth ---
    argon2_time_cost: int = 3
    argon2_memory_cost: int = 65536  # 64 MiB
    argon2_parallelism: int = 2

    # --- ops ---
    log_level: str = "INFO"
    log_format: str = "json"  # json | dev
    dev_mode: bool = False
    cors_origins: list[str] = Field(default_factory=list)  # dev: ["http://localhost:5173"]

    @field_validator("upload_chunk_max_bytes")
    @classmethod
    def _chunk_cap(cls, v: int) -> int:
        return min(v, 64 * 1024**2)

    def ensure_secure(self) -> None:
        """Production boot checks. Dev mode relaxes the secret key requirement."""
        if self.dev_mode:
            if not self.secret_key:
                # Auto-generate a dev key so local iteration "just works".
                object.__setattr__(self, "secret_key", secrets.token_hex(32))
            return
        if len(self.secret_key) < 32:
            raise RuntimeError(
                "LOCALDROP_SECRET_KEY must be set to at least 32 characters in production."
            )

    @property
    def blobs_dir(self) -> Path:
        return self.data_dir / "blobs"

    @property
    def staging_dir(self) -> Path:
        return self.data_dir / "staging"

    @property
    def thumbs_dir(self) -> Path:
        return self.data_dir / "thumbs"

    @property
    def tmp_dir(self) -> Path:
        return self.data_dir / "tmp"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_secure()
    return s
