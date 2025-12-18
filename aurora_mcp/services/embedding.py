from __future__ import annotations

import hashlib
import itertools
from typing import List, Optional

import httpx
from openai import AsyncOpenAI

from aurora_mcp.config import Settings


class EmbeddingService:
    """Embedding service adapter with deterministic fallback and OpenAI-compatible support."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.provider = settings.embedding_provider.lower()
        self.dimension = settings.embedding_dimension
        self._openai_client: Optional[AsyncOpenAI] = None

        if self.provider == "openai":
            if not settings.openai_api_key:
                raise ValueError("OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai")
            self._openai_client = AsyncOpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
                http_client=httpx.AsyncClient(trust_env=False),
            )

    async def embed(self, text: str) -> List[float]:
        if self.provider in {"mock", "debug"}:
            return self._deterministic_embedding(text)
        if self.provider == "openai":
            return await self._openai_embedding(text)
        raise NotImplementedError(f"Embedding provider '{self.provider}' not implemented")

    async def _openai_embedding(self, text: str) -> List[float]:
        assert self._openai_client is not None
        response = await self._openai_client.embeddings.create(
            model=self.settings.embedding_model,
            dimensions=self.settings.embedding_dimension,
            input=text,
        )
        return response.data[0].embedding

    def _deterministic_embedding(self, text: str) -> List[float]:
        """Generate a deterministic pseudo-embedding for offline development."""
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values = []
        for byte in itertools.islice(itertools.cycle(digest), self.dimension):
            values.append((byte / 255.0) * 2 - 1)  # scale to [-1, 1]
        return values
