"""RFC 9457 problem+json errors and the shared error catalog (spec 05 §3)."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from .logging import get_logger

log = get_logger(__name__)

TYPE_BASE = "https://localdrop.dev/errors/"


class Problem(Exception):
    """Raise anywhere in services; middleware converts to problem+json."""

    def __init__(
        self,
        status: int,
        type_suffix: str,
        title: str,
        detail: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self.type_suffix = type_suffix
        self.title = title
        self.detail = detail
        self.headers = headers
        super().__init__(detail or title)


def problem_response(
    status: int, type_suffix: str, title: str, detail: str | None, request_id: str | None
) -> JSONResponse:
    body: dict[str, object] = {
        "type": f"{TYPE_BASE}{type_suffix}",
        "title": title,
        "status": status,
    }
    if detail:
        body["detail"] = detail
    if request_id:
        body["request_id"] = request_id
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


async def problem_handler(request: Request, exc: Problem) -> JSONResponse:
    rid = getattr(request.state, "request_id", None) or getattr(exc, "request_id", None)
    log.info(
        "problem",
        status=exc.status,
        type=exc.type_suffix,
        detail=exc.detail,
        request_id=rid,
    )
    return problem_response(exc.status, exc.type_suffix, exc.title, exc.detail, rid)


# ---- commonly raised problems ----


def not_found(detail: str | None = None) -> Problem:
    """404 for missing OR not-owned objects (no existence oracle)."""
    return Problem(404, "not-found", "Not Found", detail)


def forbidden(type_suffix: str = "forbidden", detail: str | None = None) -> Problem:
    return Problem(403, type_suffix, "Forbidden", detail)


def unauthenticated(detail: str | None = None) -> Problem:
    return Problem(401, "unauthenticated", "Unauthenticated", detail)


def bad_credentials() -> Problem:
    return Problem(401, "bad-credentials", "Invalid credentials")


def validation(detail: str) -> Problem:
    return Problem(400, "validation", "Validation Error", detail)


def conflict(type_suffix: str, detail: str) -> Problem:
    return Problem(409, type_suffix, "Conflict", detail)
