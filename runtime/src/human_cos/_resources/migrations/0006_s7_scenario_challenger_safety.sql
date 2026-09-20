-- Human-COS Runtime S7-SCS append-only persistence ledger.
-- Stores only already-frozen S7 artifacts and hash lineage; it creates no new
-- cognition, process authority, Evaluator score, Final Synthesis edge, or
-- reality-execution authority.

CREATE TABLE IF NOT EXISTS human_cos_s7_artifact (
    artifact_hash TEXT PRIMARY KEY CHECK (artifact_hash ~ '^[a-f0-9]{64}$'),
    artifact_kind TEXT NOT NULL CHECK (
        artifact_kind IN (
            'RESEARCH_SAFETY_ADMISSION',
            'RESEARCH_SAFETY_RESULT',
            'SCENARIO_GENERATION_PACKET',
            'SCENARIO_GENERATION_RESULT',
            'CONTROLLER_C_INVOCATION',
            'SCENARIO_PATH',
            'INTERVENTION',
            'SCENARIO_SET',
            'CONTROLLER_C_OUTPUT',
            'RESIMULATION_SAFETY_ADMISSION',
            'RESIMULATION_SAFETY_RESULT',
            'RERUN_TASK',
            'RERUN_ROUTE',
            'RERUN_OUTPUT',
            'RESIMULATION_PLAN',
            'RESIMULATION_RESULT',
            'AT17_EVIDENCE',
            'CHALLENGER_TASK',
            'CHALLENGER_PACKET',
            'CHALLENGER_FINDING',
            'CHALLENGER_RESPONSE',
            'CHALLENGER_SATISFACTION',
            'CHALLENGER_GATE'
        )
    ),
    artifact_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    case_revision INTEGER NOT NULL CHECK (case_revision >= 1),
    protocol_version TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (artifact_kind, artifact_id),
    CONSTRAINT human_cos_s7_artifact_case_fk
        FOREIGN KEY (case_id, case_revision)
        REFERENCES human_cos_case_revision (case_id, revision)
);

CREATE TABLE IF NOT EXISTS human_cos_s7_artifact_link (
    artifact_hash TEXT NOT NULL,
    relation TEXT NOT NULL,
    source_hash TEXT NOT NULL CHECK (source_hash ~ '^[a-f0-9]{64}$'),
    source_layer TEXT NOT NULL CHECK (source_layer IN ('S6', 'S7', 'RUNTIME')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (artifact_hash, relation, source_hash),
    CONSTRAINT human_cos_s7_artifact_link_target_fk
        FOREIGN KEY (artifact_hash)
        REFERENCES human_cos_s7_artifact (artifact_hash)
);

DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'human_cos_s7_artifact',
        'human_cos_s7_artifact_link'
    ]
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_%s_no_update_delete ON %I', table_name, table_name);
        EXECUTE format(
            'CREATE TRIGGER trg_%s_no_update_delete BEFORE UPDATE OR DELETE ON %I '
            'FOR EACH ROW EXECUTE FUNCTION human_cos_block_immutable_mutation()',
            table_name,
            table_name
        );
    END LOOP;
END $$;
