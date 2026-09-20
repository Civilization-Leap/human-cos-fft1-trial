-- Roll back only S5-CDE cognitive-subject sidecars.

DROP TABLE IF EXISTS human_cos_expert_submission;
DROP TABLE IF EXISTS human_cos_expert_task;
DROP TABLE IF EXISTS human_cos_expert_profile_revision;
DROP TABLE IF EXISTS human_cos_domain_output;
DROP TABLE IF EXISTS human_cos_domain_routing_plan;
DROP TABLE IF EXISTS human_cos_domain_route;
DROP TABLE IF EXISTS human_cos_domain_task;
DROP TABLE IF EXISTS human_cos_framing_review;
DROP TABLE IF EXISTS human_cos_initial_framing;
DROP TABLE IF EXISTS human_cos_framing_requirement;
