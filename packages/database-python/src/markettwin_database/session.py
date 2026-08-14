"""Shared asynchronous SQLAlchemy session infrastructure."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_database_engine(
    database_url: str,
    *,
    echo: bool = False,
) -> AsyncEngine:
    """Create an asynchronous MarketTwin database engine."""

    return create_async_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,
    )


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Create a reusable asynchronous SQLAlchemy session factory."""

    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


@asynccontextmanager
async def session_scope(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession]:
    """Provide one database session with rollback safety."""

    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise