from __future__ import annotations

import asyncio
from pathlib import Path

from aurora_api.database import ensure_pgvector, init_engine

MIGRATIONS = [Path(__file__).resolve().parent.parent / "database" / "migrations" / "001_initial_schema.sql"]


async def run() -> None:
    engine = await init_engine()
    async with engine.begin() as conn:
        await ensure_pgvector()
        for migration in MIGRATIONS:
            sql_text = migration.read_text()
            # asyncpg does not allow multiple statements in one exec; split and run sequentially.
            statements = [stmt.strip() for stmt in sql_text.split(";") if stmt.strip()]
            for stmt in statements:
                await conn.exec_driver_sql(stmt)


if __name__ == "__main__":
    asyncio.run(run())
