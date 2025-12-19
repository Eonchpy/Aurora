# AuroraKB Core Value Design - Implementation Handbook

## Overview

This handbook guides the implementation of AuroraKB's core value features: **project-aware context tagging** and **same-project search boost**. These features solve the critical problem of context loss when AI agents spawn sub-agents or work across multiple projects.

## Current Status

- ✅ Pure MCP architecture implemented
- ✅ Basic semantic search working
- ✅ Length validation and chunking guidance added
- ✅ Tested on Gemini Codex and Claude Code
- 🎯 **Next**: Implement Core Value Design features

## Implementation Goals

### Problem Statement

When AI agents work on multiple projects or spawn sub-agents:
1. **Context Dilution**: Search results mix content from different projects
2. **Relevance Loss**: Same-project context should be prioritized but isn't
3. **Manual Filtering**: Users must manually specify namespace filters

### Solution

Automatically detect and prioritize same-project content:
1. **Auto-detect project context** from file paths
2. **Tag documents** with project_path automatically
3. **Boost search results** from the same project
4. **Maintain flexibility** - still allow cross-project search when needed

## Architecture Changes

### Database Schema Updates

**File**: `aurora_mcp/models.py`

Add two new fields to the `Document` model:

```python
class Document(Base):
    __tablename__ = "documents"

    # Existing fields...
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content = Column(Text, nullable=False)
    embedding_vector = Column(Vector(1536), nullable=False)
    metadata_json = Column("metadata", JSON, default=dict)
    namespace = Column(String(100), default="default", index=True)
    document_type = Column(String(50), nullable=False, index=True)
    source = Column(String(100), nullable=False, index=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    # NEW FIELDS - Add these
    project_path = Column(String(500), nullable=True, index=True)  # Auto-detected project root path
    priority_level = Column(Integer, default=0, index=True)  # For future priority-based ranking
```

**Migration Strategy**:
- Add columns with `nullable=True` to support existing data
- Create indexes for efficient filtering
- Default `priority_level=0` for all existing records

### Project Detection Logic

**File**: `aurora_mcp/utils/project_detector.py` (NEW FILE)

Create a utility module to detect project root from file paths:

```python
"""Project detection utilities for automatic context tagging."""

import os
from pathlib import Path
from typing import Optional


# Common project root indicators
PROJECT_ROOT_MARKERS = [
    ".git",
    ".hg",
    ".svn",
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "CMakeLists.txt",
    ".project",
    "composer.json",
    "Gemfile",
]


def find_project_root(file_path: str) -> Optional[str]:
    """
    Find the project root directory by walking up from the given file path.

    Looks for common project markers like .git, package.json, pyproject.toml, etc.

    Args:
        file_path: Absolute path to a file or directory

    Returns:
        Absolute path to project root, or None if not found

    Examples:
        >>> find_project_root("/Users/user/projects/myapp/src/main.py")
        "/Users/user/projects/myapp"

        >>> find_project_root("/tmp/random_file.txt")
        None
    """
    if not file_path:
        return None

    try:
        path = Path(file_path).resolve()

        # If it's a file, start from its parent directory
        if path.is_file():
            path = path.parent

        # Walk up the directory tree
        for parent in [path] + list(path.parents):
            # Check for project root markers
            for marker in PROJECT_ROOT_MARKERS:
                if (parent / marker).exists():
                    return str(parent)

            # Stop at filesystem root
            if parent == parent.parent:
                break

        return None

    except (OSError, ValueError):
        return None


def extract_project_name(project_path: str) -> str:
    """
    Extract a human-readable project name from the project path.

    Args:
        project_path: Absolute path to project root

    Returns:
        Project name (last directory component)

    Examples:
        >>> extract_project_name("/Users/user/projects/AuroraKB")
        "AuroraKB"
    """
    return Path(project_path).name


def is_same_project(path1: Optional[str], path2: Optional[str]) -> bool:
    """
    Check if two paths belong to the same project.

    Args:
        path1: First project path
        path2: Second project path

    Returns:
        True if both paths are non-None and identical
    """
    if path1 is None or path2 is None:
        return False
    return path1 == path2
```

**Testing Requirements**:
- Test with various project types (Python, Node.js, Rust, etc.)
- Test with nested projects (monorepo scenarios)
- Test with files outside any project
- Test edge cases (symlinks, network paths, etc.)

### Enhanced Ingest Logic

**File**: `aurora_mcp/server.py`

Update `aurora_ingest` to automatically detect and tag project context:

```python
@mcp.tool()
async def aurora_ingest(
    content: str,
    document_type: str,
    source: str,
    namespace: str = "default",
    metadata: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    """Store content into AuroraKB with automatic semantic embedding generation.

    [Existing docstring content...]

    NEW: Automatically detects project context from metadata.file_path if provided.
    """
    # Validate content length
    token_count = count_tokens(content)
    if token_count > MAX_EMBEDDING_TOKENS:
        return {
            "error": "Content exceeds maximum length",
            # ... existing error response
        }

    # NEW: Auto-detect project context
    project_path = None
    if metadata and "file_path" in metadata:
        from aurora_mcp.utils.project_detector import find_project_root
        project_path = find_project_root(metadata["file_path"])

    # Get services
    embedding_service = await get_embedding_service()
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
            project_path=project_path,  # NEW: Auto-tagged project
            priority_level=0  # NEW: Default priority
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)

        return {
            "id": str(doc.id),
            "namespace": doc.namespace,
            "document_type": doc.document_type,
            "token_count": token_count,
            "project_path": project_path,  # NEW: Return detected project
            "created_at": doc.created_at.isoformat()
        }
```

**Key Changes**:
1. Import `find_project_root` utility
2. Check if `metadata.file_path` exists
3. Auto-detect project root if file_path provided
4. Store `project_path` in document
5. Return `project_path` in response for transparency

### Enhanced Search Logic

**File**: `aurora_mcp/server.py`

Update `aurora_search` to boost same-project results:

```python
@mcp.tool()
async def aurora_search(
    query: str,
    namespace: str | None = None,
    document_type: str | None = None,
    limit: int = 10,
    threshold: float = 0.7,
    metadata_filters: Dict[str, Any] | None = None,
    current_project_path: str | None = None  # NEW parameter
) -> Dict[str, Any]:
    """Perform semantic similarity search in AuroraKB to find relevant content.

    [Existing docstring content...]

    NEW: Automatically boosts results from the same project when current_project_path is provided.
    Same-project results get a +0.15 similarity boost, making them rank higher.

    Args:
        query: Search query text describing what you're looking for
        namespace: Filter by namespace/project (optional, use only if user specifies a project)
        document_type: Filter by type (optional, use only when user explicitly mentions type)
                      Available: 'conversation', 'document', 'decision', 'resolution'
        limit: Maximum number of results to return (default: 10)
        threshold: Minimum similarity score 0.0-1.0 (default: 0.7, lower for broader results)
        metadata_filters: Optional metadata filters like author, tags, or source
        current_project_path: Current project path for boosting same-project results (optional)
                             If provided, results from the same project get +0.15 boost
    """
    # Get services
    embedding_service = await get_embedding_service()
    query_embedding = await embedding_service.embed(query)

    # Build SQL query with vector similarity
    async for session in get_session():
        # Convert embedding to PostgreSQL vector format string
        vector_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        # NEW: Build similarity expression with project boost
        if current_project_path:
            # Boost same-project results by 0.15
            similarity_expr = f"""
                CASE
                    WHEN project_path = '{current_project_path}'
                    THEN LEAST(1.0, (1 - (embedding_vector <=> '{vector_str}'::vector)) + 0.15)
                    ELSE (1 - (embedding_vector <=> '{vector_str}'::vector))
                END
            """
        else:
            # Standard similarity without boost
            similarity_expr = f"1 - (embedding_vector <=> '{vector_str}'::vector)"

        similarity_score = func.cast(
            text(similarity_expr),
            String
        ).label("similarity_score")

        stmt = select(
            Document.id,
            Document.content,
            Document.metadata_json,
            Document.namespace,
            Document.document_type,
            Document.source,
            Document.project_path,  # NEW: Include in results
            Document.created_at,
            similarity_score
        ).where(
            text(f"({similarity_expr}) > {threshold}")
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
        stmt = stmt.order_by(similarity_score.desc()).limit(limit)

        # Execute query
        result = await session.execute(stmt)
        rows = result.fetchall()

        documents = [
            {
                "id": str(row.id),
                "content": row.content,
                "metadata": row.metadata_json,
                "namespace": row.namespace,
                "document_type": row.document_type,
                "source": row.source,
                "project_path": row.project_path,  # NEW: Include in response
                "similarity_score": float(row.similarity_score),
                "created_at": row.created_at.isoformat(),
                "is_same_project": row.project_path == current_project_path if current_project_path else False  # NEW
            }
            for row in rows
        ]

        return {
            "query": query,
            "total_found": len(documents),
            "current_project": current_project_path,  # NEW: Show current project context
            "documents": documents
        }
```

**Key Changes**:
1. Add `current_project_path` parameter
2. Build conditional similarity expression with CASE statement
3. Boost same-project results by +0.15
4. Include `project_path` in SELECT
5. Add `is_same_project` flag in response
6. Return `current_project` in response

**Boost Logic Explanation**:
- Same-project documents get +0.15 similarity boost
- Capped at 1.0 using `LEAST(1.0, score + 0.15)`
- This makes same-project results rank higher without completely excluding other projects
- Users can still find cross-project content if it's highly relevant

## Implementation Steps

### Phase 1: Database Migration

1. **Create migration script**: `scripts/migrate_add_project_fields.py`
   ```python
   """Add project_path and priority_level fields to documents table."""

   async def migrate():
       # Add columns
       # Create indexes
       # Verify migration
   ```

2. **Test migration**:
   - Run on development database
   - Verify existing data is preserved
   - Check indexes are created

3. **Document rollback procedure** in case of issues

### Phase 2: Project Detection

1. **Implement** `aurora_mcp/utils/project_detector.py`
2. **Write unit tests**: `tests/test_project_detector.py`
   - Test various project types
   - Test edge cases
   - Test performance (should be fast)

3. **Manual testing**:
   ```python
   from aurora_mcp.utils.project_detector import find_project_root

   # Test with AuroraKB itself
   assert find_project_root("/Users/user/projects/AuroraKB/aurora_mcp/server.py") == "/Users/user/projects/AuroraKB"

   # Test with non-project file
   assert find_project_root("/tmp/random.txt") is None
   ```

### Phase 3: Enhanced Ingest

1. **Update** `aurora_mcp/server.py` - `aurora_ingest` function
2. **Update docstring** to document auto-detection behavior
3. **Test with file_path metadata**:
   ```python
   # Should auto-detect project
   aurora_ingest(
       content="Test content",
       document_type="document",
       source="test",
       metadata={"file_path": "/Users/user/projects/AuroraKB/README.md"}
   )
   ```

4. **Test without file_path metadata**:
   ```python
   # Should work normally, project_path=None
   aurora_ingest(
       content="Test content",
       document_type="conversation",
       source="test"
   )
   ```

### Phase 4: Enhanced Search

1. **Update** `aurora_mcp/server.py` - `aurora_search` function
2. **Update docstring** to document boost behavior
3. **Test same-project boost**:
   ```python
   # Store documents from two projects
   aurora_ingest(content="AuroraKB feature", ..., metadata={"file_path": "/path/to/AuroraKB/file.py"})
   aurora_ingest(content="OtherProject feature", ..., metadata={"file_path": "/path/to/OtherProject/file.py"})

   # Search from AuroraKB context
   results = aurora_search(
       query="feature",
       current_project_path="/path/to/AuroraKB"
   )

   # Verify AuroraKB document ranks higher
   assert results["documents"][0]["project_path"] == "/path/to/AuroraKB"
   ```

4. **Test cross-project search still works**:
   ```python
   # Without current_project_path, should work normally
   results = aurora_search(query="feature")
   ```

### Phase 5: Integration Testing

1. **Test in Gemini Codex**:
   - Store conversation with file context
   - Search from same project
   - Verify boost works

2. **Test in Claude Code**:
   - Store code snippets with file paths
   - Search from same project
   - Verify same-project results rank higher

3. **Test cross-project scenarios**:
   - Work on Project A
   - Search should still find relevant content from Project B if highly relevant
   - But Project A content should rank higher

### Phase 6: Documentation

1. **Update README.md**:
   - Document auto-detection feature
   - Explain project boost behavior
   - Provide examples

2. **Update tool docstrings**:
   - Already done in implementation above
   - Ensure clarity for AI agents

3. **Create user guide**: `docs/PROJECT_AWARE_SEARCH.md`
   - Explain the feature
   - Show examples
   - Troubleshooting tips

## Testing Checklist

### Unit Tests

- [ ] `test_project_detector.py`
  - [ ] Test with .git marker
  - [ ] Test with pyproject.toml marker
  - [ ] Test with package.json marker
  - [ ] Test with nested projects
  - [ ] Test with no project markers
  - [ ] Test with symlinks
  - [ ] Test with invalid paths

### Integration Tests

- [ ] `test_enhanced_ingest.py`
  - [ ] Auto-detect project from file_path
  - [ ] Handle missing file_path gracefully
  - [ ] Store project_path correctly
  - [ ] Return project_path in response

- [ ] `test_enhanced_search.py`
  - [ ] Boost same-project results
  - [ ] Cross-project search still works
  - [ ] Boost amount is correct (+0.15)
  - [ ] Results capped at 1.0
  - [ ] is_same_project flag is correct

### Manual Tests

- [ ] Test in Gemini Codex
- [ ] Test in Claude Code
- [ ] Test with multiple projects
- [ ] Test with no project context
- [ ] Performance test (should not slow down significantly)

## Performance Considerations

### Database Indexes

- `project_path` column is indexed for fast filtering
- `priority_level` column is indexed for future use
- Existing indexes on `namespace`, `document_type`, `source` remain

### Query Performance

- CASE statement in similarity expression adds minimal overhead
- String comparison for project_path is fast (indexed)
- Overall query performance should remain similar

### Optimization Opportunities

If performance becomes an issue:
1. Consider materialized views for frequently accessed projects
2. Add caching layer for project detection results
3. Use database-level functions for boost calculation

## Rollback Plan

If issues arise after deployment:

1. **Database rollback**:
   ```sql
   ALTER TABLE documents DROP COLUMN project_path;
   ALTER TABLE documents DROP COLUMN priority_level;
   ```

2. **Code rollback**:
   - Revert to previous commit
   - Remove project_detector.py
   - Restore original aurora_ingest and aurora_search

3. **Data preservation**:
   - Existing data is not affected
   - New fields are nullable, so old code can still read documents

## Success Metrics

After implementation, verify:

1. **Functionality**:
   - [ ] Project auto-detection works in 95%+ of cases
   - [ ] Same-project results consistently rank higher
   - [ ] Cross-project search still functional

2. **Performance**:
   - [ ] Ingest latency increase < 10ms
   - [ ] Search latency increase < 20ms
   - [ ] Database size increase < 5%

3. **User Experience**:
   - [ ] AI agents automatically benefit from project context
   - [ ] No manual namespace filtering needed
   - [ ] Search results are more relevant

## Future Enhancements

After core implementation is stable:

1. **Priority Levels**:
   - Use `priority_level` field for manual ranking
   - Allow users to mark important documents
   - Boost high-priority documents in search

2. **Project Relationships**:
   - Track dependencies between projects
   - Boost results from related projects
   - Build project knowledge graph

3. **Adaptive Boost**:
   - Learn optimal boost values from user behavior
   - Adjust boost based on project size
   - Personalize boost per user/agent

4. **Project Analytics**:
   - Show project-level statistics
   - Visualize cross-project knowledge flow
   - Identify knowledge gaps

## Questions & Clarifications

Before starting implementation, clarify:

1. **Boost Amount**: Is +0.15 the right boost? Should it be configurable?
2. **Project Detection**: Should we support custom project markers?
3. **Migration**: Should we backfill project_path for existing documents?
4. **Performance**: What's the acceptable latency increase?

## Contact & Support

- **Implementation Lead**: Codex (Gemini)
- **Code Review**: Claude Code
- **Project Owner**: User (shenshunan)

For questions during implementation, refer to:
- `docs/CORE_VALUE_DESIGN.md` - Original design document
- `README.md` - Project overview
- `aurora_mcp/server.py` - Current implementation

---

**Document Version**: 1.0
**Last Updated**: 2025-12-18
**Status**: Ready for Implementation
