-- Human-COS Runtime S1
-- Case/Evidence revision storage + immutable Context admission sidecar.

CREATE TABLE IF NOT EXISTS human_cos_case_revision (
    case_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (case_id, revision)
);

CREATE TABLE IF NOT EXISTS human_cos_evidence_revision (
    evidence_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    case_id TEXT NOT NULL,
    parent_revision INTEGER NULL,
    payload JSONB NOT NULL,
    snapshot_hash TEXT NOT NULL CHECK (snapshot_hash ~ '^[a-f0-9]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (evidence_id, revision),
    CONSTRAINT evidence_parent_revision_check CHECK (
        parent_revision IS NULL OR (parent_revision >= 1 AND parent_revision < revision)
    )
);

CREATE INDEX IF NOT EXISTS idx_human_cos_evidence_case
    ON human_cos_evidence_revision (case_id, evidence_id, revision DESC);

CREATE TABLE IF NOT EXISTS human_cos_context_admission (
    context_manifest_id TEXT PRIMARY KEY,
    manifest_hash TEXT NOT NULL CHECK (manifest_hash ~ '^[a-f0-9]{64}$'),
    record_hash TEXT NOT NULL UNIQUE CHECK (record_hash ~ '^[a-f0-9]{64}$'),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE OR REPLACE FUNCTION human_cos_block_immutable_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'Human-COS immutable record cannot be updated or deleted; append a new revision/record instead';
END;
$$;

DROP TRIGGER IF EXISTS trg_human_cos_case_no_update_delete
    ON human_cos_case_revision;
CREATE TRIGGER trg_human_cos_case_no_update_delete
BEFORE UPDATE OR DELETE ON human_cos_case_revision
FOR EACH ROW EXECUTE FUNCTION human_cos_block_immutable_mutation();

DROP TRIGGER IF EXISTS trg_human_cos_evidence_no_update_delete
    ON human_cos_evidence_revision;
CREATE TRIGGER trg_human_cos_evidence_no_update_delete
BEFORE UPDATE OR DELETE ON human_cos_evidence_revision
FOR EACH ROW EXECUTE FUNCTION human_cos_block_immutable_mutation();

DROP TRIGGER IF EXISTS trg_human_cos_context_admission_no_update_delete
    ON human_cos_context_admission;
CREATE TRIGGER trg_human_cos_context_admission_no_update_delete
BEFORE UPDATE OR DELETE ON human_cos_context_admission
FOR EACH ROW EXECUTE FUNCTION human_cos_block_immutable_mutation();
