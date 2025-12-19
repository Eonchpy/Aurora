from __future__ import annotations

from typing import Any, List

from openai import AsyncOpenAI


class Reranker:
    """Result reranking using an OpenAI-compatible model."""

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str,
        temperature: float = 0.0,
        max_tokens: int = 100,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def rerank(
        self,
        query: str,
        documents: List[dict[str, Any]],
        top_k: int = 10,
    ) -> List[dict[str, Any]]:
        """Rerank documents using LLM and return top_k."""
        if not documents:
            return []

        # Build prompt with query and document information
        prompt_lines = [
            "You are a search relevance expert. Rank these documents by relevance to the user's query.",
            "",
            f'Query: "{query}"',
            "",
            "Ranking Guidelines:",
            "1. Prioritize documents that DIRECTLY answer the query over general overviews",
            "2. Exact title matches are strong signals of relevance",
            "3. Specific documents are better than broad documents covering multiple topics",
            "4. Consider document type and tags as relevance signals",
            "5. The hybrid search score indicates initial relevance - use it as a reference",
            "",
            "Documents:",
        ]

        for i, doc in enumerate(documents[:20]):  # Only rerank top 20 for cost
            # Extract metadata
            title = doc.get("metadata", {}).get("title", "Untitled")
            tags = doc.get("metadata", {}).get("tags", "")
            doc_type = doc.get("document_type", "unknown")

            # Get longer snippet for better context
            content = doc.get("content") or ""
            snippet = content[:600] if len(content) > 600 else content

            # Get hybrid search score if available
            score = doc.get("final_score") or doc.get("similarity", 0.0)

            prompt_lines.append(f"\n{i+1}. [Score: {score:.3f}]")
            prompt_lines.append(f"   Title: {title}")
            prompt_lines.append(f"   Type: {doc_type} | Tags: {tags}")
            prompt_lines.append(f"   Content: {snippet}...")

        prompt_lines.append(
            "\nReturn ONLY the ranking as comma-separated numbers (e.g., 3,1,5,2,4)."
        )
        prompt_lines.append(
            "Put the MOST relevant document first:"
        )
        prompt = "\n".join(prompt_lines)

        response = await self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        content = response.choices[0].message.content or ""
        ranking = []
        for token in content.replace("\n", " ").split(","):
            tok = token.strip()
            if tok.isdigit():
                ranking.append(int(tok) - 1)

        reranked = [documents[i] for i in ranking if 0 <= i < len(documents)]
        # If LLM returns fewer than available, append the rest in original order
        remaining = [doc for idx, doc in enumerate(documents) if idx not in ranking]
        reranked.extend(remaining)

        return reranked[:top_k]
