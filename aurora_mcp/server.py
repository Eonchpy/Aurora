from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Dict, Literal
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
from aurora_mcp.services.query_expander import QueryExpander
from aurora_mcp.services.reranker import Reranker
from aurora_mcp.services.summarizer import Summarizer


# Initialize MCP server
mcp = FastMCP("aurora_kb")

# Allowed document types (enforced at ingest time)
ALLOWED_DOCUMENT_TYPES = {
    "document",      # General documents
    "conversation",  # Conversation records
    "decision",      # Decision records
    "resolution",    # Resolutions/solutions
    "report"         # Report documents
}

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
    document_type: Literal["document", "conversation", "decision", "resolution", "report"],
    title: str,
    namespace: str = "default",
    source: str | None = None,
    metadata: Dict[str, Any] | None = None,
    working_directory: str | None = None,
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
        title: Brief title or description (REQUIRED). Used for search result display to enable
               two-stage retrieval optimization. Should be concise (1-2 sentences) and descriptive.
        namespace: Namespace for project/domain isolation (default: 'default')
        source: Source/role identifier (optional, e.g., 'qc', 'backend', 'frontend')
                If not provided, uses AURORA_AGENT_ID from env, or defaults to 'unknown'
        metadata: Optional metadata for flexible filtering and chunk linking
                 Suggested fields: parent_id, chunk_index, total_chunks, author, tags
        working_directory: Current working directory path (recommended). Used to auto-detect
                          project root for project-aware search. Pass your cwd here.

    Project detection:
        - When working_directory is provided, project root is auto-detected and stored in project_path
        - project_path is included in the response for transparency
        - If detection fails or working_directory is missing, project_path will be None
    """
    # Validate document_type
    if document_type not in ALLOWED_DOCUMENT_TYPES:
        return {
            "error": f"Invalid document_type: '{document_type}'",
            "allowed_types": sorted(list(ALLOWED_DOCUMENT_TYPES)),
            "suggestion": "Please use one of the allowed document types"
        }

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

    # Auto-detect source if not provided
    if source is None:
        settings = get_settings()
        source = settings.agent_id or "unknown"

    # Get services
    embedding_service = await get_embedding_service()

    # Detect project path from working_directory (preferred)
    project_path: str | None = None
    if working_directory:
        project_path = find_project_root(working_directory)
        if project_path:
            logger.info("Detected project_path=%s from working_directory=%s", project_path, working_directory)
        else:
            logger.debug("No project detected for working_directory=%s", working_directory)

    # Generate embedding
    embedding = await embedding_service.embed(content)

    # Use agent-provided title as brief_summary (required field)
    brief_summary: str = title

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
            brief_summary=brief_summary,
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
            "title": brief_summary,
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
    use_hybrid: bool = True,
    expand_query: bool = False,
    rerank: bool = False,
    include_full_content: bool = False
) -> Dict[str, Any]:
    """Perform semantic or hybrid similarity search in AuroraKB to find relevant content.

    By default, searches across ALL document types to maximize recall and find the most relevant
    content regardless of where it's stored. Semantic search works best without artificial
    constraints - let similarity scores determine relevance.

    **Search Tips:**
    For better recall, consider adding synonyms or related terms to your query before calling.
    Example: "Phase 4 plan" → "Phase 4 plan execution implementation 执行计划"

    **Token Optimization (Two-Stage Retrieval):**
    By default, returns brief summaries instead of full content to reduce token consumption.
    - Stage 1 (Search): Review summaries to determine relevance
    - Stage 2 (Retrieve): Use aurora_retrieve(document_id) to fetch full content for relevant documents

    Use document_type filter ONLY when the user explicitly mentions a specific type in their query:
    - "find documents about X" → use document_type="document"
    - "search conversations about Y" → use document_type="conversation"
    - "what does aurora do" → leave document_type=None (search all types)

    Returns documents ranked by semantic similarity score, with the most relevant content first.

    Args:
        query: Search query text. For better recall, include synonyms or related terms.
        namespace: Filter by namespace/project (optional, use only if user specifies a project)
        document_type: Filter by specific type (optional, use only when user explicitly mentions type)
                      Available: 'conversation', 'document', 'decision', 'resolution'
        limit: Maximum number of results to return (default: 10)
        threshold: Minimum similarity score 0.0-1.0 (default: 0.2, lower for broader results)
        metadata_filters: Optional metadata filters like author, tags, or source
        current_project_path: Optional project root path to boost same-project results (+0.15, capped at 1.0)
        use_hybrid: Use hybrid search (embedding + full-text, weighted) when True; embedding-only when False.
        expand_query: Use LLM to auto-expand query (default: False). Usually unnecessary as you can
                     expand the query yourself with better context awareness.
        rerank: Rerank results via LLM (default: False). Usually unnecessary as hybrid search with
                mathematical scoring is more reliable than LLM subjective judgment.
        include_full_content: Return full document content instead of summaries (default: False).
                             Set to True for backward compatibility or when full content is needed immediately.
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

    original_query = query

    # Optional query expansion (only when model configured)
    settings = get_settings()
    expanded_query = None
    if expand_query and settings.query_expansion_model:
        try:
            expander = QueryExpander(
                model=settings.query_expansion_model,
                base_url=settings.query_expansion_base_url or settings.openai_base_url,
                api_key=settings.query_expansion_api_key or settings.openai_api_key,
                temperature=settings.query_expansion_temperature,
                max_tokens=settings.query_expansion_max_tokens,
            )
            expanded = await expander.expand(query)
            if expanded:
                expanded_query = expanded
                query = expanded
        except Exception as exc:  # noqa: BLE001
            logger.warning("Query expansion failed; using original query", exc_info=exc)

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
            Document.brief_summary,
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

            # Token Optimization: Return summary by default, full content on request
            if include_full_content:
                # Backward compatibility: return full content
                content_field = row.content
                has_summary = row.brief_summary is not None
            else:
                # Two-stage retrieval: return summary if available, else truncated content
                if row.brief_summary:
                    content_field = row.brief_summary
                    has_summary = True
                else:
                    # Fallback: truncate content to first 200 tokens (~800 chars)
                    content_field = row.content[:800] + "..." if len(row.content) > 800 else row.content
                    has_summary = False

            documents.append(
                {
                    "id": str(row.id),
                    "content": content_field,
                    "has_summary": has_summary,
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

        # Optional reranking
        reranked_docs = documents
        rerank_model = settings.reranking_model
        if rerank and rerank_model and documents:
            try:
                reranker = Reranker(
                    model=rerank_model,
                    base_url=settings.reranking_base_url or settings.openai_base_url,
                    api_key=settings.reranking_api_key or settings.openai_api_key,
                    temperature=settings.reranking_temperature,
                    max_tokens=settings.reranking_max_tokens,
                )
                reranked_docs = await reranker.rerank(query, documents, settings.reranking_top_k)
                logger.info(
                    "Reranking applied",
                    extra={"count": len(documents), "returned": len(reranked_docs), "model": rerank_model},
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Reranking failed; using original ranking", exc_info=exc)

        logger.info(
            "Hybrid search completed",
            extra={
                "query": query,
                "elapsed_ms": round(elapsed_ms, 3),
                "total_found": len(reranked_docs),
                "search_type": search_type,
            },
        )

        return {
            "documents": reranked_docs,
            "total_found": len(reranked_docs),
            "query": query,
            "current_project": current_project_path,
            "search_type": search_type,
            "original_query": original_query,
            "expanded_query": expanded_query,
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


@mcp.tool()
async def aurora_update(
    document_id: str,
    content: str | None = None,
    metadata: dict | None = None,
    document_type: str | None = None
) -> Dict[str, Any]:
    """Update an existing document in AuroraKB.

    Use this to modify document content, metadata, or document type.
    When content is updated, the embedding vector will be regenerated automatically.

    Args:
        document_id: Unique document identifier
        content: New content (optional, will regenerate embedding if provided)
        metadata: New metadata (optional, will merge with existing)
        document_type: New document type (optional)

    Returns:
        Updated document information or error message
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

        # Track what was updated
        updated_fields = []

        # Update content and regenerate embedding if provided
        if content is not None:
            # Validate content length
            token_count = count_tokens(content)
            if token_count > MAX_EMBEDDING_TOKENS:
                return {
                    "error": "Content exceeds maximum length",
                    "token_count": token_count,
                    "max_tokens": MAX_EMBEDDING_TOKENS
                }

            doc.content = content
            updated_fields.append("content")

            # Regenerate embedding
            embedding_service = await get_embedding_service()
            doc.embedding_vector = await embedding_service.embed(content)
            updated_fields.append("embedding")

            # Regenerate summary if configured
            settings = get_settings()
            if settings.summarization_model:
                try:
                    from aurora_mcp.services.summarizer import Summarizer
                    summarizer = Summarizer(
                        model=settings.summarization_model,
                        base_url=settings.summarization_base_url or settings.query_expansion_base_url or settings.openai_base_url,
                        api_key=settings.summarization_api_key or settings.query_expansion_api_key or settings.openai_api_key,
                        temperature=settings.summarization_temperature,
                        max_tokens=settings.summarization_max_tokens,
                    )
                    doc.brief_summary = await summarizer.summarize(content)
                    updated_fields.append("summary")
                except Exception as exc:
                    logger.warning("Summary regeneration failed", exc_info=exc)

        # Update metadata (merge with existing)
        if metadata is not None:
            existing_metadata = doc.metadata_json or {}
            existing_metadata.update(metadata)
            # Force SQLAlchemy to detect the change
            from sqlalchemy.orm.attributes import flag_modified
            doc.metadata_json = existing_metadata
            flag_modified(doc, "metadata_json")
            updated_fields.append("metadata")

        # Update document type
        if document_type is not None:
            doc.document_type = document_type
            updated_fields.append("document_type")

        if not updated_fields:
            return {"error": "No fields to update"}

        # Commit changes
        await session.commit()
        await session.refresh(doc)

        return {
            "id": str(doc.id),
            "updated_fields": updated_fields,
            "namespace": doc.namespace,
            "document_type": doc.document_type,
            "updated_at": doc.updated_at.isoformat()
        }


@mcp.tool()
async def aurora_delete(
    document_id: str
) -> Dict[str, Any]:
    """Delete a document from AuroraKB.

    Use this to remove documents that are no longer needed or were created by mistake.
    This operation is permanent and cannot be undone.

    Args:
        document_id: Unique document identifier

    Returns:
        Deletion confirmation or error message
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

        # Store info before deletion
        doc_info = {
            "id": str(doc.id),
            "namespace": doc.namespace,
            "document_type": doc.document_type,
            "created_at": doc.created_at.isoformat()
        }

        # Delete document
        await session.delete(doc)
        await session.commit()

        return {
            "success": True,
            "message": "Document deleted successfully",
            "deleted_document": doc_info
        }


@mcp.tool()
async def aurora_list(
    namespace: str | None = None,
    document_type: str | None = None,
    source: str | None = None,
    project_path: str | None = None,
    limit: int = 20,
    offset: int = 0
) -> Dict[str, Any]:
    """List documents from AuroraKB with structured filtering.

    Use this to browse documents by namespace, type, source, or project.
    Returns brief document information for users to select and retrieve.

    Args:
        namespace: Filter by namespace (optional)
        document_type: Filter by document type (optional)
        source: Filter by source (optional)
        project_path: Filter by project path (optional)
        limit: Maximum number of results (default: 20, max: 100)
        offset: Number of results to skip for pagination (default: 0)

    Returns:
        List of documents with brief information (id, title, preview)
    """
    # Validate limit
    if limit > 100:
        limit = 100
    if limit < 1:
        limit = 1

    async for session in get_session():
        # Build query
        stmt = select(
            Document.id,
            Document.brief_summary,
            Document.content,
            Document.namespace,
            Document.document_type,
            Document.source,
            Document.project_path,
            Document.created_at
        )

        # Apply filters (case-insensitive for string fields)
        if namespace:
            stmt = stmt.where(func.lower(Document.namespace) == namespace.lower())
        if document_type:
            stmt = stmt.where(func.lower(Document.document_type) == document_type.lower())
        if source:
            stmt = stmt.where(func.lower(Document.source) == source.lower())
        if project_path:
            stmt = stmt.where(func.lower(Document.project_path) == project_path.lower())

        # Order by created_at descending (newest first)
        stmt = stmt.order_by(Document.created_at.desc())

        # Get total count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = await session.scalar(count_stmt)

        # Apply pagination
        stmt = stmt.limit(limit).offset(offset)

        # Execute query
        result = await session.execute(stmt)
        rows = result.fetchall()

        documents = []
        for row in rows:
            # Use title if available, otherwise create preview
            if row.brief_summary:
                display_text = row.brief_summary
            else:
                # Create preview from first 100 characters
                display_text = row.content[:100] + "..." if len(row.content) > 100 else row.content

            documents.append({
                "id": str(row.id),
                "title": row.brief_summary,
                "preview": display_text,
                "namespace": row.namespace,
                "document_type": row.document_type,
                "source": row.source,
                "project_path": row.project_path,
                "created_at": row.created_at.isoformat()
            })

        return {
            "documents": documents,
            "total": total or 0,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + len(documents)) < (total or 0)
        }


async def main() -> None:
    """Main entry point for MCP server"""
    # Initialize database engine
    await init_engine()

    # Run MCP server
    await mcp.run_stdio_async()


if __name__ == "__main__":
    asyncio.run(main())
