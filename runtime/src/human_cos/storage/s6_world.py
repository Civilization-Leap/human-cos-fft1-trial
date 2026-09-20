"""Typed append-only PostgreSQL persistence for the authorized S6-WCI slice."""

from __future__ import annotations

from typing import Any, Protocol

from psycopg import Connection, errors
from psycopg.types.json import Jsonb

from human_cos.controllers.critical_integration import CriticalIntegrationRecord
from human_cos.integration import (
    CrossExamResponse,
    CrossExamTask,
    DisagreementNode,
    DisclosureGrant,
)
from human_cos.storage.repository import DuplicateRevisionError
from human_cos.world import (
    ActorStateSnapshot,
    CausalGraph,
    CriticalNodeDetection,
    CriticalReviewEvidence,
    CriticalReviewPacket,
    CriticalReviewPlan,
    WorldStateSnapshot,
)


class _IntegrityChecked(Protocol):
    def assert_integrity(self) -> None: ...
    def to_document(self) -> dict[str, Any]: ...


def _checked_document(record: _IntegrityChecked) -> dict[str, Any]:
    record.assert_integrity()
    return record.to_document()


def _insert(connection: Connection[Any], sql: str, params: tuple[Any, ...], label: str) -> None:
    try:
        with connection.transaction():
            connection.execute(sql, params)
    except errors.UniqueViolation as exc:
        raise DuplicateRevisionError(f"S6-WCI immutable record already exists: {label}") from exc


def store_disclosure_grant(connection: Connection[Any], record: DisclosureGrant) -> None:
    document = _checked_document(record)
    _insert(
        connection,
        """
        INSERT INTO human_cos_s6_disclosure_grant
            (grant_hash, grant_id, case_id, case_revision, reviewer_id, payload)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            record.grant_hash,
            record.grant_id,
            record.case_id,
            record.case_revision,
            record.reviewer_id,
            Jsonb(document),
        ),
        f"disclosure-grant:{record.grant_id}",
    )


def store_cross_exam_task(connection: Connection[Any], record: CrossExamTask) -> None:
    document = _checked_document(record)
    _insert(
        connection,
        """
        INSERT INTO human_cos_s6_cross_exam_task
            (task_hash, task_id, case_id, case_revision, grant_hash, reviewer_id, payload)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            record.task_hash,
            record.task_id,
            record.case_id,
            record.case_revision,
            record.grant_hash,
            record.reviewer_id,
            Jsonb(document),
        ),
        f"cross-exam-task:{record.task_id}",
    )


def store_cross_exam_response(connection: Connection[Any], record: CrossExamResponse) -> None:
    document = _checked_document(record)
    _insert(
        connection,
        """
        INSERT INTO human_cos_s6_cross_exam_response
            (response_hash, response_id, case_id, case_revision, task_hash,
             grant_hash, reviewer_id, payload)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            record.response_hash,
            record.response_id,
            record.case_id,
            record.case_revision,
            record.task_hash,
            record.grant_hash,
            record.reviewer_id,
            Jsonb(document),
        ),
        f"cross-exam-response:{record.response_id}",
    )


def store_disagreement_node(connection: Connection[Any], record: DisagreementNode) -> None:
    document = _checked_document(record)
    _insert(
        connection,
        """
        INSERT INTO human_cos_s6_disagreement_node
            (node_hash, node_id, case_id, case_revision, conflict_type,
             high_impact, unresolved, payload)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            record.node_hash,
            record.node_id,
            record.case_id,
            record.case_revision,
            record.conflict_type.value,
            record.high_impact,
            record.unresolved,
            Jsonb(document),
        ),
        f"disagreement:{record.node_id}",
    )


def store_actor_state(connection: Connection[Any], record: ActorStateSnapshot) -> None:
    document = _checked_document(record)
    _insert(
        connection,
        """
        INSERT INTO human_cos_s6_actor_state_revision
            (actor_state_id, revision, state_hash, parent_state_hash,
             actor_id, case_id, case_revision, payload)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            record.actor_state_id,
            record.revision,
            record.state_hash,
            record.parent_state_hash,
            record.actor_id,
            record.case_id,
            record.case_revision,
            Jsonb(document),
        ),
        f"actor-state:{record.actor_state_id}@{record.revision}",
    )


def store_causal_graph(connection: Connection[Any], record: CausalGraph) -> None:
    document = _checked_document(record)
    _insert(
        connection,
        """
        INSERT INTO human_cos_s6_causal_graph_revision
            (graph_id, revision, graph_hash, parent_graph_hash,
             case_id, case_revision, payload)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            record.graph_id,
            record.revision,
            record.graph_hash,
            record.parent_graph_hash,
            record.case_id,
            record.case_revision,
            Jsonb(document),
        ),
        f"causal-graph:{record.graph_id}@{record.revision}",
    )


def store_world_state(connection: Connection[Any], record: WorldStateSnapshot) -> None:
    document = _checked_document(record)
    _insert(
        connection,
        """
        INSERT INTO human_cos_s6_world_state_revision
            (world_state_id, revision, world_state_hash, parent_world_state_hash,
             case_id, case_revision, causal_graph_hash, payload)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            record.world_state_id,
            record.revision,
            record.world_state_hash,
            record.parent_world_state_hash,
            record.case_id,
            record.case_revision,
            record.causal_graph_hash,
            Jsonb(document),
        ),
        f"world-state:{record.world_state_id}@{record.revision}",
    )


def store_critical_integration(
    connection: Connection[Any], record: CriticalIntegrationRecord
) -> None:
    document = _checked_document(record)
    _insert(
        connection,
        """
        INSERT INTO human_cos_s6_critical_integration
            (integration_hash, integration_id, case_id, case_revision,
             controller_model_id, world_state_hash, causal_graph_hash, payload)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            record.integration_hash,
            record.integration_id,
            record.case_id,
            record.case_revision,
            record.controller_model_id,
            record.world_state_hash,
            record.causal_graph_hash,
            Jsonb(document),
        ),
        f"critical-integration:{record.integration_id}",
    )


def store_critical_node_detection(
    connection: Connection[Any], record: CriticalNodeDetection
) -> None:
    document = _checked_document(record)
    _insert(
        connection,
        """
        INSERT INTO human_cos_s6_critical_node_detection
            (detection_hash, detection_id, case_id, case_revision,
             integration_hash, payload)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            record.detection_hash,
            record.detection_id,
            record.case_id,
            record.case_revision,
            record.integration_hash,
            Jsonb(document),
        ),
        f"critical-detection:{record.detection_id}",
    )


def store_critical_review_plan(connection: Connection[Any], record: CriticalReviewPlan) -> None:
    document = _checked_document(record)
    _insert(
        connection,
        """
        INSERT INTO human_cos_s6_critical_review_plan
            (plan_hash, plan_id, case_id, case_revision, detection_hash, payload)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            record.plan_hash,
            record.plan_id,
            record.case_id,
            record.case_revision,
            record.detection_hash,
            Jsonb(document),
        ),
        f"critical-review-plan:{record.plan_id}",
    )


def store_critical_review_packet(connection: Connection[Any], record: CriticalReviewPacket) -> None:
    document = _checked_document(record)
    _insert(
        connection,
        """
        INSERT INTO human_cos_s6_critical_review_packet
            (packet_hash, packet_id, case_id, case_revision, detection_hash,
             plan_hash, route_id, reviewer_id, payload)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            record.packet_hash,
            record.packet_id,
            record.case_id,
            record.case_revision,
            record.detection_hash,
            record.plan_hash,
            record.route_id,
            record.reviewer_id,
            Jsonb(document),
        ),
        f"critical-review-packet:{record.packet_id}",
    )


def store_critical_review_evidence(
    connection: Connection[Any], record: CriticalReviewEvidence
) -> None:
    document = _checked_document(record)
    _insert(
        connection,
        """
        INSERT INTO human_cos_s6_critical_review_evidence
            (evidence_hash, evidence_id, case_id, case_revision, detection_hash,
             plan_hash, packet_hash, route_id, reviewer_id, assessment, payload)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            record.evidence_hash,
            record.evidence_id,
            record.case_id,
            record.case_revision,
            record.detection_hash,
            record.plan_hash,
            record.packet_hash,
            record.route_id,
            record.reviewer_id,
            record.assessment.value,
            Jsonb(document),
        ),
        f"critical-review-evidence:{record.evidence_id}",
    )
