-- Add full-text search support
ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_tsv tsvector;

-- Backfill existing rows
UPDATE documents SET content_tsv = to_tsvector('english', content) WHERE content_tsv IS NULL;

-- Index for full-text search
CREATE INDEX IF NOT EXISTS idx_documents_content_tsv ON documents USING GIN(content_tsv);

-- Trigger to keep tsvector in sync
CREATE OR REPLACE FUNCTION documents_tsv_trigger() RETURNS trigger AS $$
BEGIN
    NEW.content_tsv := to_tsvector('english', NEW.content);
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS documents_content_tsv_update ON documents;
CREATE TRIGGER documents_content_tsv_update
BEFORE INSERT OR UPDATE ON documents
FOR EACH ROW EXECUTE FUNCTION documents_tsv_trigger();
