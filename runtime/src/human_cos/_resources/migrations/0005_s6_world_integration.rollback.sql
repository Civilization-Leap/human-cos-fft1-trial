-- Roll back only S6-WCI world/causal integration sidecars.

DROP TABLE IF EXISTS human_cos_s6_critical_review_evidence;
DROP TABLE IF EXISTS human_cos_s6_critical_review_packet;
DROP TABLE IF EXISTS human_cos_s6_critical_review_plan;
DROP TABLE IF EXISTS human_cos_s6_critical_node_detection;
DROP TABLE IF EXISTS human_cos_s6_critical_integration;
DROP TABLE IF EXISTS human_cos_s6_world_state_revision;
DROP TABLE IF EXISTS human_cos_s6_causal_graph_revision;
DROP TABLE IF EXISTS human_cos_s6_actor_state_revision;
DROP TABLE IF EXISTS human_cos_s6_disagreement_node;
DROP TABLE IF EXISTS human_cos_s6_cross_exam_response;
DROP TABLE IF EXISTS human_cos_s6_cross_exam_task;
DROP TABLE IF EXISTS human_cos_s6_disclosure_grant;
