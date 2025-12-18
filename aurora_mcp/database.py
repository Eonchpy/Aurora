from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text

from aurora_mcp.config import get_settings

engine: AsyncEngine | None = None
SessionLocal: async_sessionmaker[AsyncSession] | None = None


async def init_engine() -> AsyncEngine:
    """Initialize database engine and session maker"""
    global engine, SessionLocal
    if engine is None:
        settings = get_settings()
        engine = create_async_engine(
            settings.database_url,
            echo=False,  # Disable SQL logging for MCP
            future=True
        )
        SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

        # Ensure pgvector extension is enabled
        await ensure_pgvector()

    return engine


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session"""
    if SessionLocal is None:
        await init_engine()
    assert SessionLocal is not None
    async with SessionLocal() as session:
        yield session


async def ensure_pgvector() -> None:
    """Ensure pgvector extension is installed"""
    assert engine is not None
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
