"""S7-SCS1 immutable Scenario, Intervention, and generation-admission contracts."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from human_cos.runtime.run import canonical_document_sha256
from human_cos.safety.research import (
    ResearchSafetyAdmission,
    ResearchSafetyOutcome,
    ResearchSafetyResult,
    assert_research_safety_result_binding,
)
from human_cos.world import (
    CausalGraph,
    CriticalNodeDetection,
    CriticalReviewPlan,
    ReviewRouteStatus,
    WorldStateSnapshot,
)


class ScenarioContractError(ValueError):
    """Scenario data violates the authorized S7-SCS1 contract boundary."""


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("S7-SCS1 timestamps require timezone-aware datetimes")
    return value


class _FrozenScenarioModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class ScenarioPathType(str, Enum):
    IMPROVEMENT = "IMPROVEMENT"
    BASE = "BASE"
    DETERIORATION = "DETERIORATION"


class ScenarioPathPayload(_FrozenScenarioModel):
    scenario_path_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    parent_world_state_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    parent_causal_graph_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    critical_detection_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    critical_review_plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    path_type: ScenarioPathType
    assumptions: tuple[str, ...] = ()
    affected_actors: tuple[str, ...] = ()
    affected_nodes: tuple[str, ...] = ()
    affected_domains: tuple[str, ...] = ()
    benefit_path: tuple[str, ...]
    harm_path: tuple[str, ...]
    open_unknowns: tuple[str, ...] = ()
    dissent_node_hashes: tuple[str, ...] = ()
    safety_refs: tuple[str, ...] = ()
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class ScenarioPath(ScenarioPathPayload):
    path_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"path_hash"}, exclude_none=True)
        if self.path_hash != canonical_document_sha256(payload):
            raise ScenarioContractError("ScenarioPath path_hash does not match payload")
        if not self.benefit_path or not self.harm_path:
            raise ScenarioContractError("ScenarioPath must preserve benefit and harm paths")
        for name, values in (
            ("assumptions", self.assumptions),
            ("affected_actors", self.affected_actors),
            ("affected_nodes", self.affected_nodes),
            ("affected_domains", self.affected_domains),
            ("benefit_path", self.benefit_path),
            ("harm_path", self.harm_path),
            ("open_unknowns", self.open_unknowns),
            ("dissent_node_hashes", self.dissent_node_hashes),
            ("safety_refs", self.safety_refs),
        ):
            if len(values) != len(set(values)):
                raise ScenarioContractError(f"{name} must not contain duplicates")


class InterventionPayload(_FrozenScenarioModel):
    intervention_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    objective: str = Field(min_length=1)
    owner_actor: str = Field(min_length=1)
    actions: tuple[str, ...]
    target_nodes: tuple[str, ...]
    expected_benefits: tuple[str, ...]
    expected_harms: tuple[str, ...]
    implementation_constraints: tuple[str, ...]
    affected_actors: tuple[str, ...]
    re_simulation_domains: tuple[str, ...]
    success_conditions: tuple[str, ...]
    failure_conditions: tuple[str, ...]
    rollback_conditions: tuple[str, ...]
    analytical_only: Literal[True] = True
    reality_execution_authorized: Literal[False] = False
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class InterventionRecord(InterventionPayload):
    intervention_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(
            mode="json",
            exclude={"intervention_hash"},
            exclude_none=True,
        )
        if self.intervention_hash != canonical_document_sha256(payload):
            raise ScenarioContractError("InterventionRecord hash does not match payload")
        if not self.expected_benefits or not self.expected_harms:
            raise ScenarioContractError(
                "InterventionRecord must preserve expected benefits and harms"
            )
        if not self.rollback_conditions:
            raise ScenarioContractError("InterventionRecord requires rollback conditions")
        if not self.analytical_only or self.reality_execution_authorized:
            raise ScenarioContractError(
                "InterventionRecord is analytical only and grants no execution authority"
            )


class ScenarioSetPayload(_FrozenScenarioModel):
    scenario_set_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    parent_world_state_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    parent_causal_graph_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    critical_detection_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    critical_review_plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    paths: tuple[ScenarioPath, ...]
    interventions: tuple[InterventionRecord, ...] = ()
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class ScenarioSet(ScenarioSetPayload):
    scenario_set_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(
            mode="json",
            exclude={"scenario_set_hash"},
            exclude_none=True,
        )
        if self.scenario_set_hash != canonical_document_sha256(payload):
            raise ScenarioContractError("ScenarioSet hash does not match payload")
        if not self.paths:
            raise ScenarioContractError("ScenarioSet requires ScenarioPath records")
        path_ids = tuple(path.scenario_path_id for path in self.paths)
        if len(path_ids) != len(set(path_ids)):
            raise ScenarioContractError("ScenarioSet path IDs must be unique")
        path_types = {path.path_type for path in self.paths}
        required_types = {
            ScenarioPathType.IMPROVEMENT,
            ScenarioPathType.BASE,
            ScenarioPathType.DETERIORATION,
        }
        if not required_types.issubset(path_types):
            raise ScenarioContractError(
                "ScenarioSet must preserve IMPROVEMENT, BASE, and DETERIORATION paths"
            )
        for path in self.paths:
            path.assert_integrity()
            if (
                path.case_id,
                path.case_revision,
                path.parent_world_state_hash,
                path.parent_causal_graph_hash,
                path.critical_detection_hash,
                path.critical_review_plan_hash,
                path.protocol_version,
            ) != (
                self.case_id,
                self.case_revision,
                self.parent_world_state_hash,
                self.parent_causal_graph_hash,
                self.critical_detection_hash,
                self.critical_review_plan_hash,
                self.protocol_version,
            ):
                raise ScenarioContractError("ScenarioPath lineage does not match ScenarioSet")
        intervention_ids = tuple(item.intervention_id for item in self.interventions)
        if len(intervention_ids) != len(set(intervention_ids)):
            raise ScenarioContractError("ScenarioSet intervention IDs must be unique")
        for intervention in self.interventions:
            intervention.assert_integrity()
            if (
                intervention.case_id,
                intervention.case_revision,
                intervention.protocol_version,
            ) != (self.case_id, self.case_revision, self.protocol_version):
                raise ScenarioContractError("Intervention lineage does not match ScenarioSet")


class ScenarioGenerationAdmissionOutcome(str, Enum):
    ADMIT = "ADMIT"
    BLOCK = "BLOCK"


class ScenarioGenerationAdmissionPacketPayload(_FrozenScenarioModel):
    packet_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    parent_world_state_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    parent_causal_graph_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    critical_detection_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    critical_review_plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    dissent_node_hashes: tuple[str, ...]
    open_unknowns: tuple[str, ...]
    capability_gap_route_ids: tuple[str, ...]
    pending_challenger_route_ids: tuple[str, ...]
    research_safety_admission_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class ScenarioGenerationAdmissionPacket(ScenarioGenerationAdmissionPacketPayload):
    packet_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"packet_hash"}, exclude_none=True)
        if self.packet_hash != canonical_document_sha256(payload):
            raise ScenarioContractError(
                "ScenarioGenerationAdmissionPacket hash does not match payload"
            )
        for name, values in (
            ("dissent_node_hashes", self.dissent_node_hashes),
            ("open_unknowns", self.open_unknowns),
            ("capability_gap_route_ids", self.capability_gap_route_ids),
            ("pending_challenger_route_ids", self.pending_challenger_route_ids),
        ):
            if len(values) != len(set(values)):
                raise ScenarioContractError(f"{name} must not contain duplicates")


class ScenarioGenerationAdmissionResultPayload(_FrozenScenarioModel):
    result_id: str = Field(min_length=1)
    packet_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    research_safety_result_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    outcome: ScenarioGenerationAdmissionOutcome
    reasons: tuple[str, ...]
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class ScenarioGenerationAdmissionResult(ScenarioGenerationAdmissionResultPayload):
    result_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"result_hash"}, exclude_none=True)
        if self.result_hash != canonical_document_sha256(payload):
            raise ScenarioContractError(
                "ScenarioGenerationAdmissionResult hash does not match payload"
            )
        if not self.reasons:
            raise ScenarioContractError(
                "ScenarioGenerationAdmissionResult requires deterministic reasons"
            )


def freeze_scenario_path(payload: ScenarioPathPayload) -> ScenarioPath:
    document = payload.to_document()
    path = ScenarioPath(**document, path_hash=canonical_document_sha256(document))
    path.assert_integrity()
    return path


def freeze_intervention(payload: InterventionPayload) -> InterventionRecord:
    document = payload.to_document()
    record = InterventionRecord(
        **document,
        intervention_hash=canonical_document_sha256(document),
    )
    record.assert_integrity()
    return record


def freeze_scenario_set(payload: ScenarioSetPayload) -> ScenarioSet:
    document = payload.to_document()
    scenario_set = ScenarioSet(
        **document,
        scenario_set_hash=canonical_document_sha256(document),
    )
    scenario_set.assert_integrity()
    return scenario_set


def _assert_s6_source_binding(
    *,
    world_state: WorldStateSnapshot,
    causal_graph: CausalGraph,
    detection: CriticalNodeDetection,
    review_plan: CriticalReviewPlan,
) -> None:
    world_state.assert_integrity()
    causal_graph.assert_integrity()
    detection.assert_integrity()
    review_plan.assert_integrity()
    if (
        world_state.case_id,
        world_state.case_revision,
        world_state.protocol_version,
    ) != (causal_graph.case_id, causal_graph.case_revision, causal_graph.protocol_version):
        raise ScenarioContractError("WorldState and CausalGraph Case/protocol binding mismatch")
    if world_state.causal_graph_hash != causal_graph.graph_hash:
        raise ScenarioContractError("WorldState does not bind exact CausalGraph")
    if not set(detection.dissent_node_hashes).issubset(set(world_state.dissent_node_hashes)):
        raise ScenarioContractError("CriticalNodeDetection lost WorldState dissent lineage")
    if (
        detection.case_id,
        detection.case_revision,
        detection.protocol_version,
        detection.world_state_hash,
        detection.causal_graph_hash,
    ) != (
        world_state.case_id,
        world_state.case_revision,
        world_state.protocol_version,
        world_state.world_state_hash,
        causal_graph.graph_hash,
    ):
        raise ScenarioContractError("CriticalNodeDetection does not bind exact World/Causal state")
    if (
        review_plan.case_id,
        review_plan.case_revision,
        review_plan.protocol_version,
        review_plan.detection_hash,
    ) != (
        detection.case_id,
        detection.case_revision,
        detection.protocol_version,
        detection.detection_hash,
    ):
        raise ScenarioContractError("CriticalReviewPlan does not bind exact detection")


def build_scenario_generation_admission_packet(
    *,
    packet_id: str,
    world_state: WorldStateSnapshot,
    causal_graph: CausalGraph,
    detection: CriticalNodeDetection,
    review_plan: CriticalReviewPlan,
    research_safety_admission: ResearchSafetyAdmission,
    frozen_at: datetime,
) -> ScenarioGenerationAdmissionPacket:
    _assert_s6_source_binding(
        world_state=world_state,
        causal_graph=causal_graph,
        detection=detection,
        review_plan=review_plan,
    )
    research_safety_admission.assert_integrity()
    if (
        research_safety_admission.case_id,
        research_safety_admission.case_revision,
        research_safety_admission.parent_world_state_hash,
        research_safety_admission.parent_causal_graph_hash,
        research_safety_admission.critical_detection_hash,
        research_safety_admission.critical_review_plan_hash,
        research_safety_admission.protocol_version,
    ) != (
        world_state.case_id,
        world_state.case_revision,
        world_state.world_state_hash,
        causal_graph.graph_hash,
        detection.detection_hash,
        review_plan.plan_hash,
        world_state.protocol_version,
    ):
        raise ScenarioContractError("Research Safety admission does not bind exact S6 sources")

    capability_gap_route_ids = tuple(
        route.route_id
        for route in review_plan.routes
        if route.status is ReviewRouteStatus.CAPABILITY_GAP
    )
    pending_challenger_route_ids = tuple(
        route.route_id
        for route in review_plan.routes
        if route.status is ReviewRouteStatus.PENDING_S7
    )
    payload = ScenarioGenerationAdmissionPacketPayload(
        packet_id=packet_id,
        case_id=world_state.case_id,
        case_revision=world_state.case_revision,
        parent_world_state_hash=world_state.world_state_hash,
        parent_causal_graph_hash=causal_graph.graph_hash,
        critical_detection_hash=detection.detection_hash,
        critical_review_plan_hash=review_plan.plan_hash,
        dissent_node_hashes=world_state.dissent_node_hashes,
        open_unknowns=world_state.open_unknowns,
        capability_gap_route_ids=capability_gap_route_ids,
        pending_challenger_route_ids=pending_challenger_route_ids,
        research_safety_admission_hash=research_safety_admission.admission_hash,
        protocol_version=world_state.protocol_version,
        frozen_at=frozen_at,
    )
    document = payload.to_document()
    packet = ScenarioGenerationAdmissionPacket(
        **document,
        packet_hash=canonical_document_sha256(document),
    )
    packet.assert_integrity()
    return packet


def assert_scenario_generation_packet_binding(
    *,
    packet: ScenarioGenerationAdmissionPacket,
    world_state: WorldStateSnapshot,
    causal_graph: CausalGraph,
    detection: CriticalNodeDetection,
    review_plan: CriticalReviewPlan,
    research_safety_admission: ResearchSafetyAdmission,
) -> None:
    packet.assert_integrity()
    expected = build_scenario_generation_admission_packet(
        packet_id=packet.packet_id,
        world_state=world_state,
        causal_graph=causal_graph,
        detection=detection,
        review_plan=review_plan,
        research_safety_admission=research_safety_admission,
        frozen_at=packet.frozen_at,
    )
    if packet != expected:
        raise ScenarioContractError(
            "ScenarioGenerationAdmissionPacket does not preserve exact S6 constraints"
        )


def decide_scenario_generation_admission(
    *,
    packet: ScenarioGenerationAdmissionPacket,
    research_safety_admission: ResearchSafetyAdmission,
    research_safety_result: ResearchSafetyResult,
    result_id: str,
    frozen_at: datetime,
) -> ScenarioGenerationAdmissionResult:
    packet.assert_integrity()
    assert_research_safety_result_binding(
        research_safety_admission,
        research_safety_result,
    )
    if packet.research_safety_admission_hash != research_safety_admission.admission_hash:
        raise ScenarioContractError("Scenario admission packet Safety admission hash mismatch")
    outcome = (
        ScenarioGenerationAdmissionOutcome.ADMIT
        if research_safety_result.outcome is ResearchSafetyOutcome.PASS
        else ScenarioGenerationAdmissionOutcome.BLOCK
    )
    reasons = research_safety_result.reasons
    payload = ScenarioGenerationAdmissionResultPayload(
        result_id=result_id,
        packet_hash=packet.packet_hash,
        research_safety_result_hash=research_safety_result.result_hash,
        outcome=outcome,
        reasons=reasons,
        protocol_version=packet.protocol_version,
        frozen_at=frozen_at,
    )
    document = payload.to_document()
    result = ScenarioGenerationAdmissionResult(
        **document,
        result_hash=canonical_document_sha256(document),
    )
    result.assert_integrity()
    return result


def assert_scenario_generation_result_binding(
    *,
    packet: ScenarioGenerationAdmissionPacket,
    research_safety_admission: ResearchSafetyAdmission,
    research_safety_result: ResearchSafetyResult,
    result: ScenarioGenerationAdmissionResult,
) -> None:
    result.assert_integrity()
    expected = decide_scenario_generation_admission(
        packet=packet,
        research_safety_admission=research_safety_admission,
        research_safety_result=research_safety_result,
        result_id=result.result_id,
        frozen_at=result.frozen_at,
    )
    if result != expected:
        raise ScenarioContractError(
            "ScenarioGenerationAdmissionResult does not match code-owned admission decision"
        )
