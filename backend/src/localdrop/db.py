"""Database engine and session management (async SQLAlchemy + psycopg3)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def make_engine(url: str | None = None) -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        url or settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        # Recycle well inside the typical 5-minute NAT/firewall idle timeout so
        # a connection killed by the network is replaced, not handed to a
        # request that will then fail.
        pool_recycle=1800,
        # Wait at most this long for a free pool slot. Without it a saturated
        # pool makes requests queue indefinitely instead of failing visibly.
        pool_timeout=10,
        connect_args={
            "application_name": "localdrop",
            "options": "-c timezone=UTC",
            # psycopg waits ~2 minutes for a TCP connect by default. That is
            # unacceptable for /health/ready (Docker probes with --timeout=5s)
            # and for request paths: a dead database must be *fast*. These
            # bounds also stop a firewall silently dropping packets from
            # hanging a worker for minutes.
            "connect_timeout": settings.db_connect_timeout,
            "keepalives": 1,
            "keepalives_idle": settings.db_keepalive_seconds,
            "keepalives_interval": 10,
            "keepalives_count": 3,
        },
    )


engine: AsyncEngine | None = None
SessionFactory: async_sessionmaker[AsyncSession] | None = None


def init_engine() -> None:
    global engine, SessionFactory
    engine = make_engine()
    SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def dispose_engine() -> None:
    global engine
    if engine is not None:
        await engine.dispose()
        engine = None


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, commit on success."""
    assert SessionFactory is not None, "engine not initialised"
    async with SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
