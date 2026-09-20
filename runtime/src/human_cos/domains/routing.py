"""S5-CDE3 qualification-aware Domain routing and trusted execution wrapper."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from human_cos.core.context import AdmittedEvidence, ContextAdmissionRecord
from human_cos.core.models import Case, Evidence
from human_cos.models import (
    EligibilityRequirement,
    ModelAdapter,
    ModelRegistry,
    QualificationGate,
)
from human_cos.models.profile import DomainTaskType
from human_cos.models.qualification import CapabilityGap
from human_cos.runtime.run import (
    AuditEvent,
    RawOutputRecord,
    RunManifest,
    canonical_document_sha256,
)
from human_cos.runtime.scheduler import (
    ScheduledRunResult,
    SchedulerRepository,
    TrustedScheduler,
    WorkerTask,
)
from human_cos.runtime.state_machine import CaseRuntimePosition, RuntimeState
from human_cos.runtime.tool_policy import ToolPolicy

from .contracts import DomainContractError, DomainOutputRecord, DomainTask


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("S5-CDE3 routing timestamps require timezone-aware datetimes")
    return value


class _FrozenRoutingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class DomainRoutePayload(_FrozenRoutingModel):
    task_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    domain_id: str = Field(min_length=1)
    domain_task_type: DomainTaskType
    model_id: str = Field(min_length=1)
    qualification_reason: str = Field(min_length=1)
    protocol_version: str = Field(min_length=1)
    routed_at: datetime

    _routed_at_must_be_aware = field_validator("routed_at")(_aware)


class DomainRoute(DomainRoutePayload):
    route_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"route_hash"}, exclude_none=True)
        if self.route_hash != canonical_document_sha256(payload):
            raise DomainContractError("DomainRoute route_hash does not match payload")


@dataclass(frozen=True)
class DomainRouteDecision:
    task_hash: str
    allowed: bool
    reason: str
    route: DomainRoute | None = None
    capability_gap: CapabilityGap | None = None


class DomainRoutingEntry(_FrozenRoutingModel):
    task_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    route_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    capability_gap_id: str | None = None

    @model_validator(mode="after")
    def _exactly_one_outcome(self) -> DomainRoutingEntry:
        if (self.route_hash is None) == (self.capability_gap_id is None):
            raise ValueError("DomainRoutingEntry requires exactly one route or Capability Gap")
        return self


class DomainRoutingPlanPayload(_FrozenRoutingModel):
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    framing_review_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    protocol_version: str = Field(min_length=1)
    entries: tuple[DomainRoutingEntry, ...]
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class DomainRoutingPlan(DomainRoutingPlanPayload):
    plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @property
    def routing_complete(self) -> bool:
        return bool(self.entries) and all(item.route_hash is not None for item in self.entries)

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"plan_hash"}, exclude_none=True)
        if self.plan_hash != canonical_document_sha256(payload):
            raise DomainContractError("DomainRoutingPlan plan_hash does not match payload")


def _freeze_route(payload: DomainRoutePayload) -> DomainRoute:
    document = payload.to_document()
    return DomainRoute(**document, route_hash=canonical_document_sha256(document))


def route_domain_task(
    *,
    task: DomainTask,
    model_id: str,
    qualification: QualificationGate,
    routed_at: datetime,
) -> DomainRouteDecision:
    """Route only an explicitly qualified domain/task pair; preserve Capability Gap otherwise."""
    task.assert_integrity()
    decision = qualification.domain_decision(model_id, task.domain_id, task.domain_task_type)
    if not decision.allowed:
        gap = qualification.capability_gap(model_id, task.domain_id, task.domain_task_type)
        return DomainRouteDecision(
            task_hash=task.task_hash,
            allowed=False,
            reason=decision.reason,
            capability_gap=gap,
        )
    route = _freeze_route(
        DomainRoutePayload(
            task_hash=task.task_hash,
            case_id=task.case_id,
            case_revision=task.case_revision,
            domain_id=task.domain_id,
            domain_task_type=task.domain_task_type,
            model_id=model_id,
            qualification_reason=decision.reason,
            protocol_version=task.protocol_version,
            routed_at=routed_at,
        )
    )
    return DomainRouteDecision(
        task_hash=task.task_hash,
        allowed=True,
        reason=decision.reason,
        route=route,
    )


def assert_domain_route_binding(*, task: DomainTask, route: DomainRoute) -> None:
    task.assert_integrity()
    route.assert_integrity()
    if (
        route.task_hash,
        route.case_id,
        route.case_revision,
        route.domain_id,
        route.domain_task_type,
        route.protocol_version,
    ) != (
        task.task_hash,
        task.case_id,
        task.case_revision,
        task.domain_id,
        task.domain_task_type,
        task.protocol_version,
    ):
        raise DomainContractError("DomainRoute does not bind the exact DomainTask")


def build_domain_routing_plan(
    *,
    tasks: tuple[DomainTask, ...],
    decisions: tuple[DomainRouteDecision, ...],
    framing_review_hash: str,
    frozen_at: datetime,
) -> DomainRoutingPlan:
    if not tasks or len(tasks) != len(decisions):
        raise DomainContractError("Domain routing requires one decision per non-empty task set")
    for task in tasks:
        task.assert_integrity()
    if len({task.task_hash for task in tasks}) != len(tasks):
        raise DomainContractError("Domain routing tasks must have unique task_hash values")

    entries: list[DomainRoutingEntry] = []
    for task, decision in zip(tasks, decisions, strict=True):
        if decision.task_hash != task.task_hash:
            raise DomainContractError("Domain routing decision order/binding does not match task")
        if decision.allowed:
            if decision.route is None or decision.capability_gap is not None:
                raise DomainContractError("allowed Domain route decision is malformed")
            assert_domain_route_binding(task=task, route=decision.route)
            entries.append(
                DomainRoutingEntry(task_hash=task.task_hash, route_hash=decision.route.route_hash)
            )
        else:
            if decision.route is not None or decision.capability_gap is None:
                raise DomainContractError("blocked Domain route must preserve Capability Gap")
            entries.append(
                DomainRoutingEntry(
                    task_hash=task.task_hash,
                    capability_gap_id=decision.capability_gap.capability_gap_id,
                )
            )

    first = tasks[0]
    if any(
        (task.case_id, task.case_revision, task.protocol_version, task.framing_review_hash)
        != (first.case_id, first.case_revision, first.protocol_version, framing_review_hash)
        for task in tasks
    ):
        raise DomainContractError("Domain tasks do not share one Case/review/protocol binding")
    payload = DomainRoutingPlanPayload(
        case_id=first.case_id,
        case_revision=first.case_revision,
        framing_review_hash=framing_review_hash,
        protocol_version=first.protocol_version,
        entries=tuple(entries),
        frozen_at=frozen_at,
    )
    document = payload.to_document()
    return DomainRoutingPlan(**document, plan_hash=canonical_document_sha256(document))


def assert_domain_routing_plan_binding(
    *,
    plan: DomainRoutingPlan,
    tasks: tuple[DomainTask, ...],
    routes: tuple[DomainRoute, ...],
    framing_review_hash: str,
) -> None:
    plan.assert_integrity()
    if plan.framing_review_hash != framing_review_hash:
        raise DomainContractError("DomainRoutingPlan does not bind the supplied FramingReview")
    task_by_hash = {task.task_hash: task for task in tasks}
    if len(task_by_hash) != len(tasks) or set(task_by_hash) != {
        item.task_hash for item in plan.entries
    }:
        raise DomainContractError("DomainRoutingPlan task set does not match supplied tasks")
    route_by_hash = {route.route_hash: route for route in routes}
    expected_route_hashes = {
        item.route_hash for item in plan.entries if item.route_hash is not None
    }
    if len(route_by_hash) != len(routes) or set(route_by_hash) != expected_route_hashes:
        raise DomainContractError("DomainRoutingPlan route set does not match supplied routes")
    for entry in plan.entries:
        task = task_by_hash[entry.task_hash]
        task.assert_integrity()
        if entry.route_hash is not None:
            assert_domain_route_binding(task=task, route=route_by_hash[entry.route_hash])


def assert_domain_output_set(
    *,
    plan: DomainRoutingPlan,
    tasks: tuple[DomainTask, ...],
    routes: tuple[DomainRoute, ...],
    outputs: tuple[DomainOutputRecord, ...],
) -> None:
    assert_domain_routing_plan_binding(
        plan=plan,
        tasks=tasks,
        routes=routes,
        framing_review_hash=plan.framing_review_hash,
    )
    if not plan.routing_complete:
        raise DomainContractError("Capability Gap prevents complete Domain output set")
    task_by_hash = {task.task_hash: task for task in tasks}
    route_by_hash = {route.route_hash: route for route in routes}
    expected = {(route.task_hash, route.route_hash) for route in routes}
    actual: set[tuple[str, str]] = set()
    for output in outputs:
        output.assert_integrity()
        if (
            output.case_id,
            output.case_revision,
            output.protocol_version,
        ) != (plan.case_id, plan.case_revision, plan.protocol_version):
            raise DomainContractError(
                "Domain output Case/protocol binding differs from routing plan"
            )
        task = task_by_hash.get(output.task_hash)
        route = route_by_hash.get(output.route_hash)
        if task is None or route is None:
            raise DomainContractError("Domain output does not bind a required task/route")
        if (output.domain_id, output.domain_task_type) != (
            task.domain_id,
            task.domain_task_type,
        ):
            raise DomainContractError("Domain output domain/task type differs from DomainTask")
        if (
            output.domain_id,
            output.domain_task_type,
            output.routed_model_id,
        ) != (route.domain_id, route.domain_task_type, route.model_id):
            raise DomainContractError("Domain output lineage differs from immutable DomainRoute")
        actual.add((output.task_hash, output.route_hash))
    if len(actual) != len(outputs) or actual != expected:
        raise DomainContractError(
            "Domain outputs do not cover each required routed task exactly once"
        )


class _AllowedEvidenceRepository:
    """Narrow scheduler candidates to task allowlist; Context Builder still re-checks T0/ACL."""

    def __init__(self, delegate: SchedulerRepository, allowed_ids: tuple[str, ...]) -> None:
        self._delegate = delegate
        self._allowed = frozenset(allowed_ids)

    def list_context_evidence(
        self,
        case: Case,
        *,
        actor_id: str | None,
        role_id: str | None,
        as_of: datetime,
    ) -> Sequence[AdmittedEvidence]:
        return tuple(
            item
            for item in self._delegate.list_context_evidence(
                case,
                actor_id=actor_id,
                role_id=role_id,
                as_of=as_of,
            )
            if item.evidence.evidence_id in self._allowed
        )

    def get_evidence(self, evidence_id: str, revision: int | None = None) -> tuple[Evidence, int]:
        return cast(tuple[Evidence, int], self._delegate.get_evidence(evidence_id, revision))

    def store_context_admission(self, record: ContextAdmissionRecord) -> None:
        self._delegate.store_context_admission(record)

    def append_run_manifest(self, document: dict[str, Any]) -> tuple[RunManifest, int, str]:
        return cast(
            tuple[RunManifest, int, str],
            self._delegate.append_run_manifest(document),
        )

    def store_raw_output(
        self,
        *,
        run_id: str,
        output_ref: str,
        content: str | bytes,
    ) -> RawOutputRecord:
        return self._delegate.store_raw_output(
            run_id=run_id, output_ref=output_ref, content=content
        )

    def store_audit_event(self, document: dict[str, Any]) -> tuple[AuditEvent, str]:
        return cast(tuple[AuditEvent, str], self._delegate.store_audit_event(document))


def run_qualified_domain_task(
    *,
    repository: SchedulerRepository,
    registry: ModelRegistry,
    qualification: QualificationGate,
    tool_policy: ToolPolicy,
    case: Case,
    position: CaseRuntimePosition,
    task: DomainTask,
    route: DomainRoute,
    run_id: str,
    context_manifest_id: str,
    role_id: str,
    prompt_version: str,
    adapter: ModelAdapter,
    fallback_adapter: ModelAdapter | None = None,
    requested_tools: tuple[str, ...] = (),
    forbidden_scopes: tuple[str, ...] = (),
    actor_id: str | None = None,
    reference_time: datetime | None = None,
    max_output_tokens: int = 1024,
) -> ScheduledRunResult:
    """Execute one routed Domain task through the existing trusted scheduler pipeline."""
    if position.state is not RuntimeState.DOMAIN_INDEPENDENT_RUN:
        raise DomainContractError("routed Domain execution requires DOMAIN_INDEPENDENT_RUN")
    assert_domain_route_binding(task=task, route=route)
    if (case.case_id, case.revision, case.protocol_version) != (
        task.case_id,
        task.case_revision,
        task.protocol_version,
    ):
        raise DomainContractError("DomainTask does not bind the execution Case revision/protocol")

    source = _AllowedEvidenceRepository(repository, task.allowed_evidence_ids)
    scheduler = TrustedScheduler(
        repository=source,
        registry=registry,
        qualification=qualification,
        tool_policy=tool_policy,
    )
    contract_json = json.dumps(task.to_document(), ensure_ascii=False, sort_keys=True)
    result = scheduler.run(
        case=case,
        position=position,
        task=WorkerTask(
            run_id=run_id,
            context_manifest_id=context_manifest_id,
            role_id=role_id,
            model_id=route.model_id,
            prompt_version=prompt_version,
            input_text=(
                "DOMAIN_TASK_CONTRACT_JSON (frozen task data; do not expand Evidence scope):\n"
                + contract_json
            ),
            requirement=EligibilityRequirement(
                role="domain_worker",
                domain=task.domain_id,
                task_type=task.domain_task_type,
            ),
            requested_tools=requested_tools,
            prior_run_ids=(),
            forbidden_scopes=forbidden_scopes,
            actor_id=actor_id,
            reference_time=reference_time,
            max_output_tokens=max_output_tokens,
        ),
        adapter=adapter,
        fallback_adapter=fallback_adapter,
    )
    if any(item not in task.allowed_evidence_ids for item in result.context.manifest.evidence_ids):
        raise DomainContractError("trusted Domain Context escaped the task Evidence allowlist")
    return result
