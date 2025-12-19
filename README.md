# AuroraKB

AuroraKB is a semantic search-based knowledge base system that provides persistent context storage for AI assistants through the MCP (Model Context Protocol).

## Features

- **Hybrid Search**: Combines semantic (70%) + keyword (30%) search for superior accuracy
  - Semantic understanding via vector embeddings
  - Position-aware keyword matching with PostgreSQL ts_rank_cd
  - Automatic query optimization for short queries like "Phase 2 plan"
- **Project-Aware Context**: Automatically detects and prioritizes same-project content
- **Smart Search Boost**: Same-project results get +0.15 similarity boost for better relevance
- **Flexible Namespaces**: Isolate data by project or domain
- **Metadata Filtering**: Filter by document type, author, tags, and more
- **Pure MCP Architecture**: Direct database connection without HTTP middleware - simple and efficient
- **Multi-Agent Friendly**: Each AI agent runs independently with no port conflicts
- **Plug and Play**: Just configure the MCP config file and you're ready to go

## Requirements

- Python 3.12+
- PostgreSQL 17+ with pgvector extension
- OpenAI API key (for generating embeddings)

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/AuroraKB
cd AuroraKB
```

### 2. Install Dependencies

Using `uv` for dependency management (recommended):

```bash
uv sync
```

Or using pip:

```bash
pip install -r requirements.txt
```

### 3. Setup PostgreSQL Database

Quick start with Docker (recommended):

```bash
docker run -d \
  --name aurora_kb_postgres \
  -e POSTGRES_DB=aurora_kb \
  -e POSTGRES_USER=aurora_user \
  -e POSTGRES_PASSWORD=aurora_pass \
  -p 5432:5432 \
  pgvector/pgvector:pg17
```

Run database migrations:

```bash
uv run python scripts/setup_db.py
```

### 4. Configure Claude Code MCP

Add the following configuration to your Claude Code MCP config file:

**Config file location**: `~/.config/claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "aurora_kb": {
      "command": "uv",
      "args": ["run", "python", "-m", "aurora_mcp.server"],
      "cwd": "/absolute/path/to/AuroraKB",
      "env": {
        "DATABASE_URL": "postgresql+asyncpg://aurora_user:aurora_pass@localhost:5432/aurora_kb",
        "OPENAI_API_KEY": "sk-your-openai-api-key-here",
        "OPENAI_BASE_URL": "https://api.openai.com/v1",
        "EMBEDDING_MODEL": "text-embedding-3-small",
        "EMBEDDING_DIMENSION": "1536"
      }
    }
  }
}
```

**Important Notes**:
- Replace `/absolute/path/to/AuroraKB` with the actual absolute path to the project
- Replace `sk-your-openai-api-key-here` with your OpenAI API key
- To use other embedding services, modify `OPENAI_BASE_URL` to the corresponding API endpoint

### 5. Start Claude Code

Restart Claude Code or reload the MCP configuration, and AuroraKB will start automatically!

## Usage

### Store Content (Ingest)

Use MCP tools through Claude Code chat:

```
Please store this content in AuroraKB:
"Today we discussed the project architecture and decided to use FastAPI + PostgreSQL + pgvector"

Parameters:
- namespace: my_project
- document_type: conversation
- source: claude_chat
```

### Semantic Search

```
Search AuroraKB for discussions about "project architecture"
```

### Retrieve Document

```
Retrieve document with document_id "doc_123" from AuroraKB
```

### Handling Long Documents

AuroraKB has a content length limit per storage operation (~8000 tokens / ~32,000 characters). For longer documents, use one of these strategies:

**Strategy 1: Chunked Storage (Recommended for Technical Documents)**

```
Please split this long document into chunks and store in AuroraKB:

[Long document content...]

Requirements:
1. Each chunk should not exceed 6000 tokens
2. Maintain 200 character overlap between chunks for context continuity
3. Use metadata to link all chunks:
   - parent_id: Generate a unique ID
   - chunk_index: Chunk sequence number (0, 1, 2...)
   - total_chunks: Total number of chunks
4. namespace: my_project
5. document_type: document
```

**Strategy 2: Summary Storage (Recommended for Conversation Records)**

```
Please summarize the key content of this long conversation and store in AuroraKB:

[Long conversation content...]

Requirements:
1. Extract key decisions, discussion points, and conclusions
2. Preserve original semantics and important details
3. Storage parameters:
   - namespace: my_project
   - document_type: conversation
   - metadata: {"summary": true, "original_length": "original character count"}
```

**Strategy 3: Selective Storage (Recommended for Mixed Content)**

```
Please extract the most relevant parts from this long document and store in AuroraKB:

[Long document content...]

Focus on: [Describe the topics you care about]

Requirements:
- Only store paragraphs relevant to the topic
- namespace: my_project
- document_type: document
```

## MCP Tools Reference

### aurora_ingest

Store content into AuroraKB with automatic semantic vector generation and project detection.

**Parameters**:
- `content` (required): Text content to store
  - Maximum length: ~8000 tokens (~32,000 characters)
  - Returns error and suggestions when limit exceeded
- `namespace` (required): Namespace for project isolation
- `document_type` (required): Document type (e.g., conversation, document, decision, resolution)
- `source` (required): Source identifier (e.g., claude_code, cursor, manual)
- `metadata` (optional): Additional metadata object
  - `file_path`: File path for automatic project detection (recommended)
  - `author`: Author name
  - `tags`: Tag array
  - `url`: Associated URL
  - `parent_id`: For linking chunked documents
  - `chunk_index`: Chunk sequence number (for chunked storage)
  - `total_chunks`: Total number of chunks (for chunked storage)

**Project Detection**:
When `metadata.file_path` is provided, AuroraKB automatically detects the project root by looking for markers like `.git`, `package.json`, `pyproject.toml`, etc. The detected `project_path` is stored with the document and returned in the response.

### aurora_search

Search content based on semantic similarity with optional project-aware boosting.

**Parameters**:
- `query` (required): Search query text
- `namespace` (optional): Limit to specific namespace
- `document_type` (optional): Filter by document type
- `limit` (optional): Number of results to return, default 10
- `threshold` (optional): Similarity threshold (0.0-1.0), default 0.2
- `metadata_filters` (optional): Metadata filters
  - `author`: Filter by author
  - `tags`: Filter by tags
  - `source`: Filter by source
- `current_project_path` (optional): Current project path for boosting same-project results

**Project-Aware Search**:
When `current_project_path` is provided, documents from the same project receive a +0.15 similarity boost (capped at 1.0), making them rank higher in search results. This helps prioritize relevant context from your current project while still allowing cross-project search when needed.

**Response Fields**:
- `documents`: Array of matching documents
  - `project_path`: Detected project path (if available)
  - `is_same_project`: Boolean flag indicating if document is from current project
  - `similarity_score`: Similarity score (boosted if same project)
- `current_project`: Echo of the current_project_path parameter
- `total_found`: Number of results returned

### aurora_retrieve

Retrieve a specific document by document_id.

**Parameters**:
- `document_id` (required): Document ID
- `include_embedding` (optional): Whether to include vector data, default false

## Advanced Configuration

### Using Custom Embedding Services

AuroraKB supports any OpenAI API-compatible embedding service:

```json
{
  "env": {
    "OPENAI_BASE_URL": "https://your-custom-endpoint.com/v1",
    "OPENAI_API_KEY": "your-api-key",
    "EMBEDDING_MODEL": "custom-embedding-model"
  }
}
```

## Development Guide

### Run Unit Tests

```bash
uv run pytest tests/
```

### Run MCP Server (Development Mode)

```bash
uv run python -m aurora_mcp.server
```

## Architecture

```
┌─────────────────────┐
│   Claude Code       │
│   (MCP Client)      │
└──────────┬──────────┘
           │ stdio
           ▼
┌─────────────────────┐
│   MCP Server        │
│ (aurora_mcp.server) │
└──────────┬──────────┘
           │ direct connection
           ▼
┌─────────────────────┐
│  PostgreSQL         │
│  + pgvector         │
└─────────────────────┘
```

**Pure MCP Design**:
- Direct database connection without HTTP middleware
- No manual process management needed
- Simplified configuration for better usability

## Troubleshooting

### Database Connection Failed

Verify PostgreSQL is running:

```bash
docker ps | grep aurora_kb_postgres
```

Test database connection:

```bash
psql postgresql://aurora_user:aurora_pass@localhost:5432/aurora_kb
```

### Embedding Generation Failed

Check if OpenAI API key is valid:

```bash
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

## License

MIT License

## Contributing

Issues and Pull Requests are welcome!
