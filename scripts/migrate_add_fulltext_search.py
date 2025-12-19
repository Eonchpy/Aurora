from __future__ import annotations

import asyncio
from pathlib import Path

from aurora_mcp.database import ensure_pgvector, init_engine


MIGRATION_FILE = Path(__file__).resolve().parent.parent / "database" / "migrations" / "004_add_content_tsv.sql"


def split_sql(sql_text: str) -> list[str]:
    """Split SQL statements while respecting $$ quote blocks."""
    statements = []
    buff: list[str] = []
    in_dollar = False
    i = 0
    while i < len(sql_text):
        ch = sql_text[i]
        if ch == "$" and i + 1 < len(sql_text) and sql_text[i:i+2] == "$$":
            in_dollar = not in_dollar
            buff.append("$$")
            i += 2
            continue
        if ch == ";" and not in_dollar:
            stmt = "".join(buff).strip()
            if stmt:
                statements.append(stmt)
            buff = []
        else:
            buff.append(ch)
        i += 1
    tail = "".join(buff).strip()
    if tail:
        statements.append(tail)
    return statements


async def apply_migration() -> None:
    """Apply full-text search migration (content_tsv + index + trigger)."""
    engine = await init_engine()
    async with engine.begin() as conn:
        await ensure_pgvector()
        sql_text = MIGRATION_FILE.read_text()
        statements = split_sql(sql_text)
        for statement in statements:
            await conn.exec_driver_sql(statement)


if __name__ == "__main__":
    asyncio.run(apply_migration())
