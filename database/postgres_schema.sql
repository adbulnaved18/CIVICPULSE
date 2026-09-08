-- ============================================================
-- CivicPulse — PostgreSQL Schema
-- ============================================================
-- Run this AFTER schema.sql data has been migrated.
-- Requires: PostgreSQL 14+, PostGIS, pgvector extensions.
-- ============================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- USERS
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role        TEXT NOT NULL DEFAULT 'citizen',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- COMPLAINTS
-- ============================================================

CREATE TABLE IF NOT EXISTS complaints (
    id                    SERIAL PRIMARY KEY,
    description           TEXT NOT NULL,
    category              TEXT NOT NULL,
    state                 TEXT DEFAULT 'Other',
    location              TEXT NOT NULL,
    language              TEXT DEFAULT 'en',
    status                TEXT DEFAULT 'Pending',
    priority              INTEGER DEFAULT 0,
    latitude              DOUBLE PRECISION,
    longitude             DOUBLE PRECISION,
    location_accuracy     DOUBLE PRECISION,
    location_captured_at  TEXT,
    -- PostGIS geographic point (auto-populated by trigger below)
    location_point        GEOGRAPHY(POINT, 4326),
    created_by            INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at            TIMESTAMPTZ DEFAULT NOW(),
    updated_at            TIMESTAMPTZ DEFAULT NOW(),
    -- AI audit columns
    user_selected_category TEXT,
    category_source        TEXT DEFAULT 'manual',
    ai_confidence          DOUBLE PRECISION,
    ai_analysis_id         TEXT,
    ai_needs_review        INTEGER DEFAULT 0,
    -- Embedding columns (pgvector)
    embedding              vector(768),
    embedding_model        TEXT,
    embedding_created_at   TIMESTAMPTZ,
    embedding_version      TEXT
);

-- Spatial index for geo-duplicate search
CREATE INDEX IF NOT EXISTS idx_complaints_location_point
    ON complaints USING GIST (location_point);

-- Vector index (HNSW) for semantic search — add after backfill
CREATE INDEX IF NOT EXISTS idx_complaints_embedding_hnsw
    ON complaints USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Standard indexes
CREATE INDEX IF NOT EXISTS idx_complaints_status    ON complaints (status);
CREATE INDEX IF NOT EXISTS idx_complaints_category  ON complaints (category);
CREATE INDEX IF NOT EXISTS idx_complaints_created_by ON complaints (created_by);
CREATE INDEX IF NOT EXISTS idx_complaints_created_at ON complaints (created_at DESC);

-- ============================================================
-- Auto-update updated_at
-- ============================================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_complaints_updated_at ON complaints;
CREATE TRIGGER trg_complaints_updated_at
    BEFORE UPDATE ON complaints
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- Auto-populate location_point from lat/lon
-- ============================================================

CREATE OR REPLACE FUNCTION sync_location_point()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.latitude IS NOT NULL AND NEW.longitude IS NOT NULL THEN
        NEW.location_point = ST_SetSRID(
            ST_MakePoint(NEW.longitude, NEW.latitude),
            4326
        )::geography;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_complaints_location_point ON complaints;
CREATE TRIGGER trg_complaints_location_point
    BEFORE INSERT OR UPDATE OF latitude, longitude ON complaints
    FOR EACH ROW EXECUTE FUNCTION sync_location_point();

-- ============================================================
-- COMPLAINT VOTES
-- ============================================================

CREATE TABLE IF NOT EXISTS complaint_votes (
    id           SERIAL PRIMARY KEY,
    complaint_id INTEGER NOT NULL REFERENCES complaints(id) ON DELETE CASCADE,
    voter_id     TEXT NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (complaint_id, voter_id)
);

-- ============================================================
-- COMPLAINT EVIDENCE
-- ============================================================

CREATE TABLE IF NOT EXISTS complaint_evidence (
    id           SERIAL PRIMARY KEY,
    complaint_id INTEGER NOT NULL REFERENCES complaints(id) ON DELETE CASCADE,
    file_path    TEXT NOT NULL,
    file_type    TEXT,
    uploaded_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- PARTICIPATORY PRIORITIES
-- ============================================================

CREATE TABLE IF NOT EXISTS participatory_priorities (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    issue_id   INTEGER NOT NULL REFERENCES complaints(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, issue_id)
);

CREATE TABLE IF NOT EXISTS participatory_priority_votes (
    id           SERIAL PRIMARY KEY,
    complaint_id INTEGER NOT NULL REFERENCES complaints(id) ON DELETE CASCADE,
    citizen_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (complaint_id, citizen_id)
);

-- ============================================================
-- AI ANALYSES
-- ============================================================

CREATE TABLE IF NOT EXISTS report_ai_analyses (
    id                    TEXT PRIMARY KEY,
    user_id               INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    text_sha256           TEXT NOT NULL,
    image_sha256          TEXT,
    suggested_category    TEXT NOT NULL,
    confidence            DOUBLE PRECISION NOT NULL,
    needs_review          INTEGER NOT NULL DEFAULT 0,
    detected_language     TEXT,
    short_reason          TEXT,
    text_image_consistent INTEGER,
    provider              TEXT NOT NULL,
    model                 TEXT NOT NULL,
    prompt_version        TEXT NOT NULL,
    created_at            TIMESTAMPTZ DEFAULT NOW(),
    expires_at            TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_ai_analyses_user_id   ON report_ai_analyses (user_id);
CREATE INDEX IF NOT EXISTS idx_ai_analyses_expires_at ON report_ai_analyses (expires_at);
