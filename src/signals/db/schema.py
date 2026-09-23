"""SQLite schema. Bump SCHEMA_VERSION and add a migration step when it changes.

Timestamps are stored as UTC ISO 8601 text (`2026-09-22T20:36:39Z`), which sorts correctly.
"""

SCHEMA_VERSION = 2

SUPPRESSED = """
-- Opt-outs: people and organisations who asked not to be contacted or to be erased. Their records are never
-- stored or listed again; the ID is a CQC location or provider ID, or a company number.
CREATE TABLE IF NOT EXISTS suppressed (
    entity_id       TEXT PRIMARY KEY,
    added_at        TEXT NOT NULL,
    note            TEXT
);
"""

SCHEMA = """
-- Latest known state of every record fetched from a source.
CREATE TABLE IF NOT EXISTS entities (
    source          TEXT NOT NULL,          -- "cqc", "companies_house"
    entity_type     TEXT NOT NULL,          -- "location", "provider", "company"
    entity_id       TEXT NOT NULL,
    payload         TEXT NOT NULL,          -- sanitised JSON, as last fetched
    payload_hash    TEXT NOT NULL,
    first_seen_at   TEXT NOT NULL,
    last_fetched_at TEXT NOT NULL,
    last_changed_at TEXT NOT NULL,
    gone_at         TEXT,                   -- set when the source stops returning the record (404)
    PRIMARY KEY (source, entity_type, entity_id)
);

-- One row per distinct version of a record: written on first sight and whenever the payload changes.
-- Feeds compare versions to find week-on-week changes (for example, a new rating).
CREATE TABLE IF NOT EXISTS snapshots (
    id              INTEGER PRIMARY KEY,
    source          TEXT NOT NULL,
    entity_type     TEXT NOT NULL,
    entity_id       TEXT NOT NULL,
    fetched_at      TEXT NOT NULL,
    payload_hash    TEXT NOT NULL,
    payload         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS snapshots_entity ON snapshots (source, entity_type, entity_id, fetched_at);
CREATE INDEX IF NOT EXISTS snapshots_fetched ON snapshots (fetched_at);

-- Incremental sync positions, for example the CQC changes watermark.
CREATE TABLE IF NOT EXISTS sync_state (
    source          TEXT NOT NULL,
    stream          TEXT NOT NULL,
    cursor          TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    PRIMARY KEY (source, stream)
);

-- Leads found by the feeds (milestone 3). Unique per trigger, so re-runs never duplicate a lead.
CREATE TABLE IF NOT EXISTS lead_events (
    id              INTEGER PRIMARY KEY,
    vertical        TEXT NOT NULL,
    feed            TEXT NOT NULL,
    entity_key      TEXT NOT NULL,          -- e.g. "cqc:location:1-123"
    trigger_key     TEXT NOT NULL,          -- e.g. the rating and its publication date
    event_date      TEXT,
    week_ending     TEXT NOT NULL,          -- the digest week that first reported it
    created_at      TEXT NOT NULL,
    data            TEXT NOT NULL,
    UNIQUE (vertical, feed, entity_key, trigger_key)
);
CREATE INDEX IF NOT EXISTS lead_events_week ON lead_events (vertical, week_ending);

-- Audit trail of commands that touched the database.
CREATE TABLE IF NOT EXISTS runs (
    id              INTEGER PRIMARY KEY,
    command         TEXT NOT NULL,
    params          TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    status          TEXT NOT NULL,          -- "running", "ok", "failed"
    stats           TEXT
);
""" + SUPPRESSED

# Steps from one version to the next, for databases created by older code.
MIGRATIONS = {
    2: SUPPRESSED,
}
