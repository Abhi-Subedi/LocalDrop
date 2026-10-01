"""Pydantic schemas: shared field types (NameStr) + request/response DTOs.

NameStr is THE validator for every user-supplied name (files, folders, share
labels, upload names) — BC-11. No exceptions.
"""

from __future__ import annotations

import unicodedata
from datetime import datetime
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

MAX_NAME_BYTES = 255

# Characters that enable rendering attacks or traversal; stripped/rejected by
# _validate_name.
_FORBIDDEN_CHARS = set("/\\\x00")
_CONTROL = {c for c in range(0x20)} | {0x7F}
# bidi overrides + zero-width + tag chars (spoofed names, RTL attacks)
_BIDI_ZW = {
    0x200B, 0x200C, 0x200D, 0x200E, 0x200F,  # zero-width, LRM/RLM
    0x202A, 0x202B, 0x202C, 0x202D, 0x202E,  # bidi embedding/override
    0x2066, 0x2067, 0x2068, 0x2069,          # bidi isolate
    0xFEFF,                                   # BOM/zero-width no-break space
    0xE0001,                                  # tag
}


def _validate_name(v: str) -> str:
    if not v or not v.strip():
        raise ValueError("name must not be empty")
    v = unicodedata.normalize("NFC", v)
    if any(ch in _FORBIDDEN_CHARS for ch in v):
        raise ValueError("name must not contain '/', '\\' or NUL")
    if any(ord(ch) in _CONTROL or ord(ch) in _BIDI_ZW for ch in v):
        raise ValueError("name contains forbidden control/format characters")
    if v.startswith((".", " ")) or v.endswith((".", " ")):
        raise ValueError("name must not start or end with '.' or space")
    if len(v.encode("utf-8")) > MAX_NAME_BYTES:
        raise ValueError(f"name exceeds {MAX_NAME_BYTES} bytes")
    return v


NameStr = Annotated[str, Field(min_length=1, max_length=MAX_NAME_BYTES * 4), AfterValidator(_validate_name)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- auth ----


class SetupStatus(BaseModel):
    onboarding_required: bool


class OwnerCreate(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=256)
    setup_token: str = Field(min_length=8, max_length=64)


class LoginRequest(BaseModel):
    username: str
    password: str


class PasswordChange(BaseModel):
    current: str
    new: str = Field(min_length=8, max_length=256)


class PATCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scopes: str = Field(default="read,write", pattern=r"^(read|write|read,write|write,read)$")


class SessionOut(ORMModel):
    id: Any
    created_at: datetime
    last_seen_at: datetime
    ip: str | None = None
    user_agent: str | None = None
    current: bool = False


class UserOut(ORMModel):
    id: Any
    username: str
    role: str
    storage_used: int = 0
    storage_quota: int | None = None


class TokenOut(ORMModel):
    id: Any
    name: str
    scopes: str
    created_at: datetime
    last_used_at: datetime | None = None


class TokenCreated(TokenOut):
    token: str


# ---- folders / files ----


class FolderCreate(BaseModel):
    parent_id: Any | None = None
    name: NameStr


class FolderRename(BaseModel):
    name: NameStr


class MoveRequest(BaseModel):
    folder_id: Any | None = None
    new_parent_id: Any | None = None
    overwrite: bool = False


class CopyRequest(BaseModel):
    folder_id: Any


class EntryOut(ORMModel):
    id: Any
    kind: str  # file | folder
    name: str
    size: int
    mime_type: str | None = None
    hash_status: str | None = None  # for files: blob status
    has_thumbnail: bool = False
    created_at: datetime
    updated_at: datetime | None = None
    deleted_at: datetime | None = None


class EntryPage(BaseModel):
    items: list[EntryOut]
    next_cursor: str | None = None
    total: int | None = None


class PathEntry(BaseModel):
    id: Any
    name: str


class TextPreview(BaseModel):
    text: str
    charset: str
    truncated: bool


# ---- uploads ----


class UploadOut(ORMModel):
    id: Any
    file_name: str
    total_size: int
    offset: int
    status: str
    expires_at: datetime


# ---- shares ----


class ShareCreate(BaseModel):
    file_id: Any
    expires_at: datetime | None = None
    max_downloads: int | None = Field(default=None, ge=1)
    password: str | None = Field(default=None, min_length=1, max_length=128)


class ShareUpdate(BaseModel):
    expires_at: datetime | None = None
    max_downloads: int | None = Field(default=None, ge=1)
    password: str | None = Field(default=None, min_length=1, max_length=128)
    clear_password: bool = False
    clear_expiry: bool = False


class ShareOut(ORMModel):
    id: Any
    token: str
    file_id: Any
    file_name: str | None = None
    file_size: int = 0
    url: str
    expires_at: datetime | None = None
    max_downloads: int | None = None
    download_count: int = 0
    has_password: bool = False
    revoked_at: datetime | None = None
    created_at: datetime | None = None


class ShareCreated(ShareOut):
    qr_svg: str


class SharePublicInfo(BaseModel):
    token: str
    file_id: str
    file_name: str
    file_size: int
    requires_password: bool
    unlocked: bool = False


class UnlockRequest(BaseModel):
    password: str
