-- Roll back only S8-EVAL persistence objects. Preserve S1-S7 tables.

DROP TABLE IF EXISTS human_cos_s8_artifact_link;
DROP TABLE IF EXISTS human_cos_s8_artifact;
DROP FUNCTION IF EXISTS human_cos_s8_require_target_content();
