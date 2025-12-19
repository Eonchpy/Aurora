from __future__ import annotations

import asyncio
from pathlib import Path

from aurora_mcp.database import init_engine, ensure_pgvector


MIGRATION_FILE = Path(__file__).resolve().parent.parent / "database" / "migrations" / "003_add_project_fields.sql"


async def apply_migration() -> None:
    """Apply the project fields migration (idempotent)."""
    engine = await init_engine()
    async with engine.begin() as conn:
        await ensure_pgvector()

        sql_text = MIGRATION_FILE.read_text()
        statements = [stmt.strip() for stmt in sql_text.split(";") if stmt.strip()]
        for statement in statements:
            await conn.exec_driver_sql(statement)


if __name__ == "__main__":
    asyncio.run(apply_migration())
