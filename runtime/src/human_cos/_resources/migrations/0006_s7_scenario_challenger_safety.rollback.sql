-- Roll back only S7-SCS persistence objects. Preserve S1-S6 tables.

DROP TABLE IF EXISTS human_cos_s7_artifact_link;
DROP TABLE IF EXISTS human_cos_s7_artifact;
