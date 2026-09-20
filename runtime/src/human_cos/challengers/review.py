"""S7-SCS4 Challenger contracts, blocking gate, S6 satisfaction, and third edge."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from human_cos.controllers.scenario import ControllerCOutputRecord
from human_cos.core.models import Case
from human_cos.models import QualificationGate
from human_cos.runtime.run import RunManifest, canonical_document_sha256
from human_cos.runtime.state_machine import (
    CaseMode,
    CaseRuntimePosition,
    GuardCheck,
    GuardStatus,
    RuntimeState,
    TransitionDecision,
    TransitionKey,
    TransitionRejected,
    TransitionResult,
    TransitionStatus,
    can_transition,
)
from human_cos.safety.resimulation import (
    ResimulationSafetyAdmission,
    ResimulationSafetyOutcome,
    ResimulationSafetyResult,
    assert_resimulation_safety_result_binding,
)
from human_cos.scenario.contracts import ScenarioSet
from human_cos.scenario.resimulation import (
    AT17WorldRevisionEvidence,
    ScenarioResimulationPlan,
    ScenarioResimulationResult,
)
from human_cos.world import (
    CausalGraph,
    CriticalReviewPlan,
    ReviewRouteKind,
    ReviewRouteStatus,
    WorldStateSnapshot,
)


class ChallengerContractError(ValueError):
    """Challenger data or progression violates the authorized S7-SCS4 boundary."""


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("S7-SCS4 timestamps require timezone-aware datetimes")
    return value


class _FrozenChallengerModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class ChallengerAttackType(str, Enum):
    FRAMING = "FRAMING"
    EVIDENCE = "EVIDENCE"
    MECHANISM = "MECHANISM"
    SYMMETRY = "SYMMETRY"
    CAPABILITY = "CAPABILITY"
    FALSIFICATION = "FALSIFICATION"


FROZEN_CHALLENGER_ATTACK_TYPES: tuple[ChallengerAttackType, ...] = (
    ChallengerAttackType.FRAMING,
    ChallengerAttackType.EVIDENCE,
    ChallengerAttackType.MECHANISM,
    ChallengerAttackType.SYMMETRY,
    ChallengerAttackType.CAPABILITY,
    ChallengerAttackType.FALSIFICATION,
)


class ChallengerSourceKind(str, Enum):
    CRITICAL_REVIEW_PLAN = "CRITICAL_REVIEW_PLAN"
    CONTROLLER_C_OUTPUT = "CONTROLLER_C_OUTPUT"
    SCENARIO_SET = "SCENARIO_SET"
    RESIMULATION_PLAN = "RESIMULATION_PLAN"
    RESIMULATION_RESULT = "RESIMULATION_RESULT"
    AT17_EVIDENCE = "AT17_EVIDENCE"
    WORLD_STATE = "WORLD_STATE"
    CAUSAL_GRAPH = "CAUSAL_GRAPH"


_FROZEN_SOURCE_KINDS = tuple(ChallengerSourceKind)


class ChallengerSourceRef(_FrozenChallengerModel):
    kind: ChallengerSourceKind
    ref: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ChallengerTaskPayload(_FrozenChallengerModel):
    task_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    pending_s6_route_id: str = Field(min_length=1)
    critical_review_plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    controller_c_output_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    generator_run_id: str = Field(min_length=1)
    generator_context_manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    generator_model_id: str = Field(min_length=1)
    generator_model_family: str = Field(min_length=1)
    generator_provider: str = Field(min_length=1)
    scenario_set_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    resimulation_plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    resimulation_result_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    at17_evidence_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    resulting_world_state_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    resulting_causal_graph_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    resimulation_safety_result_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    requested_challenger_model_id: str = Field(min_length=1)
    requested_challenger_model_family: str = Field(min_length=1)
    requested_challenger_provider: str = Field(min_length=1)
    attack_types: tuple[ChallengerAttackType, ...]
    require_context_independence: Literal[True] = True
    require_model_family_independence: bool = False
    require_provider_independence: bool = False
    require_expert_independence: bool = False
    requested_model_family_independent: bool
    requested_provider_independent: bool
    expert_independent: bool | None = None
    allowed_stage: Literal["ADVERSARIAL_REVIEW"] = "ADVERSARIAL_REVIEW"
    process_authority: Literal[False] = False
    reality_execution_authorized: Literal[False] = False
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class ChallengerTask(ChallengerTaskPayload):
    task_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"task_hash"}, exclude_none=True)
        if self.task_hash != canonical_document_sha256(payload):
            raise ChallengerContractError("ChallengerTask task_hash does not match payload")
        if self.attack_types != FROZEN_CHALLENGER_ATTACK_TYPES:
            raise ChallengerContractError("ChallengerTask must contain the six frozen attack types")
        if self.process_authority or self.reality_execution_authorized:
            raise ChallengerContractError(
                "Challenger Task grants no process or execution authority"
            )
        if self.require_model_family_independence and not self.requested_model_family_independent:
            raise ChallengerContractError("required Challenger model-family independence is absent")
        if self.require_provider_independence and not self.requested_provider_independent:
            raise ChallengerContractError("required Challenger provider independence is absent")
        if self.require_expert_independence and self.expert_independent is not True:
            raise ChallengerContractError("required Challenger expert independence is absent")


class ChallengerSourcePacketPayload(_FrozenChallengerModel):
    packet_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    task_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    pending_s6_route_id: str = Field(min_length=1)
    source_refs: tuple[ChallengerSourceRef, ...]
    prior_challenger_response_hashes: tuple[str, ...] = ()
    independent_required: Literal[True] = True
    allowed_stage: Literal["ADVERSARIAL_REVIEW"] = "ADVERSARIAL_REVIEW"
    process_authority: Literal[False] = False
    reality_execution_authorized: Literal[False] = False
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class ChallengerSourcePacket(ChallengerSourcePacketPayload):
    packet_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"packet_hash"}, exclude_none=True)
        if self.packet_hash != canonical_document_sha256(payload):
            raise ChallengerContractError("ChallengerSourcePacket hash does not match payload")
        if self.prior_challenger_response_hashes:
            raise ChallengerContractError(
                "independent Challenger packet cannot contain other Challenger answers pre-freeze"
            )
        kinds = tuple(item.kind for item in self.source_refs)
        if kinds != _FROZEN_SOURCE_KINDS:
            raise ChallengerContractError(
                "Challenger packet source kinds are incomplete or reordered"
            )
        hashes = tuple(item.sha256 for item in self.source_refs)
        if len(hashes) != len(set(hashes)):
            raise ChallengerContractError("Challenger packet source hashes must be unique")
        if self.process_authority or self.reality_execution_authorized:
            raise ChallengerContractError(
                "Challenger packet grants no process or execution authority"
            )


class ChallengerFindingProposal(_FrozenChallengerModel):
    finding_id: str = Field(min_length=1)
    attack_type: ChallengerAttackType
    statement: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    source_hash_refs: tuple[str, ...] = Field(min_length=1)
    falsifier_refs: tuple[str, ...] = ()
    missing_falsifier_refs: tuple[str, ...] = ()
    wrong_if_candidates: tuple[str, ...] = ()
    blocking: bool
    unresolved: bool
    impact_or_decision_relevance: str | None = None


class ChallengerProposal(_FrozenChallengerModel):
    findings: tuple[ChallengerFindingProposal, ...] = Field(min_length=6)


class ChallengerFindingPayload(_FrozenChallengerModel):
    finding_id: str = Field(min_length=1)
    task_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    packet_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    challenger_run_id: str = Field(min_length=1)
    challenger_model_id: str = Field(min_length=1)
    challenger_model_family: str = Field(min_length=1)
    challenger_provider: str = Field(min_length=1)
    attack_type: ChallengerAttackType
    statement: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    source_hash_refs: tuple[str, ...]
    falsifier_refs: tuple[str, ...] = ()
    missing_falsifier_refs: tuple[str, ...] = ()
    wrong_if_candidates: tuple[str, ...] = ()
    blocking: bool
    unresolved: bool
    impact_or_decision_relevance: str | None = None
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class ChallengerFinding(ChallengerFindingPayload):
    finding_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"finding_hash"}, exclude_none=True)
        if self.finding_hash != canonical_document_sha256(payload):
            raise ChallengerContractError("ChallengerFinding hash does not match payload")
        if not self.source_hash_refs:
            raise ChallengerContractError("every Challenger finding requires exact source hashes")
        if len(self.source_hash_refs) != len(set(self.source_hash_refs)):
            raise ChallengerContractError("Challenger finding source hashes must be unique")
        for name, values in (
            ("falsifier_refs", self.falsifier_refs),
            ("missing_falsifier_refs", self.missing_falsifier_refs),
            ("wrong_if_candidates", self.wrong_if_candidates),
        ):
            if len(values) != len(set(values)):
                raise ChallengerContractError(f"{name} must not contain duplicates")


class ChallengerResponsePayload(_FrozenChallengerModel):
    response_id: str = Field(min_length=1)
    task_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    packet_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    challenger_run_id: str = Field(min_length=1)
    challenger_context_manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    generator_run_id: str = Field(min_length=1)
    generator_context_manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    generator_model_id: str = Field(min_length=1)
    generator_model_family: str = Field(min_length=1)
    generator_provider: str = Field(min_length=1)
    requested_challenger_model_id: str = Field(min_length=1)
    challenger_model_id: str = Field(min_length=1)
    challenger_model_family: str = Field(min_length=1)
    challenger_provider: str = Field(min_length=1)
    fallback_from: str | None = None
    run_independent: Literal[True] = True
    context_independent: Literal[True] = True
    model_family_independent: bool
    provider_independent: bool
    expert_independent: bool | None = None
    raw_output_ref: str = Field(min_length=1)
    raw_output_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    findings: tuple[ChallengerFinding, ...]
    attack_types_covered: tuple[ChallengerAttackType, ...]
    process_authority: Literal[False] = False
    evaluator_authority: Literal[False] = False
    reality_execution_authorized: Literal[False] = False
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class ChallengerResponse(ChallengerResponsePayload):
    response_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"response_hash"}, exclude_none=True)
        if self.response_hash != canonical_document_sha256(payload):
            raise ChallengerContractError("ChallengerResponse hash does not match payload")
        if self.attack_types_covered != FROZEN_CHALLENGER_ATTACK_TYPES:
            raise ChallengerContractError("ChallengerResponse must cover all six frozen attacks")
        finding_ids = tuple(item.finding_id for item in self.findings)
        finding_hashes = tuple(item.finding_hash for item in self.findings)
        if not finding_ids or len(finding_ids) != len(set(finding_ids)):
            raise ChallengerContractError("Challenger findings must have unique identities")
        if len(finding_hashes) != len(set(finding_hashes)):
            raise ChallengerContractError("Challenger finding hashes must be unique")
        if {item.attack_type for item in self.findings} != set(FROZEN_CHALLENGER_ATTACK_TYPES):
            raise ChallengerContractError("Challenger findings do not cover all attack types")
        for finding in self.findings:
            finding.assert_integrity()
            if (
                finding.task_hash,
                finding.packet_hash,
                finding.challenger_run_id,
                finding.challenger_model_id,
                finding.challenger_model_family,
                finding.challenger_provider,
                finding.protocol_version,
                finding.frozen_at,
            ) != (
                self.task_hash,
                self.packet_hash,
                self.challenger_run_id,
                self.challenger_model_id,
                self.challenger_model_family,
                self.challenger_provider,
                self.protocol_version,
                self.frozen_at,
            ):
                raise ChallengerContractError(
                    "Challenger finding identity/qualification lineage differs"
                )
        if self.challenger_run_id == self.generator_run_id:
            raise ChallengerContractError("Scenario generator cannot be its own Challenger Run")
        if self.challenger_context_manifest_hash == self.generator_context_manifest_hash:
            raise ChallengerContractError(
                "Challenger Context must be independent from Controller C"
            )
        if self.challenger_model_id == self.requested_challenger_model_id:
            if self.fallback_from is not None:
                raise ChallengerContractError(
                    "Challenger cannot claim fallback when primary executed"
                )
        elif self.fallback_from != self.requested_challenger_model_id:
            raise ChallengerContractError(
                "Challenger actual model differs without explicit fallback"
            )
        if self.model_family_independent != (
            self.challenger_model_family != self.generator_model_family
        ):
            raise ChallengerContractError(
                "Challenger model-family independence fact is inconsistent"
            )
        if self.provider_independent != (self.challenger_provider != self.generator_provider):
            raise ChallengerContractError("Challenger provider independence fact is inconsistent")
        if self.process_authority or self.evaluator_authority or self.reality_execution_authorized:
            raise ChallengerContractError(
                "Challenger response grants no process/Evaluator authority"
            )


class PendingChallengerSatisfactionPayload(_FrozenChallengerModel):
    satisfaction_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    critical_review_plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    pending_s6_route_id: str = Field(min_length=1)
    challenger_task_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    challenger_packet_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    challenger_response_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    challenger_finding_hashes: tuple[str, ...]
    status: Literal["SATISFIED"] = "SATISFIED"
    blocking_or_unresolved_present: bool
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class PendingChallengerSatisfaction(PendingChallengerSatisfactionPayload):
    satisfaction_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(
            mode="json",
            exclude={"satisfaction_hash"},
            exclude_none=True,
        )
        if self.satisfaction_hash != canonical_document_sha256(payload):
            raise ChallengerContractError("PendingChallengerSatisfaction hash mismatch")
        if not self.challenger_finding_hashes:
            raise ChallengerContractError("Challenger satisfaction requires finding hashes")
        if len(self.challenger_finding_hashes) != len(set(self.challenger_finding_hashes)):
            raise ChallengerContractError("Challenger satisfaction finding hashes must be unique")


class ChallengerReviewOutcome(str, Enum):
    PASS = "PASS"
    BLOCK = "BLOCK"


class ChallengerReviewGateResultPayload(_FrozenChallengerModel):
    gate_result_id: str = Field(min_length=1)
    challenger_response_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    satisfaction_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    outcome: ChallengerReviewOutcome
    blocking_finding_hashes: tuple[str, ...]
    unresolved_finding_hashes: tuple[str, ...]
    six_attack_coverage_complete: Literal[True] = True
    reasons: tuple[str, ...]
    evaluator_score: Literal[None] = None
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class ChallengerReviewGateResult(ChallengerReviewGateResultPayload):
    gate_result_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(
            mode="json",
            exclude={"gate_result_hash"},
            exclude_none=True,
        )
        if self.gate_result_hash != canonical_document_sha256(payload):
            raise ChallengerContractError("ChallengerReviewGateResult hash mismatch")
        for name, values in (
            ("blocking_finding_hashes", self.blocking_finding_hashes),
            ("unresolved_finding_hashes", self.unresolved_finding_hashes),
        ):
            if len(values) != len(set(values)):
                raise ChallengerContractError(f"{name} must not contain duplicates")
        should_block = bool(self.blocking_finding_hashes or self.unresolved_finding_hashes)
        if should_block != (self.outcome is ChallengerReviewOutcome.BLOCK):
            raise ChallengerContractError("Challenger gate outcome does not match frozen findings")
        if not self.reasons:
            raise ChallengerContractError("Challenger gate requires code-owned reasons")


def _assert_position(case: Case, position: CaseRuntimePosition) -> None:
    if case.case_mode != position.mode.value:
        raise ChallengerContractError("Case Mode does not match SCS4 runtime position")
    if case.revision != position.case_revision:
        raise ChallengerContractError("Case revision does not match SCS4 runtime position")
    if position.mode not in {
        CaseMode.LIVE_FORESIGHT,
        CaseMode.MECHANISM_BENCHMARK,
        CaseMode.SCENARIO_STRESS_TEST,
    }:
        raise ChallengerContractError("SCS4 Challenger path excludes HISTORICAL_BLIND_EVAL")
    if position.state is not RuntimeState.SCENARIO_RESIMULATION:
        raise ChallengerContractError("SCS4 admission must freeze at SCENARIO_RESIMULATION")


def _pending_route(plan: CriticalReviewPlan) -> str:
    plan.assert_integrity()
    pending = tuple(
        route.route_id
        for route in plan.routes
        if route.kind is ReviewRouteKind.CHALLENGER and route.status is ReviewRouteStatus.PENDING_S7
    )
    if len(pending) != 1:
        raise ChallengerContractError("SCS4 requires exactly one S6 PENDING_S7 Challenger route")
    return str(pending[0])


def _assert_controller_run_binding(
    *,
    controller_output: ControllerCOutputRecord,
    controller_run: RunManifest,
) -> None:
    controller_output.assert_integrity()
    if controller_run.status != "FROZEN":
        raise ChallengerContractError("Controller C Run must be FROZEN before Challenger admission")
    if controller_run.stage != RuntimeState.SCENARIO_GENERATION.value:
        raise ChallengerContractError("Controller C Run stage is not SCENARIO_GENERATION")
    if controller_run.structured_output_hash != controller_output.output_hash:
        raise ChallengerContractError("Controller C Run does not bind exact Controller C output")
    if (
        controller_run.model_id,
        controller_run.model_family,
        controller_run.provider,
        controller_run.protocol_version,
    ) != (
        controller_output.controller_model_id,
        controller_output.controller_model_family,
        controller_output.controller_provider,
        controller_output.protocol_version,
    ):
        raise ChallengerContractError("Controller C Run identity/protocol differs from output")


def _assert_safety_scs3_binding(
    *,
    case: Case,
    scenario_set: ScenarioSet,
    resimulation_plan: ScenarioResimulationPlan,
    safety_admission: ResimulationSafetyAdmission,
    safety_result: ResimulationSafetyResult,
) -> None:
    assert_resimulation_safety_result_binding(safety_admission, safety_result)
    if (
        safety_admission.case_id,
        safety_admission.case_revision,
        safety_admission.scenario_set_hash,
        safety_admission.scenario_path_hash,
        safety_admission.intervention_hash,
        safety_admission.parent_world_state_hash,
        safety_admission.parent_causal_graph_hash,
        safety_admission.protocol_version,
    ) != (
        case.case_id,
        case.revision,
        scenario_set.scenario_set_hash,
        resimulation_plan.scenario_path_hash,
        resimulation_plan.intervention_hash,
        resimulation_plan.parent_world_state_hash,
        resimulation_plan.parent_causal_graph_hash,
        case.protocol_version,
    ):
        raise ChallengerContractError("SCS4 Safety admission does not bind exact SCS3 scenario")
    if (
        resimulation_plan.resimulation_safety_admission_hash,
        resimulation_plan.resimulation_safety_result_hash,
    ) != (safety_admission.admission_hash, safety_result.result_hash):
        raise ChallengerContractError("SCS4 Safety lineage differs from re-simulation plan")
    if safety_result.outcome is not ResimulationSafetyOutcome.PASS:
        raise ChallengerContractError("SCS4 Challenger path requires re-simulation Safety PASS")


def _assert_result_at17_binding(
    *,
    case: Case,
    resimulation_plan: ScenarioResimulationPlan,
    resimulation_result: ScenarioResimulationResult,
    at17: AT17WorldRevisionEvidence,
    world_state: WorldStateSnapshot,
    causal_graph: CausalGraph,
) -> None:
    if (
        resimulation_result.plan_hash,
        resimulation_result.scenario_set_hash,
        resimulation_result.scenario_path_hash,
        resimulation_result.intervention_hash,
        resimulation_result.parent_world_state_hash,
        resimulation_result.parent_causal_graph_hash,
    ) != (
        resimulation_plan.plan_hash,
        resimulation_plan.scenario_set_hash,
        resimulation_plan.scenario_path_hash,
        resimulation_plan.intervention_hash,
        resimulation_plan.parent_world_state_hash,
        resimulation_plan.parent_causal_graph_hash,
    ):
        raise ChallengerContractError("re-simulation result does not bind exact frozen plan")
    if at17.resimulation_result_hash != resimulation_result.result_hash:
        raise ChallengerContractError("AT-17 does not bind exact re-simulation result")
    if at17.protocol_version != case.protocol_version:
        raise ChallengerContractError("AT-17 protocol differs from Case protocol")
    if (
        at17.parent_world_state_hash,
        at17.parent_causal_graph_hash,
        at17.resulting_world_state_hash,
        at17.resulting_causal_graph_hash,
    ) != (
        resimulation_result.parent_world_state_hash,
        resimulation_result.parent_causal_graph_hash,
        resimulation_result.resulting_world_state_hash,
        resimulation_result.resulting_causal_graph_hash,
    ):
        raise ChallengerContractError(
            "AT-17 World/Causal lineage differs from re-simulation result"
        )
    if (
        world_state.world_state_hash,
        causal_graph.graph_hash,
        world_state.causal_graph_hash,
        world_state.parent_world_state_hash,
        causal_graph.parent_graph_hash,
        world_state.revision,
        causal_graph.revision,
    ) != (
        at17.resulting_world_state_hash,
        at17.resulting_causal_graph_hash,
        at17.resulting_causal_graph_hash,
        at17.parent_world_state_hash,
        at17.parent_causal_graph_hash,
        at17.resulting_world_revision,
        at17.resulting_causal_revision,
    ):
        raise ChallengerContractError("final World/Causal revisions differ from AT-17 evidence")
    if resimulation_result.at17_runtime_revision_complete is not True or at17.status != "PASS":
        raise ChallengerContractError("SCS4 requires completed AT-17 runtime revision evidence")


def _assert_source_binding(
    *,
    case: Case,
    critical_review_plan: CriticalReviewPlan,
    controller_output: ControllerCOutputRecord,
    controller_run: RunManifest,
    scenario_set: ScenarioSet,
    resimulation_plan: ScenarioResimulationPlan,
    resimulation_result: ScenarioResimulationResult,
    at17: AT17WorldRevisionEvidence,
    world_state: WorldStateSnapshot,
    causal_graph: CausalGraph,
    safety_admission: ResimulationSafetyAdmission,
    safety_result: ResimulationSafetyResult,
) -> str:
    critical_review_plan.assert_integrity()
    controller_output.assert_integrity()
    scenario_set.assert_integrity()
    resimulation_plan.assert_integrity()
    resimulation_result.assert_integrity()
    at17.assert_integrity()
    world_state.assert_integrity()
    causal_graph.assert_integrity()
    _assert_controller_run_binding(
        controller_output=controller_output,
        controller_run=controller_run,
    )
    pending_route_id = _pending_route(critical_review_plan)

    expected_case = (case.case_id, case.revision, case.protocol_version)
    source_case_bindings = (
        (
            "CriticalReviewPlan",
            (
                critical_review_plan.case_id,
                critical_review_plan.case_revision,
                critical_review_plan.protocol_version,
            ),
        ),
        (
            "ControllerCOutput",
            (
                controller_output.case_id,
                controller_output.case_revision,
                controller_output.protocol_version,
            ),
        ),
        (
            "ScenarioSet",
            (
                scenario_set.case_id,
                scenario_set.case_revision,
                scenario_set.protocol_version,
            ),
        ),
        (
            "ResimulationPlan",
            (
                resimulation_plan.case_id,
                resimulation_plan.case_revision,
                resimulation_plan.protocol_version,
            ),
        ),
        (
            "ResimulationResult",
            (
                resimulation_result.case_id,
                resimulation_result.case_revision,
                resimulation_result.protocol_version,
            ),
        ),
        (
            "WorldState",
            (
                world_state.case_id,
                world_state.case_revision,
                world_state.protocol_version,
            ),
        ),
        (
            "CausalGraph",
            (
                causal_graph.case_id,
                causal_graph.case_revision,
                causal_graph.protocol_version,
            ),
        ),
    )
    for label, actual in source_case_bindings:
        if actual != expected_case:
            raise ChallengerContractError(f"{label} Case/revision/protocol binding mismatch")

    if controller_output.scenario_set_hash != scenario_set.scenario_set_hash:
        raise ChallengerContractError("Controller C output does not bind exact ScenarioSet")
    if resimulation_plan.controller_c_output_hash != controller_output.output_hash:
        raise ChallengerContractError("re-simulation plan does not bind exact Controller C output")
    if resimulation_plan.scenario_set_hash != scenario_set.scenario_set_hash:
        raise ChallengerContractError("re-simulation plan does not bind exact ScenarioSet")
    _assert_safety_scs3_binding(
        case=case,
        scenario_set=scenario_set,
        resimulation_plan=resimulation_plan,
        safety_admission=safety_admission,
        safety_result=safety_result,
    )
    _assert_result_at17_binding(
        case=case,
        resimulation_plan=resimulation_plan,
        resimulation_result=resimulation_result,
        at17=at17,
        world_state=world_state,
        causal_graph=causal_graph,
    )
    if pending_route_id not in controller_output.pending_challenger_route_ids:
        raise ChallengerContractError("Controller C output lost S6 PENDING_S7 Challenger route")
    if pending_route_id not in resimulation_plan.pending_challenger_route_ids:
        raise ChallengerContractError("re-simulation plan lost S6 PENDING_S7 Challenger route")
    if pending_route_id not in resimulation_result.pending_challenger_route_ids:
        raise ChallengerContractError("re-simulation result lost S6 PENDING_S7 Challenger route")
    if world_state.dissent_node_hashes != resimulation_result.preserved_dissent_node_hashes:
        raise ChallengerContractError("SCS4 resulting WorldState changed preserved dissent lineage")
    return pending_route_id


def build_challenger_task(
    *,
    case: Case,
    position: CaseRuntimePosition,
    qualification: QualificationGate,
    challenger_model_id: str,
    critical_review_plan: CriticalReviewPlan,
    controller_output: ControllerCOutputRecord,
    controller_run: RunManifest,
    scenario_set: ScenarioSet,
    resimulation_plan: ScenarioResimulationPlan,
    resimulation_result: ScenarioResimulationResult,
    at17: AT17WorldRevisionEvidence,
    world_state: WorldStateSnapshot,
    causal_graph: CausalGraph,
    safety_admission: ResimulationSafetyAdmission,
    safety_result: ResimulationSafetyResult,
    task_id: str,
    frozen_at: datetime,
    require_model_family_independence: bool = False,
    require_provider_independence: bool = False,
    require_expert_independence: bool = False,
    expert_independent: bool | None = None,
) -> ChallengerTask:
    _assert_position(case, position)
    pending_route_id = _assert_source_binding(
        case=case,
        critical_review_plan=critical_review_plan,
        controller_output=controller_output,
        controller_run=controller_run,
        scenario_set=scenario_set,
        resimulation_plan=resimulation_plan,
        resimulation_result=resimulation_result,
        at17=at17,
        world_state=world_state,
        causal_graph=causal_graph,
        safety_admission=safety_admission,
        safety_result=safety_result,
    )
    profile = qualification.assert_challenger_eligible(challenger_model_id)
    source_times = (
        critical_review_plan.frozen_at,
        controller_output.frozen_at,
        resimulation_plan.frozen_at,
        resimulation_result.frozen_at,
        at17.frozen_at,
        world_state.frozen_at,
        causal_graph.frozen_at,
        safety_result.frozen_at,
    )
    if frozen_at < max(source_times):
        raise ChallengerContractError("Challenger Task cannot freeze before its source lineage")
    family_independent = profile.model_family != controller_output.controller_model_family
    provider_independent = profile.provider != controller_output.controller_provider
    payload = ChallengerTaskPayload(
        task_id=task_id,
        case_id=case.case_id,
        case_revision=case.revision,
        pending_s6_route_id=pending_route_id,
        critical_review_plan_hash=critical_review_plan.plan_hash,
        controller_c_output_hash=controller_output.output_hash,
        generator_run_id=controller_run.run_id,
        generator_context_manifest_hash=controller_run.context_manifest_hash,
        generator_model_id=controller_output.controller_model_id,
        generator_model_family=controller_output.controller_model_family,
        generator_provider=controller_output.controller_provider,
        scenario_set_hash=scenario_set.scenario_set_hash,
        resimulation_plan_hash=resimulation_plan.plan_hash,
        resimulation_result_hash=resimulation_result.result_hash,
        at17_evidence_hash=at17.evidence_hash,
        resulting_world_state_hash=world_state.world_state_hash,
        resulting_causal_graph_hash=causal_graph.graph_hash,
        resimulation_safety_result_hash=safety_result.result_hash,
        requested_challenger_model_id=profile.model_id,
        requested_challenger_model_family=profile.model_family,
        requested_challenger_provider=profile.provider,
        attack_types=FROZEN_CHALLENGER_ATTACK_TYPES,
        require_model_family_independence=require_model_family_independence,
        require_provider_independence=require_provider_independence,
        require_expert_independence=require_expert_independence,
        requested_model_family_independent=family_independent,
        requested_provider_independent=provider_independent,
        expert_independent=expert_independent,
        protocol_version=case.protocol_version,
        frozen_at=frozen_at,
    )
    document = payload.to_document()
    task = ChallengerTask(**document, task_hash=canonical_document_sha256(document))
    task.assert_integrity()
    return task


def assert_challenger_task_binding(
    *,
    task: ChallengerTask,
    case: Case,
    position: CaseRuntimePosition,
    qualification: QualificationGate,
    critical_review_plan: CriticalReviewPlan,
    controller_output: ControllerCOutputRecord,
    controller_run: RunManifest,
    scenario_set: ScenarioSet,
    resimulation_plan: ScenarioResimulationPlan,
    resimulation_result: ScenarioResimulationResult,
    at17: AT17WorldRevisionEvidence,
    world_state: WorldStateSnapshot,
    causal_graph: CausalGraph,
    safety_admission: ResimulationSafetyAdmission,
    safety_result: ResimulationSafetyResult,
) -> None:
    task.assert_integrity()
    _assert_position(case, position)
    pending_route_id = _assert_source_binding(
        case=case,
        critical_review_plan=critical_review_plan,
        controller_output=controller_output,
        controller_run=controller_run,
        scenario_set=scenario_set,
        resimulation_plan=resimulation_plan,
        resimulation_result=resimulation_result,
        at17=at17,
        world_state=world_state,
        causal_graph=causal_graph,
        safety_admission=safety_admission,
        safety_result=safety_result,
    )
    profile = qualification.assert_challenger_eligible(task.requested_challenger_model_id)
    expected = (
        case.case_id,
        case.revision,
        pending_route_id,
        critical_review_plan.plan_hash,
        controller_output.output_hash,
        controller_run.run_id,
        controller_run.context_manifest_hash,
        controller_output.controller_model_id,
        controller_output.controller_model_family,
        controller_output.controller_provider,
        scenario_set.scenario_set_hash,
        resimulation_plan.plan_hash,
        resimulation_result.result_hash,
        at17.evidence_hash,
        world_state.world_state_hash,
        causal_graph.graph_hash,
        safety_result.result_hash,
        profile.model_id,
        profile.model_family,
        profile.provider,
        case.protocol_version,
    )
    actual = (
        task.case_id,
        task.case_revision,
        task.pending_s6_route_id,
        task.critical_review_plan_hash,
        task.controller_c_output_hash,
        task.generator_run_id,
        task.generator_context_manifest_hash,
        task.generator_model_id,
        task.generator_model_family,
        task.generator_provider,
        task.scenario_set_hash,
        task.resimulation_plan_hash,
        task.resimulation_result_hash,
        task.at17_evidence_hash,
        task.resulting_world_state_hash,
        task.resulting_causal_graph_hash,
        task.resimulation_safety_result_hash,
        task.requested_challenger_model_id,
        task.requested_challenger_model_family,
        task.requested_challenger_provider,
        task.protocol_version,
    )
    if actual != expected:
        raise ChallengerContractError("Challenger Task source/qualification binding mismatch")
    family_independent = profile.model_family != controller_output.controller_model_family
    provider_independent = profile.provider != controller_output.controller_provider
    if task.requested_model_family_independent != family_independent:
        raise ChallengerContractError("Challenger model-family independence fact changed")
    if task.requested_provider_independent != provider_independent:
        raise ChallengerContractError("Challenger provider independence fact changed")


def _assert_packet_source_objects(
    *,
    critical_review_plan: CriticalReviewPlan,
    controller_output: ControllerCOutputRecord,
    scenario_set: ScenarioSet,
    resimulation_plan: ScenarioResimulationPlan,
    resimulation_result: ScenarioResimulationResult,
    at17: AT17WorldRevisionEvidence,
    world_state: WorldStateSnapshot,
    causal_graph: CausalGraph,
) -> None:
    critical_review_plan.assert_integrity()
    controller_output.assert_integrity()
    scenario_set.assert_integrity()
    resimulation_plan.assert_integrity()
    resimulation_result.assert_integrity()
    at17.assert_integrity()
    world_state.assert_integrity()
    causal_graph.assert_integrity()


def build_challenger_source_packet(
    *,
    task: ChallengerTask,
    critical_review_plan: CriticalReviewPlan,
    controller_output: ControllerCOutputRecord,
    scenario_set: ScenarioSet,
    resimulation_plan: ScenarioResimulationPlan,
    resimulation_result: ScenarioResimulationResult,
    at17: AT17WorldRevisionEvidence,
    world_state: WorldStateSnapshot,
    causal_graph: CausalGraph,
    packet_id: str,
    frozen_at: datetime,
) -> ChallengerSourcePacket:
    task.assert_integrity()
    _assert_packet_source_objects(
        critical_review_plan=critical_review_plan,
        controller_output=controller_output,
        scenario_set=scenario_set,
        resimulation_plan=resimulation_plan,
        resimulation_result=resimulation_result,
        at17=at17,
        world_state=world_state,
        causal_graph=causal_graph,
    )
    if frozen_at < task.frozen_at:
        raise ChallengerContractError("Challenger packet cannot freeze before Challenger Task")
    refs = (
        ChallengerSourceRef(
            kind=ChallengerSourceKind.CRITICAL_REVIEW_PLAN,
            ref=f"critical-review-plan:{critical_review_plan.plan_id}",
            sha256=critical_review_plan.plan_hash,
        ),
        ChallengerSourceRef(
            kind=ChallengerSourceKind.CONTROLLER_C_OUTPUT,
            ref=f"controller-c-output:{controller_output.output_id}",
            sha256=controller_output.output_hash,
        ),
        ChallengerSourceRef(
            kind=ChallengerSourceKind.SCENARIO_SET,
            ref=f"scenario-set:{scenario_set.scenario_set_id}",
            sha256=scenario_set.scenario_set_hash,
        ),
        ChallengerSourceRef(
            kind=ChallengerSourceKind.RESIMULATION_PLAN,
            ref=f"resimulation-plan:{resimulation_plan.plan_id}",
            sha256=resimulation_plan.plan_hash,
        ),
        ChallengerSourceRef(
            kind=ChallengerSourceKind.RESIMULATION_RESULT,
            ref=f"resimulation-result:{resimulation_result.result_id}",
            sha256=resimulation_result.result_hash,
        ),
        ChallengerSourceRef(
            kind=ChallengerSourceKind.AT17_EVIDENCE,
            ref=f"at17:{at17.evidence_id}",
            sha256=at17.evidence_hash,
        ),
        ChallengerSourceRef(
            kind=ChallengerSourceKind.WORLD_STATE,
            ref=f"world-state:{world_state.world_state_id}",
            sha256=world_state.world_state_hash,
        ),
        ChallengerSourceRef(
            kind=ChallengerSourceKind.CAUSAL_GRAPH,
            ref=f"causal-graph:{causal_graph.graph_id}",
            sha256=causal_graph.graph_hash,
        ),
    )
    expected_hashes = (
        task.critical_review_plan_hash,
        task.controller_c_output_hash,
        task.scenario_set_hash,
        task.resimulation_plan_hash,
        task.resimulation_result_hash,
        task.at17_evidence_hash,
        task.resulting_world_state_hash,
        task.resulting_causal_graph_hash,
    )
    if tuple(item.sha256 for item in refs) != expected_hashes:
        raise ChallengerContractError("Challenger packet sources differ from frozen Task")
    payload = ChallengerSourcePacketPayload(
        packet_id=packet_id,
        case_id=task.case_id,
        case_revision=task.case_revision,
        task_hash=task.task_hash,
        pending_s6_route_id=task.pending_s6_route_id,
        source_refs=refs,
        protocol_version=task.protocol_version,
        frozen_at=frozen_at,
    )
    document = payload.to_document()
    packet = ChallengerSourcePacket(**document, packet_hash=canonical_document_sha256(document))
    packet.assert_integrity()
    return packet


def assert_challenger_packet_binding(
    *,
    task: ChallengerTask,
    packet: ChallengerSourcePacket,
) -> None:
    task.assert_integrity()
    packet.assert_integrity()
    if (
        packet.case_id,
        packet.case_revision,
        packet.task_hash,
        packet.pending_s6_route_id,
        packet.protocol_version,
    ) != (
        task.case_id,
        task.case_revision,
        task.task_hash,
        task.pending_s6_route_id,
        task.protocol_version,
    ):
        raise ChallengerContractError("Challenger packet does not bind exact Task")
    expected_hashes = (
        task.critical_review_plan_hash,
        task.controller_c_output_hash,
        task.scenario_set_hash,
        task.resimulation_plan_hash,
        task.resimulation_result_hash,
        task.at17_evidence_hash,
        task.resulting_world_state_hash,
        task.resulting_causal_graph_hash,
    )
    if tuple(item.sha256 for item in packet.source_refs) != expected_hashes:
        raise ChallengerContractError("Challenger packet source hashes differ from Task")


def freeze_challenger_response(
    *,
    task: ChallengerTask,
    packet: ChallengerSourcePacket,
    proposal: ChallengerProposal,
    qualification: QualificationGate,
    challenger_run_id: str,
    challenger_context_manifest_hash: str,
    actual_model_id: str,
    fallback_from: str | None,
    raw_output_ref: str,
    raw_output_hash: str,
    response_id: str,
    frozen_at: datetime,
) -> ChallengerResponse:
    task.assert_integrity()
    assert_challenger_packet_binding(task=task, packet=packet)
    if frozen_at < packet.frozen_at:
        raise ChallengerContractError("Challenger response cannot freeze before its source packet")
    if challenger_run_id == task.generator_run_id:
        raise ChallengerContractError("Scenario generator cannot be its own sole Challenger Run")
    if challenger_context_manifest_hash == task.generator_context_manifest_hash:
        raise ChallengerContractError("Challenger Context is not independent from Controller C")
    profile = qualification.assert_challenger_eligible(actual_model_id)
    if actual_model_id == task.requested_challenger_model_id:
        if fallback_from is not None:
            raise ChallengerContractError("primary Challenger execution cannot claim fallback")
    elif fallback_from != task.requested_challenger_model_id:
        raise ChallengerContractError("actual Challenger model differs without explicit fallback")
    family_independent = profile.model_family != task.generator_model_family
    provider_independent = profile.provider != task.generator_provider
    if task.require_model_family_independence and not family_independent:
        raise ChallengerContractError(
            "actual Challenger violates required model-family independence"
        )
    if task.require_provider_independence and not provider_independent:
        raise ChallengerContractError("actual Challenger violates required provider independence")
    if task.require_expert_independence and task.expert_independent is not True:
        raise ChallengerContractError("actual Challenger lacks required expert independence")
    source_hashes = {item.sha256 for item in packet.source_refs}
    finding_ids = tuple(item.finding_id for item in proposal.findings)
    if len(finding_ids) != len(set(finding_ids)):
        raise ChallengerContractError("Challenger proposal finding IDs must be unique")
    if {item.attack_type for item in proposal.findings} != set(FROZEN_CHALLENGER_ATTACK_TYPES):
        raise ChallengerContractError("Challenger proposal must cover all six frozen attack types")
    order = {attack: index for index, attack in enumerate(FROZEN_CHALLENGER_ATTACK_TYPES)}
    frozen_findings: list[ChallengerFinding] = []
    for item in proposal.findings:
        if not item.source_hash_refs or not set(item.source_hash_refs).issubset(source_hashes):
            raise ChallengerContractError(
                "Challenger finding references source hash outside packet"
            )
        finding_payload = ChallengerFindingPayload(
            finding_id=item.finding_id,
            task_hash=task.task_hash,
            packet_hash=packet.packet_hash,
            challenger_run_id=challenger_run_id,
            challenger_model_id=profile.model_id,
            challenger_model_family=profile.model_family,
            challenger_provider=profile.provider,
            attack_type=item.attack_type,
            statement=item.statement,
            rationale=item.rationale,
            source_hash_refs=item.source_hash_refs,
            falsifier_refs=item.falsifier_refs,
            missing_falsifier_refs=item.missing_falsifier_refs,
            wrong_if_candidates=item.wrong_if_candidates,
            blocking=item.blocking,
            unresolved=item.unresolved,
            impact_or_decision_relevance=item.impact_or_decision_relevance,
            protocol_version=task.protocol_version,
            frozen_at=frozen_at,
        )
        document = finding_payload.to_document()
        finding = ChallengerFinding(
            **document,
            finding_hash=canonical_document_sha256(document),
        )
        finding.assert_integrity()
        frozen_findings.append(finding)
    frozen_findings.sort(key=lambda item: (order[item.attack_type], item.finding_id))
    covered = tuple(
        attack
        for attack in FROZEN_CHALLENGER_ATTACK_TYPES
        if any(item.attack_type is attack for item in frozen_findings)
    )
    response_payload = ChallengerResponsePayload(
        response_id=response_id,
        task_hash=task.task_hash,
        packet_hash=packet.packet_hash,
        case_id=task.case_id,
        case_revision=task.case_revision,
        challenger_run_id=challenger_run_id,
        challenger_context_manifest_hash=challenger_context_manifest_hash,
        generator_run_id=task.generator_run_id,
        generator_context_manifest_hash=task.generator_context_manifest_hash,
        generator_model_id=task.generator_model_id,
        generator_model_family=task.generator_model_family,
        generator_provider=task.generator_provider,
        requested_challenger_model_id=task.requested_challenger_model_id,
        challenger_model_id=profile.model_id,
        challenger_model_family=profile.model_family,
        challenger_provider=profile.provider,
        fallback_from=fallback_from,
        model_family_independent=family_independent,
        provider_independent=provider_independent,
        expert_independent=task.expert_independent,
        raw_output_ref=raw_output_ref,
        raw_output_hash=raw_output_hash,
        findings=tuple(frozen_findings),
        attack_types_covered=covered,
        protocol_version=task.protocol_version,
        frozen_at=frozen_at,
    )
    document = response_payload.to_document()
    response = ChallengerResponse(**document, response_hash=canonical_document_sha256(document))
    response.assert_integrity()
    return response


def freeze_pending_challenger_satisfaction(
    *,
    critical_review_plan: CriticalReviewPlan,
    task: ChallengerTask,
    packet: ChallengerSourcePacket,
    response: ChallengerResponse,
    satisfaction_id: str,
    frozen_at: datetime,
) -> PendingChallengerSatisfaction:
    critical_review_plan.assert_integrity()
    task.assert_integrity()
    assert_challenger_packet_binding(task=task, packet=packet)
    response.assert_integrity()
    if frozen_at < response.frozen_at:
        raise ChallengerContractError(
            "Challenger satisfaction cannot freeze before Challenger response"
        )
    pending_route_id = _pending_route(critical_review_plan)
    if (
        task.critical_review_plan_hash,
        task.pending_s6_route_id,
        response.task_hash,
        response.packet_hash,
    ) != (
        critical_review_plan.plan_hash,
        pending_route_id,
        task.task_hash,
        packet.packet_hash,
    ):
        raise ChallengerContractError("S6 pending Challenger satisfaction lineage mismatch")
    finding_hashes = tuple(item.finding_hash for item in response.findings)
    blocked = any(item.blocking or item.unresolved for item in response.findings)
    payload = PendingChallengerSatisfactionPayload(
        satisfaction_id=satisfaction_id,
        case_id=task.case_id,
        case_revision=task.case_revision,
        critical_review_plan_hash=critical_review_plan.plan_hash,
        pending_s6_route_id=pending_route_id,
        challenger_task_hash=task.task_hash,
        challenger_packet_hash=packet.packet_hash,
        challenger_response_hash=response.response_hash,
        challenger_finding_hashes=finding_hashes,
        blocking_or_unresolved_present=blocked,
        protocol_version=task.protocol_version,
        frozen_at=frozen_at,
    )
    document = payload.to_document()
    satisfaction = PendingChallengerSatisfaction(
        **document,
        satisfaction_hash=canonical_document_sha256(document),
    )
    satisfaction.assert_integrity()
    return satisfaction


def evaluate_challenger_review_gate(
    *,
    response: ChallengerResponse,
    satisfaction: PendingChallengerSatisfaction,
    gate_result_id: str,
    frozen_at: datetime,
) -> ChallengerReviewGateResult:
    response.assert_integrity()
    satisfaction.assert_integrity()
    if frozen_at < satisfaction.frozen_at:
        raise ChallengerContractError("Challenger gate cannot freeze before satisfaction sidecar")
    if satisfaction.challenger_response_hash != response.response_hash:
        raise ChallengerContractError("Challenger gate satisfaction/response mismatch")
    response_finding_hashes = tuple(item.finding_hash for item in response.findings)
    if satisfaction.challenger_finding_hashes != response_finding_hashes:
        raise ChallengerContractError("Challenger satisfaction finding set differs from response")
    blocking = tuple(item.finding_hash for item in response.findings if item.blocking)
    unresolved = tuple(item.finding_hash for item in response.findings if item.unresolved)
    frozen_block_state = bool(blocking or unresolved)
    if satisfaction.blocking_or_unresolved_present != frozen_block_state:
        raise ChallengerContractError(
            "Challenger satisfaction blocking state differs from response"
        )
    outcome = ChallengerReviewOutcome.BLOCK if frozen_block_state else ChallengerReviewOutcome.PASS
    reasons: list[str] = []
    if blocking:
        reasons.append("one or more frozen Challenger findings are explicitly blocking")
    if unresolved:
        reasons.append("one or more frozen Challenger findings remain unresolved")
    if not reasons:
        reasons.append("all six frozen Challenger attack families completed without blocking state")
    payload = ChallengerReviewGateResultPayload(
        gate_result_id=gate_result_id,
        challenger_response_hash=response.response_hash,
        satisfaction_hash=satisfaction.satisfaction_hash,
        outcome=outcome,
        blocking_finding_hashes=blocking,
        unresolved_finding_hashes=unresolved,
        reasons=tuple(reasons),
        protocol_version=response.protocol_version,
        frozen_at=frozen_at,
    )
    document = payload.to_document()
    result = ChallengerReviewGateResult(
        **document,
        gate_result_hash=canonical_document_sha256(document),
    )
    result.assert_integrity()
    return result


def assert_challenger_clear_for_downstream(result: ChallengerReviewGateResult) -> None:
    """Fail closed for any future downstream grant; SCS4 does not grant that edge."""
    result.assert_integrity()
    if result.outcome is ChallengerReviewOutcome.BLOCK:
        raise ChallengerContractError("unresolved/blocking Challenger finding prevents progression")


_S7_COMMON_MODES = (
    CaseMode.LIVE_FORESIGHT,
    CaseMode.MECHANISM_BENCHMARK,
    CaseMode.SCENARIO_STRESS_TEST,
)

S7_SCS4_TRANSITIONS: frozenset[TransitionKey] = frozenset(
    TransitionKey(
        mode,
        RuntimeState.SCENARIO_RESIMULATION,
        RuntimeState.ADVERSARIAL_REVIEW,
    )
    for mode in _S7_COMMON_MODES
)


def _guard(name: str, passed: bool | None, reason: str) -> GuardCheck:
    if passed is None:
        return GuardCheck(name, GuardStatus.UNAVAILABLE, reason)
    if passed:
        return GuardCheck(name, GuardStatus.PASS, reason)
    return GuardCheck(name, GuardStatus.FAIL, reason)


def _with_guard(
    base: TransitionDecision,
    guard: GuardCheck,
    *,
    reason: str,
) -> TransitionDecision:
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
        reason=reason,
    )


def can_s7_scs4_transition(
    position: CaseRuntimePosition,
    target: RuntimeState,
    *,
    case: Case | None = None,
    task: ChallengerTask | None = None,
    packet: ChallengerSourcePacket | None = None,
    qualification: QualificationGate | None = None,
    critical_review_plan: CriticalReviewPlan | None = None,
    controller_output: ControllerCOutputRecord | None = None,
    controller_run: RunManifest | None = None,
    scenario_set: ScenarioSet | None = None,
    resimulation_plan: ScenarioResimulationPlan | None = None,
    resimulation_result: ScenarioResimulationResult | None = None,
    at17: AT17WorldRevisionEvidence | None = None,
    world_state: WorldStateSnapshot | None = None,
    causal_graph: CausalGraph | None = None,
    safety_admission: ResimulationSafetyAdmission | None = None,
    safety_result: ResimulationSafetyResult | None = None,
) -> TransitionDecision:
    """Authorize only SCENARIO_RESIMULATION -> ADVERSARIAL_REVIEW admission."""
    base = can_transition(
        position,
        target,
        authorized_future_transitions=S7_SCS4_TRANSITIONS,
    )
    if not base.allowed:
        return base
    required = (
        case,
        task,
        packet,
        qualification,
        critical_review_plan,
        controller_output,
        controller_run,
        scenario_set,
        resimulation_plan,
        resimulation_result,
        at17,
        world_state,
        causal_graph,
        safety_admission,
        safety_result,
    )
    if any(item is None for item in required):
        return _with_guard(
            base,
            _guard(
                "challenger_admission_frozen",
                None,
                (
                    "exact S6/SCS3/AT-17/Safety lineage and qualified Challenger "
                    "task/packet are required"
                ),
            ),
            reason="S7-SCS4 Challenger admission prerequisite was not satisfied",
        )
    assert case is not None
    assert task is not None
    assert packet is not None
    assert qualification is not None
    assert critical_review_plan is not None
    assert controller_output is not None
    assert controller_run is not None
    assert scenario_set is not None
    assert resimulation_plan is not None
    assert resimulation_result is not None
    assert at17 is not None
    assert world_state is not None
    assert causal_graph is not None
    assert safety_admission is not None
    assert safety_result is not None
    try:
        assert_challenger_task_binding(
            task=task,
            case=case,
            position=position,
            qualification=qualification,
            critical_review_plan=critical_review_plan,
            controller_output=controller_output,
            controller_run=controller_run,
            scenario_set=scenario_set,
            resimulation_plan=resimulation_plan,
            resimulation_result=resimulation_result,
            at17=at17,
            world_state=world_state,
            causal_graph=causal_graph,
            safety_admission=safety_admission,
            safety_result=safety_result,
        )
        assert_challenger_packet_binding(task=task, packet=packet)
        if task.case_revision != position.case_revision:
            raise ChallengerContractError("Challenger Task Case revision mismatch")
        if task.protocol_version != base.protocol_version:
            raise ChallengerContractError("Challenger Task protocol mismatch")
    except (ValueError, PermissionError, KeyError) as exc:
        return _with_guard(
            base,
            _guard("challenger_admission_frozen", False, str(exc)),
            reason="S7-SCS4 Challenger admission prerequisite was not satisfied",
        )
    return _with_guard(
        base,
        _guard(
            "challenger_admission_frozen",
            True,
            (
                "qualified independent Challenger task/packet is frozen over exact "
                "SCS3 AT-17/Safety lineage"
            ),
        ),
        reason="S7-SCS4 Challenger admission prerequisite was not satisfied",
    )


def transition_s7_scs4(
    position: CaseRuntimePosition,
    target: RuntimeState,
    *,
    case: Case | None = None,
    task: ChallengerTask | None = None,
    packet: ChallengerSourcePacket | None = None,
    qualification: QualificationGate | None = None,
    critical_review_plan: CriticalReviewPlan | None = None,
    controller_output: ControllerCOutputRecord | None = None,
    controller_run: RunManifest | None = None,
    scenario_set: ScenarioSet | None = None,
    resimulation_plan: ScenarioResimulationPlan | None = None,
    resimulation_result: ScenarioResimulationResult | None = None,
    at17: AT17WorldRevisionEvidence | None = None,
    world_state: WorldStateSnapshot | None = None,
    causal_graph: CausalGraph | None = None,
    safety_admission: ResimulationSafetyAdmission | None = None,
    safety_result: ResimulationSafetyResult | None = None,
) -> TransitionResult:
    decision = can_s7_scs4_transition(
        position,
        target,
        case=case,
        task=task,
        packet=packet,
        qualification=qualification,
        critical_review_plan=critical_review_plan,
        controller_output=controller_output,
        controller_run=controller_run,
        scenario_set=scenario_set,
        resimulation_plan=resimulation_plan,
        resimulation_result=resimulation_result,
        at17=at17,
        world_state=world_state,
        causal_graph=causal_graph,
        safety_admission=safety_admission,
        safety_result=safety_result,
    )
    if not decision.allowed:
        raise TransitionRejected(decision)
    return TransitionResult(
        position=CaseRuntimePosition(
            mode=position.mode,
            state=target,
            case_revision=position.case_revision,
        ),
        decision=decision,
    )
