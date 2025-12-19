from __future__ import annotations

import pytest

from aurora_mcp.services.query_expander import QueryExpander
from aurora_mcp.config import get_settings


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
async def test_expander_success(monkeypatch: pytest.MonkeyPatch):
    expander = QueryExpander(
        model="m",
        base_url="http://x",
        api_key="k",
    )
    # Mock response must contain original query and pass length validation
    # Original: "database query" (14 chars), Expanded: "database query optimization indexing" (37 chars, <5x)
    monkeypatch.setattr(expander, "_client", _FakeClient("database query optimization indexing"))

    expanded = await expander.expand("database query")
    assert expanded == "database query optimization indexing"


@pytest.mark.anyio
async def test_expander_failure(monkeypatch: pytest.MonkeyPatch):
    expander = QueryExpander(
        model="m",
        base_url="http://x",
        api_key="k",
    )
    monkeypatch.setattr(expander, "_client", _FakeClient(raise_err=RuntimeError("boom")))

    # Exception is caught and None is returned (graceful degradation)
    result = await expander.expand("orig")
    assert result is None


@pytest.mark.anyio
async def test_expander_integration_when_configured():
    """Real call only when QUERY_EXPANSION_MODEL and keys are configured."""
    settings = get_settings()
    model = settings.query_expansion_model
    api_key = settings.query_expansion_api_key or settings.openai_api_key
    base_url = settings.query_expansion_base_url or settings.openai_base_url

    if not model or not api_key or not base_url or "sk-your" in (api_key or ""):
        pytest.skip("Query expansion not configured with real credentials")

    expander = QueryExpander(
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=settings.query_expansion_temperature,
        max_tokens=settings.query_expansion_max_tokens,
    )

    expanded = await expander.expand("database migration guide")
    assert expanded
    assert isinstance(expanded, str)
