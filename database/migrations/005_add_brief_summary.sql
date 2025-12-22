-- Migration 005: Add brief_summary column for token optimization
-- Purpose: Enable two-stage retrieval pattern (summary → full content)
-- Impact: Reduces token consumption by ~90% in search results

-- Add brief_summary column (nullable for gradual migration)
ALTER TABLE documents ADD COLUMN IF NOT EXISTS brief_summary TEXT NULL;

-- Add partial index for documents with summaries
-- This improves query performance when filtering by summary existence
CREATE INDEX IF NOT EXISTS documents_brief_summary_idx
ON documents(brief_summary)
WHERE brief_summary IS NOT NULL;

-- Add comment for documentation
COMMENT ON COLUMN documents.brief_summary IS
'Brief summary (100-200 tokens) generated at ingest time for token-efficient search results. NULL indicates summary not yet generated.';
