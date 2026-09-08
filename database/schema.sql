-- ============================================================
-- CIVICPULSE DATABASE SCHEMA
-- ============================================================

PRAGMA foreign_keys = ON;


-- ============================================================
-- USERS
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    name TEXT NOT NULL,

    email TEXT NOT NULL UNIQUE,

    password_hash TEXT NOT NULL,

    role TEXT NOT NULL DEFAULT 'citizen'
        CHECK (role IN ('citizen', 'admin')),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ============================================================
-- COMPLAINTS
-- ============================================================

CREATE TABLE IF NOT EXISTS complaints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    description TEXT NOT NULL,

    category TEXT NOT NULL,

    state TEXT NOT NULL DEFAULT 'Other',

    location TEXT NOT NULL,

    language TEXT NOT NULL DEFAULT 'en',

    status TEXT NOT NULL DEFAULT 'Pending'
        CHECK (
            status IN (
                'Pending',
                'In Progress',
                'Resolved'
            )
        ),

    priority INTEGER NOT NULL DEFAULT 0,

    latitude REAL,

    longitude REAL,

    location_accuracy REAL,

    location_captured_at TEXT,

    created_by INTEGER,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (created_by)
        REFERENCES users(id)
        ON DELETE SET NULL
);


-- ============================================================
-- COMPLAINT VOTES / COMMUNITY SUPPORT
-- ============================================================

CREATE TABLE IF NOT EXISTS complaint_votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    complaint_id INTEGER NOT NULL,

    voter_id TEXT NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (
        complaint_id,
        voter_id
    ),

    FOREIGN KEY (complaint_id)
        REFERENCES complaints(id)
        ON DELETE CASCADE
);


-- ============================================================
-- COMPLAINT EVIDENCE
-- ============================================================

CREATE TABLE IF NOT EXISTS complaint_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    complaint_id INTEGER NOT NULL,

    file_path TEXT NOT NULL,

    file_type TEXT,

    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (complaint_id)
        REFERENCES complaints(id)
        ON DELETE CASCADE
);


-- ============================================================
-- PARTICIPATORY BUDGETING SUBMISSIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS participatory_priorities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    user_id INTEGER NOT NULL,

    issue_id INTEGER NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (
        user_id,
        issue_id
    ),

    FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE,

    FOREIGN KEY (issue_id)
        REFERENCES complaints(id)
        ON DELETE CASCADE
);


-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_complaints_status
    ON complaints(status);


CREATE INDEX IF NOT EXISTS idx_complaints_category
    ON complaints(category);


CREATE INDEX IF NOT EXISTS idx_complaints_location
    ON complaints(location);


CREATE INDEX IF NOT EXISTS idx_complaints_created_by
    ON complaints(created_by);


CREATE INDEX IF NOT EXISTS idx_complaints_created_at
    ON complaints(created_at);


CREATE INDEX IF NOT EXISTS idx_complaint_votes_complaint
    ON complaint_votes(complaint_id);


CREATE INDEX IF NOT EXISTS idx_complaint_votes_voter
    ON complaint_votes(voter_id);


CREATE INDEX IF NOT EXISTS idx_evidence_complaint
    ON complaint_evidence(complaint_id);


CREATE INDEX IF NOT EXISTS idx_pb_user
    ON participatory_priorities(user_id);


CREATE INDEX IF NOT EXISTS idx_pb_issue
    ON participatory_priorities(issue_id);


-- ============================================================
-- TRIGGER: UPDATE COMPLAINT TIMESTAMP
-- ============================================================

CREATE TRIGGER IF NOT EXISTS update_complaint_timestamp
AFTER UPDATE ON complaints
FOR EACH ROW
BEGIN
    UPDATE complaints
    SET updated_at = CURRENT_TIMESTAMP
    WHERE id = OLD.id;
END;


-- ============================================================
-- AI ANALYSIS AUDIT TABLE
-- ============================================================
-- Stores AI classification results for audit and hash
-- verification. Raw audio and image bytes are NOT stored here.
-- The record expires after 1 hour to avoid long-term retention.

CREATE TABLE IF NOT EXISTS report_ai_analyses (
    id TEXT PRIMARY KEY,

    user_id INTEGER NOT NULL,

    text_sha256 TEXT NOT NULL,

    image_sha256 TEXT,

    suggested_category TEXT NOT NULL,

    confidence REAL NOT NULL,

    needs_review INTEGER NOT NULL DEFAULT 0,

    detected_language TEXT,

    short_reason TEXT,

    text_image_consistent INTEGER,

    provider TEXT NOT NULL,

    model TEXT NOT NULL,

    prompt_version TEXT NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    expires_at TIMESTAMP,

    FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);


CREATE INDEX IF NOT EXISTS idx_ai_analyses_user
    ON report_ai_analyses(user_id);


CREATE INDEX IF NOT EXISTS idx_ai_analyses_expires
    ON report_ai_analyses(expires_at);