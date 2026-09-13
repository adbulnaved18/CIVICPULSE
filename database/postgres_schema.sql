-- ============================================================
-- CivicPulse — PostgreSQL Schema
-- ============================================================
-- Idempotent: safe to run on an existing database (IF NOT EXISTS,
-- DO $$ conditional blocks).
-- Requires: PostgreSQL 14+
-- Optional extensions: postgis, pgvector (vector)
--   Both are attempted by initialize_database(); this file does NOT
--   call CREATE EXTENSION so it can be applied even when an extension
--   is unavailable.
-- ============================================================

-- ============================================================
-- USERS
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'citizen',
    created_at    TIMESTAMPTZ DEFAULT NOW()
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
    created_by            INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at            TIMESTAMPTZ DEFAULT NOW(),
    updated_at            TIMESTAMPTZ DEFAULT NOW(),
    -- AI audit columns
    user_selected_category TEXT,
    category_source        TEXT DEFAULT 'manual',
    ai_confidence          DOUBLE PRECISION,
    ai_analysis_id         TEXT,
    ai_needs_review        INTEGER DEFAULT 0,
    -- Embedding columns (populated when pgvector is available)
    embedding_model        TEXT,
    embedding_created_at   TIMESTAMPTZ,
    embedding_version      TEXT,
    -- JSON fallback for embeddings when pgvector is unavailable
    embedding_json         TEXT
);

-- ============================================================
-- pgvector: add vector(768) column if the extension is available
-- ============================================================

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        -- Add embedding column if it doesn't exist
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'complaints' AND column_name = 'embedding'
        ) THEN
            EXECUTE 'ALTER TABLE complaints ADD COLUMN embedding vector(768)';
        END IF;

        -- HNSW index (add after backfill; may already exist)
        BEGIN
            EXECUTE $idx$
                CREATE INDEX IF NOT EXISTS idx_complaints_embedding_hnsw
                ON complaints USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64)
            $idx$;
        EXCEPTION WHEN OTHERS THEN
            RAISE WARNING 'Could not create HNSW index: %', SQLERRM;
        END;
    END IF;
END
$$;

-- ============================================================
-- PostGIS: add geography column + trigger if extension is available
-- ============================================================

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'postgis') THEN
        -- Add location_point column if it doesn't exist
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'complaints' AND column_name = 'location_point'
        ) THEN
            EXECUTE 'ALTER TABLE complaints ADD COLUMN location_point GEOGRAPHY(POINT, 4326)';
        END IF;

        -- Spatial index
        BEGIN
            EXECUTE $idx$
                CREATE INDEX IF NOT EXISTS idx_complaints_location_point
                ON complaints USING GIST (location_point)
            $idx$;
        EXCEPTION WHEN OTHERS THEN
            RAISE WARNING 'Could not create GIST index: %', SQLERRM;
        END;
    END IF;
END
$$;

-- ============================================================
-- Standard indexes on complaints
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_complaints_status     ON complaints (status);
CREATE INDEX IF NOT EXISTS idx_complaints_category   ON complaints (category);
CREATE INDEX IF NOT EXISTS idx_complaints_created_by ON complaints (created_by);
CREATE INDEX IF NOT EXISTS idx_complaints_created_at ON complaints (created_at DESC);

-- ============================================================
-- Auto-update updated_at trigger
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
-- Auto-populate location_point (only when PostGIS is present)
-- ============================================================

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'postgis') THEN
        -- Sync trigger function
        BEGIN
            EXECUTE $func$
                CREATE OR REPLACE FUNCTION sync_location_point()
                RETURNS TRIGGER AS $t$
                BEGIN
                    IF NEW.latitude IS NOT NULL AND NEW.longitude IS NOT NULL THEN
                        NEW.location_point = ST_SetSRID(
                            ST_MakePoint(NEW.longitude, NEW.latitude), 4326
                        )::geography;
                    END IF;
                    RETURN NEW;
                END;
                $t$ LANGUAGE plpgsql
            $func$;
        EXCEPTION WHEN OTHERS THEN
            RAISE WARNING 'Could not create sync_location_point(): %', SQLERRM;
        END;

        -- Sync trigger on complaints
        BEGIN
            EXECUTE $trig$
                DROP TRIGGER IF EXISTS trg_complaints_location_point ON complaints;
                CREATE TRIGGER trg_complaints_location_point
                    BEFORE INSERT OR UPDATE OF latitude, longitude ON complaints
                    FOR EACH ROW EXECUTE FUNCTION sync_location_point()
            $trig$;
        EXCEPTION WHEN OTHERS THEN
            RAISE WARNING 'Could not create location_point trigger: %', SQLERRM;
        END;
    END IF;
END
$$;

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

CREATE INDEX IF NOT EXISTS idx_complaint_votes_complaint
    ON complaint_votes (complaint_id);

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

CREATE INDEX IF NOT EXISTS idx_complaint_evidence_complaint
    ON complaint_evidence (complaint_id);

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

CREATE INDEX IF NOT EXISTS idx_ai_analyses_user_id    ON report_ai_analyses (user_id);
CREATE INDEX IF NOT EXISTS idx_ai_analyses_expires_at ON report_ai_analyses (expires_at);

-- ============================================================
-- ROW-LEVEL SECURITY
-- Enable RLS on all application tables to prevent direct
-- PostgREST/anon Data API access to sensitive data.
-- The backend service-role (postgres) bypasses RLS and retains
-- full administrative access.
-- ============================================================

ALTER TABLE users                      ENABLE ROW LEVEL SECURITY;
ALTER TABLE complaints                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE complaint_votes            ENABLE ROW LEVEL SECURITY;
ALTER TABLE complaint_evidence         ENABLE ROW LEVEL SECURITY;
ALTER TABLE participatory_priorities   ENABLE ROW LEVEL SECURITY;
ALTER TABLE participatory_priority_votes ENABLE ROW LEVEL SECURITY;
ALTER TABLE report_ai_analyses         ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- REVOKE DIRECT API ACCESS
-- Revoke all privileges from Supabase anon and authenticated
-- roles on public schema tables and sequences.  Wrapped in a
-- DO $$ block so the script is safe even if those roles don't
-- exist (e.g. a plain PostgreSQL install without Supabase).
-- ============================================================

DO $$
DECLARE
    _tbl TEXT;
    _seq TEXT;
    _civicpulse_tables TEXT[] := ARRAY[
        'users', 'complaints', 'complaint_votes', 'complaint_evidence',
        'participatory_priorities', 'participatory_priority_votes',
        'report_ai_analyses'
    ];
BEGIN
    -- Revoke table and sequence privileges only on CivicPulse objects
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        FOREACH _tbl IN ARRAY _civicpulse_tables LOOP
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = _tbl) THEN
                EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon', _tbl);
            END IF;
            -- Revoke on the associated sequence (id column)
            _seq := _tbl || '_id_seq';
            IF EXISTS (SELECT 1 FROM information_schema.sequences WHERE sequence_schema = 'public' AND sequence_name = _seq) THEN
                EXECUTE format('REVOKE ALL ON SEQUENCE public.%I FROM anon', _seq);
            END IF;
        END LOOP;
    END IF;

    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        FOREACH _tbl IN ARRAY _civicpulse_tables LOOP
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = _tbl) THEN
                EXECUTE format('REVOKE ALL ON TABLE public.%I FROM authenticated', _tbl);
            END IF;
            _seq := _tbl || '_id_seq';
            IF EXISTS (SELECT 1 FROM information_schema.sequences WHERE sequence_schema = 'public' AND sequence_name = _seq) THEN
                EXECUTE format('REVOKE ALL ON SEQUENCE public.%I FROM authenticated', _seq);
            END IF;
        END LOOP;
    END IF;
END
$$;
