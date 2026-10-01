"""All LocalDrop tables (spec 04 §3). One file for V1 speed; same aggregates."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import LargeBinary

from ..models.base import PkMixin, TimestampsMixin, new_uuid, utcnow
from ..db import Base
from .base import PkMixin, TimestampsMixin, new_uuid, utcnow


class User(Base, PkMixin, TimestampsMixin):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column("username", String(32), nullable=False)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="owner"
    )  # owner|admin|user|viewer
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    quota_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("uq_users_username", func.lower(text("username")), unique=True),
        Index(
            "uq_users_email",
            func.lower(text("email")),
            unique=True,
            postgresql_where=text("email IS NOT NULL"),
        ),
        CheckConstraint("role IN ('owner','admin','user','viewer')", name="role_enum"),
    )


class AuthSession(Base, PkMixin):
    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ip: Mapped[str | None] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(Text)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(lazy="joined")

    __table_args__ = (
        Index("uq_sessions_token_hash", "token_hash", unique=True),
        Index("ix_sessions_user_id", "user_id"),
        Index("ix_sessions_expires_at", "expires_at"),
    )


class PersonalAccessToken(Base, PkMixin, TimestampsMixin):
    __tablename__ = "personal_access_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[str] = mapped_column(String(16), nullable=False, server_default="read,write")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("uq_pat_token_hash", "token_hash", unique=True),)


class Folder(Base, PkMixin, TimestampsMixin):
    __tablename__ = "folders"

    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("folders.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "uq_folders_live_name",
            text("coalesce(parent_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            func.lower(text("name")),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_folders_owner_id", "owner_id"),
        Index("ix_folders_parent_id", "parent_id"),
    )


class Blob(Base, PkMixin):
    __tablename__ = "blobs"

    sha256: Mapped[bytes | None] = mapped_column(LargeBinary(32), nullable=True)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="pending"
    )  # pending|verified
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    mime_hint: Mapped[str | None] = mapped_column(Text)
    mime_sniffed: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    __table_args__ = (
        Index(
            "uq_blobs_sha256",
            "sha256",
            unique=True,
            postgresql_where=text("status = 'verified'"),
        ),
        Index("ix_blobs_status", "status"),
    )


class File(Base, PkMixin, TimestampsMixin):
    __tablename__ = "files"

    folder_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("folders.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    blob_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("blobs.id"), nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="application/octet-stream")
    size: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    uploader_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    blob: Mapped[Blob] = relationship(lazy="joined")
    folder: Mapped[Folder] = relationship(lazy="joined")

    __table_args__ = (
        Index(
            "uq_files_live_name",
            "folder_id",
            func.lower(text("name")),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_files_folder_id", "folder_id"),
        Index("ix_files_blob_id", "blob_id"),
        Index("ix_files_uploader_id", "uploader_id"),
        Index(
            "ix_files_name_trgm",
            text("lower(name) gin_trgm_ops"),
            postgresql_using="gin",
        ),
    )


class UploadSession(Base, PkMixin):
    __tablename__ = "upload_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    folder_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("folders.id"), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(Text)
    total_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    offset: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="active"
    )  # active|finalized|cancelled|expired
    chunk_hashes: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    staging_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(text('"offset" <= total_size'), name="offset_le_total"),
        Index("ix_upload_sessions_user_status", "user_id", "status"),
        Index("ix_upload_sessions_expires_at", "expires_at"),
    )


class Share(Base, PkMixin):
    __tablename__ = "shares"

    token: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="file")
    file_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("files.id"), nullable=True)
    folder_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("folders.id"), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    max_downloads: Mapped[int | None] = mapped_column(Integer)
    download_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    password_hash: Mapped[str | None] = mapped_column(Text)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    file: Mapped[File | None] = relationship(lazy="joined", foreign_keys=[file_id])

    __table_args__ = (
        CheckConstraint(
            "(file_id IS NOT NULL) <> (folder_id IS NOT NULL)", name="single_target"
        ),
        CheckConstraint("target_type IN ('file','folder')", name="target_type_enum"),
        Index("uq_shares_token", "token", unique=True),
        Index("ix_shares_created_by", "created_by"),
    )


class ShareDownload(Base):
    __tablename__ = "share_downloads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    share_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("shares.id", ondelete="CASCADE"), nullable=False
    )
    session_key: Mapped[str] = mapped_column(String(64), nullable=False)
    file_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("files.id"), nullable=False)
    ip: Mapped[str | None] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("uq_share_downloads_human", "share_id", "session_key", unique=True),
    )


class AuditEvent(Base, PkMixin):
    __tablename__ = "audit_events"

    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    actor_ip: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str | None] = mapped_column(Text)
    target_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("ix_audit_actor_created", "actor_id", "created_at"),
        Index("ix_audit_action_created", "action", "created_at"),
    )


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
