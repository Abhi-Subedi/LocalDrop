"""Audit event recording (services call this, never routers)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .models import AuditEvent


async def audit(
    db: AsyncSession,
    action: str,
    actor_id: str | None = None,
    actor_ip: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditEvent(
            actor_id=actor_id,  # type: ignore[arg-type]
            actor_ip=actor_ip,
            action=action,
            target_type=target_type,
            target_id=target_id,  # type: ignore[arg-type]
            details=details or {},
        )
    )
