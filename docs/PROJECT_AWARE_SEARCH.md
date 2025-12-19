# Project-Aware Search Guide

## Overview

AuroraKB's project-aware search feature automatically detects and prioritizes content from your current project, solving the critical problem of context dilution when AI agents work across multiple projects.

## The Problem

When AI agents work on multiple projects or spawn sub-agents:
- **Context Dilution**: Search results mix content from different projects
- **Relevance Loss**: Same-project context should be prioritized but isn't
- **Manual Filtering**: Users must manually specify namespace filters

## The Solution

AuroraKB automatically:
1. **Detects project context** from file paths
2. **Tags documents** with project_path
3. **Boosts search results** from the same project (+0.15 similarity)
4. **Maintains flexibility** - cross-project search still works

---

## How It Works

### 1. Automatic Project Detection

When you store content with a `file_path` in metadata, AuroraKB automatically detects the project root by looking for common markers:

**Supported Project Markers**:
- Version Control: `.git`, `.hg`, `.svn`
- Python: `pyproject.toml`
- Node.js: `package.json`
- Rust: `Cargo.toml`
- Go: `go.mod`
- Java: `pom.xml`, `build.gradle`
- C/C++: `CMakeLists.txt`
- PHP: `composer.json`
- Ruby: `Gemfile`
- IDE: `.project`

**Example**:
```
File path: /Users/user/projects/AuroraKB/aurora_mcp/server.py
Detected project: /Users/user/projects/AuroraKB
```

### 2. Smart Search Boost

When searching with `current_project_path`, same-project documents receive a **+0.15 similarity boost** (capped at 1.0).

**Example**:
```
Without boost:
- AuroraKB doc: similarity 0.65
- OtherProject doc: similarity 0.70
→ OtherProject ranks higher

With boost (+0.15 for AuroraKB):
- AuroraKB doc: 0.65 + 0.15 = 0.80
- OtherProject doc: 0.70
→ AuroraKB ranks higher ✓
```

### 3. Cross-Project Search Still Works

The boost doesn't filter out other projects - it just adjusts ranking. If another project has highly relevant content, it will still appear in results.

---

## Usage Examples

### Example 1: Store Content with Project Context

```python
# AI agent stores code snippet with file path
aurora_ingest(
    content="def find_project_root(file_path: str) -> Optional[str]: ...",
    document_type="document",
    source="claude_code",
    namespace="AuroraKB",
    metadata={
        "file_path": "/Users/user/projects/AuroraKB/aurora_mcp/utils/project_detector.py",
        "language": "python"
    }
)

# Response includes detected project:
{
    "id": "doc_123",
    "project_path": "/Users/user/projects/AuroraKB",  # Auto-detected
    "token_count": 245,
    ...
}
```

### Example 2: Search with Project Boost

```python
# Search from AuroraKB project context
aurora_search(
    query="project detection utility",
    namespace="AuroraKB",
    current_project_path="/Users/user/projects/AuroraKB"
)

# Response shows boosted same-project results:
{
    "documents": [
        {
            "id": "doc_123",
            "content": "def find_project_root...",
            "project_path": "/Users/user/projects/AuroraKB",
            "is_same_project": True,  # ✓ Same project
            "similarity_score": 0.85  # Boosted from 0.70
        },
        {
            "id": "doc_456",
            "content": "Project detection in OtherProject...",
            "project_path": "/Users/user/projects/OtherProject",
            "is_same_project": False,  # Different project
            "similarity_score": 0.72  # No boost
        }
    ],
    "current_project": "/Users/user/projects/AuroraKB",
    "total_found": 2
}
```

### Example 3: Cross-Project Search

```python
# Search without current_project_path - no boost applied
aurora_search(
    query="project detection utility",
    namespace="AuroraKB"
)

# All projects treated equally:
{
    "documents": [
        {
            "id": "doc_456",
            "project_path": "/Users/user/projects/OtherProject",
            "is_same_project": False,  # No current project specified
            "similarity_score": 0.72  # Original score
        },
        {
            "id": "doc_123",
            "project_path": "/Users/user/projects/AuroraKB",
            "is_same_project": False,
            "similarity_score": 0.70  # Original score
        }
    ],
    "current_project": None,
    "total_found": 2
}
```

---

## Best Practices

### 1. Always Provide file_path When Possible

```python
# ✓ Good - enables project detection
aurora_ingest(
    content="Implementation notes",
    document_type="document",
    source="claude_code",
    metadata={"file_path": "/path/to/project/file.py"}
)

# ✗ Less optimal - no project context
aurora_ingest(
    content="Implementation notes",
    document_type="document",
    source="claude_code"
)
```

### 2. Use current_project_path for Project-Specific Searches

```python
# ✓ Good - prioritizes current project
aurora_search(
    query="database migration",
    current_project_path="/Users/user/projects/AuroraKB"
)

# ✓ Also good - cross-project search when needed
aurora_search(
    query="database migration best practices"
    # No current_project_path - search all projects equally
)
```

### 3. Use Absolute Paths

```python
# ✓ Good - absolute path
metadata={"file_path": "/Users/user/projects/AuroraKB/server.py"}

# ✗ Bad - relative path (may not detect correctly)
metadata={"file_path": "./server.py"}
```

### 4. Consistent Path Format

```python
# ✓ Good - use resolved paths
from pathlib import Path
file_path = str(Path("/path/to/file").resolve())

# This ensures consistent project detection
```

---

## How AI Agents Use This Feature

### Gemini Codex Workflow

```
1. Codex generates implementation plan
2. Stores plan with file_path metadata
   → AuroraKB auto-detects project: /Users/user/projects/AuroraKB
3. Claude Code searches for "implementation plan"
   → Passes current_project_path: /Users/user/projects/AuroraKB
4. Same-project plan ranks higher (boosted)
5. Claude Code retrieves correct plan ✓
```

### Claude Code Workflow

```
1. User asks: "What's our database schema?"
2. Claude Code searches AuroraKB
   → Passes current working directory as current_project_path
3. Same-project schema docs rank higher
4. Claude Code provides accurate project-specific answer ✓
```

---

## Troubleshooting

### Project Not Detected

**Symptom**: `project_path` is `None` in response

**Possible Causes**:
1. No `file_path` provided in metadata
2. File path doesn't contain any project markers
3. File is outside any project (e.g., `/tmp/file.txt`)

**Solution**:
- Ensure `file_path` is provided
- Check if project has markers (`.git`, `package.json`, etc.)
- Use absolute paths

### Boost Not Applied

**Symptom**: Same-project results not ranking higher

**Possible Causes**:
1. `current_project_path` not provided in search
2. Path mismatch (different path format)
3. Documents don't have `project_path` set

**Solution**:
- Provide `current_project_path` parameter
- Use consistent path format (absolute, resolved)
- Re-ingest documents with `file_path` metadata

### Wrong Project Detected

**Symptom**: Detected project is not the expected one

**Possible Causes**:
1. Nested projects (monorepo)
2. Multiple project markers in parent directories

**Behavior**:
- AuroraKB picks the **nearest** marker (closest parent directory)
- This is usually correct for nested projects

**Example**:
```
/Users/user/monorepo/
├── .git                    # Monorepo root
├── packages/
│   └── aurora/
│       ├── package.json    # Package root (nearest marker)
│       └── src/
│           └── file.py     # This file

Detected project: /Users/user/monorepo/packages/aurora ✓
```

---

## Technical Details

### Boost Formula

```sql
CASE
    WHEN project_path = current_project_path
    THEN LEAST(1.0, similarity_score + 0.15)
    ELSE similarity_score
END
```

- **+0.15 boost**: Empirically chosen for good balance
- **LEAST(1.0, ...)**: Caps score at 1.0 (prevents overflow)
- **Conditional**: Only applies when paths match exactly

### Performance Impact

- **Project Detection**: < 1ms per ingest (filesystem walk)
- **Search Boost**: < 5ms per search (SQL CASE statement)
- **Index Usage**: `project_path` column is indexed for fast filtering

### Database Schema

```sql
-- New columns added to documents table
ALTER TABLE documents ADD COLUMN project_path VARCHAR(500);
ALTER TABLE documents ADD COLUMN priority_level INTEGER DEFAULT 0;

-- Indexes for performance
CREATE INDEX idx_documents_project_path ON documents(project_path);
CREATE INDEX idx_documents_priority_level ON documents(priority_level);
```

---

## Future Enhancements

### Priority Levels (Planned)

Use `priority_level` field for manual ranking:
```python
# High-priority documents
aurora_ingest(..., metadata={"priority": 10})

# Boost high-priority docs in search
aurora_search(..., boost_priority=True)
```

### Project Relationships (Planned)

Track dependencies between projects:
```python
# Define project relationships
set_project_relationship(
    project="/Users/user/projects/AuroraKB",
    related_projects=["/Users/user/projects/SharedLib"]
)

# Boost related projects in search
aurora_search(..., include_related_projects=True)
```

### Adaptive Boost (Planned)

Learn optimal boost values from user behavior:
- Adjust boost based on project size
- Personalize boost per user/agent
- A/B test different boost values

---

## FAQ

### Q: Does this replace namespaces?

**A**: No, namespaces and project-aware search serve different purposes:
- **Namespaces**: Logical grouping (e.g., "work", "personal")
- **Project-aware**: Automatic context detection and ranking

You can use both together for maximum flexibility.

### Q: What if I don't provide file_path?

**A**: The feature is optional:
- Without `file_path`: `project_path` is `None`, no boost applied
- Everything works as before (backward compatible)

### Q: Can I disable the boost?

**A**: Yes, simply don't provide `current_project_path` in search:
```python
# With boost
aurora_search(query="...", current_project_path="/path/to/project")

# Without boost (standard search)
aurora_search(query="...")
```

### Q: Does this work with all embedding models?

**A**: Yes, project-aware search is independent of the embedding model. It works with any OpenAI-compatible embedding service.

### Q: What about monorepos?

**A**: AuroraKB picks the **nearest** project marker, which usually gives correct results for monorepos. If you have nested projects, the innermost project is detected.

---

## Related Documentation

- [Implementation Handbook](IMPLEMENTATION_HANDBOOK.md) - Technical implementation details
- [Core Value Design](CORE_VALUE_DESIGN.md) - Original design document
- [README.md](../README.md) - Project overview and setup

---

**Document Version**: 1.0
**Last Updated**: 2025-12-19
**Status**: Production Ready
