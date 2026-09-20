-- Human-COS Runtime S3-N2 rollback.
-- Leaves S1 Case/Evidence/Context tables and the shared immutability function intact.

DROP TABLE IF EXISTS human_cos_audit_event;
DROP TABLE IF EXISTS human_cos_raw_output;
DROP TABLE IF EXISTS human_cos_run_manifest_revision;
