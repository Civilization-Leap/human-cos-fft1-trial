-- Human-COS Runtime S4-V rollback.
-- Removes only S4-V Validation-Lab objects and leaves S1/S3 substrate intact.

DROP TABLE IF EXISTS human_cos_result_registry;
DROP TABLE IF EXISTS human_cos_reveal_record;
DROP TABLE IF EXISTS human_cos_judge_submission;
DROP TABLE IF EXISTS human_cos_blind_identity_mapping;
DROP TABLE IF EXISTS human_cos_blind_judge_bundle;
DROP TABLE IF EXISTS human_cos_contamination_gate;
DROP TABLE IF EXISTS human_cos_recognition_precheck;
DROP TABLE IF EXISTS human_cos_parity_report;
DROP TABLE IF EXISTS human_cos_validation_track;
DROP TABLE IF EXISTS human_cos_experiment_revision;
