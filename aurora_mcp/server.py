from __future__ import annotations

import asyncio
from typing import Any, Dict
from uuid import UUID

import tiktoken
from fastmcp import FastMCP
from sqlalchemy import select, func, text, literal_column, bindparam, cast, String
from sqlalchemy.ext.asyncio import AsyncSession

from aurora_mcp.config import get_settings
from aurora_mcp.database import get_session, init_engine
from aurora_mcp.models import Document
from aurora_mcp.services.embedding import EmbeddingService


# Initialize MCP server
mcp = FastMCP("aurora_kb")

# Global services (initialized on first use)
_embedding_service: EmbeddingService | None = None
_tokenizer = None

# Token limit for embeddings (留一些余量)
MAX_EMBEDDING_TOKENS = 8000


def count_tokens(text: str, model: str = "cl100k_base") -> int:
    """Count tokens in text using tiktoken."""
    global _tokenizer
    if _tokenizer is None:
        _tokenizer = tiktoken.get_encoding(model)
    return len(_tokenizer.encode(text))


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
                 Suggested fields: parent_id, chunk_index, total_chunks, author, tags
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
            source=source
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)

        return {
            "id": str(doc.id),
            "namespace": doc.namespace,
            "document_type": doc.document_type,
            "token_count": token_count,
            "created_at": doc.created_at.isoformat()
        }


@mcp.tool()
async def aurora_search(
    query: str,
    namespace: str | None = None,
    document_type: str | None = None,
    limit: int = 10,
    threshold: float = 0.7,
    metadata_filters: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    """Perform semantic similarity search in AuroraKB to find relevant content.

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
        threshold: Minimum similarity score 0.0-1.0 (default: 0.7, lower for broader results)
        metadata_filters: Optional metadata filters like author, tags, or source
    """
    # Get services
    embedding_service = await get_embedding_service()

    # Generate query embedding
    query_embedding = await embedding_service.embed(query)

    # Build SQL query with vector similarity
    async for session in get_session():
        # Convert embedding to PostgreSQL vector format string
        vector_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        # Build base query with cosine similarity using text() for the entire expression
        similarity_score = func.cast(
            text(f"1 - (embedding_vector <=> '{vector_str}'::vector)"),
            String
        ).label("similarity_score")

        stmt = select(
            Document.id,
            Document.content,
            Document.metadata_json,
            Document.namespace,
            Document.document_type,
            Document.source,
            Document.created_at,
            similarity_score
        ).where(
            text(f"1 - (embedding_vector <=> '{vector_str}'::vector) > {threshold}")
        )

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
        stmt = stmt.order_by(text("similarity_score DESC")).limit(limit)

        # Execute query
        result = await session.execute(stmt)
        rows = result.fetchall()

        documents = [
            {
                "id": str(row.id),
                "content": row.content,
                "metadata": row.metadata_json or {},
                "namespace": row.namespace,
                "document_type": row.document_type,
                "source": row.source,
                "created_at": row.created_at.isoformat(),
                "similarity_score": float(row.similarity_score)
            }
            for row in rows
        ]

        return {
            "documents": documents,
            "total_found": len(documents),
            "query": query
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
