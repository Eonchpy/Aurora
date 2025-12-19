-- Add project-aware columns for documents
ALTER TABLE documents ADD COLUMN IF NOT EXISTS project_path VARCHAR(500);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS priority_level INTEGER DEFAULT 0;

-- Ensure existing rows have a default priority value
UPDATE documents SET priority_level = 0 WHERE priority_level IS NULL;

-- Indexes for project context and priority-based lookups
CREATE INDEX IF NOT EXISTS documents_project_path_idx ON documents(project_path);
CREATE INDEX IF NOT EXISTS documents_priority_level_idx ON documents(priority_level);
