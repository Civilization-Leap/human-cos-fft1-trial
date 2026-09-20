"""S5-CDE3 immutable Domain task and output sidecars."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from human_cos.core.models import Case, ContextManifest
from human_cos.models.profile import DomainTaskType
from human_cos.runtime.run import RunManifest, canonical_document_sha256

from .catalog import get_domain_descriptor

if TYPE_CHECKING:
    from .routing import DomainRoute


class DomainContractError(ValueError):
    """A Domain task/output violates its frozen CDE3 contract or lineage."""


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("S5-CDE3 timestamps require timezone-aware datetimes")
    return value


class _FrozenDomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class DomainTaskPayload(_FrozenDomainModel):
    task_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    domain_id: str = Field(min_length=1)
    case_question: str = Field(min_length=1)
    allowed_evidence_ids: tuple[str, ...]
    actor_scope: tuple[str, ...]
    time_boundary: datetime
    assumptions: tuple[str, ...]
    requested_horizon: str = Field(min_length=1)
    domain_task_type: DomainTaskType
    framing_review_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _time_boundary_must_be_aware = field_validator("time_boundary")(_aware)
    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class DomainTask(DomainTaskPayload):
    task_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        get_domain_descriptor(self.domain_id)
        payload = self.model_dump(mode="json", exclude={"task_hash"}, exclude_none=True)
        if self.task_hash != canonical_document_sha256(payload):
            raise DomainContractError("DomainTask task_hash does not match payload")


class DomainOutputContent(_FrozenDomainModel):
    facts_used: tuple[str, ...] = ()
    mechanisms: tuple[str, ...] = ()
    benefit_path: tuple[str, ...] = ()
    harm_path: tuple[str, ...] = ()
    actor_actions: tuple[str, ...] = ()
    first_order_effects: tuple[str, ...] = ()
    second_order_effects: tuple[str, ...] = ()
    third_order_effects: tuple[str, ...] = ()
    feedback_loops: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    capability_gaps: tuple[str, ...] = ()
    critical_node_candidates: tuple[str, ...] = ()
    falsifiers: tuple[str, ...] = ()
    confidence: float | None = Field(default=None, ge=0, le=1)
    calibration_note: str | None = None


class DomainOutputPayload(_FrozenDomainModel):
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    task_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    route_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    domain_id: str = Field(min_length=1)
    domain_task_type: DomainTaskType
    run_id: str = Field(min_length=1)
    context_manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    routed_model_id: str = Field(min_length=1)
    actual_model_id: str = Field(min_length=1)
    fallback_from: str | None = None
    model_family: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    raw_output_ref: str = Field(min_length=1)
    raw_output_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    structured_output_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    protocol_version: str = Field(min_length=1)
    finished_at: datetime
    content: DomainOutputContent

    _finished_at_must_be_aware = field_validator("finished_at")(_aware)


class DomainOutputRecord(DomainOutputPayload):
    record_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        get_domain_descriptor(self.domain_id)
        payload = self.model_dump(mode="json", exclude={"record_hash"}, exclude_none=True)
        if self.record_hash != canonical_document_sha256(payload):
            raise DomainContractError("DomainOutputRecord record_hash does not match payload")
        if self.actual_model_id == self.routed_model_id:
            if self.fallback_from is not None:
                raise DomainContractError(
                    "DomainOutputRecord cannot claim fallback when routed model executed"
                )
        elif self.fallback_from != self.routed_model_id:
            raise DomainContractError(
                "DomainOutputRecord actual model differs without explicit routed-model fallback"
            )


def freeze_domain_task(payload: DomainTaskPayload) -> DomainTask:
    get_domain_descriptor(payload.domain_id)
    document = payload.to_document()
    return DomainTask(**document, task_hash=canonical_document_sha256(document))


def build_domain_task(
    *,
    case: Case,
    task_id: str,
    domain_id: str,
    domain_task_type: DomainTaskType,
    allowed_evidence_ids: tuple[str, ...],
    actor_scope: tuple[str, ...],
    assumptions: tuple[str, ...],
    requested_horizon: str,
    framing_review_hash: str,
    frozen_at: datetime,
) -> DomainTask:
    """Freeze an exact Domain Task Contract bound to Case revision and review."""
    get_domain_descriptor(domain_id)
    if case.domains is not None and domain_id not in case.domains:
        raise DomainContractError("Domain Task is outside the Case domains")
    if len(allowed_evidence_ids) != len(set(allowed_evidence_ids)):
        raise DomainContractError("allowed_evidence_ids must not contain duplicates")
    return freeze_domain_task(
        DomainTaskPayload(
            task_id=task_id,
            case_id=case.case_id,
            case_revision=case.revision,
            domain_id=domain_id,
            case_question=case.question,
            allowed_evidence_ids=allowed_evidence_ids,
            actor_scope=actor_scope,
            time_boundary=case.time_boundary.T0,
            assumptions=assumptions,
            requested_horizon=requested_horizon,
            domain_task_type=domain_task_type,
            framing_review_hash=framing_review_hash,
            protocol_version=case.protocol_version,
            frozen_at=frozen_at,
        )
    )


def freeze_domain_output_payload(payload: DomainOutputPayload) -> DomainOutputRecord:
    get_domain_descriptor(payload.domain_id)
    document = payload.to_document()
    return DomainOutputRecord(**document, record_hash=canonical_document_sha256(document))


def bind_domain_output(
    *,
    task: DomainTask,
    route: DomainRoute,
    content: DomainOutputContent,
    frozen_run: RunManifest,
    context_manifest: ContextManifest,
) -> DomainOutputRecord:
    """Bind structured Domain output to one exact route and frozen trusted worker run."""
    from .routing import assert_domain_route_binding

    task.assert_integrity()
    assert_domain_route_binding(task=task, route=route)
    if frozen_run.case_id != task.case_id:
        raise DomainContractError("Domain Run Case does not match task")
    if frozen_run.protocol_version != task.protocol_version:
        raise DomainContractError("Domain Run protocol version does not match task")
    if frozen_run.stage != "DOMAIN_INDEPENDENT_RUN":
        raise DomainContractError("Domain output requires DOMAIN_INDEPENDENT_RUN")
    if frozen_run.role_type != "domain_worker" or frozen_run.status != "FROZEN":
        raise DomainContractError("Domain output requires a frozen domain_worker Run")
    if (
        frozen_run.raw_output_ref is None
        or frozen_run.raw_output_hash is None
        or frozen_run.structured_output_hash is None
        or frozen_run.finished_at is None
    ):
        raise DomainContractError("frozen Domain Run is missing output lineage")
    if context_manifest.case_id != task.case_id or context_manifest.run_id != frozen_run.run_id:
        raise DomainContractError("Context Manifest does not bind the same Domain Case/Run")
    if context_manifest.stage != "DOMAIN_INDEPENDENT_RUN":
        raise DomainContractError("Context Manifest is not a Domain independent-run context")
    if context_manifest.hash_sha256 != frozen_run.context_manifest_hash:
        raise DomainContractError("Context hash does not match frozen Domain Run")
    if context_manifest.prior_run_ids:
        raise DomainContractError("independent Domain worker cannot see prior worker runs")
    if any(item not in task.allowed_evidence_ids for item in context_manifest.evidence_ids):
        raise DomainContractError("Domain Context includes Evidence outside task allowlist")
    if any(item not in task.allowed_evidence_ids for item in content.facts_used):
        raise DomainContractError("Domain facts_used includes Evidence outside task allowlist")
    if frozen_run.model_id != route.model_id and frozen_run.fallback_from != route.model_id:
        raise DomainContractError(
            "Domain Run identity is not the routed model or explicit fallback"
        )

    return freeze_domain_output_payload(
        DomainOutputPayload(
            case_id=task.case_id,
            case_revision=task.case_revision,
            task_hash=task.task_hash,
            route_hash=route.route_hash,
            domain_id=task.domain_id,
            domain_task_type=task.domain_task_type,
            run_id=frozen_run.run_id,
            context_manifest_hash=frozen_run.context_manifest_hash,
            routed_model_id=route.model_id,
            actual_model_id=frozen_run.model_id,
            fallback_from=frozen_run.fallback_from,
            model_family=frozen_run.model_family,
            provider=frozen_run.provider,
            raw_output_ref=frozen_run.raw_output_ref,
            raw_output_hash=frozen_run.raw_output_hash,
            structured_output_hash=frozen_run.structured_output_hash,
            protocol_version=frozen_run.protocol_version,
            finished_at=frozen_run.finished_at,
            content=content,
        )
    )
