from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import pytest

from aurora_mcp import server
from aurora_mcp.server import aurora_search
from aurora_mcp.models import Document


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


def _doc_row(project_path: str | None, similarity_score: float, boosted: float | None = None):
    # mimic SQLAlchemy row object with attributes
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
    r.embedding_score = similarity_score
    if boosted is not None:
        r.final_score = boosted
    return r


@pytest.fixture(autouse=True)
def patch_services(monkeypatch: pytest.MonkeyPatch):
    async def _fake_embedding_service():
        return _FakeEmbeddingService()

    monkeypatch.setattr(server, "get_embedding_service", _fake_embedding_service)
    yield


@pytest.mark.anyio
async def test_search_with_boost():
    rows = [
        _doc_row("/proj", 0.7, 0.85),  # boosted
        _doc_row("/other", 0.8, 0.8),  # higher raw, no boost
    ]
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(server, "get_session", lambda: _fake_get_session(rows))

    result = await aurora_search("q", current_project_path="/proj", use_hybrid=False, expand_query=False)
    monkeypatch.undo()

    assert result["documents"][0]["project_path"] == "/proj"
    assert result["documents"][0]["is_same_project"] is True
    assert result["documents"][0]["similarity_score"] == 0.85
    assert result["documents"][1]["is_same_project"] is False
    assert result["current_project"] == "/proj"


@pytest.mark.anyio
async def test_search_without_boost():
    rows = [
        _doc_row("/proj", 0.6),
        _doc_row("/other", 0.9),
    ]
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(server, "get_session", lambda: _fake_get_session(rows))

    result = await aurora_search("q", use_hybrid=False, expand_query=False)
    monkeypatch.undo()

    assert result["documents"][0]["similarity_score"] == 0.6
    assert result["documents"][1]["similarity_score"] == 0.9
    assert result["current_project"] is None


@pytest.mark.anyio
async def test_search_cap_at_one():
    rows = [
        _doc_row("/proj", 0.95, 1.0),
    ]
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(server, "get_session", lambda: _fake_get_session(rows))

    result = await aurora_search("q", current_project_path="/proj", use_hybrid=False, expand_query=False)
    monkeypatch.undo()

    assert result["documents"][0]["similarity_score"] == 1.0
    assert result["documents"][0]["is_same_project"] is True
