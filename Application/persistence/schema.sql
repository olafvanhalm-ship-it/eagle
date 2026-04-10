-- ============================================================
-- Eagle Report Viewer — Database Schema
-- Supports both PostgreSQL (production) and SQLite (dev/test)
-- Aligned with eagle_software_architecture v1.5 §6
-- ============================================================

-- Review sessions (one per upload)
CREATE TABLE IF NOT EXISTS review_sessions (
    session_id          TEXT PRIMARY KEY,
    filename            TEXT NOT NULL,
    uploaded_at         TEXT NOT NULL,

    -- Manager info
    aifm_name           TEXT,
    filing_type         TEXT,
    template_type       TEXT,
    reporting_period    TEXT,
    reporting_member_state TEXT,
    num_aifs            INTEGER,

    -- Source canonical (full SourceCanonical serialized)
    source_canonical    TEXT NOT NULL DEFAULT '{}',

    -- Status tracking
    status              TEXT NOT NULL DEFAULT 'DRAFT',

    -- Product context (P15 platform-first)
    product_id          TEXT NOT NULL DEFAULT 'AIFMD_ANNEX_IV',

    updated_at          TEXT NOT NULL
);

-- Report canonical per report type (AIFM + N AIFs)
CREATE TABLE IF NOT EXISTS review_reports (
    report_id           TEXT PRIMARY KEY,
    session_id          TEXT NOT NULL REFERENCES review_sessions(session_id),
    report_type         TEXT NOT NULL,
    entity_name         TEXT,
    entity_index        INTEGER,
    nca_codes           TEXT,
    nca_national_codes  TEXT DEFAULT '{}',

    -- Report canonical data (JSON)
    fields_json         TEXT NOT NULL DEFAULT '{}',
    groups_json         TEXT NOT NULL DEFAULT '{}',
    history_json        TEXT DEFAULT '{}',

    -- Cached metrics
    completeness        REAL,
    field_count         INTEGER,
    filled_count        INTEGER,

    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_review_reports_session ON review_reports(session_id);

-- Edit log for diff panel and audit trail
CREATE TABLE IF NOT EXISTS review_edits (
    edit_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          TEXT NOT NULL REFERENCES review_sessions(session_id),
    report_id           TEXT,

    edit_type           TEXT NOT NULL,
    target              TEXT NOT NULL,
    old_value           TEXT,
    new_value           TEXT,
    cascaded_fields     TEXT,

    edited_at           TEXT NOT NULL
);

-- Validation run results
CREATE TABLE IF NOT EXISTS review_validation_runs (
    run_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          TEXT NOT NULL REFERENCES review_sessions(session_id),
    report_id           TEXT,

    xsd_valid           INTEGER,
    dqf_pass            INTEGER,
    dqf_fail            INTEGER,
    findings_json       TEXT,
    has_critical         INTEGER DEFAULT 0,

    run_at              TEXT NOT NULL
);
