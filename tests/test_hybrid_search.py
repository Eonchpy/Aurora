from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import pytest

from aurora_mcp import server
from aurora_mcp.server import aurora_search


class _FakeResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    async def execute(self, stmt):
        return _FakeResult(self._rows)


async def _fake_get_session(rows: list[Any]) -> AsyncGenerator[_FakeSession, None]:
    yield _FakeSession(rows)


class _FakeEmbeddingService:
    async def embed(self, content: str) -> list[float]:
        return [0.0, 0.0, 0.0]


def _row(final_score: float, embedding_score: float, keyword_score: float | None = None, project_path: str | None = None):
    class Row:
        pass

    r = Row()
    r.id = uuid.uuid4()
    r.content = "content"
    r.metadata_json = {}
    r.namespace = "default"
    r.document_type = "document"
    r.source = "test"
    r.created_at = datetime.now(timezone.utc)
    r.project_path = project_path
    r.embedding_score = embedding_score
    if keyword_score is not None:
        r.keyword_score = keyword_score
    r.final_score = final_score
    return r


@pytest.fixture(autouse=True)
def patch_embedding(monkeypatch: pytest.MonkeyPatch):
    async def _fake_embedding_service():
        return _FakeEmbeddingService()

    monkeypatch.setattr(server, "get_embedding_service", _fake_embedding_service)
    yield


@pytest.mark.anyio
async def test_hybrid_search_with_special_characters():
    rows = [
        _row(final_score=0.8, embedding_score=0.6, keyword_score=0.9),
    ]
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(server, "get_session", lambda: _fake_get_session(rows))

    result = await aurora_search(query="database-migration!", namespace="test", use_hybrid=True)
    monkeypatch.undo()

    assert result["documents"]
    assert result["documents"][0]["keyword_score"] is not None
    assert result["search_type"] == "hybrid"


@pytest.mark.anyio
async def test_hybrid_search_empty_query():
    result = await aurora_search(query="", namespace="test", use_hybrid=True)
    assert result["total_found"] == 0
    assert result["search_type"] == "hybrid"
