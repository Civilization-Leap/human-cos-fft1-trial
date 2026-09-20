-- Human-COS Runtime S6-WCI world/causal integration sidecars.
-- Persists WCI1 disclosure/dissent, WCI2 world/causal revisions,
-- WCI3 Controller B integration, and WCI4 Critical Node review records.
-- Depends on 0001_s1_case_evidence.sql for Case revisions and immutable trigger.

CREATE TABLE IF NOT EXISTS human_cos_s6_disclosure_grant (
    grant_hash TEXT PRIMARY KEY CHECK (grant_hash ~ '^[a-f0-9]{64}$'),
    grant_id TEXT NOT NULL UNIQUE,
    case_id TEXT NOT NULL,
    case_revision INTEGER NOT NULL CHECK (case_revision >= 1),
    reviewer_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT human_cos_s6_disclosure_grant_case_fk
        FOREIGN KEY (case_id, case_revision)
        REFERENCES human_cos_case_revision (case_id, revision)
);

CREATE TABLE IF NOT EXISTS human_cos_s6_cross_exam_task (
    task_hash TEXT PRIMARY KEY CHECK (task_hash ~ '^[a-f0-9]{64}$'),
    task_id TEXT NOT NULL UNIQUE,
    case_id TEXT NOT NULL,
    case_revision INTEGER NOT NULL CHECK (case_revision >= 1),
    grant_hash TEXT NOT NULL,
    reviewer_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT human_cos_s6_cross_exam_task_case_fk
        FOREIGN KEY (case_id, case_revision)
        REFERENCES human_cos_case_revision (case_id, revision),
    CONSTRAINT human_cos_s6_cross_exam_task_grant_fk
        FOREIGN KEY (grant_hash) REFERENCES human_cos_s6_disclosure_grant (grant_hash)
);

CREATE TABLE IF NOT EXISTS human_cos_s6_cross_exam_response (
    response_hash TEXT PRIMARY KEY CHECK (response_hash ~ '^[a-f0-9]{64}$'),
    response_id TEXT NOT NULL UNIQUE,
    case_id TEXT NOT NULL,
    case_revision INTEGER NOT NULL CHECK (case_revision >= 1),
    task_hash TEXT NOT NULL,
    grant_hash TEXT NOT NULL,
    reviewer_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT human_cos_s6_cross_exam_response_case_fk
        FOREIGN KEY (case_id, case_revision)
        REFERENCES human_cos_case_revision (case_id, revision),
    CONSTRAINT human_cos_s6_cross_exam_response_task_fk
        FOREIGN KEY (task_hash) REFERENCES human_cos_s6_cross_exam_task (task_hash),
    CONSTRAINT human_cos_s6_cross_exam_response_grant_fk
        FOREIGN KEY (grant_hash) REFERENCES human_cos_s6_disclosure_grant (grant_hash)
);

CREATE TABLE IF NOT EXISTS human_cos_s6_disagreement_node (
    node_hash TEXT PRIMARY KEY CHECK (node_hash ~ '^[a-f0-9]{64}$'),
    node_id TEXT NOT NULL UNIQUE,
    case_id TEXT NOT NULL,
    case_revision INTEGER NOT NULL CHECK (case_revision >= 1),
    conflict_type TEXT NOT NULL,
    high_impact BOOLEAN NOT NULL,
    unresolved BOOLEAN NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT human_cos_s6_disagreement_node_case_fk
        FOREIGN KEY (case_id, case_revision)
        REFERENCES human_cos_case_revision (case_id, revision)
);

CREATE TABLE IF NOT EXISTS human_cos_s6_actor_state_revision (
    actor_state_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    state_hash TEXT NOT NULL UNIQUE CHECK (state_hash ~ '^[a-f0-9]{64}$'),
    parent_state_hash TEXT CHECK (parent_state_hash IS NULL OR parent_state_hash ~ '^[a-f0-9]{64}$'),
    actor_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    case_revision INTEGER NOT NULL CHECK (case_revision >= 1),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (actor_state_id, revision),
    CONSTRAINT human_cos_s6_actor_state_case_fk
        FOREIGN KEY (case_id, case_revision)
        REFERENCES human_cos_case_revision (case_id, revision)
);

CREATE TABLE IF NOT EXISTS human_cos_s6_causal_graph_revision (
    graph_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    graph_hash TEXT NOT NULL UNIQUE CHECK (graph_hash ~ '^[a-f0-9]{64}$'),
    parent_graph_hash TEXT CHECK (parent_graph_hash IS NULL OR parent_graph_hash ~ '^[a-f0-9]{64}$'),
    case_id TEXT NOT NULL,
    case_revision INTEGER NOT NULL CHECK (case_revision >= 1),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (graph_id, revision),
    CONSTRAINT human_cos_s6_causal_graph_case_fk
        FOREIGN KEY (case_id, case_revision)
        REFERENCES human_cos_case_revision (case_id, revision)
);

CREATE TABLE IF NOT EXISTS human_cos_s6_world_state_revision (
    world_state_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    world_state_hash TEXT NOT NULL UNIQUE CHECK (world_state_hash ~ '^[a-f0-9]{64}$'),
    parent_world_state_hash TEXT CHECK (
        parent_world_state_hash IS NULL OR parent_world_state_hash ~ '^[a-f0-9]{64}$'
    ),
    case_id TEXT NOT NULL,
    case_revision INTEGER NOT NULL CHECK (case_revision >= 1),
    causal_graph_hash TEXT CHECK (causal_graph_hash IS NULL OR causal_graph_hash ~ '^[a-f0-9]{64}$'),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (world_state_id, revision),
    CONSTRAINT human_cos_s6_world_state_case_fk
        FOREIGN KEY (case_id, case_revision)
        REFERENCES human_cos_case_revision (case_id, revision),
    CONSTRAINT human_cos_s6_world_state_graph_fk
        FOREIGN KEY (causal_graph_hash) REFERENCES human_cos_s6_causal_graph_revision (graph_hash)
);

CREATE TABLE IF NOT EXISTS human_cos_s6_critical_integration (
    integration_hash TEXT PRIMARY KEY CHECK (integration_hash ~ '^[a-f0-9]{64}$'),
    integration_id TEXT NOT NULL UNIQUE,
    case_id TEXT NOT NULL,
    case_revision INTEGER NOT NULL CHECK (case_revision >= 1),
    controller_model_id TEXT NOT NULL,
    world_state_hash TEXT NOT NULL,
    causal_graph_hash TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT human_cos_s6_critical_integration_case_fk
        FOREIGN KEY (case_id, case_revision)
        REFERENCES human_cos_case_revision (case_id, revision),
    CONSTRAINT human_cos_s6_critical_integration_world_fk
        FOREIGN KEY (world_state_hash) REFERENCES human_cos_s6_world_state_revision (world_state_hash),
    CONSTRAINT human_cos_s6_critical_integration_graph_fk
        FOREIGN KEY (causal_graph_hash) REFERENCES human_cos_s6_causal_graph_revision (graph_hash)
);

CREATE TABLE IF NOT EXISTS human_cos_s6_critical_node_detection (
    detection_hash TEXT PRIMARY KEY CHECK (detection_hash ~ '^[a-f0-9]{64}$'),
    detection_id TEXT NOT NULL UNIQUE,
    case_id TEXT NOT NULL,
    case_revision INTEGER NOT NULL CHECK (case_revision >= 1),
    integration_hash TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT human_cos_s6_critical_node_detection_case_fk
        FOREIGN KEY (case_id, case_revision)
        REFERENCES human_cos_case_revision (case_id, revision),
    CONSTRAINT human_cos_s6_critical_node_detection_integration_fk
        FOREIGN KEY (integration_hash)
        REFERENCES human_cos_s6_critical_integration (integration_hash)
);

CREATE TABLE IF NOT EXISTS human_cos_s6_critical_review_plan (
    plan_hash TEXT PRIMARY KEY CHECK (plan_hash ~ '^[a-f0-9]{64}$'),
    plan_id TEXT NOT NULL UNIQUE,
    case_id TEXT NOT NULL,
    case_revision INTEGER NOT NULL CHECK (case_revision >= 1),
    detection_hash TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT human_cos_s6_critical_review_plan_case_fk
        FOREIGN KEY (case_id, case_revision)
        REFERENCES human_cos_case_revision (case_id, revision),
    CONSTRAINT human_cos_s6_critical_review_plan_detection_fk
        FOREIGN KEY (detection_hash)
        REFERENCES human_cos_s6_critical_node_detection (detection_hash)
);

CREATE TABLE IF NOT EXISTS human_cos_s6_critical_review_packet (
    packet_hash TEXT PRIMARY KEY CHECK (packet_hash ~ '^[a-f0-9]{64}$'),
    packet_id TEXT NOT NULL UNIQUE,
    case_id TEXT NOT NULL,
    case_revision INTEGER NOT NULL CHECK (case_revision >= 1),
    detection_hash TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    route_id TEXT NOT NULL,
    reviewer_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT human_cos_s6_critical_review_packet_case_fk
        FOREIGN KEY (case_id, case_revision)
        REFERENCES human_cos_case_revision (case_id, revision),
    CONSTRAINT human_cos_s6_critical_review_packet_detection_fk
        FOREIGN KEY (detection_hash)
        REFERENCES human_cos_s6_critical_node_detection (detection_hash),
    CONSTRAINT human_cos_s6_critical_review_packet_plan_fk
        FOREIGN KEY (plan_hash) REFERENCES human_cos_s6_critical_review_plan (plan_hash)
);

CREATE TABLE IF NOT EXISTS human_cos_s6_critical_review_evidence (
    evidence_hash TEXT PRIMARY KEY CHECK (evidence_hash ~ '^[a-f0-9]{64}$'),
    evidence_id TEXT NOT NULL UNIQUE,
    case_id TEXT NOT NULL,
    case_revision INTEGER NOT NULL CHECK (case_revision >= 1),
    detection_hash TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    packet_hash TEXT NOT NULL,
    route_id TEXT NOT NULL,
    reviewer_id TEXT NOT NULL,
    assessment TEXT NOT NULL CHECK (assessment IN ('SUPPORTS', 'CHALLENGES', 'UNCERTAIN')),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT human_cos_s6_critical_review_evidence_case_fk
        FOREIGN KEY (case_id, case_revision)
        REFERENCES human_cos_case_revision (case_id, revision),
    CONSTRAINT human_cos_s6_critical_review_evidence_detection_fk
        FOREIGN KEY (detection_hash)
        REFERENCES human_cos_s6_critical_node_detection (detection_hash),
    CONSTRAINT human_cos_s6_critical_review_evidence_plan_fk
        FOREIGN KEY (plan_hash) REFERENCES human_cos_s6_critical_review_plan (plan_hash),
    CONSTRAINT human_cos_s6_critical_review_evidence_packet_fk
        FOREIGN KEY (packet_hash) REFERENCES human_cos_s6_critical_review_packet (packet_hash)
);

DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'human_cos_s6_disclosure_grant',
        'human_cos_s6_cross_exam_task',
        'human_cos_s6_cross_exam_response',
        'human_cos_s6_disagreement_node',
        'human_cos_s6_actor_state_revision',
        'human_cos_s6_causal_graph_revision',
        'human_cos_s6_world_state_revision',
        'human_cos_s6_critical_integration',
        'human_cos_s6_critical_node_detection',
        'human_cos_s6_critical_review_plan',
        'human_cos_s6_critical_review_packet',
        'human_cos_s6_critical_review_evidence'
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
