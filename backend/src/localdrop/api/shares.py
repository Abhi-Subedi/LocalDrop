"""Share endpoints: authenticated management + public surface (spec 05 §2.6)."""

from __future__ import annotations

import uuid as uuid_mod

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import (
    SHARE_COOKIE,
    Principal,
    check_csrf,
    require_read,
    require_write,
)
from ..config import get_settings
from ..db import get_db
from ..errors import forbidden, not_found
from ..ratelimit import LIMITS
from ..schemas import (
    ShareCreated,
    ShareCreate,
    ShareOut,
    SharePublicInfo,
    ShareUpdate,
    UnlockRequest,
)
from ..services import downloads, shares
from ..services.tree import get_owned_file_with_blob
from ..storage import get_storage

router = APIRouter(tags=["shares"])


def _base_url(request: Request) -> str:
    s: "object" = request.app.state.settings
    if getattr(s, "public_url", ""):
        return str(getattr(s, "public_url")).rstrip("/")
    proto = request.headers.get("X-Forwarded-Proto", request.url.scheme)
    host = request.headers.get("Host") or request.url.netloc
    return f"{proto}://{host}"


def _share_out(share, base_url: str, file_name: str | None = None, file_size: int = 0) -> ShareOut:
    return ShareOut(
        id=share.id,
        token=share.token,
        file_id=share.file_id,
        file_name=file_name,
        file_size=file_size,
        url=f"{base_url}/s/{share.token}",
        expires_at=share.expires_at,
        max_downloads=share.max_downloads,
        download_count=share.download_count,
        has_password=share.password_hash is not None,
        revoked_at=share.revoked_at,
        created_at=share.created_at,
    )


# ---------- authenticated ----------


@router.post("/shares", response_model=ShareCreated, status_code=201)
async def create_ep(
    body: ShareCreate,
    request: Request,
    p: Principal = Depends(require_write),
    db: AsyncSession = Depends(get_db),
) -> ShareCreated:
    check_csrf(request)
    base = _base_url(request)
    file_id_uuid = uuid_mod.UUID(str(body.file_id))
    f = await get_owned_file_with_blob(db, p, file_id_uuid)
    share, url = await shares.create_share(
        db, p, file_id_uuid, body.expires_at, body.max_downloads, body.password, base
    )
    await db.commit()
    qr = await shares.get_share_qr_svg(url)
    out = _share_out(share, base, file_name=f.name, file_size=f.size)
    return ShareCreated(**out.model_dump(), qr_svg=qr)


@router.get("/shares", response_model=list[ShareOut])
async def list_ep(
    request: Request,
    p: Principal = Depends(require_read),
    db: AsyncSession = Depends(get_db),
) -> list[ShareOut]:
    rows = await shares.list_shares(db, p)
    await db.commit()
    base = _base_url(request)
    return [_share_out(s, base) for s in rows]


@router.patch("/shares/{share_id}", response_model=ShareOut)
async def update_ep(
    share_id: uuid_mod.UUID,
    body: ShareUpdate,
    request: Request,
    p: Principal = Depends(require_write),
    db: AsyncSession = Depends(get_db),
) -> ShareOut:
    check_csrf(request)
    share = await shares.update_share(
        db, p, share_id,
        expires_at=body.expires_at,
        max_downloads=body.max_downloads,
        password=body.password,
        clear_password=body.clear_password,
        clear_expiry=body.clear_expiry,
    )
    await db.commit()
    return _share_out(share, _base_url(request))


@router.delete("/shares/{share_id}", status_code=204)
async def revoke_ep(
    share_id: uuid_mod.UUID,
    request: Request,
    p: Principal = Depends(require_write),
    db: AsyncSession = Depends(get_db),
) -> Response:
    check_csrf(request)
    await shares.revoke_share(db, p, share_id)
    await db.commit()
    return Response(status_code=204)


# ---------- public (anonymous, rate class `share`) ----------

public = APIRouter(tags=["shares-public"])


def _client_ip(request: Request) -> str:
    s = request.app.state.settings
    from ..ratelimit import client_ip_from_headers

    return client_ip_from_headers(
        request.client.host if request.client else "0.0.0.0",
        request.headers.get("X-Forwarded-For"),
        s.trusted_proxies,
    )


def _share_cookie_secure(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("X-Forwarded-Proto") == "https"


@public.get("/shares/{token}", response_model=SharePublicInfo)
async def public_info_ep(token: str, request: Request, db: AsyncSession = Depends(get_db)) -> SharePublicInfo:
    LIMITS.share.check(_client_ip(request))
    share = await shares.get_public_share(db, token)
    f = await shares.share_file(share)
    await db.commit()
    unlocked = share.password_hash is None or request.cookies.get(SHARE_COOKIE) == shares.expected_share_key(token)
    return SharePublicInfo(
        token=share.token,
        file_name=f.name,
        file_size=f.size,
        requires_password=share.password_hash is not None,
        unlocked=unlocked,
    )


@public.post("/shares/{token}/unlock", status_code=204)
async def public_unlock_ep(
    token: str, body: UnlockRequest, request: Request, response: Response,
    db: AsyncSession = Depends(get_db),
) -> Response:
    LIMITS.share.check(_client_ip(request))
    key = await shares.unlock_share(db, _client_ip(request), token, body.password)
    await db.commit()
    response.set_cookie(
        SHARE_COOKIE, key, httponly=True, samesite="lax",
        secure=_share_cookie_secure(request), max_age=3600, path="/",
    )
    response.status_code = 204
    return response


@public.get("/shares/{token}/files/{file_id}/content")
async def public_content_ep(
    token: str, file_id: uuid_mod.UUID, request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip = _client_ip(request)
    LIMITS.share.check(ip)
    share = await shares.get_public_share(db, token)
    f = await shares.share_file(share)
    if f.id != file_id:
        raise not_found()

    # password gate: cookie must be the HMAC key bound to THIS share token
    if share.password_hash is not None:
        key = request.cookies.get(SHARE_COOKIE)
        if not key or key != shares.expected_share_key(token):
            raise forbidden("share-locked", "Password required.")

    # TOCTOU-free download limit
    allowed = await shares.increment_download_atomic(db, share)
    if not allowed:
        raise forbidden("share-limit-reached", "Download limit reached.")
    await shares.record_download(
        db, share, f.id, request.cookies.get(SHARE_COOKIE) or "anon", ip,
        request.headers.get("User-Agent", ""),
    )
    await db.commit()

    from ..services.downloads import blob_etag, file_response

    etag = await blob_etag(db, f.blob_id)
    return file_response(
        get_storage(), f, request.headers.get("Range"), request.headers.get("If-Range"), etag
    )
