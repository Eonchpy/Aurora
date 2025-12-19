from __future__ import annotations

import hashlib
import logging
import time
from typing import Optional

from cachetools import TTLCache
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class QueryExpander:
    """Query expansion using an OpenAI-compatible model with caching."""

    # Class-level cache shared across all instances
    # TTL=3600 (1 hour), maxsize=1000 queries
    _cache: TTLCache = TTLCache(maxsize=1000, ttl=3600)

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str,
        temperature: float = 0.3,
        max_tokens: int = 50,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    def _get_cache_key(self, query: str) -> str:
        """Generate cache key from query and model parameters."""
        # Include model and temperature in cache key to avoid conflicts
        key_data = f"{query}|{self.model}|{self.temperature}"
        return hashlib.md5(key_data.encode()).hexdigest()

    async def expand(self, query: str) -> Optional[str]:
        """Expand a search query with related terms (with caching)."""
        # Input validation
        if not query or not query.strip():
            return None

        # Check cache first
        cache_key = self._get_cache_key(query)
        if cache_key in self._cache:
            cached_result = self._cache[cache_key]
            logger.debug(
                "Query expansion cache hit",
                extra={"query": query, "cached_result": cached_result}
            )
            return cached_result

        # Cache miss - call LLM
        start = time.perf_counter()

        prompt = f"""Given this search query, expand it with related technical terms that would help find relevant documents.

Original query: "{query}"

Rules:
1. Keep the original query intact
2. Add 3-5 related technical terms
3. Focus on synonyms and related concepts
4. Return only the expanded query, no explanation

Examples:
- Input: "database optimization"
  Output: database optimization performance tuning query indexing connection pooling

- Input: "API authentication"
  Output: API authentication OAuth JWT token authorization security

Expanded query:"""

        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            if not response.choices:
                return None

            expanded = response.choices[0].message.content or ""
            expanded = expanded.strip()

            # Remove quotes if LLM added them
            if expanded.startswith('"') and expanded.endswith('"'):
                expanded = expanded[1:-1]

            # Validation 1: Check if expanded query is empty
            if not expanded:
                logger.warning("LLM returned empty expansion")
                return None

            # Validation 2: Check if expanded query contains original query
            if query.lower() not in expanded.lower():
                logger.warning(
                    "Expanded query doesn't contain original query",
                    extra={"original": query, "expanded": expanded}
                )
                return None

            # Validation 3: Length check - expanded should be longer but not too long
            if len(expanded) < len(query):
                logger.warning(
                    "Expanded query is shorter than original",
                    extra={"original": query, "expanded": expanded}
                )
                return None

            if len(expanded) > len(query) * 5:
                logger.warning(
                    "Expanded query is too long (>5x original)",
                    extra={"original": query, "expanded": expanded, "ratio": len(expanded) / len(query)}
                )
                return None

            # Validation 4: Format check - should not contain newlines or excessive punctuation
            if "\n" in expanded or expanded.count(".") > 2:
                logger.warning(
                    "Expanded query has invalid format (newlines or excessive punctuation)",
                    extra={"original": query, "expanded": expanded}
                )
                return None

            # Store in cache
            if expanded:
                self._cache[cache_key] = expanded

            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "Query expansion completed",
                extra={
                    "original_query": query,
                    "expanded_query": expanded,
                    "elapsed_ms": elapsed_ms,
                    "model": self.model,
                    "cache_hit": False
                }
            )

            return expanded

        except Exception as exc:
            logger.error("Query expansion failed", exc_info=exc)
            return None
