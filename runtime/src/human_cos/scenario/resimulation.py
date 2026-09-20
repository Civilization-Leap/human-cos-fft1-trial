"""S7-SCS3 Scenario re-simulation, affected-domain routing, and AT-17 revision closure."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from human_cos.core.models import Case
from human_cos.domains.catalog import get_domain_descriptor
from human_cos.models import QualificationGate
from human_cos.models.profile import DomainTaskType
from human_cos.models.qualification import CapabilityGap
from human_cos.runtime.run import canonical_document_sha256
from human_cos.runtime.state_machine import CaseMode, CaseRuntimePosition, RuntimeState
from human_cos.safety.resimulation import (
    ResimulationSafetyAdmission,
    ResimulationSafetyOutcome,
    ResimulationSafetyResult,
    assert_resimulation_safety_result_binding,
)
from human_cos.world import (
    ActorStateSnapshot,
    ActorStateSnapshotPayload,
    CausalEdge,
    CausalEdgeType,
    CausalGraph,
    CausalGraphPayload,
    CausalNode,
    CausalNodeType,
    ProvenanceRef,
    SourceClass,
    WorldStateSnapshot,
    WorldStateSnapshotPayload,
    freeze_actor_state,
    freeze_causal_graph,
    freeze_world_state,
)

from .contracts import InterventionRecord, ScenarioPath, ScenarioSet


class ScenarioResimulationError(ValueError):
    """Scenario re-simulation violates the authorized S7-SCS3 boundary."""


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("S7-SCS3 timestamps require timezone-aware datetimes")
    return value


def _ordered_unique(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _unique_source_refs(values: Sequence[ProvenanceRef]) -> tuple[ProvenanceRef, ...]:
    seen: set[tuple[str, str, str]] = set()
    output: list[ProvenanceRef] = []
    for item in values:
        key = (item.source_class.value, item.ref, item.sha256)
        if key not in seen:
            seen.add(key)
            output.append(item)
    return tuple(output)


class _FrozenResimulationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class ControllerCOutputLike(Protocol):
    output_hash: str
    case_id: str
    case_revision: int
    scenario_set_hash: str
    scenario_path_hashes: tuple[str, ...]
    intervention_hashes: tuple[str, ...]
    affected_domains: tuple[str, ...]
    preserved_dissent_node_hashes: tuple[str, ...]
    preserved_open_unknowns: tuple[str, ...]
    capability_gap_route_ids: tuple[str, ...]
    pending_challenger_route_ids: tuple[str, ...]
    protocol_version: str

    def assert_integrity(self) -> None: ...


class ScenarioDomainRerunTaskPayload(_FrozenResimulationModel):
    rerun_task_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    scenario_set_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    scenario_path_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    intervention_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    parent_world_state_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    parent_causal_graph_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    domain_id: str = Field(min_length=1)
    domain_task_type: DomainTaskType
    dependency_node_ids: tuple[str, ...]
    affected_actor_ids: tuple[str, ...]
    assumptions: tuple[str, ...] = ()
    benefit_path: tuple[str, ...]
    harm_path: tuple[str, ...]
    rollback_conditions: tuple[str, ...]
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class ScenarioDomainRerunTask(ScenarioDomainRerunTaskPayload):
    task_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        get_domain_descriptor(self.domain_id)
        payload = self.model_dump(mode="json", exclude={"task_hash"}, exclude_none=True)
        if self.task_hash != canonical_document_sha256(payload):
            raise ScenarioResimulationError(
                "ScenarioDomainRerunTask task_hash does not match payload"
            )
        if self.domain_task_type != "scenario_analysis":
            raise ScenarioResimulationError(
                "S7-SCS3 affected-domain reruns require scenario_analysis qualification"
            )
        for name, values in (
            ("dependency_node_ids", self.dependency_node_ids),
            ("affected_actor_ids", self.affected_actor_ids),
            ("assumptions", self.assumptions),
            ("benefit_path", self.benefit_path),
            ("harm_path", self.harm_path),
            ("rollback_conditions", self.rollback_conditions),
        ):
            if len(values) != len(set(values)):
                raise ScenarioResimulationError(f"{name} must not contain duplicates")
        if not self.dependency_node_ids:
            raise ScenarioResimulationError("Scenario Domain rerun requires dependency nodes")
        if not self.affected_actor_ids:
            raise ScenarioResimulationError("Scenario Domain rerun requires affected actors")
        if not self.benefit_path or not self.harm_path:
            raise ScenarioResimulationError(
                "Scenario Domain rerun must preserve benefit and harm paths"
            )
        if not self.rollback_conditions:
            raise ScenarioResimulationError(
                "Scenario Domain rerun requires rollback/discard conditions"
            )


class ScenarioDomainRerunRoutePayload(_FrozenResimulationModel):
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


class ScenarioDomainRerunRoute(ScenarioDomainRerunRoutePayload):
    route_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"route_hash"}, exclude_none=True)
        if self.route_hash != canonical_document_sha256(payload):
            raise ScenarioResimulationError(
                "ScenarioDomainRerunRoute route_hash does not match payload"
            )


@dataclass(frozen=True)
class ScenarioDomainRerunRouteDecision:
    task_hash: str
    candidate_model_id: str
    allowed: bool
    reason: str
    route: ScenarioDomainRerunRoute | None = None
    capability_gap: CapabilityGap | None = None


class ScenarioRerunRoutingEntry(_FrozenResimulationModel):
    task_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    candidate_model_id: str = Field(min_length=1)
    route_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    capability_gap_id: str | None = None
    capability_gap_reason: str | None = None

    @model_validator(mode="after")
    def _exactly_one_outcome(self) -> ScenarioRerunRoutingEntry:
        route_present = self.route_hash is not None
        gap_present = self.capability_gap_id is not None
        if route_present == gap_present:
            raise ValueError("Scenario rerun routing requires exactly one route or Capability Gap")
        if gap_present and not self.capability_gap_reason:
            raise ValueError("Capability Gap routing entry requires a reason")
        if route_present and self.capability_gap_reason is not None:
            raise ValueError("successful route cannot carry Capability Gap reason")
        return self


class ScenarioResimulationPlanPayload(_FrozenResimulationModel):
    plan_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    controller_c_output_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    scenario_set_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    scenario_path_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    intervention_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    parent_world_state_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    parent_causal_graph_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    parent_actor_state_hashes: tuple[str, ...]
    dependency_node_ids: tuple[str, ...]
    dependency_edge_ids: tuple[str, ...]
    affected_actor_ids: tuple[str, ...]
    affected_domains: tuple[str, ...]
    rerun_tasks: tuple[ScenarioDomainRerunTask, ...]
    routing_entries: tuple[ScenarioRerunRoutingEntry, ...]
    resimulation_safety_admission_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    resimulation_safety_result_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    preserved_dissent_node_hashes: tuple[str, ...]
    preserved_open_unknowns: tuple[str, ...]
    inherited_capability_gap_route_ids: tuple[str, ...]
    pending_challenger_route_ids: tuple[str, ...]
    rollback_conditions: tuple[str, ...]
    process_authority: Literal[False] = False
    reality_execution_authorized: Literal[False] = False
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class ScenarioResimulationPlan(ScenarioResimulationPlanPayload):
    plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @property
    def routing_complete(self) -> bool:
        return bool(self.routing_entries) and all(
            entry.route_hash is not None for entry in self.routing_entries
        )

    @property
    def rerun_capability_gap_ids(self) -> tuple[str, ...]:
        return tuple(
            entry.capability_gap_id
            for entry in self.routing_entries
            if entry.capability_gap_id is not None
        )

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"plan_hash"}, exclude_none=True)
        if self.plan_hash != canonical_document_sha256(payload):
            raise ScenarioResimulationError("ScenarioResimulationPlan hash does not match payload")
        if self.process_authority or self.reality_execution_authorized:
            raise ScenarioResimulationError(
                "Scenario re-simulation plan grants no process or execution authority"
            )
        for name, values in (
            ("parent_actor_state_hashes", self.parent_actor_state_hashes),
            ("dependency_node_ids", self.dependency_node_ids),
            ("dependency_edge_ids", self.dependency_edge_ids),
            ("affected_actor_ids", self.affected_actor_ids),
            ("affected_domains", self.affected_domains),
            ("preserved_dissent_node_hashes", self.preserved_dissent_node_hashes),
            ("preserved_open_unknowns", self.preserved_open_unknowns),
            (
                "inherited_capability_gap_route_ids",
                self.inherited_capability_gap_route_ids,
            ),
            ("pending_challenger_route_ids", self.pending_challenger_route_ids),
            ("rollback_conditions", self.rollback_conditions),
        ):
            if len(values) != len(set(values)):
                raise ScenarioResimulationError(f"{name} must not contain duplicates")
        if not self.parent_actor_state_hashes:
            raise ScenarioResimulationError("Resimulation plan requires parent ActorState lineage")
        if not self.dependency_node_ids:
            raise ScenarioResimulationError("Resimulation plan requires dependency propagation")
        if not self.affected_actor_ids or not self.affected_domains:
            raise ScenarioResimulationError(
                "Resimulation plan requires affected actors and affected domains"
            )
        if not self.rollback_conditions:
            raise ScenarioResimulationError(
                "Resimulation plan requires rollback/discard conditions"
            )
        task_hashes = tuple(task.task_hash for task in self.rerun_tasks)
        if not task_hashes or len(task_hashes) != len(set(task_hashes)):
            raise ScenarioResimulationError("Resimulation rerun tasks must be non-empty and unique")
        task_domains = tuple(task.domain_id for task in self.rerun_tasks)
        if len(task_domains) != len(set(task_domains)):
            raise ScenarioResimulationError("Resimulation requires one rerun task per domain")
        if set(task_domains) != set(self.affected_domains):
            raise ScenarioResimulationError("Rerun task domains must equal affected domains")
        entry_hashes = tuple(entry.task_hash for entry in self.routing_entries)
        if len(entry_hashes) != len(set(entry_hashes)) or set(entry_hashes) != set(task_hashes):
            raise ScenarioResimulationError(
                "Resimulation routing entries must cover each rerun task exactly once"
            )
        for task in self.rerun_tasks:
            task.assert_integrity()
            if (
                task.case_id,
                task.case_revision,
                task.scenario_set_hash,
                task.scenario_path_hash,
                task.intervention_hash,
                task.parent_world_state_hash,
                task.parent_causal_graph_hash,
                task.protocol_version,
                task.frozen_at,
            ) != (
                self.case_id,
                self.case_revision,
                self.scenario_set_hash,
                self.scenario_path_hash,
                self.intervention_hash,
                self.parent_world_state_hash,
                self.parent_causal_graph_hash,
                self.protocol_version,
                self.frozen_at,
            ):
                raise ScenarioResimulationError("Rerun task lineage differs from plan")


@dataclass(frozen=True)
class ScenarioResimulationBuild:
    plan: ScenarioResimulationPlan
    tasks: tuple[ScenarioDomainRerunTask, ...]
    routes: tuple[ScenarioDomainRerunRoute, ...]
    capability_gaps: tuple[CapabilityGap, ...]
    scenario_path: ScenarioPath
    intervention: InterventionRecord | None


class ScenarioActorStateDelta(_FrozenResimulationModel):
    actor_id: str = Field(min_length=1)
    observable_actions: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    interests: tuple[str, ...] = ()
    beliefs_or_expectations: tuple[str, ...] = ()
    risk_tolerance_direction: str | None = None
    commitments: tuple[str, ...] = ()
    information_visible: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()


class ScenarioDomainRerunProposal(_FrozenResimulationModel):
    system_state_deltas: tuple[str, ...] = Field(min_length=1)
    actor_state_deltas: tuple[ScenarioActorStateDelta, ...] = ()
    causal_effects: tuple[str, ...] = Field(min_length=1)
    benefit_path_deltas: tuple[str, ...] = Field(min_length=1)
    harm_path_deltas: tuple[str, ...] = Field(min_length=1)
    unknowns: tuple[str, ...] = ()
    rollback_conditions: tuple[str, ...] = ()
    critical_node_refs: tuple[str, ...] = ()


class ScenarioDomainRerunOutputPayload(_FrozenResimulationModel):
    output_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    task_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    route_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    domain_id: str = Field(min_length=1)
    domain_task_type: DomainTaskType
    scenario_set_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    scenario_path_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    intervention_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    parent_world_state_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    parent_causal_graph_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    run_id: str = Field(min_length=1)
    context_manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    routed_model_id: str = Field(min_length=1)
    actual_model_id: str = Field(min_length=1)
    fallback_from: str | None = None
    model_family: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    raw_output_ref: str = Field(min_length=1)
    raw_output_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    content: ScenarioDomainRerunProposal
    process_authority: Literal[False] = False
    reality_execution_authorized: Literal[False] = False
    protocol_version: str = Field(min_length=1)
    finished_at: datetime

    _finished_at_must_be_aware = field_validator("finished_at")(_aware)


class ScenarioDomainRerunOutput(ScenarioDomainRerunOutputPayload):
    output_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        get_domain_descriptor(self.domain_id)
        payload = self.model_dump(mode="json", exclude={"output_hash"}, exclude_none=True)
        if self.output_hash != canonical_document_sha256(payload):
            raise ScenarioResimulationError(
                "ScenarioDomainRerunOutput output_hash does not match payload"
            )
        if self.process_authority or self.reality_execution_authorized:
            raise ScenarioResimulationError(
                "Scenario Domain rerun output grants no process or execution authority"
            )
        if self.actual_model_id == self.routed_model_id:
            if self.fallback_from is not None:
                raise ScenarioResimulationError(
                    "Scenario Domain rerun cannot claim fallback when routed model executed"
                )
        elif self.fallback_from != self.routed_model_id:
            raise ScenarioResimulationError(
                "Scenario Domain rerun actual model differs without explicit fallback"
            )
        if not self.content.system_state_deltas or not self.content.causal_effects:
            raise ScenarioResimulationError(
                "Scenario Domain rerun must produce system-state and causal deltas"
            )
        if not self.content.benefit_path_deltas or not self.content.harm_path_deltas:
            raise ScenarioResimulationError(
                "Scenario Domain rerun must preserve benefit and harm deltas"
            )
        for name, values in (
            ("system_state_deltas", self.content.system_state_deltas),
            ("causal_effects", self.content.causal_effects),
            ("benefit_path_deltas", self.content.benefit_path_deltas),
            ("harm_path_deltas", self.content.harm_path_deltas),
            ("unknowns", self.content.unknowns),
            ("rollback_conditions", self.content.rollback_conditions),
            ("critical_node_refs", self.content.critical_node_refs),
        ):
            if len(values) != len(set(values)):
                raise ScenarioResimulationError(f"{name} must not contain duplicates")


class ScenarioResimulationResultPayload(_FrozenResimulationModel):
    result_id: str = Field(min_length=1)
    plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    scenario_set_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    scenario_path_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    intervention_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    parent_world_state_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    parent_causal_graph_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    parent_actor_state_hashes: tuple[str, ...]
    rerun_task_hashes: tuple[str, ...]
    rerun_route_hashes: tuple[str, ...]
    rerun_output_hashes: tuple[str, ...]
    revised_actor_state_hashes: tuple[str, ...]
    resulting_world_actor_state_hashes: tuple[str, ...]
    resulting_world_state_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    resulting_causal_graph_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    benefit_path_deltas: tuple[str, ...]
    harm_path_deltas: tuple[str, ...]
    open_unknowns: tuple[str, ...]
    rollback_conditions: tuple[str, ...]
    preserved_dissent_node_hashes: tuple[str, ...]
    inherited_capability_gap_route_ids: tuple[str, ...]
    pending_challenger_route_ids: tuple[str, ...]
    at17_runtime_revision_complete: Literal[True] = True
    process_authority: Literal[False] = False
    reality_execution_authorized: Literal[False] = False
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class ScenarioResimulationResult(ScenarioResimulationResultPayload):
    result_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"result_hash"}, exclude_none=True)
        if self.result_hash != canonical_document_sha256(payload):
            raise ScenarioResimulationError(
                "ScenarioResimulationResult result_hash does not match payload"
            )
        if self.process_authority or self.reality_execution_authorized:
            raise ScenarioResimulationError(
                "Scenario re-simulation result grants no process or execution authority"
            )
        for name, values in (
            ("parent_actor_state_hashes", self.parent_actor_state_hashes),
            ("rerun_task_hashes", self.rerun_task_hashes),
            ("rerun_route_hashes", self.rerun_route_hashes),
            ("rerun_output_hashes", self.rerun_output_hashes),
            ("revised_actor_state_hashes", self.revised_actor_state_hashes),
            (
                "resulting_world_actor_state_hashes",
                self.resulting_world_actor_state_hashes,
            ),
            ("benefit_path_deltas", self.benefit_path_deltas),
            ("harm_path_deltas", self.harm_path_deltas),
            ("open_unknowns", self.open_unknowns),
            ("rollback_conditions", self.rollback_conditions),
            ("preserved_dissent_node_hashes", self.preserved_dissent_node_hashes),
            (
                "inherited_capability_gap_route_ids",
                self.inherited_capability_gap_route_ids,
            ),
            ("pending_challenger_route_ids", self.pending_challenger_route_ids),
        ):
            if len(values) != len(set(values)):
                raise ScenarioResimulationError(f"{name} must not contain duplicates")
        if not self.revised_actor_state_hashes:
            raise ScenarioResimulationError("AT-17 result requires revised ActorState records")
        if not self.benefit_path_deltas or not self.harm_path_deltas:
            raise ScenarioResimulationError(
                "AT-17 result must preserve benefit and harm path deltas"
            )


class AT17WorldRevisionEvidencePayload(_FrozenResimulationModel):
    evidence_id: str = Field(min_length=1)
    resimulation_result_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    parent_world_state_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    resulting_world_state_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    parent_world_revision: int = Field(ge=1)
    resulting_world_revision: int = Field(ge=2)
    parent_causal_graph_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    resulting_causal_graph_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    parent_causal_revision: int = Field(ge=1)
    resulting_causal_revision: int = Field(ge=2)
    revised_actor_state_hashes: tuple[str, ...]
    status: Literal["PASS"] = "PASS"
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class AT17WorldRevisionEvidence(AT17WorldRevisionEvidencePayload):
    evidence_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"evidence_hash"}, exclude_none=True)
        if self.evidence_hash != canonical_document_sha256(payload):
            raise ScenarioResimulationError(
                "AT17WorldRevisionEvidence evidence_hash does not match payload"
            )
        if self.resulting_world_revision != self.parent_world_revision + 1:
            raise ScenarioResimulationError("AT-17 WorldState revision must increment by one")
        if self.resulting_causal_revision != self.parent_causal_revision + 1:
            raise ScenarioResimulationError("AT-17 CausalGraph revision must increment by one")
        if not self.revised_actor_state_hashes:
            raise ScenarioResimulationError("AT-17 evidence requires revised ActorState hashes")


@dataclass(frozen=True)
class ScenarioResimulationArtifacts:
    revised_actor_states: tuple[ActorStateSnapshot, ...]
    causal_graph: CausalGraph
    world_state: WorldStateSnapshot
    result: ScenarioResimulationResult
    at17: AT17WorldRevisionEvidence


_COMMON_S7_MODES = frozenset(
    {
        CaseMode.LIVE_FORESIGHT,
        CaseMode.MECHANISM_BENCHMARK,
        CaseMode.SCENARIO_STRESS_TEST,
    }
)


def _assert_generation_position(case: Case, position: CaseRuntimePosition) -> None:
    if case.case_mode != position.mode.value:
        raise ScenarioResimulationError("Case Mode does not match SCS3 runtime position")
    if case.revision != position.case_revision:
        raise ScenarioResimulationError("Case revision does not match SCS3 runtime position")
    if position.mode not in _COMMON_S7_MODES:
        raise ScenarioResimulationError("SCS3 common path excludes HISTORICAL_BLIND_EVAL")
    if position.state is not RuntimeState.SCENARIO_GENERATION:
        raise ScenarioResimulationError(
            "SCS3 plan must be frozen while runtime is at SCENARIO_GENERATION"
        )


def _select_path(scenario_set: ScenarioSet, path_id: str) -> ScenarioPath:
    matches = tuple(path for path in scenario_set.paths if path.scenario_path_id == path_id)
    if len(matches) != 1:
        raise ScenarioResimulationError("selected ScenarioPath must exist exactly once")
    return matches[0]


def _select_intervention(
    scenario_set: ScenarioSet,
    intervention_id: str | None,
) -> InterventionRecord | None:
    if intervention_id is None:
        return None
    matches = tuple(
        item for item in scenario_set.interventions if item.intervention_id == intervention_id
    )
    if len(matches) != 1:
        raise ScenarioResimulationError("selected Intervention must exist exactly once")
    return matches[0]


def _assert_controller_generation_binding(
    *,
    case: Case,
    controller_output: ControllerCOutputLike,
    scenario_set: ScenarioSet,
    parent_world_state: WorldStateSnapshot,
    parent_causal_graph: CausalGraph,
) -> None:
    controller_output.assert_integrity()
    scenario_set.assert_integrity()
    parent_world_state.assert_integrity()
    parent_causal_graph.assert_integrity()
    if (
        controller_output.case_id,
        controller_output.case_revision,
        controller_output.protocol_version,
    ) != (case.case_id, case.revision, case.protocol_version):
        raise ScenarioResimulationError("Controller C output Case/protocol binding mismatch")
    if (
        scenario_set.case_id,
        scenario_set.case_revision,
        scenario_set.protocol_version,
    ) != (case.case_id, case.revision, case.protocol_version):
        raise ScenarioResimulationError("ScenarioSet Case/protocol binding mismatch")
    if controller_output.scenario_set_hash != scenario_set.scenario_set_hash:
        raise ScenarioResimulationError("Controller C output does not bind exact ScenarioSet")
    if set(controller_output.scenario_path_hashes) != {
        path.path_hash for path in scenario_set.paths
    }:
        raise ScenarioResimulationError("Controller C output ScenarioPath set mismatch")
    if set(controller_output.intervention_hashes) != {
        item.intervention_hash for item in scenario_set.interventions
    }:
        raise ScenarioResimulationError("Controller C output Intervention set mismatch")
    if (
        scenario_set.parent_world_state_hash,
        scenario_set.parent_causal_graph_hash,
    ) != (parent_world_state.world_state_hash, parent_causal_graph.graph_hash):
        raise ScenarioResimulationError("ScenarioSet does not bind exact parent World/Causal state")
    if parent_world_state.causal_graph_hash != parent_causal_graph.graph_hash:
        raise ScenarioResimulationError("parent WorldState does not bind exact parent CausalGraph")
    if controller_output.preserved_dissent_node_hashes != parent_world_state.dissent_node_hashes:
        raise ScenarioResimulationError("Controller C output changed parent dissent lineage")
    if not set(parent_world_state.open_unknowns).issubset(
        set(controller_output.preserved_open_unknowns)
    ):
        raise ScenarioResimulationError("Controller C output lost parent open unknowns")


def _assert_parent_actor_binding(
    parent_world_state: WorldStateSnapshot,
    parent_actor_states: tuple[ActorStateSnapshot, ...],
) -> None:
    if not parent_actor_states:
        raise ScenarioResimulationError("SCS3 requires parent ActorState records")
    for actor in parent_actor_states:
        actor.assert_integrity()
        if (
            actor.case_id,
            actor.case_revision,
            actor.protocol_version,
        ) != (
            parent_world_state.case_id,
            parent_world_state.case_revision,
            parent_world_state.protocol_version,
        ):
            raise ScenarioResimulationError("parent ActorState Case/protocol mismatch")
    hashes = tuple(actor.state_hash for actor in parent_actor_states)
    if len(hashes) != len(set(hashes)):
        raise ScenarioResimulationError("parent ActorState records must be unique")
    if set(hashes) != set(parent_world_state.actor_state_hashes):
        raise ScenarioResimulationError(
            "supplied parent ActorState set must exactly cover WorldState actor hashes"
        )
    actor_ids = tuple(actor.actor_id for actor in parent_actor_states)
    if len(actor_ids) != len(set(actor_ids)):
        raise ScenarioResimulationError("parent ActorState actor_id values must be unique")


def derive_dependency_closure(
    *,
    scenario_path: ScenarioPath,
    intervention: InterventionRecord | None,
    parent_world_state: WorldStateSnapshot,
    parent_causal_graph: CausalGraph,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Deterministically propagate selected Scenario effects forward through the parent graph."""
    parent_causal_graph.assert_integrity()
    seeds = _ordered_unique(
        scenario_path.affected_nodes + (() if intervention is None else intervention.target_nodes)
    )
    if not seeds:
        seeds = parent_world_state.critical_node_refs
    if not seeds:
        raise ScenarioResimulationError(
            "dependency propagation requires affected/target/critical seed nodes"
        )
    node_ids = {node.node_id for node in parent_causal_graph.nodes}
    unknown_seeds = tuple(seed for seed in seeds if seed not in node_ids)
    if unknown_seeds:
        raise ScenarioResimulationError(
            "Scenario dependency seed references unknown parent graph nodes: "
            + ", ".join(unknown_seeds)
        )

    reached = set(seeds)
    reached_edges: set[str] = set()
    changed = True
    while changed:
        changed = False
        for edge in parent_causal_graph.edges:
            if edge.source_node_id in reached and edge.target_node_id not in reached:
                reached.add(edge.target_node_id)
                reached_edges.add(edge.edge_id)
                changed = True
            elif edge.source_node_id in reached:
                reached_edges.add(edge.edge_id)
    ordered_nodes = tuple(
        node.node_id for node in parent_causal_graph.nodes if node.node_id in reached
    )
    ordered_edges = tuple(
        edge.edge_id for edge in parent_causal_graph.edges if edge.edge_id in reached_edges
    )
    return ordered_nodes, ordered_edges


def freeze_scenario_domain_rerun_task(
    payload: ScenarioDomainRerunTaskPayload,
) -> ScenarioDomainRerunTask:
    document = payload.to_document()
    task = ScenarioDomainRerunTask(
        **document,
        task_hash=canonical_document_sha256(document),
    )
    task.assert_integrity()
    return task


def route_scenario_domain_rerun(
    *,
    task: ScenarioDomainRerunTask,
    model_id: str,
    qualification: QualificationGate,
    routed_at: datetime,
) -> ScenarioDomainRerunRouteDecision:
    task.assert_integrity()
    decision = qualification.domain_decision(model_id, task.domain_id, task.domain_task_type)
    if not decision.allowed:
        gap = qualification.capability_gap(model_id, task.domain_id, task.domain_task_type)
        return ScenarioDomainRerunRouteDecision(
            task_hash=task.task_hash,
            candidate_model_id=model_id,
            allowed=False,
            reason=decision.reason,
            capability_gap=gap,
        )
    payload = ScenarioDomainRerunRoutePayload(
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
    document = payload.to_document()
    route = ScenarioDomainRerunRoute(
        **document,
        route_hash=canonical_document_sha256(document),
    )
    route.assert_integrity()
    return ScenarioDomainRerunRouteDecision(
        task_hash=task.task_hash,
        candidate_model_id=model_id,
        allowed=True,
        reason=decision.reason,
        route=route,
    )


def assert_scenario_domain_rerun_route_binding(
    *,
    task: ScenarioDomainRerunTask,
    route: ScenarioDomainRerunRoute,
) -> None:
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
        raise ScenarioResimulationError("Scenario rerun route does not bind exact task")


def _assert_safety_binding(
    *,
    admission: ResimulationSafetyAdmission,
    result: ResimulationSafetyResult,
    scenario_set: ScenarioSet,
    scenario_path: ScenarioPath,
    intervention: InterventionRecord | None,
    parent_world_state: WorldStateSnapshot,
    parent_causal_graph: CausalGraph,
) -> None:
    assert_resimulation_safety_result_binding(admission, result)
    expected_intervention_hash = None if intervention is None else intervention.intervention_hash
    if (
        admission.case_id,
        admission.case_revision,
        admission.scenario_set_hash,
        admission.scenario_path_hash,
        admission.intervention_hash,
        admission.parent_world_state_hash,
        admission.parent_causal_graph_hash,
        admission.protocol_version,
    ) != (
        scenario_set.case_id,
        scenario_set.case_revision,
        scenario_set.scenario_set_hash,
        scenario_path.path_hash,
        expected_intervention_hash,
        parent_world_state.world_state_hash,
        parent_causal_graph.graph_hash,
        scenario_set.protocol_version,
    ):
        raise ScenarioResimulationError(
            "Scenario re-simulation Safety does not bind exact selected Scenario lineage"
        )


def build_scenario_resimulation_plan(
    *,
    case: Case,
    position: CaseRuntimePosition,
    controller_output: ControllerCOutputLike,
    scenario_set: ScenarioSet,
    scenario_path_id: str,
    intervention_id: str | None,
    parent_world_state: WorldStateSnapshot,
    parent_causal_graph: CausalGraph,
    parent_actor_states: tuple[ActorStateSnapshot, ...],
    qualification: QualificationGate,
    model_ids_by_domain: Mapping[str, str],
    safety_admission: ResimulationSafetyAdmission,
    safety_result: ResimulationSafetyResult,
    plan_id: str,
    frozen_at: datetime,
) -> ScenarioResimulationBuild:
    """Freeze exact re-simulation tasks/routes without mutating S5 DomainTask semantics."""
    _assert_generation_position(case, position)
    _assert_controller_generation_binding(
        case=case,
        controller_output=controller_output,
        scenario_set=scenario_set,
        parent_world_state=parent_world_state,
        parent_causal_graph=parent_causal_graph,
    )
    _assert_parent_actor_binding(parent_world_state, parent_actor_states)
    scenario_path = _select_path(scenario_set, scenario_path_id)
    intervention = _select_intervention(scenario_set, intervention_id)
    _assert_safety_binding(
        admission=safety_admission,
        result=safety_result,
        scenario_set=scenario_set,
        scenario_path=scenario_path,
        intervention=intervention,
        parent_world_state=parent_world_state,
        parent_causal_graph=parent_causal_graph,
    )
    if frozen_at != safety_result.frozen_at:
        raise ScenarioResimulationError(
            "Resimulation plan time must equal code-owned Safety result freeze time"
        )

    dependency_node_ids, dependency_edge_ids = derive_dependency_closure(
        scenario_path=scenario_path,
        intervention=intervention,
        parent_world_state=parent_world_state,
        parent_causal_graph=parent_causal_graph,
    )
    affected_actor_ids = _ordered_unique(
        scenario_path.affected_actors
        + (() if intervention is None else intervention.affected_actors)
        + (() if intervention is None else (intervention.owner_actor,))
    )
    affected_domains = _ordered_unique(
        scenario_path.affected_domains
        + (() if intervention is None else intervention.re_simulation_domains)
    )
    if not affected_actor_ids or not affected_domains:
        raise ScenarioResimulationError(
            "selected Scenario must identify affected actors and affected domains"
        )
    parent_actor_ids = {actor.actor_id for actor in parent_actor_states}
    missing_actors = tuple(
        actor_id for actor_id in affected_actor_ids if actor_id not in parent_actor_ids
    )
    if missing_actors:
        raise ScenarioResimulationError(
            "selected Scenario references actors absent from parent WorldState: "
            + ", ".join(missing_actors)
        )
    for domain in affected_domains:
        get_domain_descriptor(domain)
        if domain not in model_ids_by_domain:
            raise ScenarioResimulationError(
                f"affected domain {domain!r} requires an explicit rerun model candidate"
            )

    rollback_conditions = _ordered_unique(
        (() if intervention is None else intervention.rollback_conditions)
        + ("discard hypothetical re-simulation and retain the immutable parent state",)
    )
    tasks = tuple(
        freeze_scenario_domain_rerun_task(
            ScenarioDomainRerunTaskPayload(
                rerun_task_id=f"{plan_id}:domain:{domain}",
                case_id=case.case_id,
                case_revision=case.revision,
                scenario_set_hash=scenario_set.scenario_set_hash,
                scenario_path_hash=scenario_path.path_hash,
                intervention_hash=(
                    None if intervention is None else intervention.intervention_hash
                ),
                parent_world_state_hash=parent_world_state.world_state_hash,
                parent_causal_graph_hash=parent_causal_graph.graph_hash,
                domain_id=domain,
                domain_task_type="scenario_analysis",
                dependency_node_ids=dependency_node_ids,
                affected_actor_ids=affected_actor_ids,
                assumptions=scenario_path.assumptions,
                benefit_path=scenario_path.benefit_path,
                harm_path=scenario_path.harm_path,
                rollback_conditions=rollback_conditions,
                protocol_version=case.protocol_version,
                frozen_at=frozen_at,
            )
        )
        for domain in affected_domains
    )
    decisions = tuple(
        route_scenario_domain_rerun(
            task=task,
            model_id=model_ids_by_domain[task.domain_id],
            qualification=qualification,
            routed_at=frozen_at,
        )
        for task in tasks
    )
    routes = tuple(decision.route for decision in decisions if decision.route is not None)
    capability_gaps = tuple(
        decision.capability_gap for decision in decisions if decision.capability_gap is not None
    )
    routing_entries = tuple(
        ScenarioRerunRoutingEntry(
            task_hash=decision.task_hash,
            candidate_model_id=decision.candidate_model_id,
            route_hash=(None if decision.route is None else decision.route.route_hash),
            capability_gap_id=(
                None
                if decision.capability_gap is None
                else decision.capability_gap.capability_gap_id
            ),
            capability_gap_reason=(None if decision.allowed else decision.reason),
        )
        for decision in decisions
    )
    rerun_gap_unknowns = tuple(
        f"rerun-capability-gap:{gap.capability_gap_id}" for gap in capability_gaps
    )
    payload = ScenarioResimulationPlanPayload(
        plan_id=plan_id,
        case_id=case.case_id,
        case_revision=case.revision,
        controller_c_output_hash=controller_output.output_hash,
        scenario_set_hash=scenario_set.scenario_set_hash,
        scenario_path_hash=scenario_path.path_hash,
        intervention_hash=(None if intervention is None else intervention.intervention_hash),
        parent_world_state_hash=parent_world_state.world_state_hash,
        parent_causal_graph_hash=parent_causal_graph.graph_hash,
        parent_actor_state_hashes=parent_world_state.actor_state_hashes,
        dependency_node_ids=dependency_node_ids,
        dependency_edge_ids=dependency_edge_ids,
        affected_actor_ids=affected_actor_ids,
        affected_domains=affected_domains,
        rerun_tasks=tasks,
        routing_entries=routing_entries,
        resimulation_safety_admission_hash=safety_admission.admission_hash,
        resimulation_safety_result_hash=safety_result.result_hash,
        preserved_dissent_node_hashes=controller_output.preserved_dissent_node_hashes,
        preserved_open_unknowns=_ordered_unique(
            controller_output.preserved_open_unknowns + rerun_gap_unknowns
        ),
        inherited_capability_gap_route_ids=controller_output.capability_gap_route_ids,
        pending_challenger_route_ids=controller_output.pending_challenger_route_ids,
        rollback_conditions=rollback_conditions,
        protocol_version=case.protocol_version,
        frozen_at=frozen_at,
    )
    document = payload.to_document()
    plan = ScenarioResimulationPlan(
        **document,
        plan_hash=canonical_document_sha256(document),
    )
    plan.assert_integrity()
    return ScenarioResimulationBuild(
        plan=plan,
        tasks=tasks,
        routes=routes,
        capability_gaps=capability_gaps,
        scenario_path=scenario_path,
        intervention=intervention,
    )


def assert_scenario_resimulation_plan_binding(
    *,
    plan: ScenarioResimulationPlan,
    case: Case,
    position: CaseRuntimePosition,
    controller_output: ControllerCOutputLike,
    scenario_set: ScenarioSet,
    parent_world_state: WorldStateSnapshot,
    parent_causal_graph: CausalGraph,
    parent_actor_states: tuple[ActorStateSnapshot, ...],
    qualification: QualificationGate,
    routes: tuple[ScenarioDomainRerunRoute, ...],
    safety_admission: ResimulationSafetyAdmission,
    safety_result: ResimulationSafetyResult,
) -> None:
    plan.assert_integrity()
    _assert_generation_position(case, position)
    _assert_controller_generation_binding(
        case=case,
        controller_output=controller_output,
        scenario_set=scenario_set,
        parent_world_state=parent_world_state,
        parent_causal_graph=parent_causal_graph,
    )
    _assert_parent_actor_binding(parent_world_state, parent_actor_states)
    scenario_path = tuple(
        path for path in scenario_set.paths if path.path_hash == plan.scenario_path_hash
    )
    if len(scenario_path) != 1:
        raise ScenarioResimulationError("plan ScenarioPath hash is not in ScenarioSet")
    intervention: InterventionRecord | None = None
    if plan.intervention_hash is not None:
        matches = tuple(
            item
            for item in scenario_set.interventions
            if item.intervention_hash == plan.intervention_hash
        )
        if len(matches) != 1:
            raise ScenarioResimulationError("plan Intervention hash is not in ScenarioSet")
        intervention = matches[0]
    _assert_safety_binding(
        admission=safety_admission,
        result=safety_result,
        scenario_set=scenario_set,
        scenario_path=scenario_path[0],
        intervention=intervention,
        parent_world_state=parent_world_state,
        parent_causal_graph=parent_causal_graph,
    )
    expected_nodes, expected_edges = derive_dependency_closure(
        scenario_path=scenario_path[0],
        intervention=intervention,
        parent_world_state=parent_world_state,
        parent_causal_graph=parent_causal_graph,
    )
    expected_actors = _ordered_unique(
        scenario_path[0].affected_actors
        + (() if intervention is None else intervention.affected_actors)
        + (() if intervention is None else (intervention.owner_actor,))
    )
    expected_domains = _ordered_unique(
        scenario_path[0].affected_domains
        + (() if intervention is None else intervention.re_simulation_domains)
    )
    if (
        plan.controller_c_output_hash,
        plan.scenario_set_hash,
        plan.parent_world_state_hash,
        plan.parent_causal_graph_hash,
        plan.parent_actor_state_hashes,
        plan.dependency_node_ids,
        plan.dependency_edge_ids,
        plan.affected_actor_ids,
        plan.affected_domains,
        plan.resimulation_safety_admission_hash,
        plan.resimulation_safety_result_hash,
        plan.preserved_dissent_node_hashes,
        plan.inherited_capability_gap_route_ids,
        plan.pending_challenger_route_ids,
        plan.protocol_version,
        plan.frozen_at,
    ) != (
        controller_output.output_hash,
        scenario_set.scenario_set_hash,
        parent_world_state.world_state_hash,
        parent_causal_graph.graph_hash,
        parent_world_state.actor_state_hashes,
        expected_nodes,
        expected_edges,
        expected_actors,
        expected_domains,
        safety_admission.admission_hash,
        safety_result.result_hash,
        controller_output.preserved_dissent_node_hashes,
        controller_output.capability_gap_route_ids,
        controller_output.pending_challenger_route_ids,
        case.protocol_version,
        safety_result.frozen_at,
    ):
        raise ScenarioResimulationError("ScenarioResimulationPlan source binding mismatch")
    if not set(controller_output.preserved_open_unknowns).issubset(
        set(plan.preserved_open_unknowns)
    ):
        raise ScenarioResimulationError("Resimulation plan lost Controller C open unknowns")

    task_by_hash = {task.task_hash: task for task in plan.rerun_tasks}
    route_by_hash = {route.route_hash: route for route in routes}
    if len(route_by_hash) != len(routes):
        raise ScenarioResimulationError("Scenario rerun routes must be unique")
    expected_route_hashes = {
        entry.route_hash for entry in plan.routing_entries if entry.route_hash is not None
    }
    if set(route_by_hash) != expected_route_hashes:
        raise ScenarioResimulationError("supplied Scenario rerun route set differs from plan")
    for entry in plan.routing_entries:
        task = task_by_hash[entry.task_hash]
        if entry.route_hash is not None:
            route = route_by_hash[entry.route_hash]
            assert_scenario_domain_rerun_route_binding(task=task, route=route)
            if route.model_id != entry.candidate_model_id:
                raise ScenarioResimulationError("routing candidate/model binding mismatch")
            qualification.assert_domain_eligible(
                route.model_id,
                route.domain_id,
                route.domain_task_type,
            )
        else:
            decision = qualification.domain_decision(
                entry.candidate_model_id,
                task.domain_id,
                task.domain_task_type,
            )
            if decision.allowed:
                raise ScenarioResimulationError(
                    "Capability Gap entry no longer matches qualification facts"
                )
            gap = qualification.capability_gap(
                entry.candidate_model_id,
                task.domain_id,
                task.domain_task_type,
            )
            if gap.capability_gap_id != entry.capability_gap_id:
                raise ScenarioResimulationError("Capability Gap identity mismatch")


def freeze_scenario_domain_rerun_output(
    *,
    task: ScenarioDomainRerunTask,
    route: ScenarioDomainRerunRoute,
    proposal: ScenarioDomainRerunProposal,
    run_id: str,
    context_manifest_hash: str,
    routed_model_id: str,
    actual_model_id: str,
    fallback_from: str | None,
    model_family: str,
    provider: str,
    raw_output_ref: str,
    raw_output_hash: str,
    output_id: str,
    finished_at: datetime,
) -> ScenarioDomainRerunOutput:
    assert_scenario_domain_rerun_route_binding(task=task, route=route)
    if routed_model_id != route.model_id:
        raise ScenarioResimulationError("rerun output routed_model_id differs from route")
    actor_ids = tuple(delta.actor_id for delta in proposal.actor_state_deltas)
    if len(actor_ids) != len(set(actor_ids)):
        raise ScenarioResimulationError("rerun proposal contains duplicate actor deltas")
    if any(actor_id not in task.affected_actor_ids for actor_id in actor_ids):
        raise ScenarioResimulationError("rerun proposal contains actor outside affected set")
    payload = ScenarioDomainRerunOutputPayload(
        output_id=output_id,
        case_id=task.case_id,
        case_revision=task.case_revision,
        task_hash=task.task_hash,
        route_hash=route.route_hash,
        domain_id=task.domain_id,
        domain_task_type=task.domain_task_type,
        scenario_set_hash=task.scenario_set_hash,
        scenario_path_hash=task.scenario_path_hash,
        intervention_hash=task.intervention_hash,
        parent_world_state_hash=task.parent_world_state_hash,
        parent_causal_graph_hash=task.parent_causal_graph_hash,
        run_id=run_id,
        context_manifest_hash=context_manifest_hash,
        routed_model_id=routed_model_id,
        actual_model_id=actual_model_id,
        fallback_from=fallback_from,
        model_family=model_family,
        provider=provider,
        raw_output_ref=raw_output_ref,
        raw_output_hash=raw_output_hash,
        content=proposal,
        protocol_version=task.protocol_version,
        finished_at=finished_at,
    )
    document = payload.to_document()
    output = ScenarioDomainRerunOutput(
        **document,
        output_hash=canonical_document_sha256(document),
    )
    output.assert_integrity()
    return output


def assert_scenario_rerun_output_set(
    *,
    plan: ScenarioResimulationPlan,
    routes: tuple[ScenarioDomainRerunRoute, ...],
    outputs: tuple[ScenarioDomainRerunOutput, ...],
) -> None:
    plan.assert_integrity()
    if not plan.routing_complete:
        raise ScenarioResimulationError(
            "Capability Gap prevents complete Scenario Domain rerun output set"
        )
    task_by_hash = {task.task_hash: task for task in plan.rerun_tasks}
    route_by_hash = {route.route_hash: route for route in routes}
    expected = {(route.task_hash, route.route_hash) for route in routes}
    actual: set[tuple[str, str]] = set()
    for output in outputs:
        output.assert_integrity()
        task = task_by_hash.get(output.task_hash)
        route = route_by_hash.get(output.route_hash)
        if task is None or route is None:
            raise ScenarioResimulationError("rerun output does not bind required task/route")
        assert_scenario_domain_rerun_route_binding(task=task, route=route)
        if (
            output.case_id,
            output.case_revision,
            output.domain_id,
            output.domain_task_type,
            output.scenario_set_hash,
            output.scenario_path_hash,
            output.intervention_hash,
            output.parent_world_state_hash,
            output.parent_causal_graph_hash,
            output.protocol_version,
        ) != (
            plan.case_id,
            plan.case_revision,
            task.domain_id,
            task.domain_task_type,
            plan.scenario_set_hash,
            plan.scenario_path_hash,
            plan.intervention_hash,
            plan.parent_world_state_hash,
            plan.parent_causal_graph_hash,
            plan.protocol_version,
        ):
            raise ScenarioResimulationError("rerun output lineage differs from plan")
        actual.add((output.task_hash, output.route_hash))
    if len(actual) != len(outputs) or actual != expected:
        raise ScenarioResimulationError(
            "rerun outputs must cover every qualified affected-domain route exactly once"
        )


def _merge_delta_field(
    parent: tuple[str, ...],
    deltas: Sequence[ScenarioActorStateDelta],
    field_name: str,
) -> tuple[str, ...]:
    additions: list[str] = []
    for delta in deltas:
        additions.extend(getattr(delta, field_name))
    return _ordered_unique(parent + tuple(additions))


def _build_actor_revision(
    *,
    parent: ActorStateSnapshot,
    deltas: tuple[ScenarioActorStateDelta, ...],
    output_refs: tuple[ProvenanceRef, ...],
    scenario_ref: ProvenanceRef,
    frozen_at: datetime,
) -> ActorStateSnapshot:
    if not deltas:
        raise ScenarioResimulationError(
            f"affected actor {parent.actor_id!r} has no Scenario rerun state delta"
        )
    risk_values = {
        delta.risk_tolerance_direction
        for delta in deltas
        if delta.risk_tolerance_direction is not None
    }
    if len(risk_values) > 1:
        raise ScenarioResimulationError(
            f"affected actor {parent.actor_id!r} has conflicting risk-tolerance deltas"
        )
    risk_value = next(iter(risk_values)) if risk_values else parent.risk_tolerance_direction
    return freeze_actor_state(
        ActorStateSnapshotPayload(
            actor_state_id=parent.actor_state_id,
            actor_id=parent.actor_id,
            case_id=parent.case_id,
            case_revision=parent.case_revision,
            revision=parent.revision + 1,
            parent_state_hash=parent.state_hash,
            timestamp=frozen_at,
            observable_actions=_merge_delta_field(
                parent.observable_actions,
                deltas,
                "observable_actions",
            ),
            capabilities=_merge_delta_field(parent.capabilities, deltas, "capabilities"),
            constraints=_merge_delta_field(parent.constraints, deltas, "constraints"),
            interests=_merge_delta_field(parent.interests, deltas, "interests"),
            beliefs_or_expectations=_merge_delta_field(
                parent.beliefs_or_expectations,
                deltas,
                "beliefs_or_expectations",
            ),
            risk_tolerance_direction=risk_value,
            commitments=_merge_delta_field(parent.commitments, deltas, "commitments"),
            information_visible=_merge_delta_field(
                parent.information_visible,
                deltas,
                "information_visible",
            ),
            uncertainties=_merge_delta_field(parent.uncertainties, deltas, "uncertainties"),
            source_refs=_unique_source_refs(parent.source_refs + (scenario_ref,) + output_refs),
            protocol_version=parent.protocol_version,
            frozen_at=frozen_at,
        ),
        parent=parent,
    )


def _result_source_ref(output: ScenarioDomainRerunOutput) -> ProvenanceRef:
    return ProvenanceRef(
        source_class=SourceClass.MODEL,
        ref=f"scenario-domain-rerun:{output.output_id}",
        sha256=output.output_hash,
    )


def integrate_scenario_resimulation(
    *,
    plan: ScenarioResimulationPlan,
    controller_output: ControllerCOutputLike,
    scenario_set: ScenarioSet,
    parent_world_state: WorldStateSnapshot,
    parent_causal_graph: CausalGraph,
    parent_actor_states: tuple[ActorStateSnapshot, ...],
    qualification: QualificationGate,
    routes: tuple[ScenarioDomainRerunRoute, ...],
    outputs: tuple[ScenarioDomainRerunOutput, ...],
    safety_admission: ResimulationSafetyAdmission,
    safety_result: ResimulationSafetyResult,
    result_id: str,
    at17_evidence_id: str,
    frozen_at: datetime,
) -> ScenarioResimulationArtifacts:
    """Integrate true rerun outputs into append-only Actor/World/Causal revisions."""
    plan.assert_integrity()
    controller_output.assert_integrity()
    scenario_set.assert_integrity()
    _assert_parent_actor_binding(parent_world_state, parent_actor_states)
    assert_scenario_rerun_output_set(plan=plan, routes=routes, outputs=outputs)
    if (
        controller_output.output_hash,
        controller_output.scenario_set_hash,
        scenario_set.scenario_set_hash,
        parent_world_state.world_state_hash,
        parent_causal_graph.graph_hash,
    ) != (
        plan.controller_c_output_hash,
        plan.scenario_set_hash,
        plan.scenario_set_hash,
        plan.parent_world_state_hash,
        plan.parent_causal_graph_hash,
    ):
        raise ScenarioResimulationError("integration sources differ from frozen plan")
    supplied_parent_hashes = {actor.state_hash for actor in parent_actor_states}
    if supplied_parent_hashes != set(plan.parent_actor_state_hashes):
        raise ScenarioResimulationError(
            "integration parent ActorState set differs from frozen plan"
        )
    for route in routes:
        qualification.assert_domain_eligible(
            route.model_id,
            route.domain_id,
            route.domain_task_type,
        )

    selected_paths = tuple(
        path for path in scenario_set.paths if path.path_hash == plan.scenario_path_hash
    )
    if len(selected_paths) != 1:
        raise ScenarioResimulationError("integration ScenarioPath is not in ScenarioSet")
    scenario_path = selected_paths[0]
    selected_intervention: InterventionRecord | None = None
    scenario_ref = ProvenanceRef(
        source_class=SourceClass.ASSUMPTION,
        ref=f"scenario-path:{scenario_path.scenario_path_id}",
        sha256=scenario_path.path_hash,
    )
    intervention_ref: ProvenanceRef | None = None
    if plan.intervention_hash is not None:
        selected_interventions = tuple(
            item
            for item in scenario_set.interventions
            if item.intervention_hash == plan.intervention_hash
        )
        if len(selected_interventions) != 1:
            raise ScenarioResimulationError("integration Intervention is not in ScenarioSet")
        selected_intervention = selected_interventions[0]
        intervention_ref = ProvenanceRef(
            source_class=SourceClass.ASSUMPTION,
            ref=f"intervention:{selected_intervention.intervention_id}",
            sha256=selected_intervention.intervention_hash,
        )
    _assert_safety_binding(
        admission=safety_admission,
        result=safety_result,
        scenario_set=scenario_set,
        scenario_path=scenario_path,
        intervention=selected_intervention,
        parent_world_state=parent_world_state,
        parent_causal_graph=parent_causal_graph,
    )
    if (
        plan.resimulation_safety_admission_hash,
        plan.resimulation_safety_result_hash,
    ) != (safety_admission.admission_hash, safety_result.result_hash):
        raise ScenarioResimulationError("integration Safety hashes differ from frozen plan")
    if safety_result.outcome is not ResimulationSafetyOutcome.PASS:
        raise ScenarioResimulationError("AT-17 integration requires Safety PASS")

    output_by_task = {output.task_hash: output for output in outputs}
    output_refs = tuple(_result_source_ref(output) for output in outputs)
    parent_by_actor = {actor.actor_id: actor for actor in parent_actor_states}
    revised_actor_states: list[ActorStateSnapshot] = []
    revised_by_actor: dict[str, ActorStateSnapshot] = {}
    for actor_id in plan.affected_actor_ids:
        actor_deltas = tuple(
            delta
            for output in outputs
            for delta in output.content.actor_state_deltas
            if delta.actor_id == actor_id
        )
        contributing_refs = tuple(
            _result_source_ref(output)
            for output in outputs
            if any(delta.actor_id == actor_id for delta in output.content.actor_state_deltas)
        )
        revised = _build_actor_revision(
            parent=parent_by_actor[actor_id],
            deltas=actor_deltas,
            output_refs=contributing_refs,
            scenario_ref=scenario_ref,
            frozen_at=frozen_at,
        )
        revised_actor_states.append(revised)
        revised_by_actor[actor_id] = revised

    parent_node_ids = {node.node_id for node in parent_causal_graph.nodes}
    new_nodes: list[CausalNode] = []
    new_edges: list[CausalEdge] = []
    for task in plan.rerun_tasks:
        output = output_by_task[task.task_hash]
        source_ref = _result_source_ref(output)
        for index, effect in enumerate(output.content.causal_effects, start=1):
            node_id = f"s7:{plan.plan_id}:{task.domain_id}:effect:{index}"
            if node_id in parent_node_ids:
                raise ScenarioResimulationError("generated S7 Causal node ID collides with parent")
            new_nodes.append(
                CausalNode(
                    node_id=node_id,
                    node_type=CausalNodeType.SYSTEM_STATE,
                    label=effect,
                    source_refs=(source_ref,),
                )
            )
            for dependency_id in task.dependency_node_ids:
                new_edges.append(
                    CausalEdge(
                        edge_id=(
                            f"s7:{plan.plan_id}:{task.domain_id}:{dependency_id}:effect:{index}"
                        ),
                        source_node_id=dependency_id,
                        target_node_id=node_id,
                        edge_type=CausalEdgeType.CAUSES,
                        source_refs=(source_ref,),
                    )
                )

    revised_causal_graph = freeze_causal_graph(
        CausalGraphPayload(
            graph_id=parent_causal_graph.graph_id,
            case_id=parent_causal_graph.case_id,
            case_revision=parent_causal_graph.case_revision,
            revision=parent_causal_graph.revision + 1,
            parent_graph_hash=parent_causal_graph.graph_hash,
            nodes=parent_causal_graph.nodes + tuple(new_nodes),
            edges=parent_causal_graph.edges + tuple(new_edges),
            feedback_loops=parent_causal_graph.feedback_loops,
            dissent_node_hashes=parent_causal_graph.dissent_node_hashes,
            protocol_version=parent_causal_graph.protocol_version,
            frozen_at=frozen_at,
        ),
        parent=parent_causal_graph,
    )

    parent_hash_to_actor = {actor.state_hash: actor for actor in parent_actor_states}
    resulting_world_actor_hashes = tuple(
        (
            revised_by_actor[parent_hash_to_actor[state_hash].actor_id].state_hash
            if parent_hash_to_actor[state_hash].actor_id in revised_by_actor
            else state_hash
        )
        for state_hash in parent_world_state.actor_state_hashes
    )
    known_critical_refs = {node.node_id for node in revised_causal_graph.nodes}
    output_critical_refs = _ordered_unique(
        tuple(ref for output in outputs for ref in output.content.critical_node_refs)
    )
    if any(ref not in known_critical_refs for ref in output_critical_refs):
        raise ScenarioResimulationError("rerun output references unknown Critical Node")
    system_state_deltas = _ordered_unique(
        tuple(value for output in outputs for value in output.content.system_state_deltas)
    )
    if not system_state_deltas:
        raise ScenarioResimulationError("true re-simulation requires system-state deltas")
    benefit_deltas = _ordered_unique(
        tuple(value for output in outputs for value in output.content.benefit_path_deltas)
    )
    harm_deltas = _ordered_unique(
        tuple(value for output in outputs for value in output.content.harm_path_deltas)
    )
    output_unknowns = _ordered_unique(
        tuple(value for output in outputs for value in output.content.unknowns)
    )
    output_rollbacks = _ordered_unique(
        tuple(value for output in outputs for value in output.content.rollback_conditions)
    )
    inherited_gap_unknowns = tuple(
        f"inherited-capability-gap:{gap_id}" for gap_id in plan.inherited_capability_gap_route_ids
    )
    open_unknowns = _ordered_unique(
        parent_world_state.open_unknowns
        + plan.preserved_open_unknowns
        + inherited_gap_unknowns
        + output_unknowns
    )
    additional_refs = (scenario_ref,) + (() if intervention_ref is None else (intervention_ref,))
    revised_world_state = freeze_world_state(
        WorldStateSnapshotPayload(
            world_state_id=parent_world_state.world_state_id,
            case_id=parent_world_state.case_id,
            case_revision=parent_world_state.case_revision,
            revision=parent_world_state.revision + 1,
            parent_world_state_hash=parent_world_state.world_state_hash,
            timestamp=frozen_at,
            system_states=_ordered_unique(parent_world_state.system_states + system_state_deltas),
            actor_state_hashes=resulting_world_actor_hashes,
            causal_graph_hash=revised_causal_graph.graph_hash,
            critical_node_refs=_ordered_unique(
                parent_world_state.critical_node_refs + output_critical_refs
            ),
            open_unknowns=open_unknowns,
            dissent_node_hashes=parent_world_state.dissent_node_hashes,
            claim_refs=parent_world_state.claim_refs,
            source_refs=_unique_source_refs(
                parent_world_state.source_refs + additional_refs + output_refs
            ),
            protocol_version=parent_world_state.protocol_version,
            frozen_at=frozen_at,
        ),
        parent=parent_world_state,
    )

    result_payload = ScenarioResimulationResultPayload(
        result_id=result_id,
        plan_hash=plan.plan_hash,
        case_id=plan.case_id,
        case_revision=plan.case_revision,
        scenario_set_hash=plan.scenario_set_hash,
        scenario_path_hash=plan.scenario_path_hash,
        intervention_hash=plan.intervention_hash,
        parent_world_state_hash=parent_world_state.world_state_hash,
        parent_causal_graph_hash=parent_causal_graph.graph_hash,
        parent_actor_state_hashes=parent_world_state.actor_state_hashes,
        rerun_task_hashes=tuple(task.task_hash for task in plan.rerun_tasks),
        rerun_route_hashes=tuple(route.route_hash for route in routes),
        rerun_output_hashes=tuple(output.output_hash for output in outputs),
        revised_actor_state_hashes=tuple(actor.state_hash for actor in revised_actor_states),
        resulting_world_actor_state_hashes=resulting_world_actor_hashes,
        resulting_world_state_hash=revised_world_state.world_state_hash,
        resulting_causal_graph_hash=revised_causal_graph.graph_hash,
        benefit_path_deltas=benefit_deltas,
        harm_path_deltas=harm_deltas,
        open_unknowns=open_unknowns,
        rollback_conditions=_ordered_unique(plan.rollback_conditions + output_rollbacks),
        preserved_dissent_node_hashes=parent_world_state.dissent_node_hashes,
        inherited_capability_gap_route_ids=plan.inherited_capability_gap_route_ids,
        pending_challenger_route_ids=plan.pending_challenger_route_ids,
        protocol_version=plan.protocol_version,
        frozen_at=frozen_at,
    )
    result_document = result_payload.to_document()
    result = ScenarioResimulationResult(
        **result_document,
        result_hash=canonical_document_sha256(result_document),
    )
    result.assert_integrity()
    at17 = evaluate_at17_world_revision(
        evidence_id=at17_evidence_id,
        plan=plan,
        parent_world_state=parent_world_state,
        parent_causal_graph=parent_causal_graph,
        parent_actor_states=parent_actor_states,
        revised_actor_states=tuple(revised_actor_states),
        revised_causal_graph=revised_causal_graph,
        revised_world_state=revised_world_state,
        result=result,
        frozen_at=frozen_at,
    )
    return ScenarioResimulationArtifacts(
        revised_actor_states=tuple(revised_actor_states),
        causal_graph=revised_causal_graph,
        world_state=revised_world_state,
        result=result,
        at17=at17,
    )


def evaluate_at17_world_revision(
    *,
    evidence_id: str,
    plan: ScenarioResimulationPlan,
    parent_world_state: WorldStateSnapshot,
    parent_causal_graph: CausalGraph,
    parent_actor_states: tuple[ActorStateSnapshot, ...],
    revised_actor_states: tuple[ActorStateSnapshot, ...],
    revised_causal_graph: CausalGraph,
    revised_world_state: WorldStateSnapshot,
    result: ScenarioResimulationResult,
    frozen_at: datetime,
) -> AT17WorldRevisionEvidence:
    """Record AT-17 PASS only after real append-only World/Causal/Actor revisions exist."""
    plan.assert_integrity()
    parent_world_state.assert_integrity()
    parent_causal_graph.assert_integrity()
    revised_causal_graph.assert_integrity()
    revised_world_state.assert_integrity()
    result.assert_integrity()
    _assert_parent_actor_binding(parent_world_state, parent_actor_states)
    if not revised_actor_states:
        raise ScenarioResimulationError("AT-17 requires at least one revised ActorState")
    parent_by_actor = {actor.actor_id: actor for actor in parent_actor_states}
    revised_by_actor = {actor.actor_id: actor for actor in revised_actor_states}
    if len(revised_by_actor) != len(revised_actor_states):
        raise ScenarioResimulationError("AT-17 revised ActorState actor IDs must be unique")
    if set(revised_by_actor) != set(plan.affected_actor_ids):
        raise ScenarioResimulationError(
            "AT-17 revised ActorState set must equal plan affected actors"
        )
    for actor_id, revised in revised_by_actor.items():
        parent = parent_by_actor[actor_id]
        revised.assert_integrity()
        if (
            revised.revision,
            revised.parent_state_hash,
            revised.case_id,
            revised.case_revision,
            revised.protocol_version,
        ) != (
            parent.revision + 1,
            parent.state_hash,
            parent.case_id,
            parent.case_revision,
            parent.protocol_version,
        ):
            raise ScenarioResimulationError(
                f"AT-17 ActorState revision binding failed for {actor_id!r}"
            )
    if (
        revised_causal_graph.revision,
        revised_causal_graph.parent_graph_hash,
    ) != (parent_causal_graph.revision + 1, parent_causal_graph.graph_hash):
        raise ScenarioResimulationError("AT-17 CausalGraph revision binding failed")
    if (
        revised_world_state.revision,
        revised_world_state.parent_world_state_hash,
        revised_world_state.causal_graph_hash,
    ) != (
        parent_world_state.revision + 1,
        parent_world_state.world_state_hash,
        revised_causal_graph.graph_hash,
    ):
        raise ScenarioResimulationError("AT-17 WorldState revision binding failed")
    if revised_world_state.world_state_hash == parent_world_state.world_state_hash:
        raise ScenarioResimulationError("AT-17 requires a new WorldState hash")
    if revised_causal_graph.graph_hash == parent_causal_graph.graph_hash:
        raise ScenarioResimulationError("AT-17 requires a new CausalGraph hash")
    if (
        result.plan_hash,
        result.parent_world_state_hash,
        result.parent_causal_graph_hash,
        result.resulting_world_state_hash,
        result.resulting_causal_graph_hash,
        result.revised_actor_state_hashes,
        result.resulting_world_actor_state_hashes,
        result.preserved_dissent_node_hashes,
    ) != (
        plan.plan_hash,
        parent_world_state.world_state_hash,
        parent_causal_graph.graph_hash,
        revised_world_state.world_state_hash,
        revised_causal_graph.graph_hash,
        tuple(actor.state_hash for actor in revised_actor_states),
        revised_world_state.actor_state_hashes,
        parent_world_state.dissent_node_hashes,
    ):
        raise ScenarioResimulationError("AT-17 result/revision lineage mismatch")
    payload = AT17WorldRevisionEvidencePayload(
        evidence_id=evidence_id,
        resimulation_result_hash=result.result_hash,
        parent_world_state_hash=parent_world_state.world_state_hash,
        resulting_world_state_hash=revised_world_state.world_state_hash,
        parent_world_revision=parent_world_state.revision,
        resulting_world_revision=revised_world_state.revision,
        parent_causal_graph_hash=parent_causal_graph.graph_hash,
        resulting_causal_graph_hash=revised_causal_graph.graph_hash,
        parent_causal_revision=parent_causal_graph.revision,
        resulting_causal_revision=revised_causal_graph.revision,
        revised_actor_state_hashes=tuple(actor.state_hash for actor in revised_actor_states),
        protocol_version=plan.protocol_version,
        frozen_at=frozen_at,
    )
    document = payload.to_document()
    evidence = AT17WorldRevisionEvidence(
        **document,
        evidence_hash=canonical_document_sha256(document),
    )
    evidence.assert_integrity()
    return evidence
