-- Human-COS Runtime S5-CDE cognitive-subject sidecars.
-- Persists CDE1 framing, CDE2 review, CDE3 Domain, and CDE4 Expert records.
-- Depends on 0001_s1_case_evidence.sql for Case revisions and immutable trigger.

CREATE TABLE IF NOT EXISTS human_cos_framing_requirement (
    case_id TEXT NOT NULL,
    case_revision INTEGER NOT NULL CHECK (case_revision >= 1),
    record_hash TEXT NOT NULL CHECK (record_hash ~ '^[a-f0-9]{64}$'),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (case_id, case_revision),
    CONSTRAINT human_cos_framing_requirement_case_fk
        FOREIGN KEY (case_id, case_revision)
        REFERENCES human_cos_case_revision (case_id, revision)
);

CREATE TABLE IF NOT EXISTS human_cos_initial_framing (
    case_id TEXT NOT NULL,
    case_revision INTEGER NOT NULL CHECK (case_revision >= 1),
    lane TEXT NOT NULL CHECK (lane IN ('A1', 'A2')),
    run_id TEXT NOT NULL,
    record_hash TEXT NOT NULL CHECK (record_hash ~ '^[a-f0-9]{64}$'),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (case_id, case_revision, lane),
    UNIQUE (run_id),
    CONSTRAINT human_cos_initial_framing_case_fk
        FOREIGN KEY (case_id, case_revision)
        REFERENCES human_cos_case_revision (case_id, revision)
);

CREATE TABLE IF NOT EXISTS human_cos_framing_review (
    case_id TEXT NOT NULL,
    case_revision INTEGER NOT NULL CHECK (case_revision >= 1),
    requirement_hash TEXT NOT NULL CHECK (requirement_hash ~ '^[a-f0-9]{64}$'),
    a1_record_hash TEXT NOT NULL CHECK (a1_record_hash ~ '^[a-f0-9]{64}$'),
    a2_record_hash TEXT NOT NULL CHECK (a2_record_hash ~ '^[a-f0-9]{64}$'),
    review_hash TEXT NOT NULL CHECK (review_hash ~ '^[a-f0-9]{64}$'),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (case_id, case_revision),
    CONSTRAINT human_cos_framing_review_requirement_fk
        FOREIGN KEY (case_id, case_revision)
        REFERENCES human_cos_framing_requirement (case_id, case_revision)
);

CREATE TABLE IF NOT EXISTS human_cos_domain_task (
    task_hash TEXT PRIMARY KEY CHECK (task_hash ~ '^[a-f0-9]{64}$'),
    task_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    case_revision INTEGER NOT NULL CHECK (case_revision >= 1),
    domain_id TEXT NOT NULL,
    framing_review_hash TEXT NOT NULL CHECK (framing_review_hash ~ '^[a-f0-9]{64}$'),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (task_id),
    CONSTRAINT human_cos_domain_task_case_fk
        FOREIGN KEY (case_id, case_revision)
        REFERENCES human_cos_case_revision (case_id, revision)
);

CREATE TABLE IF NOT EXISTS human_cos_domain_route (
    route_hash TEXT PRIMARY KEY CHECK (route_hash ~ '^[a-f0-9]{64}$'),
    task_hash TEXT NOT NULL,
    model_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT human_cos_domain_route_task_fk
        FOREIGN KEY (task_hash) REFERENCES human_cos_domain_task (task_hash)
);

CREATE TABLE IF NOT EXISTS human_cos_domain_routing_plan (
    plan_hash TEXT PRIMARY KEY CHECK (plan_hash ~ '^[a-f0-9]{64}$'),
    case_id TEXT NOT NULL,
    case_revision INTEGER NOT NULL CHECK (case_revision >= 1),
    framing_review_hash TEXT NOT NULL CHECK (framing_review_hash ~ '^[a-f0-9]{64}$'),
    routing_complete BOOLEAN NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT human_cos_domain_routing_plan_case_fk
        FOREIGN KEY (case_id, case_revision)
        REFERENCES human_cos_case_revision (case_id, revision)
);

CREATE TABLE IF NOT EXISTS human_cos_domain_output (
    record_hash TEXT PRIMARY KEY CHECK (record_hash ~ '^[a-f0-9]{64}$'),
    task_hash TEXT NOT NULL,
    route_hash TEXT NOT NULL,
    run_id TEXT NOT NULL,
    actual_model_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (task_hash, route_hash),
    CONSTRAINT human_cos_domain_output_task_fk
        FOREIGN KEY (task_hash) REFERENCES human_cos_domain_task (task_hash),
    CONSTRAINT human_cos_domain_output_route_fk
        FOREIGN KEY (route_hash) REFERENCES human_cos_domain_route (route_hash)
);

CREATE TABLE IF NOT EXISTS human_cos_expert_profile_revision (
    expert_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    profile_hash TEXT NOT NULL CHECK (profile_hash ~ '^[a-f0-9]{64}$'),
    domain TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (expert_id, revision),
    UNIQUE (profile_hash)
);

CREATE TABLE IF NOT EXISTS human_cos_expert_task (
    task_hash TEXT PRIMARY KEY CHECK (task_hash ~ '^[a-f0-9]{64}$'),
    task_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    case_revision INTEGER NOT NULL CHECK (case_revision >= 1),
    expert_id TEXT NOT NULL,
    profile_revision INTEGER NOT NULL CHECK (profile_revision >= 1),
    profile_hash TEXT NOT NULL CHECK (profile_hash ~ '^[a-f0-9]{64}$'),
    independent_required BOOLEAN NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (task_id),
    CONSTRAINT human_cos_expert_task_case_fk
        FOREIGN KEY (case_id, case_revision)
        REFERENCES human_cos_case_revision (case_id, revision),
    CONSTRAINT human_cos_expert_task_profile_fk
        FOREIGN KEY (expert_id, profile_revision)
        REFERENCES human_cos_expert_profile_revision (expert_id, revision)
);

CREATE TABLE IF NOT EXISTS human_cos_expert_submission (
    submission_hash TEXT PRIMARY KEY CHECK (submission_hash ~ '^[a-f0-9]{64}$'),
    submission_id TEXT NOT NULL UNIQUE,
    task_hash TEXT NOT NULL,
    expert_id TEXT NOT NULL,
    profile_revision INTEGER NOT NULL CHECK (profile_revision >= 1),
    actor_type TEXT NOT NULL CHECK (actor_type = 'HUMAN'),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT human_cos_expert_submission_task_fk
        FOREIGN KEY (task_hash) REFERENCES human_cos_expert_task (task_hash),
    CONSTRAINT human_cos_expert_submission_profile_fk
        FOREIGN KEY (expert_id, profile_revision)
        REFERENCES human_cos_expert_profile_revision (expert_id, revision)
);

DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'human_cos_framing_requirement',
        'human_cos_initial_framing',
        'human_cos_framing_review',
        'human_cos_domain_task',
        'human_cos_domain_route',
        'human_cos_domain_routing_plan',
        'human_cos_domain_output',
        'human_cos_expert_profile_revision',
        'human_cos_expert_task',
        'human_cos_expert_submission'
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
