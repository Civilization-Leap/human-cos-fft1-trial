-- Human-COS Runtime S1 rollback.
-- Destructive by definition: intended only before retained S1 data is authoritative.

DROP TABLE IF EXISTS human_cos_context_admission;
DROP TABLE IF EXISTS human_cos_evidence_revision;
DROP TABLE IF EXISTS human_cos_case_revision;
DROP FUNCTION IF EXISTS human_cos_block_immutable_mutation();
