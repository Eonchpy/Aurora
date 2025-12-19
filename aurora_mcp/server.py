from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Dict
from uuid import UUID

import tiktoken
from fastmcp import FastMCP
from sqlalchemy import select, func, text, literal_column, bindparam, cast, String, Float, case, or_
from sqlalchemy.ext.asyncio import AsyncSession

from aurora_mcp.config import get_settings
from aurora_mcp.database import get_session, init_engine
from aurora_mcp.models import Document
from aurora_mcp.services.embedding import EmbeddingService
from aurora_mcp.utils.project_detector import find_project_root


# Initialize MCP server
mcp = FastMCP("aurora_kb")

# Global services (initialized on first use)
_embedding_service: EmbeddingService | None = None
_tokenizer = None
logger = logging.getLogger(__name__)

# Token limit for embeddings (留一些余量)
MAX_EMBEDDING_TOKENS = 8000


def count_tokens(text: str, model: str = "cl100k_base") -> int:
    """Count tokens in text using tiktoken."""
    global _tokenizer
    if _tokenizer is None:
        _tokenizer = tiktoken.get_encoding(model)
    return len(_tokenizer.encode(text))


def build_tsquery(query: str) -> str:
    """Build a safe tsquery string from user input."""
    safe_query = re.sub(r"[^\w\s]", " ", query or "")
    terms = [term for term in safe_query.split() if term]
    return " & ".join(terms)


async def get_embedding_service() -> EmbeddingService:
    """Get or create embedding service"""
    global _embedding_service
    if _embedding_service is None:
        settings = get_settings()
        _embedding_service = EmbeddingService(settings)
    return _embedding_service


@mcp.tool()
async def aurora_ingest(
    content: str,
    document_type: str,
    source: str,
    namespace: str = "default",
    metadata: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    """Store content into AuroraKB with automatic semantic embedding generation.

    Use this to save conversations, documents, or any text content that you want to
    retrieve later based on semantic similarity. Supports namespaces for project
    isolation and metadata for flexible filtering.

    IMPORTANT - Content Length Limits:
    - Maximum: ~8000 tokens (~32,000 characters for English text)
    - If content exceeds limit, you have several options:
      1. Split into multiple parts and link with metadata (e.g., parent_id, chunk_index)
      2. Summarize key points and store the summary
      3. Store only the most relevant sections

    For long documents, consider splitting strategically:
    - Use metadata.parent_id to link related chunks
    - Use metadata.chunk_index to maintain order
    - Add overlap between chunks for context continuity

    Args:
        content: Text content to store (max ~8000 tokens / ~32,000 characters)
        document_type: Type of content ('conversation', 'document', 'decision', 'resolution')
        source: Source system or origin (e.g., 'claude_code', 'cursor', 'manual')
        namespace: Namespace for project/domain isolation (default: 'default')
        metadata: Optional metadata for flexible filtering and chunk linking
                 Suggested fields: parent_id, chunk_index, total_chunks, author, tags, file_path

    Project detection:
        - When metadata.file_path is provided, project root is auto-detected and stored in project_path
        - project_path is included in the response for transparency
        - If detection fails or file_path is missing, project_path will be None
    """
    # Validate content length
    token_count = count_tokens(content)
    if token_count > MAX_EMBEDDING_TOKENS:
        return {
            "error": "Content exceeds maximum length",
            "token_count": token_count,
            "max_tokens": MAX_EMBEDDING_TOKENS,
            "char_count": len(content),
            "suggestion": (
                "Content is too long for embedding generation. Consider:\n"
                "1. Split into chunks with metadata linking (parent_id, chunk_index)\n"
                "2. Summarize key points and store the summary\n"
                "3. Store only the most relevant sections\n"
                f"Current: {token_count} tokens, Max: {MAX_EMBEDDING_TOKENS} tokens"
            )
        }

    # Get services
    embedding_service = await get_embedding_service()

    # Detect project path if file_path provided
    project_path: str | None = None
    file_path = None
    if metadata and isinstance(metadata, dict):
        file_path = metadata.get("file_path")
    if file_path:
        project_path = find_project_root(str(file_path))
        if project_path:
            logger.info("Detected project_path=%s for file_path=%s", project_path, file_path)
        else:
            logger.debug("No project detected for file_path=%s", file_path)

    # Generate embedding
    embedding = await embedding_service.embed(content)

    # Create document
    async for session in get_session():
        doc = Document(
            content=content,
            embedding_vector=embedding,
            metadata_json=metadata or {},
            namespace=namespace,
            document_type=document_type,
            source=source,
            project_path=project_path,
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)

        return {
            "id": str(doc.id),
            "namespace": doc.namespace,
            "document_type": doc.document_type,
            "token_count": token_count,
            "project_path": project_path,
            "created_at": doc.created_at.isoformat()
        }


@mcp.tool()
async def aurora_search(
    query: str,
    namespace: str | None = None,
    document_type: str | None = None,
    limit: int = 10,
    threshold: float = 0.2,
    metadata_filters: Dict[str, Any] | None = None,
    current_project_path: str | None = None,
    use_hybrid: bool = True
) -> Dict[str, Any]:
    """Perform semantic or hybrid similarity search in AuroraKB to find relevant content.

    By default, searches across ALL document types to maximize recall and find the most relevant
    content regardless of where it's stored. Semantic search works best without artificial
    constraints - let similarity scores determine relevance.

    Use document_type filter ONLY when the user explicitly mentions a specific type in their query:
    - "find documents about X" → use document_type="document"
    - "search conversations about Y" → use document_type="conversation"
    - "what does aurora do" → leave document_type=None (search all types)

    Returns documents ranked by semantic similarity score, with the most relevant content first.

    Args:
        query: Search query text describing what you're looking for
        namespace: Filter by namespace/project (optional, use only if user specifies a project)
        document_type: Filter by specific type (optional, use only when user explicitly mentions type)
                      Available: 'conversation', 'document', 'decision', 'resolution'
        limit: Maximum number of results to return (default: 10)
        threshold: Minimum similarity score 0.0-1.0 (default: 0.2, lower for broader results)
        metadata_filters: Optional metadata filters like author, tags, or source
        current_project_path: Optional project root path to boost same-project results (+0.15, capped at 1.0)
        use_hybrid: Use hybrid search (embedding + full-text, weighted) when True; embedding-only when False.
    """
    # Guard empty query
    if not query:
        return {
            "documents": [],
            "total_found": 0,
            "query": query,
            "current_project": current_project_path,
            "search_type": "hybrid" if use_hybrid else "embedding",
        }

    # Get services
    embedding_service = await get_embedding_service()

    # Generate query embedding
    query_embedding = await embedding_service.embed(query)

    # Build SQL query with vector similarity
    async for session in get_session():
        # Convert embedding to PostgreSQL vector format string
        vector_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        # Build embedding similarity expression as raw SQL
        embedding_similarity_sql = f"(1.0 - (embedding_vector <=> '{vector_str}'::vector))"

        tsquery_str = build_tsquery(query)

        stmt = select(
            Document.id,
            Document.content,
            Document.metadata_json,
            Document.namespace,
            Document.document_type,
            Document.source,
            Document.created_at,
            Document.project_path,
            literal_column(embedding_similarity_sql).label("embedding_score"),
        )

        search_type = "hybrid" if use_hybrid else "embedding"

        if use_hybrid and tsquery_str:
            # Build hybrid search with ts_rank_cd
            keyword_rank_sql = f"ts_rank_cd(content_tsv, to_tsquery('english', '{tsquery_str}'), 32)"
            hybrid_score_sql = f"((0.7 * {embedding_similarity_sql}) + (0.3 * {keyword_rank_sql}))"

            if current_project_path:
                # Escape single quotes in path
                safe_path = current_project_path.replace("'", "''")
                final_score_sql = f"""
                    CASE
                        WHEN project_path = '{safe_path}'
                        THEN LEAST(1.0, {hybrid_score_sql} + 0.15)
                        ELSE {hybrid_score_sql}
                    END
                """
            else:
                final_score_sql = hybrid_score_sql

            stmt = stmt.add_columns(
                literal_column(keyword_rank_sql).label("keyword_score"),
                literal_column(final_score_sql).label("final_score")
            )

            # WHERE clause: embedding similarity OR full-text match
            stmt = stmt.where(
                or_(
                    text(f"{embedding_similarity_sql} > {threshold}"),
                    text(f"content_tsv @@ to_tsquery('english', '{tsquery_str}')"),
                )
            )
            order_expr = text("final_score DESC")
        else:
            # Embedding-only path or empty tsquery
            if current_project_path:
                safe_path = current_project_path.replace("'", "''")
                final_score_sql = f"""
                    CASE
                        WHEN project_path = '{safe_path}'
                        THEN LEAST(1.0, {embedding_similarity_sql} + 0.15)
                        ELSE {embedding_similarity_sql}
                    END
                """
            else:
                final_score_sql = embedding_similarity_sql

            stmt = stmt.add_columns(literal_column(final_score_sql).label("final_score"))
            stmt = stmt.where(text(f"{embedding_similarity_sql} > {threshold}"))
            order_expr = text("final_score DESC")

        # Apply filters
        if namespace:
            stmt = stmt.where(Document.namespace == namespace)
        if document_type:
            stmt = stmt.where(Document.document_type == document_type)

        # Apply metadata filters
        if metadata_filters:
            for key, value in metadata_filters.items():
                stmt = stmt.where(
                    func.jsonb_extract_path_text(Document.metadata_json, key) == str(value)
                )

        # Order by similarity and limit
        stmt = stmt.order_by(order_expr).limit(limit)

        # Execute query
        start = time.perf_counter()
        result = await session.execute(stmt)
        rows = result.fetchall()
        elapsed_ms = (time.perf_counter() - start) * 1000

        documents = []
        for row in rows:
            embedding_score = float(row.embedding_score)
            keyword_score_val = float(row.keyword_score) if hasattr(row, "keyword_score") else None
            final_score = (
                float(row.final_score) if hasattr(row, "final_score") else embedding_score
            )
            documents.append(
                {
                    "id": str(row.id),
                    "content": row.content,
                    "metadata": row.metadata_json or {},
                    "namespace": row.namespace,
                    "document_type": row.document_type,
                    "source": row.source,
                    "created_at": row.created_at.isoformat(),
                    "project_path": row.project_path,
                    "is_same_project": bool(
                        current_project_path and row.project_path == current_project_path
                    ),
                    "similarity_score": final_score,
                    "embedding_score": embedding_score,
                    "keyword_score": keyword_score_val,
                }
            )

        logger.info(
            "Hybrid search completed",
            extra={
                "query": query,
                "elapsed_ms": round(elapsed_ms, 3),
                "total_found": len(documents),
                "search_type": search_type,
            },
        )

        return {
            "documents": documents,
            "total_found": len(documents),
            "query": query,
            "current_project": current_project_path,
            "search_type": search_type,
        }


@mcp.tool()
async def aurora_retrieve(
    document_id: str,
    include_embedding: bool = False
) -> Dict[str, Any]:
    """Retrieve a specific document from AuroraKB by its unique ID.

    Use this when you already know the document ID (e.g., from a previous search)
    and want to fetch the full content and metadata.

    Args:
        document_id: Unique document identifier
        include_embedding: Whether to include the embedding vector (default: False)
    """
    async for session in get_session():
        # Parse UUID
        try:
            doc_uuid = UUID(document_id)
        except ValueError:
            return {"error": f"Invalid document ID format: {document_id}"}

        # Query document
        stmt = select(Document).where(Document.id == doc_uuid)
        result = await session.execute(stmt)
        doc = result.scalar_one_or_none()

        if not doc:
            return {"error": f"Document not found: {document_id}"}

        response = {
            "id": str(doc.id),
            "content": doc.content,
            "metadata": doc.metadata_json or {},
            "namespace": doc.namespace,
            "document_type": doc.document_type,
            "source": doc.source,
            "created_at": doc.created_at.isoformat(),
            "updated_at": doc.updated_at.isoformat()
        }

        if include_embedding:
            response["embedding"] = doc.embedding_vector

        return response


async def main() -> None:
    """Main entry point for MCP server"""
    # Initialize database engine
    await init_engine()

    # Run MCP server
    await mcp.run_stdio_async()


if __name__ == "__main__":
    asyncio.run(main())
