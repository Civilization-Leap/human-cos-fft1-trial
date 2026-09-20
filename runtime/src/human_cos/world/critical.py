"""S6-WCI4 Critical Node detection and independent review routing/evidence."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from human_cos.experts import ExpertTask
from human_cos.models import QualificationGate
from human_cos.models.profile import DomainTaskType
from human_cos.runtime.run import canonical_document_sha256
from human_cos.runtime.state_machine import (
    CaseMode,
    CaseRuntimePosition,
    GuardCheck,
    GuardStatus,
    RuntimeState,
    TransitionDecision,
    TransitionKey,
    TransitionStatus,
    can_transition,
)

from .causal import CausalGraph
from .state import ProvenanceRef, WorldStateSnapshot

if TYPE_CHECKING:
    from human_cos.controllers.critical_integration import CriticalIntegrationRecord


class CriticalNodeContractError(ValueError):
    """Critical Node detection/review data violates the authorized WCI4 boundary."""


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("S6-WCI4 timestamps require timezone-aware datetimes")
    return value


class ReviewRouteKind(str, Enum):
    CROSS_FAMILY_CONTROLLER = "CROSS_FAMILY_CONTROLLER"
    DOMAIN = "DOMAIN"
    EXPERT = "EXPERT"
    CHALLENGER = "CHALLENGER"


class ReviewRouteStatus(str, Enum):
    READY = "READY"
    CAPABILITY_GAP = "CAPABILITY_GAP"
    PENDING_S7 = "PENDING_S7"


class CriticalReviewAssessment(str, Enum):
    SUPPORTS = "SUPPORTS"
    CHALLENGES = "CHALLENGES"
    UNCERTAIN = "UNCERTAIN"


class DomainReviewRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    domain: str = Field(min_length=1)
    task_type: DomainTaskType


class DomainReviewerAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    domain: str = Field(min_length=1)
    task_type: DomainTaskType
    model_id: str = Field(min_length=1)


class CriticalNodeDetectionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    detection_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    integration_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    origin_controller_model_id: str = Field(min_length=1)
    origin_controller_model_family: str = Field(min_length=1)
    world_state_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    causal_graph_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    dissent_node_hashes: tuple[str, ...]
    candidate_refs: tuple[str, ...]
    cross_family_review_required: bool
    domain_review_requirements: tuple[DomainReviewRequirement, ...] = ()
    expert_review_required: bool
    challenger_review_required: bool
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class CriticalNodeDetection(CriticalNodeDetectionPayload):
    detection_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"detection_hash"}, exclude_none=True)
        if self.detection_hash != canonical_document_sha256(payload):
            raise CriticalNodeContractError("CriticalNodeDetection hash does not match payload")
        if not self.candidate_refs:
            raise CriticalNodeContractError("CriticalNodeDetection requires at least one candidate")
        if len(self.candidate_refs) != len(set(self.candidate_refs)):
            raise CriticalNodeContractError("CriticalNodeDetection candidate refs must be unique")
        if len(self.dissent_node_hashes) != len(set(self.dissent_node_hashes)):
            raise CriticalNodeContractError("CriticalNodeDetection dissent refs must be unique")


class CriticalReviewRoute(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    route_id: str = Field(min_length=1)
    kind: ReviewRouteKind
    status: ReviewRouteStatus
    reviewer_id: str | None = None
    model_family: str | None = None
    domain: str | None = None
    task_type: DomainTaskType | None = None
    expert_task_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    reason: str = Field(min_length=1)


class CriticalReviewPlanPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    detection_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    routes: tuple[CriticalReviewRoute, ...]
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class CriticalReviewPlan(CriticalReviewPlanPayload):
    plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"plan_hash"}, exclude_none=True)
        if self.plan_hash != canonical_document_sha256(payload):
            raise CriticalNodeContractError("CriticalReviewPlan hash does not match payload")
        route_ids = tuple(route.route_id for route in self.routes)
        if not route_ids or len(route_ids) != len(set(route_ids)):
            raise CriticalNodeContractError(
                "CriticalReviewPlan route IDs must be non-empty and unique"
            )
        for route in self.routes:
            if route.status is ReviewRouteStatus.READY and route.reviewer_id is None:
                raise CriticalNodeContractError("READY review route requires reviewer_id")
            if route.kind is ReviewRouteKind.CHALLENGER:
                if route.status is not ReviewRouteStatus.PENDING_S7:
                    raise CriticalNodeContractError(
                        "Challenger route must remain PENDING_S7 in WCI4"
                    )


class CriticalReviewPacketPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    packet_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    detection_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    route_id: str = Field(min_length=1)
    reviewer_id: str = Field(min_length=1)
    visible_materials: tuple[ProvenanceRef, ...]
    prior_review_evidence_hashes: tuple[str, ...] = ()
    independent_required: bool = True
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class CriticalReviewPacket(CriticalReviewPacketPayload):
    packet_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"packet_hash"}, exclude_none=True)
        if self.packet_hash != canonical_document_sha256(payload):
            raise CriticalNodeContractError("CriticalReviewPacket hash does not match payload")
        if not self.visible_materials:
            raise CriticalNodeContractError("CriticalReviewPacket requires visible materials")
        if self.independent_required and self.prior_review_evidence_hashes:
            raise CriticalNodeContractError(
                "independent Critical Node reviewer cannot see other review answers before freeze"
            )


class CriticalReviewEvidencePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    detection_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    packet_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    route_id: str = Field(min_length=1)
    reviewer_id: str = Field(min_length=1)
    assessment: CriticalReviewAssessment
    rationale: str = Field(min_length=1)
    source_refs: tuple[ProvenanceRef, ...]
    protocol_version: str = Field(min_length=1)
    submitted_at: datetime
    frozen_at: datetime

    _submitted_at_must_be_aware = field_validator("submitted_at")(_aware)
    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class CriticalReviewEvidence(CriticalReviewEvidencePayload):
    evidence_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"evidence_hash"}, exclude_none=True)
        if self.evidence_hash != canonical_document_sha256(payload):
            raise CriticalNodeContractError("CriticalReviewEvidence hash does not match payload")
        if not self.source_refs:
            raise CriticalNodeContractError("CriticalReviewEvidence requires source refs")
        if self.frozen_at < self.submitted_at:
            raise CriticalNodeContractError(
                "CriticalReviewEvidence cannot freeze before submission"
            )


def build_critical_node_detection(
    *,
    integration: CriticalIntegrationRecord,
    world_state: WorldStateSnapshot,
    causal_graph: CausalGraph,
    detection_id: str,
    candidate_refs: tuple[str, ...],
    cross_family_review_required: bool,
    domain_review_requirements: tuple[DomainReviewRequirement, ...],
    expert_review_required: bool,
    challenger_review_required: bool,
    frozen_at: datetime,
) -> CriticalNodeDetection:
    integration.assert_integrity()
    world_state.assert_integrity()
    causal_graph.assert_integrity()
    if (
        world_state.world_state_hash != integration.world_state_hash
        or causal_graph.graph_hash != integration.causal_graph_hash
    ):
        raise CriticalNodeContractError(
            "Critical Node detection source hashes do not match integration"
        )
    if (world_state.case_id, world_state.case_revision, world_state.protocol_version) != (
        integration.case_id,
        integration.case_revision,
        integration.protocol_version,
    ):
        raise CriticalNodeContractError("Critical Node detection WorldState binding mismatch")
    if not set(candidate_refs).issubset(set(integration.content.critical_node_candidate_refs)):
        raise CriticalNodeContractError("detection candidate was not emitted by Controller B")
    if not set(integration.disagreement_node_hashes).issubset(set(world_state.dissent_node_hashes)):
        raise CriticalNodeContractError("Critical Node detection lost disagreement lineage")

    payload = CriticalNodeDetectionPayload(
        detection_id=detection_id,
        case_id=integration.case_id,
        case_revision=integration.case_revision,
        integration_hash=integration.integration_hash,
        origin_controller_model_id=integration.controller_model_id,
        origin_controller_model_family=integration.controller_model_family,
        world_state_hash=integration.world_state_hash,
        causal_graph_hash=integration.causal_graph_hash,
        dissent_node_hashes=integration.disagreement_node_hashes,
        candidate_refs=candidate_refs,
        cross_family_review_required=cross_family_review_required,
        domain_review_requirements=domain_review_requirements,
        expert_review_required=expert_review_required,
        challenger_review_required=challenger_review_required,
        protocol_version=integration.protocol_version,
        frozen_at=frozen_at,
    )
    document = payload.to_document()
    detection = CriticalNodeDetection(
        **document,
        detection_hash=canonical_document_sha256(document),
    )
    detection.assert_integrity()
    return detection


def _cross_family_route(
    *,
    detection: CriticalNodeDetection,
    qualification: QualificationGate,
    model_id: str | None,
) -> CriticalReviewRoute:
    route_id = "cross-family-controller"
    if model_id is None:
        return CriticalReviewRoute(
            route_id=route_id,
            kind=ReviewRouteKind.CROSS_FAMILY_CONTROLLER,
            status=ReviewRouteStatus.CAPABILITY_GAP,
            reason="required cross-family Controller reviewer is unassigned",
        )
    decision = qualification.controller_decision(model_id)
    if not decision.allowed:
        return CriticalReviewRoute(
            route_id=route_id,
            kind=ReviewRouteKind.CROSS_FAMILY_CONTROLLER,
            status=ReviewRouteStatus.CAPABILITY_GAP,
            reviewer_id=model_id,
            reason=decision.reason,
        )
    profile = qualification.assert_controller_eligible(model_id)
    if profile.model_family == detection.origin_controller_model_family:
        return CriticalReviewRoute(
            route_id=route_id,
            kind=ReviewRouteKind.CROSS_FAMILY_CONTROLLER,
            status=ReviewRouteStatus.CAPABILITY_GAP,
            reviewer_id=model_id,
            model_family=profile.model_family,
            reason="reviewer is qualified but not cross-family independent",
        )
    return CriticalReviewRoute(
        route_id=route_id,
        kind=ReviewRouteKind.CROSS_FAMILY_CONTROLLER,
        status=ReviewRouteStatus.READY,
        reviewer_id=model_id,
        model_family=profile.model_family,
        reason="qualified cross-family Controller reviewer assigned",
    )


def _domain_routes(
    *,
    detection: CriticalNodeDetection,
    qualification: QualificationGate,
    assignments: tuple[DomainReviewerAssignment, ...],
) -> tuple[CriticalReviewRoute, ...]:
    assignment_map = {(item.domain, item.task_type): item for item in assignments}
    if len(assignment_map) != len(assignments):
        raise CriticalNodeContractError("duplicate Domain reviewer assignments are not allowed")
    routes: list[CriticalReviewRoute] = []
    for index, requirement in enumerate(detection.domain_review_requirements, start=1):
        key = (requirement.domain, requirement.task_type)
        assignment = assignment_map.get(key)
        route_id = f"domain-{index}-{requirement.domain}-{requirement.task_type}"
        if assignment is None:
            routes.append(
                CriticalReviewRoute(
                    route_id=route_id,
                    kind=ReviewRouteKind.DOMAIN,
                    status=ReviewRouteStatus.CAPABILITY_GAP,
                    domain=requirement.domain,
                    task_type=requirement.task_type,
                    reason="required professional Domain reviewer is unassigned",
                )
            )
            continue
        decision = qualification.domain_decision(
            assignment.model_id,
            requirement.domain,
            requirement.task_type,
        )
        profile = (
            qualification.assert_domain_eligible(
                assignment.model_id,
                requirement.domain,
                requirement.task_type,
            )
            if decision.allowed
            else None
        )
        routes.append(
            CriticalReviewRoute(
                route_id=route_id,
                kind=ReviewRouteKind.DOMAIN,
                status=(
                    ReviewRouteStatus.READY
                    if decision.allowed
                    else ReviewRouteStatus.CAPABILITY_GAP
                ),
                reviewer_id=assignment.model_id,
                model_family=profile.model_family if profile is not None else None,
                domain=requirement.domain,
                task_type=requirement.task_type,
                reason=decision.reason,
            )
        )
    return tuple(routes)


def build_critical_review_plan(
    *,
    detection: CriticalNodeDetection,
    qualification: QualificationGate,
    plan_id: str,
    cross_family_controller_model_id: str | None,
    domain_reviewer_assignments: tuple[DomainReviewerAssignment, ...],
    expert_task: ExpertTask | None,
    frozen_at: datetime,
) -> CriticalReviewPlan:
    """Route reviews without fabricating missing capability or S7 Challenger completion."""
    detection.assert_integrity()
    routes: list[CriticalReviewRoute] = []
    if detection.cross_family_review_required:
        routes.append(
            _cross_family_route(
                detection=detection,
                qualification=qualification,
                model_id=cross_family_controller_model_id,
            )
        )
    routes.extend(
        _domain_routes(
            detection=detection,
            qualification=qualification,
            assignments=domain_reviewer_assignments,
        )
    )
    if detection.expert_review_required:
        if expert_task is None:
            routes.append(
                CriticalReviewRoute(
                    route_id="expert-review",
                    kind=ReviewRouteKind.EXPERT,
                    status=ReviewRouteStatus.CAPABILITY_GAP,
                    reason="required Human Expert task is not available",
                )
            )
        else:
            expert_task.assert_integrity()
            if (expert_task.case_id, expert_task.case_revision, expert_task.protocol_version) != (
                detection.case_id,
                detection.case_revision,
                detection.protocol_version,
            ):
                raise CriticalNodeContractError("Expert Task Case/revision/protocol mismatch")
            routes.append(
                CriticalReviewRoute(
                    route_id="expert-review",
                    kind=ReviewRouteKind.EXPERT,
                    status=ReviewRouteStatus.READY,
                    reviewer_id=expert_task.expert_id,
                    expert_task_hash=expert_task.task_hash,
                    reason="independent Human Expert task is bound",
                )
            )
    if detection.challenger_review_required:
        routes.append(
            CriticalReviewRoute(
                route_id="challenger-review",
                kind=ReviewRouteKind.CHALLENGER,
                status=ReviewRouteStatus.PENDING_S7,
                reason="Challenger review is required by escalation but remains S7-owned",
            )
        )
    if not routes:
        raise CriticalNodeContractError("CriticalReviewPlan requires at least one review route")

    payload = CriticalReviewPlanPayload(
        plan_id=plan_id,
        case_id=detection.case_id,
        case_revision=detection.case_revision,
        detection_hash=detection.detection_hash,
        routes=tuple(routes),
        protocol_version=detection.protocol_version,
        frozen_at=frozen_at,
    )
    document = payload.to_document()
    plan = CriticalReviewPlan(**document, plan_hash=canonical_document_sha256(document))
    plan.assert_integrity()
    return plan


def build_critical_review_packet(
    *,
    detection: CriticalNodeDetection,
    plan: CriticalReviewPlan,
    route_id: str,
    packet_id: str,
    visible_materials: tuple[ProvenanceRef, ...],
    frozen_at: datetime,
    prior_review_evidence_hashes: tuple[str, ...] = (),
) -> CriticalReviewPacket:
    detection.assert_integrity()
    plan.assert_integrity()
    if plan.detection_hash != detection.detection_hash:
        raise CriticalNodeContractError("CriticalReviewPlan does not bind detection")
    matches = tuple(route for route in plan.routes if route.route_id == route_id)
    if len(matches) != 1:
        raise CriticalNodeContractError("review route does not exist exactly once")
    route = matches[0]
    if route.status is not ReviewRouteStatus.READY or route.reviewer_id is None:
        raise CriticalNodeContractError("review packet cannot be issued for a non-READY route")
    if prior_review_evidence_hashes:
        raise CriticalNodeContractError(
            "independent Critical Node reviewer cannot receive prior review answers"
        )
    payload = CriticalReviewPacketPayload(
        packet_id=packet_id,
        case_id=detection.case_id,
        case_revision=detection.case_revision,
        detection_hash=detection.detection_hash,
        plan_hash=plan.plan_hash,
        route_id=route.route_id,
        reviewer_id=route.reviewer_id,
        visible_materials=visible_materials,
        prior_review_evidence_hashes=prior_review_evidence_hashes,
        independent_required=True,
        protocol_version=detection.protocol_version,
        frozen_at=frozen_at,
    )
    document = payload.to_document()
    packet = CriticalReviewPacket(**document, packet_hash=canonical_document_sha256(document))
    packet.assert_integrity()
    return packet


def freeze_critical_review_evidence(
    *,
    detection: CriticalNodeDetection,
    plan: CriticalReviewPlan,
    packet: CriticalReviewPacket,
    evidence_id: str,
    assessment: CriticalReviewAssessment,
    rationale: str,
    source_refs: tuple[ProvenanceRef, ...],
    submitted_at: datetime,
    frozen_at: datetime,
) -> CriticalReviewEvidence:
    detection.assert_integrity()
    plan.assert_integrity()
    packet.assert_integrity()
    if (
        packet.detection_hash,
        packet.plan_hash,
        packet.case_id,
        packet.case_revision,
        packet.protocol_version,
    ) != (
        detection.detection_hash,
        plan.plan_hash,
        detection.case_id,
        detection.case_revision,
        detection.protocol_version,
    ):
        raise CriticalNodeContractError("Critical review packet lineage does not match")
    payload = CriticalReviewEvidencePayload(
        evidence_id=evidence_id,
        case_id=detection.case_id,
        case_revision=detection.case_revision,
        detection_hash=detection.detection_hash,
        plan_hash=plan.plan_hash,
        packet_hash=packet.packet_hash,
        route_id=packet.route_id,
        reviewer_id=packet.reviewer_id,
        assessment=assessment,
        rationale=rationale,
        source_refs=source_refs,
        protocol_version=detection.protocol_version,
        submitted_at=submitted_at,
        frozen_at=frozen_at,
    )
    document = payload.to_document()
    evidence = CriticalReviewEvidence(
        **document,
        evidence_hash=canonical_document_sha256(document),
    )
    evidence.assert_integrity()
    return evidence


_S6_COMMON_MODES = (
    CaseMode.LIVE_FORESIGHT,
    CaseMode.MECHANISM_BENCHMARK,
    CaseMode.SCENARIO_STRESS_TEST,
)

S6_WCI4_TRANSITIONS: frozenset[TransitionKey] = frozenset(
    TransitionKey(
        mode,
        RuntimeState.CRITICAL_NODE_DETECTION,
        RuntimeState.CRITICAL_NODE_REVIEW,
    )
    for mode in _S6_COMMON_MODES
)


def _guard(name: str, passed: bool | None, reason: str) -> GuardCheck:
    if passed is None:
        return GuardCheck(name, GuardStatus.UNAVAILABLE, reason)
    if passed:
        return GuardCheck(name, GuardStatus.PASS, reason)
    return GuardCheck(name, GuardStatus.FAIL, reason)


def _with_guard(base: TransitionDecision, guard: GuardCheck) -> TransitionDecision:
    if guard.status is GuardStatus.PASS:
        return base
    status = (
        TransitionStatus.GUARD_UNAVAILABLE
        if guard.status is GuardStatus.UNAVAILABLE
        else TransitionStatus.GUARD_FAILED
    )
    return TransitionDecision(
        allowed=False,
        status=status,
        mode=base.mode,
        source=base.source,
        target=base.target,
        protocol_version=base.protocol_version,
        guard_results=base.guard_results + (guard,),
        reason="S6-WCI4 Critical Node review routing prerequisite was not satisfied",
    )


def can_s6_wci4_transition(
    position: CaseRuntimePosition,
    target: RuntimeState,
    *,
    detection: CriticalNodeDetection | None = None,
    review_plan: CriticalReviewPlan | None = None,
) -> TransitionDecision:
    """Activate only CRITICAL_NODE_DETECTION -> CRITICAL_NODE_REVIEW."""
    base = can_transition(
        position,
        target,
        authorized_future_transitions=S6_WCI4_TRANSITIONS,
    )
    if not base.allowed:
        return base
    if detection is None or review_plan is None:
        return _with_guard(
            base,
            _guard("critical_review_plan_frozen", None, "detection/review plan was not supplied"),
        )
    try:
        detection.assert_integrity()
        review_plan.assert_integrity()
        if review_plan.detection_hash != detection.detection_hash:
            raise CriticalNodeContractError("CriticalReviewPlan does not bind exact detection")
        if detection.case_revision != position.case_revision:
            raise CriticalNodeContractError("CriticalNodeDetection Case revision mismatch")
        if detection.protocol_version != base.protocol_version:
            raise CriticalNodeContractError("CriticalNodeDetection protocol version mismatch")
    except CriticalNodeContractError as exc:
        return _with_guard(base, _guard("critical_review_plan_frozen", False, str(exc)))
    return _with_guard(
        base,
        _guard(
            "critical_review_plan_frozen",
            True,
            "Critical Node review routes are frozen; S7 Challenger requirements remain explicit",
        ),
    )
