from __future__ import annotations

import hashlib
import logging
import time
from typing import Optional

from cachetools import TTLCache
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class Summarizer:
    """Document summarization using an OpenAI-compatible model with caching."""

    # Class-level cache shared across all instances
    # TTL=3600 (1 hour), maxsize=500 summaries
    _cache: TTLCache = TTLCache(maxsize=500, ttl=3600)

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str,
        temperature: float = 0.3,
        max_tokens: int = 150,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    def _get_cache_key(self, content: str) -> str:
        """Generate cache key from content hash and model parameters."""
        # Use content hash to avoid storing large content in cache key
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        key_data = f"{content_hash}|{self.model}|{self.temperature}|{self.max_tokens}"
        return hashlib.md5(key_data.encode()).hexdigest()

    async def summarize(self, content: str) -> Optional[str]:
        """Generate a brief summary of document content (with caching).

        Args:
            content: Full document content to summarize

        Returns:
            Brief summary (100-200 tokens) or None if summarization fails
        """
        # Input validation
        if not content or not content.strip():
            return None

        # Check cache first
        cache_key = self._get_cache_key(content)
        if cache_key in self._cache:
            cached_result = self._cache[cache_key]
            logger.debug(
                "Summarization cache hit",
                extra={"content_length": len(content), "summary_length": len(cached_result)}
            )
            return cached_result

        # Cache miss - call LLM
        start = time.perf_counter()

        prompt = f"""Summarize the following document in 2-3 concise sentences (100-200 tokens). Focus on the main topics, key points, and essential information that would help someone determine if this document is relevant to their search.

Document:
{content}

Brief Summary:"""

        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            if not response.choices:
                return None

            summary = response.choices[0].message.content or ""
            summary = summary.strip()

            # Validation 1: Check if summary is empty
            if not summary:
                logger.warning("LLM returned empty summary")
                return None

            # Validation 2: Summary should be shorter than original
            if len(summary) >= len(content):
                logger.warning(
                    "Summary is longer than or equal to original content",
                    extra={"content_length": len(content), "summary_length": len(summary)}
                )
                return None

            # Validation 3: Summary should be reasonable length (50-1000 chars)
            if len(summary) < 50:
                logger.warning(
                    "Summary is too short",
                    extra={"summary_length": len(summary), "summary": summary}
                )
                return None

            if len(summary) > 1000:
                logger.warning(
                    "Summary is too long (>1000 chars), truncating",
                    extra={"summary_length": len(summary)}
                )
                summary = summary[:1000] + "..."

            # Validation 4: Format check - should not have excessive newlines
            if summary.count("\n") > 5:
                logger.warning(
                    "Summary has excessive newlines, cleaning",
                    extra={"newline_count": summary.count("\n")}
                )
                # Replace multiple newlines with single space
                summary = " ".join(line.strip() for line in summary.split("\n") if line.strip())

            # Store in cache
            if summary:
                self._cache[cache_key] = summary

            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "Summarization completed",
                extra={
                    "content_length": len(content),
                    "summary_length": len(summary),
                    "elapsed_ms": elapsed_ms,
                    "model": self.model,
                    "cache_hit": False
                }
            )

            return summary

        except Exception as exc:
            logger.error("Summarization failed", exc_info=exc)
            return None
