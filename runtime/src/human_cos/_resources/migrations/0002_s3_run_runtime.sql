-- Human-COS Runtime S3-N2
-- Immutable Run Manifest lifecycle snapshots, RawOutput artifacts, and Audit Events.
-- Depends on 0001_s1_case_evidence.sql for human_cos_block_immutable_mutation().

CREATE TABLE IF NOT EXISTS human_cos_run_manifest_revision (
    run_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence >= 1),
    case_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('CREATED', 'RUNNING', 'FROZEN', 'INVALID', 'FAILED')),
    parent_run_id TEXT NULL,
    fallback_from TEXT NULL,
    manifest_hash TEXT NOT NULL CHECK (manifest_hash ~ '^[a-f0-9]{64}$'),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (run_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_human_cos_run_case
    ON human_cos_run_manifest_revision (case_id, run_id, sequence DESC);

CREATE INDEX IF NOT EXISTS idx_human_cos_run_parent
    ON human_cos_run_manifest_revision (parent_run_id)
    WHERE parent_run_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS human_cos_raw_output (
    output_ref TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    raw_bytes BYTEA NOT NULL,
    raw_output_hash TEXT NOT NULL CHECK (raw_output_hash ~ '^[a-f0-9]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_human_cos_raw_output_run
    ON human_cos_raw_output (run_id);

CREATE TABLE IF NOT EXISTS human_cos_audit_event (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NULL,
    event_type TEXT NOT NULL,
    event_hash TEXT NOT NULL CHECK (event_hash ~ '^[a-f0-9]{64}$'),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_human_cos_audit_run
    ON human_cos_audit_event (run_id, created_at, event_id)
    WHERE run_id IS NOT NULL;

DROP TRIGGER IF EXISTS trg_human_cos_run_manifest_no_update_delete
    ON human_cos_run_manifest_revision;
CREATE TRIGGER trg_human_cos_run_manifest_no_update_delete
BEFORE UPDATE OR DELETE ON human_cos_run_manifest_revision
FOR EACH ROW EXECUTE FUNCTION human_cos_block_immutable_mutation();

DROP TRIGGER IF EXISTS trg_human_cos_raw_output_no_update_delete
    ON human_cos_raw_output;
CREATE TRIGGER trg_human_cos_raw_output_no_update_delete
BEFORE UPDATE OR DELETE ON human_cos_raw_output
FOR EACH ROW EXECUTE FUNCTION human_cos_block_immutable_mutation();

DROP TRIGGER IF EXISTS trg_human_cos_audit_event_no_update_delete
    ON human_cos_audit_event;
CREATE TRIGGER trg_human_cos_audit_event_no_update_delete
BEFORE UPDATE OR DELETE ON human_cos_audit_event
FOR EACH ROW EXECUTE FUNCTION human_cos_block_immutable_mutation();
