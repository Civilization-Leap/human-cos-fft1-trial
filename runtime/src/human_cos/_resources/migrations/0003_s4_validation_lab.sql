-- Human-COS Runtime S4-V Validation Lab
-- V1/V2/V3/V4: Experiment, tracks, gates, Blind Judge, Reveal, and Result Registry.
-- Depends on 0001_s1_case_evidence.sql for Case revisions and immutable-mutation trigger.

CREATE TABLE IF NOT EXISTS human_cos_experiment_revision (
    experiment_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    case_id TEXT NOT NULL,
    case_revision INTEGER NOT NULL CHECK (case_revision >= 1),
    protocol_version TEXT NOT NULL,
    parent_manifest_hash TEXT NULL CHECK (
        parent_manifest_hash IS NULL OR parent_manifest_hash ~ '^[a-f0-9]{64}$'
    ),
    manifest_hash TEXT NOT NULL CHECK (manifest_hash ~ '^[a-f0-9]{64}$'),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (experiment_id, revision),
    CONSTRAINT human_cos_experiment_case_revision_fk
        FOREIGN KEY (case_id, case_revision)
        REFERENCES human_cos_case_revision (case_id, revision),
    CONSTRAINT human_cos_experiment_parent_revision_check CHECK (
        (revision = 1 AND parent_manifest_hash IS NULL)
        OR (revision > 1 AND parent_manifest_hash IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_human_cos_experiment_case
    ON human_cos_experiment_revision (case_id, case_revision, experiment_id, revision DESC);

DROP TRIGGER IF EXISTS trg_human_cos_experiment_no_update_delete
    ON human_cos_experiment_revision;
CREATE TRIGGER trg_human_cos_experiment_no_update_delete
BEFORE UPDATE OR DELETE ON human_cos_experiment_revision
FOR EACH ROW EXECUTE FUNCTION human_cos_block_immutable_mutation();

CREATE TABLE IF NOT EXISTS human_cos_validation_track (
    experiment_id TEXT NOT NULL,
    experiment_revision INTEGER NOT NULL CHECK (experiment_revision >= 1),
    track_kind TEXT NOT NULL CHECK (track_kind IN ('HC', 'BASELINE')),
    binding_hash TEXT NOT NULL CHECK (binding_hash ~ '^[a-f0-9]{64}$'),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (experiment_id, experiment_revision, track_kind),
    CONSTRAINT human_cos_validation_track_experiment_fk
        FOREIGN KEY (experiment_id, experiment_revision)
        REFERENCES human_cos_experiment_revision (experiment_id, revision)
);

DROP TRIGGER IF EXISTS trg_human_cos_validation_track_no_update_delete
    ON human_cos_validation_track;
CREATE TRIGGER trg_human_cos_validation_track_no_update_delete
BEFORE UPDATE OR DELETE ON human_cos_validation_track
FOR EACH ROW EXECUTE FUNCTION human_cos_block_immutable_mutation();

CREATE TABLE IF NOT EXISTS human_cos_parity_report (
    experiment_id TEXT NOT NULL,
    experiment_revision INTEGER NOT NULL CHECK (experiment_revision >= 1),
    status TEXT NOT NULL CHECK (status IN ('PASS', 'FAIL')),
    report_hash TEXT NOT NULL CHECK (report_hash ~ '^[a-f0-9]{64}$'),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (experiment_id, experiment_revision),
    CONSTRAINT human_cos_parity_report_experiment_fk
        FOREIGN KEY (experiment_id, experiment_revision)
        REFERENCES human_cos_experiment_revision (experiment_id, revision)
);

DROP TRIGGER IF EXISTS trg_human_cos_parity_report_no_update_delete
    ON human_cos_parity_report;
CREATE TRIGGER trg_human_cos_parity_report_no_update_delete
BEFORE UPDATE OR DELETE ON human_cos_parity_report
FOR EACH ROW EXECUTE FUNCTION human_cos_block_immutable_mutation();

CREATE TABLE IF NOT EXISTS human_cos_recognition_precheck (
    experiment_id TEXT NOT NULL,
    experiment_revision INTEGER NOT NULL CHECK (experiment_revision >= 1),
    status TEXT NOT NULL CHECK (status IN ('PASS', 'FAIL')),
    report_hash TEXT NOT NULL CHECK (report_hash ~ '^[a-f0-9]{64}$'),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (experiment_id, experiment_revision),
    CONSTRAINT human_cos_recognition_precheck_experiment_fk
        FOREIGN KEY (experiment_id, experiment_revision)
        REFERENCES human_cos_experiment_revision (experiment_id, revision)
);

DROP TRIGGER IF EXISTS trg_human_cos_recognition_precheck_no_update_delete
    ON human_cos_recognition_precheck;
CREATE TRIGGER trg_human_cos_recognition_precheck_no_update_delete
BEFORE UPDATE OR DELETE ON human_cos_recognition_precheck
FOR EACH ROW EXECUTE FUNCTION human_cos_block_immutable_mutation();

CREATE TABLE IF NOT EXISTS human_cos_contamination_gate (
    experiment_id TEXT NOT NULL,
    experiment_revision INTEGER NOT NULL CHECK (experiment_revision >= 1),
    hc_binding_hash TEXT NOT NULL CHECK (hc_binding_hash ~ '^[a-f0-9]{64}$'),
    baseline_binding_hash TEXT NOT NULL CHECK (baseline_binding_hash ~ '^[a-f0-9]{64}$'),
    status TEXT NOT NULL CHECK (status IN ('PASS', 'FAIL')),
    report_hash TEXT NOT NULL CHECK (report_hash ~ '^[a-f0-9]{64}$'),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (experiment_id, experiment_revision),
    CONSTRAINT human_cos_contamination_gate_experiment_fk
        FOREIGN KEY (experiment_id, experiment_revision)
        REFERENCES human_cos_experiment_revision (experiment_id, revision)
);

DROP TRIGGER IF EXISTS trg_human_cos_contamination_gate_no_update_delete
    ON human_cos_contamination_gate;
CREATE TRIGGER trg_human_cos_contamination_gate_no_update_delete
BEFORE UPDATE OR DELETE ON human_cos_contamination_gate
FOR EACH ROW EXECUTE FUNCTION human_cos_block_immutable_mutation();

CREATE TABLE IF NOT EXISTS human_cos_blind_judge_bundle (
    experiment_id TEXT NOT NULL,
    experiment_revision INTEGER NOT NULL CHECK (experiment_revision >= 1),
    bundle_hash TEXT NOT NULL CHECK (bundle_hash ~ '^[a-f0-9]{64}$'),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (experiment_id, experiment_revision),
    CONSTRAINT human_cos_blind_judge_bundle_experiment_fk
        FOREIGN KEY (experiment_id, experiment_revision)
        REFERENCES human_cos_experiment_revision (experiment_id, revision)
);

DROP TRIGGER IF EXISTS trg_human_cos_blind_judge_bundle_no_update_delete
    ON human_cos_blind_judge_bundle;
CREATE TRIGGER trg_human_cos_blind_judge_bundle_no_update_delete
BEFORE UPDATE OR DELETE ON human_cos_blind_judge_bundle
FOR EACH ROW EXECUTE FUNCTION human_cos_block_immutable_mutation();

CREATE TABLE IF NOT EXISTS human_cos_blind_identity_mapping (
    experiment_id TEXT NOT NULL,
    experiment_revision INTEGER NOT NULL CHECK (experiment_revision >= 1),
    bundle_hash TEXT NOT NULL CHECK (bundle_hash ~ '^[a-f0-9]{64}$'),
    mapping_hash TEXT NOT NULL CHECK (mapping_hash ~ '^[a-f0-9]{64}$'),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (experiment_id, experiment_revision),
    CONSTRAINT human_cos_blind_identity_mapping_bundle_fk
        FOREIGN KEY (experiment_id, experiment_revision)
        REFERENCES human_cos_blind_judge_bundle (experiment_id, experiment_revision)
);

DROP TRIGGER IF EXISTS trg_human_cos_blind_identity_mapping_no_update_delete
    ON human_cos_blind_identity_mapping;
CREATE TRIGGER trg_human_cos_blind_identity_mapping_no_update_delete
BEFORE UPDATE OR DELETE ON human_cos_blind_identity_mapping
FOR EACH ROW EXECUTE FUNCTION human_cos_block_immutable_mutation();

CREATE TABLE IF NOT EXISTS human_cos_judge_submission (
    experiment_id TEXT NOT NULL,
    experiment_revision INTEGER NOT NULL CHECK (experiment_revision >= 1),
    bundle_hash TEXT NOT NULL CHECK (bundle_hash ~ '^[a-f0-9]{64}$'),
    submission_hash TEXT NOT NULL CHECK (submission_hash ~ '^[a-f0-9]{64}$'),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (experiment_id, experiment_revision),
    CONSTRAINT human_cos_judge_submission_bundle_fk
        FOREIGN KEY (experiment_id, experiment_revision)
        REFERENCES human_cos_blind_judge_bundle (experiment_id, experiment_revision)
);

DROP TRIGGER IF EXISTS trg_human_cos_judge_submission_no_update_delete
    ON human_cos_judge_submission;
CREATE TRIGGER trg_human_cos_judge_submission_no_update_delete
BEFORE UPDATE OR DELETE ON human_cos_judge_submission
FOR EACH ROW EXECUTE FUNCTION human_cos_block_immutable_mutation();

CREATE TABLE IF NOT EXISTS human_cos_reveal_record (
    experiment_id TEXT NOT NULL,
    experiment_revision INTEGER NOT NULL CHECK (experiment_revision >= 1),
    submission_hash TEXT NOT NULL CHECK (submission_hash ~ '^[a-f0-9]{64}$'),
    mapping_hash TEXT NOT NULL CHECK (mapping_hash ~ '^[a-f0-9]{64}$'),
    reveal_hash TEXT NOT NULL CHECK (reveal_hash ~ '^[a-f0-9]{64}$'),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (experiment_id, experiment_revision),
    CONSTRAINT human_cos_reveal_submission_fk
        FOREIGN KEY (experiment_id, experiment_revision)
        REFERENCES human_cos_judge_submission (experiment_id, experiment_revision),
    CONSTRAINT human_cos_reveal_mapping_fk
        FOREIGN KEY (experiment_id, experiment_revision)
        REFERENCES human_cos_blind_identity_mapping (experiment_id, experiment_revision)
);

DROP TRIGGER IF EXISTS trg_human_cos_reveal_record_no_update_delete
    ON human_cos_reveal_record;
CREATE TRIGGER trg_human_cos_reveal_record_no_update_delete
BEFORE UPDATE OR DELETE ON human_cos_reveal_record
FOR EACH ROW EXECUTE FUNCTION human_cos_block_immutable_mutation();

CREATE TABLE IF NOT EXISTS human_cos_result_registry (
    experiment_id TEXT NOT NULL,
    experiment_revision INTEGER NOT NULL CHECK (experiment_revision >= 1),
    registry_hash TEXT NOT NULL CHECK (registry_hash ~ '^[a-f0-9]{64}$'),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (experiment_id, experiment_revision),
    CONSTRAINT human_cos_result_registry_reveal_fk
        FOREIGN KEY (experiment_id, experiment_revision)
        REFERENCES human_cos_reveal_record (experiment_id, experiment_revision)
);

DROP TRIGGER IF EXISTS trg_human_cos_result_registry_no_update_delete
    ON human_cos_result_registry;
CREATE TRIGGER trg_human_cos_result_registry_no_update_delete
BEFORE UPDATE OR DELETE ON human_cos_result_registry
FOR EACH ROW EXECUTE FUNCTION human_cos_block_immutable_mutation();
