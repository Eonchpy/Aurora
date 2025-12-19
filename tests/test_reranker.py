from __future__ import annotations

import pytest

from aurora_mcp.services.reranker import Reranker


class _FakeResponse:
    class Choice:
        def __init__(self, content: str) -> None:
            self.message = type("Msg", (), {"content": content})

    def __init__(self, content: str) -> None:
        self.choices = [self.Choice(content)]


class _FakeClient:
    def __init__(self, content: str | None = None, raise_err: Exception | None = None) -> None:
        self._content = content
        self._raise = raise_err

    class _Chat:
        def __init__(self, parent: "_FakeClient") -> None:
            self._parent = parent

        class _Completions:
            def __init__(self, parent: "_FakeClient") -> None:
                self._parent = parent

            async def create(self, **kwargs):
                if self._parent._raise:
                    raise self._parent._raise
                return _FakeResponse(self._parent._content or "")

        @property
        def completions(self):
            return self._Completions(self._parent)

    @property
    def chat(self):
        return self._Chat(self)


@pytest.mark.anyio
async def test_reranker_success(monkeypatch: pytest.MonkeyPatch):
    reranker = Reranker(model="m", base_url="http://x", api_key="k")
    monkeypatch.setattr(reranker, "_client", _FakeClient("2,1"))
    docs = [{"content": "a"}, {"content": "b"}]
    result = await reranker.rerank("q", docs, top_k=2)
    assert result[0]["content"] == "b"
    assert result[1]["content"] == "a"


@pytest.mark.anyio
async def test_reranker_failure(monkeypatch: pytest.MonkeyPatch):
    reranker = Reranker(model="m", base_url="http://x", api_key="k")
    monkeypatch.setattr(reranker, "_client", _FakeClient(raise_err=RuntimeError("boom")))
    docs = [{"content": "a"}, {"content": "b"}]
    with pytest.raises(RuntimeError):
        await reranker.rerank("q", docs, top_k=2)
