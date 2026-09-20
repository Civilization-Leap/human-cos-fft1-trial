-- Human-COS Runtime S8-EVAL append-only persistence ledger.
-- Stores only already-frozen S8 evaluation artifacts and exact hash lineage.
-- This migration creates no Evaluator, regression, recognition, process,
-- Final Synthesis, Final Claim, Seal, or reality-execution authority.
--
-- Artifact instance identity is (artifact_kind, artifact_id).  artifact_hash is
-- a non-unique content hash because immutable declarations and metric rules may
-- be reused by multiple Cases without becoming the same Case-owned record.

CREATE TABLE IF NOT EXISTS human_cos_s8_artifact (
    artifact_hash TEXT NOT NULL CHECK (artifact_hash ~ '^[a-f0-9]{64}$'),
    artifact_kind TEXT NOT NULL CHECK (
        artifact_kind IN (
            'EVALUATOR_TASK',
            'EVALUATOR_INPUT_PACKET',
            'EVALUATOR_FINDING',
            'EVALUATOR_RESULT',
            'HC_REGRESSION_PARITY_DECLARATION',
            'HC_REGRESSION_METRIC_RULE',
            'HC_REGRESSION_METRIC_SOURCE',
            'HC_REGRESSION_PREREGISTRATION',
            'HC_REGRESSION_TRACK_SNAPSHOT',
            'HC_REGRESSION_REPORT',
            'LOW_RECOGNITION_VISIBILITY_POLICY',
            'LOW_RECOGNITION_EXPOSURE_SOURCE',
            'LOW_RECOGNITION_EXPOSURE_SNAPSHOT',
            'LOW_RECOGNITION_GATE',
            'LOW_RECOGNITION_REVEAL',
            'EVALUATION_EVIDENCE_BINDING'
        )
    ),
    artifact_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    case_revision INTEGER NOT NULL CHECK (case_revision >= 1),
    protocol_version TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (artifact_kind, artifact_id),
    CONSTRAINT human_cos_s8_artifact_case_fk
        FOREIGN KEY (case_id, case_revision)
        REFERENCES human_cos_case_revision (case_id, revision)
);

CREATE TABLE IF NOT EXISTS human_cos_s8_artifact_link (
    artifact_hash TEXT NOT NULL CHECK (artifact_hash ~ '^[a-f0-9]{64}$'),
    relation TEXT NOT NULL,
    source_hash TEXT NOT NULL CHECK (source_hash ~ '^[a-f0-9]{64}$'),
    source_layer TEXT NOT NULL CHECK (
        source_layer IN ('S5', 'S6', 'S7', 'S8', 'RUNTIME')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (artifact_hash, relation, source_hash)
);

CREATE INDEX IF NOT EXISTS idx_human_cos_s8_case
    ON human_cos_s8_artifact (case_id, case_revision, artifact_kind);

CREATE INDEX IF NOT EXISTS idx_human_cos_s8_artifact_hash
    ON human_cos_s8_artifact (artifact_hash, artifact_kind);

CREATE INDEX IF NOT EXISTS idx_human_cos_s8_source
    ON human_cos_s8_artifact_link (source_hash, source_layer);

CREATE OR REPLACE FUNCTION human_cos_s8_require_target_content()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM human_cos_s8_artifact
        WHERE artifact_hash = NEW.artifact_hash
    ) THEN
        RAISE EXCEPTION
            'S8 lineage target content hash is not stored: %',
            NEW.artifact_hash;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_human_cos_s8_link_require_target
    ON human_cos_s8_artifact_link;
CREATE TRIGGER trg_human_cos_s8_link_require_target
BEFORE INSERT ON human_cos_s8_artifact_link
FOR EACH ROW EXECUTE FUNCTION human_cos_s8_require_target_content();

DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'human_cos_s8_artifact',
        'human_cos_s8_artifact_link'
    ]
    LOOP
        EXECUTE format(
            'DROP TRIGGER IF EXISTS trg_%s_no_update_delete ON %I',
            table_name,
            table_name
        );
        EXECUTE format(
            'CREATE TRIGGER trg_%s_no_update_delete BEFORE UPDATE OR DELETE ON %I '
            'FOR EACH ROW EXECUTE FUNCTION human_cos_block_immutable_mutation()',
            table_name,
            table_name
        );
    END LOOP;
END $$;
