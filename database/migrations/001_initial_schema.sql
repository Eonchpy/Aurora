-- Create pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Documents table
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT NOT NULL,
    embedding_vector vector(1536) NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    namespace VARCHAR(100) DEFAULT 'default',
    document_type VARCHAR(50) NOT NULL,
    source VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Vector index
CREATE INDEX IF NOT EXISTS documents_embedding_idx
ON documents USING ivfflat (embedding_vector vector_cosine_ops)
WITH (lists = 100);

-- Metadata and helper indexes
CREATE INDEX IF NOT EXISTS documents_metadata_idx ON documents USING gin(metadata);
CREATE INDEX IF NOT EXISTS documents_type_idx ON documents(document_type);
CREATE INDEX IF NOT EXISTS documents_source_idx ON documents(source);
CREATE INDEX IF NOT EXISTS documents_namespace_idx ON documents(namespace);
CREATE INDEX IF NOT EXISTS documents_created_at_idx ON documents(created_at);
CREATE INDEX IF NOT EXISTS documents_namespace_type_idx ON documents(namespace, document_type);
