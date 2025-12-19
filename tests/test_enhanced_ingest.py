from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import pytest

from aurora_mcp import server
from aurora_mcp.server import aurora_ingest


class _FakeEmbeddingService:
    async def embed(self, content: str) -> list[float]:
        return [0.0, 0.0, 0.0]


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def commit(self) -> None:  # pragma: no cover - no-op
        return None

    async def refresh(self, obj: Any) -> None:
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.now(timezone.utc)


async def _fake_get_session() -> AsyncGenerator[_FakeSession, None]:
    yield _FakeSession()


@pytest.fixture(autouse=True)
def patch_services(monkeypatch: pytest.MonkeyPatch):
    async def _fake_embedding_service():
        return _FakeEmbeddingService()

    monkeypatch.setattr(server, "get_embedding_service", _fake_embedding_service)
    monkeypatch.setattr(server, "get_session", lambda: _fake_get_session())
    yield


@pytest.mark.anyio
async def test_ingest_with_valid_file_path(tmp_path):
    project_root = tmp_path / "proj"
    project_root.mkdir()
    (project_root / ".git").mkdir()
    file_path = project_root / "src" / "file.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("print('hello')")

    result = await aurora_ingest(
        content="Test content",
        document_type="document",
        source="test",
        metadata={"file_path": str(file_path)},
    )

    assert result["project_path"] == str(project_root)
    assert "id" in result


@pytest.mark.anyio
async def test_ingest_without_file_path():
    result = await aurora_ingest(
        content="Test content",
        document_type="conversation",
        source="test",
    )

    assert result["project_path"] is None
    assert "id" in result


@pytest.mark.anyio
async def test_ingest_with_invalid_file_path():
    result = await aurora_ingest(
        content="Test content",
        document_type="document",
        source="test",
        metadata={"file_path": "/nonexistent/path/file.txt"},
    )

    assert result["project_path"] is None
    assert "id" in result
