-- Hybrid RAG Database Schema

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ── Documents table ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS documents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT NOT NULL,
    original_name   TEXT NOT NULL,
    file_path       TEXT NOT NULL,
    file_size       BIGINT,
    mime_type       TEXT,
    department      TEXT NOT NULL DEFAULT 'general',
    owner           TEXT NOT NULL DEFAULT 'system',
    tags            TEXT[] DEFAULT '{}',
    confidentiality TEXT NOT NULL DEFAULT 'internal'
                        CHECK (confidentiality IN ('public','internal','restricted','confidential')),
    version         INTEGER NOT NULL DEFAULT 1,
    content_hash    TEXT,
    status          TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','processing','indexed','failed','deleted')),
    error_message   TEXT,
    chunk_count     INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    indexed_at      TIMESTAMPTZ
);

-- ── Chunks metadata table ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chunks (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,
    content         TEXT NOT NULL,
    page_number     INTEGER,
    section_heading TEXT,
    chunk_type      TEXT DEFAULT 'text',
    token_count     INTEGER,
    qdrant_id       TEXT,
    es_id           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Query logs table ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS query_logs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    query           TEXT NOT NULL,
    rewritten_query TEXT,
    answer          TEXT,
    sources         JSONB DEFAULT '[]',
    latency_ms      INTEGER,
    chunk_count     INTEGER,
    model_used      TEXT,
    status          TEXT DEFAULT 'success',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Indexes ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_documents_department  ON documents(department);
CREATE INDEX IF NOT EXISTS idx_documents_status      ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_created_at  ON documents(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_hash        ON documents(content_hash);
CREATE INDEX IF NOT EXISTS idx_chunks_document_id    ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_query_logs_created_at ON query_logs(created_at DESC);

-- ── Auto-update updated_at ────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
