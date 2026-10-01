"""V1 schema: all tables (spec 04).

Revision ID: 0001
Revises:
Create Date: 2026-10-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("username", sa.String(32), nullable=False),
        sa.Column("email", sa.Text()),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False, server_default="owner"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=text("true")),
        sa.Column("quota_bytes", sa.BigInteger()),
        sa.Column("email_verified_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=func.now(), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("role IN ('owner','admin','user','viewer')", name="role_enum"),
    )
    op.create_index("uq_users_username", "users", [func.lower(text("username"))], unique=True)
    op.create_index(
        "uq_users_email",
        "users",
        [func.lower(text("email"))],
        unique=True,
        postgresql_where=text("email IS NOT NULL"),
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip", sa.Text()),
        sa.Column("user_agent", sa.Text()),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("uq_sessions_token_hash", "sessions", ["token_hash"], unique=True)
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])

    op.create_table(
        "personal_access_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("scopes", sa.String(16), nullable=False, server_default="read,write"),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=func.now(), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("uq_pat_token_hash", "personal_access_tokens", ["token_hash"], unique=True)

    op.create_table(
        "folders",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("parent_id", sa.Uuid(), sa.ForeignKey("folders.id", ondelete="CASCADE")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=func.now(), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "uq_folders_live_name",
        "folders",
        [
            text("coalesce(parent_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            func.lower(text("name")),
        ],
        unique=True,
        postgresql_where=text("deleted_at IS NULL"),
    )
    op.create_index("ix_folders_owner_id", "folders", ["owner_id"])
    op.create_index("ix_folders_parent_id", "folders", ["parent_id"])

    op.create_table(
        "blobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("sha256", sa.LargeBinary(32)),
        sa.Column("size", sa.BigInteger(), nullable=False, server_default=text("0")),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("mime_hint", sa.Text()),
        sa.Column("mime_sniffed", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=func.now(), nullable=False
        ),
    )
    op.create_index(
        "uq_blobs_sha256",
        "blobs",
        ["sha256"],
        unique=True,
        postgresql_where=text("status = 'verified'"),
    )
    op.create_index("ix_blobs_status", "blobs", ["status"])

    op.create_table(
        "files",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "folder_id", sa.Uuid(), sa.ForeignKey("folders.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("blob_id", sa.Uuid(), sa.ForeignKey("blobs.id"), nullable=False),
        sa.Column(
            "mime_type", sa.Text(), nullable=False, server_default="application/octet-stream"
        ),
        sa.Column("size", sa.BigInteger(), nullable=False, server_default=text("0")),
        sa.Column("uploader_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=func.now(), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "uq_files_live_name",
        "files",
        ["folder_id", func.lower(text("name"))],
        unique=True,
        postgresql_where=text("deleted_at IS NULL"),
    )
    op.create_index("ix_files_folder_id", "files", ["folder_id"])
    op.create_index("ix_files_blob_id", "files", ["blob_id"])
    op.create_index("ix_files_uploader_id", "files", ["uploader_id"])
    op.create_index(
        "ix_files_name_trgm",
        "files",
        [text("lower(name) gin_trgm_ops")],
        postgresql_using="gin",
    )

    op.create_table(
        "upload_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("folder_id", sa.Uuid(), sa.ForeignKey("folders.id"), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.Text()),
        sa.Column("total_size", sa.BigInteger(), nullable=False),
        sa.Column("offset", sa.BigInteger(), nullable=False, server_default=text("0")),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("chunk_hashes", JSONB()),
        sa.Column("staging_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(text('"offset" <= total_size'), name="offset_le_total"),
    )
    op.create_index("ix_upload_sessions_user_status", "upload_sessions", ["user_id", "status"])
    op.create_index("ix_upload_sessions_expires_at", "upload_sessions", ["expires_at"])

    op.create_table(
        "shares",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False, server_default="file"),
        sa.Column("file_id", sa.Uuid(), sa.ForeignKey("files.id")),
        sa.Column("folder_id", sa.Uuid(), sa.ForeignKey("folders.id")),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("max_downloads", sa.Integer()),
        sa.Column("download_count", sa.Integer(), nullable=False, server_default=text("0")),
        sa.Column("password_hash", sa.Text()),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=func.now()),
        sa.CheckConstraint(
            "(file_id IS NOT NULL) <> (folder_id IS NOT NULL)", name="single_target"
        ),
        sa.CheckConstraint("target_type IN ('file','folder')", name="target_type_enum"),
    )
    op.create_index("uq_shares_token", "shares", ["token"], unique=True)
    op.create_index("ix_shares_created_by", "shares", ["created_by"])

    op.create_table(
        "share_downloads",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "share_id", sa.Uuid(), sa.ForeignKey("shares.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("session_key", sa.String(64), nullable=False),
        sa.Column("file_id", sa.Uuid(), sa.ForeignKey("files.id"), nullable=False),
        sa.Column("ip", sa.Text()),
        sa.Column("user_agent", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=func.now()),
    )
    op.create_index(
        "uq_share_downloads_human", "share_downloads", ["share_id", "session_key"], unique=True
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("actor_ip", sa.Text()),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text()),
        sa.Column("target_id", sa.Uuid()),
        sa.Column("details", JSONB(), server_default=text("'{}'")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=func.now(), nullable=False
        ),
    )
    op.create_index("ix_audit_actor_created", "audit_events", ["actor_id", "created_at"])
    op.create_index("ix_audit_action_created", "audit_events", ["action", "created_at"])

    op.create_table(
        "settings",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value", JSONB(), server_default=text("'{}'")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=func.now()),
    )


def downgrade() -> None:
    for t in (
        "settings",
        "audit_events",
        "share_downloads",
        "shares",
        "upload_sessions",
        "files",
        "blobs",
        "folders",
        "personal_access_tokens",
        "sessions",
        "users",
    ):
        op.drop_table(t)
