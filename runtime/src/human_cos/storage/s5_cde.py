"""Typed append-only PostgreSQL persistence for the authorized S5-CDE slice."""

from __future__ import annotations

from typing import Any, Protocol

from psycopg import Connection, errors
from psycopg.types.json import Jsonb

from human_cos.controllers.framing import FramingRequirement, InitialFramingRecord
from human_cos.controllers.review import FramingReview
from human_cos.domains import DomainOutputRecord, DomainRoute, DomainRoutingPlan, DomainTask
from human_cos.experts import ExpertProfile, ExpertSubmission, ExpertTask
from human_cos.storage.repository import DuplicateRevisionError


class _IntegrityChecked(Protocol):
    def assert_integrity(self) -> None: ...
    def to_document(self) -> dict[str, Any]: ...


def _insert(connection: Connection[Any], sql: str, params: tuple[Any, ...], label: str) -> None:
    try:
        with connection.transaction():
            connection.execute(sql, params)
    except errors.UniqueViolation as exc:
        raise DuplicateRevisionError(f"S5-CDE immutable record already exists: {label}") from exc


def _checked_document(record: _IntegrityChecked) -> dict[str, Any]:
    record.assert_integrity()
    return record.to_document()


def store_framing_requirement(connection: Connection[Any], record: FramingRequirement) -> None:
    document = _checked_document(record)
    _insert(
        connection,
        """
        INSERT INTO human_cos_framing_requirement
            (case_id, case_revision, record_hash, payload)
        VALUES (%s, %s, %s, %s)
        """,
        (record.case_id, record.case_revision, record.record_hash, Jsonb(document)),
        f"framing-requirement:{record.case_id}@{record.case_revision}",
    )


def store_initial_framing(connection: Connection[Any], record: InitialFramingRecord) -> None:
    document = _checked_document(record)
    _insert(
        connection,
        """
        INSERT INTO human_cos_initial_framing
            (case_id, case_revision, lane, run_id, record_hash, payload)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            record.case_id,
            record.case_revision,
            record.lane,
            record.run_id,
            record.record_hash,
            Jsonb(document),
        ),
        f"initial-framing:{record.case_id}@{record.case_revision}:{record.lane}",
    )


def store_framing_review(connection: Connection[Any], record: FramingReview) -> None:
    document = _checked_document(record)
    _insert(
        connection,
        """
        INSERT INTO human_cos_framing_review
            (case_id, case_revision, requirement_hash, a1_record_hash,
             a2_record_hash, review_hash, payload)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            record.case_id,
            record.case_revision,
            record.requirement_hash,
            record.a1_record_hash,
            record.a2_record_hash,
            record.review_hash,
            Jsonb(document),
        ),
        f"framing-review:{record.case_id}@{record.case_revision}",
    )


def store_domain_task(connection: Connection[Any], record: DomainTask) -> None:
    document = _checked_document(record)
    _insert(
        connection,
        """
        INSERT INTO human_cos_domain_task
            (task_hash, task_id, case_id, case_revision, domain_id,
             framing_review_hash, payload)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            record.task_hash,
            record.task_id,
            record.case_id,
            record.case_revision,
            record.domain_id,
            record.framing_review_hash,
            Jsonb(document),
        ),
        f"domain-task:{record.task_id}",
    )


def store_domain_route(connection: Connection[Any], record: DomainRoute) -> None:
    document = _checked_document(record)
    _insert(
        connection,
        """
        INSERT INTO human_cos_domain_route
            (route_hash, task_hash, model_id, payload)
        VALUES (%s, %s, %s, %s)
        """,
        (record.route_hash, record.task_hash, record.model_id, Jsonb(document)),
        f"domain-route:{record.route_hash}",
    )


def store_domain_routing_plan(connection: Connection[Any], record: DomainRoutingPlan) -> None:
    document = _checked_document(record)
    _insert(
        connection,
        """
        INSERT INTO human_cos_domain_routing_plan
            (plan_hash, case_id, case_revision, framing_review_hash,
             routing_complete, payload)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            record.plan_hash,
            record.case_id,
            record.case_revision,
            record.framing_review_hash,
            record.routing_complete,
            Jsonb(document),
        ),
        f"domain-routing-plan:{record.plan_hash}",
    )


def store_domain_output(connection: Connection[Any], record: DomainOutputRecord) -> None:
    document = _checked_document(record)
    _insert(
        connection,
        """
        INSERT INTO human_cos_domain_output
            (record_hash, task_hash, route_hash, run_id, actual_model_id, payload)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            record.record_hash,
            record.task_hash,
            record.route_hash,
            record.run_id,
            record.actual_model_id,
            Jsonb(document),
        ),
        f"domain-output:{record.record_hash}",
    )


def store_expert_profile(connection: Connection[Any], record: ExpertProfile) -> None:
    document = _checked_document(record)
    _insert(
        connection,
        """
        INSERT INTO human_cos_expert_profile_revision
            (expert_id, revision, profile_hash, domain, payload)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            record.expert_id,
            record.revision,
            record.profile_hash,
            record.domain,
            Jsonb(document),
        ),
        f"expert-profile:{record.expert_id}@{record.revision}",
    )


def store_expert_task(connection: Connection[Any], record: ExpertTask) -> None:
    document = _checked_document(record)
    _insert(
        connection,
        """
        INSERT INTO human_cos_expert_task
            (task_hash, task_id, case_id, case_revision, expert_id,
             profile_revision, profile_hash, independent_required, payload)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            record.task_hash,
            record.task_id,
            record.case_id,
            record.case_revision,
            record.expert_id,
            record.profile_revision,
            record.profile_hash,
            record.independent_required,
            Jsonb(document),
        ),
        f"expert-task:{record.task_id}",
    )


def store_expert_submission(connection: Connection[Any], record: ExpertSubmission) -> None:
    document = _checked_document(record)
    _insert(
        connection,
        """
        INSERT INTO human_cos_expert_submission
            (submission_hash, submission_id, task_hash, expert_id,
             profile_revision, actor_type, payload)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            record.submission_hash,
            record.submission_id,
            record.task_hash,
            record.expert_id,
            record.profile_revision,
            record.actor_type,
            Jsonb(document),
        ),
        f"expert-submission:{record.submission_id}",
    )
