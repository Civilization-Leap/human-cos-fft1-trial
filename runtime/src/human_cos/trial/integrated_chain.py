"""Installed SBX5 exercise of the real S5--S8 application and storage surfaces."""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from psycopg import Connection, sql

from human_cos.challengers import (
    FROZEN_CHALLENGER_ATTACK_TYPES,
    ChallengerAttackType,
    ChallengerExecutor,
    ChallengerFindingProposal,
    ChallengerProposal,
    ChallengerRunTask,
    ChallengerSourceBundle,
    build_challenger_source_packet,
    build_challenger_task,
    evaluate_challenger_review_gate,
    freeze_pending_challenger_satisfaction,
    transition_s7_scs4,
)
from human_cos.controllers.activation import transition_s5_cde3
from human_cos.controllers.critical_integration import (
    CriticalIntegrationContent,
    CriticalIntegrationPayload,
    CriticalIntegrationRecord,
    can_s6_wci3_transition,
)
from human_cos.controllers.framing import (
    FramingRequirementPayload,
    InitialFramingContent,
    bind_initial_framing,
    freeze_framing_requirement,
)
from human_cos.controllers.review import build_framing_review
from human_cos.controllers.scenario import (
    ControllerCProposal,
    ControllerCSourceBundle,
    ControllerCTask,
    ScenarioController,
    build_controller_c_invocation_packet,
)
from human_cos.core.context import ContextBuildError
from human_cos.domains import (
    DomainContractError,
    DomainOutputContent,
    bind_domain_output,
    build_domain_routing_plan,
    build_domain_task,
    route_domain_task,
    run_qualified_domain_task,
)
from human_cos.evaluation import (
    EvaluationBindingSubject,
    EvaluationFindingKind,
    EvaluationSourceLayer,
    EvaluationTaskType,
    EvaluatorExecutor,
    EvaluatorInputPacketPayload,
    EvaluatorRunTask,
    EvaluatorSourceBundle,
    EvaluatorSourceDocument,
    EvaluatorSourceRef,
    EvaluatorTaskPayload,
    HCRegressionMetricObservation,
    HCRegressionMetricRulePayload,
    HCRegressionMetricSourcePayload,
    HCRegressionParityDeclarationPayload,
    HCRegressionPreregistrationPayload,
    HCRegressionTrackSnapshotPayload,
    LowRecognitionExposureSnapshotPayload,
    LowRecognitionExposureSourcePayload,
    LowRecognitionVisibilityPolicyPayload,
    RegressionMetricDirection,
    RegressionParityDimension,
    assert_hc_regression_evidence_binding,
    assert_low_recognition_evidence_binding,
    evaluate_hc_regression,
    evaluate_low_recognition_gate,
    freeze_evaluator_input_packet,
    freeze_evaluator_task,
    freeze_hc_regression_metric_rule,
    freeze_hc_regression_metric_source,
    freeze_hc_regression_parity_declaration,
    freeze_hc_regression_preregistration,
    freeze_hc_regression_track_snapshot,
    freeze_low_recognition_exposure_snapshot,
    freeze_low_recognition_exposure_source,
    freeze_low_recognition_visibility_policy,
)
from human_cos.integration import (
    ConflictType,
    CrossExamFinding,
    DisagreementNodePayload,
    DisclosureGrantPayload,
    DissentPosition,
    ResolutionRoute,
    ReviewPromptType,
    SourceKind,
    SourceRef,
    build_cross_exam_task,
    can_s6_wci1_transition,
    freeze_cross_exam_response,
    freeze_disagreement_node,
    freeze_disclosure_grant,
)
from human_cos.models import (
    EligibilityRequirement,
    MockAdapter,
    ModelIdentity,
    ModelRegistry,
    QualificationGate,
    parse_model_profile,
)
from human_cos.runtime.run import RunIndependence, RunManifest, canonical_document_sha256
from human_cos.runtime.scheduler import TrustedScheduler, WorkerTask
from human_cos.runtime.state_machine import (
    CaseMode,
    CaseRuntimePosition,
    RuntimeState,
    TransitionDecision,
    TransitionRejected,
    TransitionStatus,
    can_transition,
)
from human_cos.runtime.tool_policy import ToolPolicy
from human_cos.safety import (
    ResimulationSafetyAdmissionPayload,
    evaluate_resimulation_safety,
    freeze_resimulation_safety_admission,
)
from human_cos.safety.research import (
    ResearchSafetyAdmissionPayload,
    ResearchSafetyOutcome,
    evaluate_research_safety,
    freeze_research_safety_admission,
)
from human_cos.scenario import (
    ScenarioDomainRerunExecutor,
    ScenarioDomainRerunProposal,
    ScenarioPathType,
    ScenarioRerunRunTask,
    ScenarioRerunSourceBundle,
    build_scenario_generation_admission_packet,
    build_scenario_resimulation_plan,
    decide_scenario_generation_admission,
    integrate_scenario_resimulation,
    transition_s7_scs1,
    transition_s7_scs3,
)
from human_cos.storage.migrations import (
    apply_s1_migration,
    apply_s3_migration,
    apply_s4_migration,
    apply_s5_migration,
    apply_s6_migration,
    apply_s7_migration,
    apply_s8_migration,
    rollback_s1_migration,
    rollback_s3_migration,
    rollback_s4_migration,
    rollback_s5_migration,
    rollback_s6_migration,
    rollback_s7_migration,
    rollback_s8_migration,
)
from human_cos.storage.repository import PostgresRepository
from human_cos.storage.s5_cde import (
    store_domain_output,
    store_domain_route,
    store_domain_routing_plan,
    store_domain_task,
    store_framing_requirement,
    store_framing_review,
    store_initial_framing,
)
from human_cos.storage.s6_world import (
    store_actor_state,
    store_causal_graph,
    store_critical_integration,
    store_critical_node_detection,
    store_critical_review_plan,
    store_cross_exam_response,
    store_cross_exam_task,
    store_disagreement_node,
    store_disclosure_grant,
    store_world_state,
)
from human_cos.storage.s7_scenario import (
    store_at17_evidence,
    store_challenger_finding,
    store_challenger_gate,
    store_challenger_packet,
    store_challenger_response,
    store_challenger_satisfaction,
    store_challenger_task,
    store_controller_c_invocation,
    store_controller_c_output,
    store_rerun_output,
    store_rerun_route,
    store_rerun_task,
    store_research_safety_admission,
    store_research_safety_result,
    store_resimulation_plan,
    store_resimulation_result,
    store_resimulation_safety_admission,
    store_resimulation_safety_result,
    store_scenario_generation_packet,
    store_scenario_generation_result,
    store_scenario_path,
    store_scenario_set,
)
from human_cos.storage.s8_evaluation import (
    store_bound_hc_regression,
    store_bound_low_recognition,
    store_evaluator_finding,
    store_evaluator_input_packet,
    store_evaluator_result,
    store_evaluator_task,
)
from human_cos.world import (
    ActorStateSnapshotPayload,
    CausalEdge,
    CausalEdgeType,
    CausalGraphPayload,
    CausalNode,
    CausalNodeType,
    CriticalNodeDetection,
    CriticalNodeDetectionPayload,
    CriticalReviewPlan,
    CriticalReviewPlanPayload,
    CriticalReviewRoute,
    ProvenanceRef,
    ReviewRouteKind,
    ReviewRouteStatus,
    SourceClass,
    WorldStateSnapshotPayload,
    can_s6_wci2_transition,
    can_s6_wci4_transition,
    freeze_actor_state,
    freeze_causal_graph,
    freeze_world_state,
)

_NOW = datetime(2026, 8, 29, tzinfo=timezone.utc)
_GEN_TIME = _NOW + timedelta(minutes=1)
_PROBE_TIME = datetime(2026, 9, 15, tzinfo=timezone.utc)
_CASE_ID = "case-sbx5-installed-chain"

EXPECTED_STAGE_TRANSITIONS = (
    ("BOUNDARY_AND_POLICY_FROZEN", "FRAMING_INDEPENDENT"),
    ("FRAMING_INDEPENDENT", "FRAMING_REVIEWED"),
    ("FRAMING_REVIEWED", "DOMAIN_ROUTED"),
    ("DOMAIN_ROUTED", "DOMAIN_INDEPENDENT_RUN"),
    ("DOMAIN_INDEPENDENT_RUN", "DOMAIN_OUTPUT_FROZEN"),
    ("DOMAIN_OUTPUT_FROZEN", "CROSS_EXAMINATION"),
    ("CROSS_EXAMINATION", "WORLD_CAUSAL_INTEGRATION"),
    ("WORLD_CAUSAL_INTEGRATION", "CRITICAL_NODE_DETECTION"),
    ("CRITICAL_NODE_DETECTION", "CRITICAL_NODE_REVIEW"),
    ("CRITICAL_NODE_REVIEW", "SCENARIO_GENERATION"),
    ("SCENARIO_GENERATION", "SCENARIO_RESIMULATION"),
    ("SCENARIO_RESIMULATION", "ADVERSARIAL_REVIEW"),
)


class InstalledApplicationChainError(ValueError):
    """The installed application/storage chain was incomplete or unsafe."""

    def __init__(
        self,
        message: str,
        *,
        checkpoint: InstalledApplicationChainCheckpoint | None = None,
    ) -> None:
        super().__init__(message)
        self.checkpoint = checkpoint


_N3_DOMAIN_CONTEXT_REASONS = frozenset(
    {
        "context source returned multiple admissible revisions for one evidence_id",
        "trusted Domain Context escaped the task Evidence allowlist",
        "Domain Context includes Evidence outside task allowlist",
        "Domain facts_used includes Evidence outside task allowlist",
    }
)


def _is_n3_context_constraint(exc: BaseException) -> bool:
    """Recognize only authoritative Context/allowlist-equivalence failures."""

    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, ContextBuildError) and str(current) in _N3_DOMAIN_CONTEXT_REASONS:
            return True
        if isinstance(current, DomainContractError) and str(current) in _N3_DOMAIN_CONTEXT_REASONS:
            return True
        current = current.__cause__ or current.__context__
    return False


def _run_fft_domain_task(**kwargs: Any) -> Any:
    """Run the trusted Domain path, classifying only demonstrated N-3 constraints."""

    try:
        return run_qualified_domain_task(**kwargs)
    except Exception as exc:
        if _is_n3_context_constraint(exc):
            raise InstalledApplicationChainError(
                f"FFT1_BLOCKED_BY_N3: {type(exc).__name__}: {exc}"
            ) from exc
        raise


@dataclass(frozen=True)
class SyntheticS7AdmissionLineage:
    """Complete hash-bound S6/Safety lineage for the deterministic FFT probe."""

    world_state: Any
    causal_graph: Any
    detection: Any
    review_plan: Any
    safety_admission: Any
    safety_result: Any
    admission_packet: Any
    admission_result: Any


def build_synthetic_s7_admission_lineage(*, blocked: bool) -> SyntheticS7AdmissionLineage:
    """Build matched S7 admission fixtures exclusively through production builders."""

    source = ProvenanceRef(
        source_class=SourceClass.MODEL,
        ref="domain-output:fft1a-safety-probe",
        sha256="a" * 64,
    )
    actor = freeze_actor_state(
        ActorStateSnapshotPayload(
            actor_state_id="actor-state:fft1a-safety-probe",
            actor_id="synthetic-market",
            case_id="fft1a-safety-probe",
            case_revision=1,
            revision=1,
            timestamp=_PROBE_TIME,
            observable_actions=("synthetic observation",),
            source_refs=(source,),
            protocol_version="0.1",
            frozen_at=_PROBE_TIME,
        )
    )
    graph = freeze_causal_graph(
        CausalGraphPayload(
            graph_id="causal-graph:fft1a-safety-probe",
            case_id="fft1a-safety-probe",
            case_revision=1,
            revision=1,
            nodes=(
                CausalNode(
                    node_id="synthetic-liquidity",
                    node_type=CausalNodeType.SYSTEM_STATE,
                    label="synthetic liquidity",
                    source_refs=(source,),
                ),
            ),
            edges=(),
            protocol_version="0.1",
            frozen_at=_PROBE_TIME,
        )
    )
    world = freeze_world_state(
        WorldStateSnapshotPayload(
            world_state_id="world-state:fft1a-safety-probe",
            case_id="fft1a-safety-probe",
            case_revision=1,
            revision=1,
            timestamp=_PROBE_TIME,
            system_states=("synthetic liquidity observable",),
            actor_state_hashes=(actor.state_hash,),
            causal_graph_hash=graph.graph_hash,
            critical_node_refs=("synthetic-liquidity",),
            source_refs=(source,),
            protocol_version="0.1",
            frozen_at=_PROBE_TIME,
        )
    )
    detection_payload = CriticalNodeDetectionPayload(
        detection_id="critical-detection:fft1a-safety-probe",
        case_id="fft1a-safety-probe",
        case_revision=1,
        integration_hash="b" * 64,
        origin_controller_model_id="mock-controller-b",
        origin_controller_model_family="mock-family-b",
        world_state_hash=world.world_state_hash,
        causal_graph_hash=graph.graph_hash,
        dissent_node_hashes=(),
        candidate_refs=("synthetic-liquidity",),
        cross_family_review_required=False,
        expert_review_required=False,
        challenger_review_required=False,
        protocol_version="0.1",
        frozen_at=_PROBE_TIME,
    )
    detection_document = detection_payload.to_document()
    detection = CriticalNodeDetection(
        **detection_document,
        detection_hash=canonical_document_sha256(detection_document),
    )
    detection.assert_integrity()
    plan_payload = CriticalReviewPlanPayload(
        plan_id="critical-plan:fft1a-safety-probe",
        case_id="fft1a-safety-probe",
        case_revision=1,
        detection_hash=detection.detection_hash,
        routes=(
            CriticalReviewRoute(
                route_id="cross-family:fft1a-safety-probe",
                kind=ReviewRouteKind.CROSS_FAMILY_CONTROLLER,
                status=ReviewRouteStatus.READY,
                reviewer_id="mock-controller-reviewer",
                model_family="mock-family-reviewer",
                reason="complete synthetic S6 review lineage",
            ),
        ),
        protocol_version="0.1",
        frozen_at=_PROBE_TIME,
    )
    plan_document = plan_payload.to_document()
    plan = CriticalReviewPlan(
        **plan_document,
        plan_hash=canonical_document_sha256(plan_document),
    )
    plan.assert_integrity()
    safety = freeze_research_safety_admission(
        ResearchSafetyAdmissionPayload(
            admission_id="research-safety:fft1a-probe",
            case_id="fft1a-safety-probe",
            case_revision=1,
            parent_world_state_hash=world.world_state_hash,
            parent_causal_graph_hash=graph.graph_hash,
            critical_detection_hash=detection.detection_hash,
            critical_review_plan_hash=plan.plan_hash,
            required_safety_facts=("read-only-research",),
            present_safety_facts=() if blocked else ("read-only-research",),
            requested_capability_refs=("read-only-research",),
            protocol_version="0.1",
            frozen_at=_PROBE_TIME,
        )
    )
    safety_result = evaluate_research_safety(
        safety,
        result_id="research-safety-result:fft1a-probe",
        frozen_at=_PROBE_TIME,
    )
    packet = build_scenario_generation_admission_packet(
        packet_id="scenario-generation-packet:fft1a-probe",
        world_state=world,
        causal_graph=graph,
        detection=detection,
        review_plan=plan,
        research_safety_admission=safety,
        frozen_at=_PROBE_TIME,
    )
    result = decide_scenario_generation_admission(
        packet=packet,
        research_safety_admission=safety,
        research_safety_result=safety_result,
        result_id="scenario-generation-result:fft1a-probe",
        frozen_at=_PROBE_TIME,
    )
    return SyntheticS7AdmissionLineage(
        world, graph, detection, plan, safety, safety_result, packet, result
    )


class InstalledApplicationCleanupError(InstalledApplicationChainError):
    """The installed application chain could not prove complete rollback."""


@dataclass(frozen=True)
class InstalledApplicationChainCheckpoint:
    """Hash-bound progress captured before migration rollback starts."""

    s5_terminal_hash: str | None
    s6_terminal_hash: str | None
    s7_terminal_hash: str | None
    s8_terminal_hash: str | None
    tables_exercised: tuple[str, ...]
    evidence_snapshot_json: str
    evidence_snapshot_hash: str
    checkpoint_hash: str

    def to_document(self, *, include_hash: bool = True) -> dict[str, object]:
        document: dict[str, object] = {
            "s5_terminal_hash": self.s5_terminal_hash,
            "s6_terminal_hash": self.s6_terminal_hash,
            "s7_terminal_hash": self.s7_terminal_hash,
            "s8_terminal_hash": self.s8_terminal_hash,
            "tables_exercised": list(self.tables_exercised),
            "evidence_snapshot_json": self.evidence_snapshot_json,
            "evidence_snapshot_hash": self.evidence_snapshot_hash,
        }
        if include_hash:
            document["checkpoint_hash"] = self.checkpoint_hash
        return document

    def assert_integrity(self) -> None:
        if any(
            value is not None and len(value) != 64
            for value in (
                self.s5_terminal_hash,
                self.s6_terminal_hash,
                self.s7_terminal_hash,
                self.s8_terminal_hash,
            )
        ):
            raise InstalledApplicationChainError("application checkpoint has an invalid hash")
        _assert_evidence_snapshot(
            self.evidence_snapshot_json,
            self.evidence_snapshot_hash,
            self.tables_exercised,
        )
        if self.checkpoint_hash != canonical_document_sha256(self.to_document(include_hash=False)):
            raise InstalledApplicationChainError("application checkpoint hash differs from payload")


@dataclass(frozen=True)
class InstalledApplicationChainReceipt:
    migration_names: tuple[str, ...]
    s5_terminal_hash: str
    s6_terminal_hash: str
    s7_terminal_hash: str
    s8_terminal_hash: str
    tables_exercised: tuple[str, ...]
    evidence_snapshot_json: str
    evidence_snapshot_hash: str
    stage_trace: tuple[dict[str, object], ...]
    final_runtime_state: str
    migrations_rolled_back: bool
    receipt_hash: str

    def to_document(self, *, include_hash: bool = True) -> dict[str, object]:
        document: dict[str, object] = {
            "migration_names": list(self.migration_names),
            "s5_terminal_hash": self.s5_terminal_hash,
            "s6_terminal_hash": self.s6_terminal_hash,
            "s7_terminal_hash": self.s7_terminal_hash,
            "s8_terminal_hash": self.s8_terminal_hash,
            "tables_exercised": list(self.tables_exercised),
            "evidence_snapshot_json": self.evidence_snapshot_json,
            "evidence_snapshot_hash": self.evidence_snapshot_hash,
            "stage_trace": list(self.stage_trace),
            "final_runtime_state": self.final_runtime_state,
            "migrations_rolled_back": self.migrations_rolled_back,
        }
        if include_hash:
            document["receipt_hash"] = self.receipt_hash
        return document

    def assert_integrity(self) -> None:
        if self.migration_names != ("0001", "0002", "0003", "0004", "0005", "0006", "0007"):
            raise InstalledApplicationChainError(
                "installed chain did not apply migrations 0001--0007"
            )
        if not self.migrations_rolled_back:
            raise InstalledApplicationChainError("installed chain migrations were not rolled back")
        observed_transitions = tuple(
            (item.get("source"), item.get("target")) for item in self.stage_trace
        )
        if observed_transitions != EXPECTED_STAGE_TRANSITIONS:
            raise InstalledApplicationChainError(
                "installed chain did not exercise the exact ordered S5--S8 transitions"
            )
        if self.final_runtime_state != RuntimeState.ADVERSARIAL_REVIEW.value:
            raise InstalledApplicationChainError("installed chain escaped ADVERSARIAL_REVIEW")
        for index, item in enumerate(self.stage_trace, start=1):
            if item.get("sequence") != index or item.get("status") != "ALLOWED":
                raise InstalledApplicationChainError("installed transition trace is incomplete")
        hashes = (
            self.s5_terminal_hash,
            self.s6_terminal_hash,
            self.s7_terminal_hash,
            self.s8_terminal_hash,
        )
        if any(len(value) != 64 for value in hashes):
            raise InstalledApplicationChainError("installed chain lacks a stage terminal hash")
        if not set(_EVIDENCE_REQUIRED_TABLES).issubset(self.tables_exercised):
            raise InstalledApplicationChainError(
                "installed chain lacks required wrapper or typed-store evidence"
            )
        _assert_evidence_snapshot(
            self.evidence_snapshot_json,
            self.evidence_snapshot_hash,
            self.tables_exercised,
        )
        if self.receipt_hash != canonical_document_sha256(self.to_document(include_hash=False)):
            raise InstalledApplicationChainError(
                "installed chain receipt hash differs from payload"
            )


_MIGRATIONS = (
    apply_s1_migration,
    apply_s3_migration,
    apply_s4_migration,
    apply_s5_migration,
    apply_s6_migration,
    apply_s7_migration,
    apply_s8_migration,
)
_ROLLBACKS = (
    rollback_s8_migration,
    rollback_s7_migration,
    rollback_s6_migration,
    rollback_s5_migration,
    rollback_s4_migration,
    rollback_s3_migration,
    rollback_s1_migration,
)
_TABLES = (
    "human_cos_framing_requirement",
    "human_cos_domain_output",
    "human_cos_s6_disclosure_grant",
    "human_cos_s6_world_state_revision",
    "human_cos_s6_critical_review_plan",
    "human_cos_s7_artifact",
    "human_cos_s8_artifact",
)
_EVIDENCE_REQUIRED_TABLES = (
    *_TABLES,
    "human_cos_context_admission",
    "human_cos_run_manifest_revision",
    "human_cos_raw_output",
    "human_cos_audit_event",
)
_MIGRATION_FUNCTIONS = (
    "human_cos_block_immutable_mutation",
    "human_cos_s8_require_target_content",
)


class _ChainProgress(list[str | None]):
    """List-compatible progress ledger carrying non-persistent orchestration objects."""

    def __init__(self) -> None:
        super().__init__((None, None, None, None))
        self.artifacts: dict[str, Any] = {}


class _ChronologicalTransitions:
    """Advance only through production guards, immediately before stage effects."""

    def __init__(self, case_revision: int = 1) -> None:
        self.position = CaseRuntimePosition(
            CaseMode.MECHANISM_BENCHMARK,
            RuntimeState.BOUNDARY_AND_POLICY_FROZEN,
            case_revision,
        )
        self.values: dict[str, Any] = {}
        self.decisions: list[TransitionDecision] = []

    def advance(self, target: RuntimeState, values: dict[str, Any]) -> None:
        self.values.update(values)
        v = self.values
        if target in {
            RuntimeState.FRAMING_INDEPENDENT,
            RuntimeState.FRAMING_REVIEWED,
            RuntimeState.DOMAIN_ROUTED,
            RuntimeState.DOMAIN_INDEPENDENT_RUN,
            RuntimeState.DOMAIN_OUTPUT_FROZEN,
        }:
            kwargs = {
                key: v[key]
                for key in (
                    "requirement",
                    "records",
                    "review",
                    "plan",
                    "tasks",
                    "routes",
                    "outputs",
                    "no_unresolved_protocol_invalid",
                )
                if key in v
            }
            result = transition_s5_cde3(self.position, target, **kwargs)
            decision, next_position = result.decision, result.position
        elif target is RuntimeState.CROSS_EXAMINATION:
            decision = can_s6_wci1_transition(
                self.position, target, grant=v["disclosure_grant"], tasks=(v["cross_exam_task"],)
            )
            next_position = CaseRuntimePosition(
                self.position.mode, target, self.position.case_revision
            )
        elif target is RuntimeState.WORLD_CAUSAL_INTEGRATION:
            decision = can_s6_wci2_transition(
                self.position,
                target,
                responses=(v["cross_exam_response"],),
                disagreement_nodes=(v["disagreement"],),
                required_high_impact_position_ids=("minority-high",),
            )
            next_position = CaseRuntimePosition(
                self.position.mode, target, self.position.case_revision
            )
        elif target is RuntimeState.CRITICAL_NODE_DETECTION:
            decision = can_s6_wci3_transition(
                self.position, target, integration=v["critical_integration"]
            )
            next_position = CaseRuntimePosition(
                self.position.mode, target, self.position.case_revision
            )
        elif target is RuntimeState.CRITICAL_NODE_REVIEW:
            decision = can_s6_wci4_transition(
                self.position, target, detection=v["detection"], review_plan=v["critical_plan"]
            )
            next_position = CaseRuntimePosition(
                self.position.mode, target, self.position.case_revision
            )
        elif target is RuntimeState.SCENARIO_GENERATION:
            result = transition_s7_scs1(
                self.position,
                target,
                world_state=v["world"],
                causal_graph=v["graph"],
                detection=v["detection"],
                review_plan=v["critical_plan"],
                research_safety_admission=v["research_safety_admission"],
                research_safety_result=v["research_safety_result"],
                admission_packet=v["scenario_admission_packet"],
                admission_result=v["scenario_admission_result"],
            )
            decision, next_position = result.decision, result.position
        elif target is RuntimeState.SCENARIO_RESIMULATION:
            result = transition_s7_scs3(
                self.position,
                target,
                case=v["case"],
                controller_output=v["controller_output"],
                scenario_set=v["scenario_set"],
                parent_world_state=v["world"],
                parent_causal_graph=v["graph"],
                parent_actor_states=(v["actor"],),
                qualification=v["qualification"],
                routes=v["resimulation_routes"],
                safety_admission=v["resimulation_safety_admission"],
                safety_result=v["resimulation_safety_result"],
                plan=v["resimulation_plan"],
            )
            decision, next_position = result.decision, result.position
        else:
            result = transition_s7_scs4(
                self.position,
                target,
                case=v["case"],
                task=v["challenger_task"],
                packet=v["challenger_packet"],
                qualification=v["qualification"],
                critical_review_plan=v["critical_plan"],
                controller_output=v["controller_output"],
                controller_run=v["controller_run"],
                scenario_set=v["scenario_set"],
                resimulation_plan=v["resimulation_plan"],
                resimulation_result=v["resimulation_result"],
                at17=v["at17"],
                world_state=v["revised_world"],
                causal_graph=v["revised_graph"],
                safety_admission=v["resimulation_safety_admission"],
                safety_result=v["resimulation_safety_result"],
            )
            decision, next_position = result.decision, result.position
        if not decision.allowed:
            raise TransitionRejected(decision)
        self.decisions.append(decision)
        self.position = next_position

    def trace(self) -> tuple[dict[str, object], ...]:
        return tuple(_trace_item(index, item) for index, item in enumerate(self.decisions, 1))


def _call_stage(function: Callable[..., Any], *args: Any, advance: Callable[..., Any]) -> Any:
    """Keep private stage test doubles compatible while injecting the real guard hook."""
    if "advance" in inspect.signature(function).parameters:
        return function(*args, advance=advance)
    return function(*args)


def _managed_database_objects(connection: Connection[Any]) -> tuple[tuple[str, str], ...]:
    tables = connection.execute(
        """
        SELECT tablename
        FROM pg_catalog.pg_tables
        WHERE schemaname = 'public' AND tablename LIKE 'human_cos_%'
        ORDER BY tablename
        """
    ).fetchall()
    functions = connection.execute(
        """
        SELECT routine_name
        FROM information_schema.routines
        WHERE routine_schema = 'public'
          AND routine_type = 'FUNCTION'
          AND routine_name = ANY(%s)
        ORDER BY routine_name
        """,
        (list(_MIGRATION_FUNCTIONS),),
    ).fetchall()
    return tuple(("table", str(row[0])) for row in tables) + tuple(
        ("function", str(row[0])) for row in functions
    )


def _assert_clean_database(connection: Connection[Any]) -> None:
    if _managed_database_objects(connection):
        raise InstalledApplicationChainError("refusing to replace pre-existing application objects")


def assert_installed_application_resources_clean(connection: Connection[Any]) -> None:
    """Prove no migration-owned public-schema objects remain."""

    remaining = _managed_database_objects(connection)
    if remaining:
        raise InstalledApplicationCleanupError(
            "installed application migrations remain after cleanup: "
            + ", ".join(f"{kind}:{name}" for kind, name in remaining)
        )


def _assert_evidence_snapshot(
    snapshot_json: str,
    snapshot_hash: str,
    tables_exercised: tuple[str, ...],
) -> None:
    try:
        document = json.loads(snapshot_json)
    except json.JSONDecodeError as exc:
        raise InstalledApplicationChainError("installed evidence snapshot is not JSON") from exc
    canonical_json = json.dumps(document, sort_keys=True, separators=(",", ":"))
    if snapshot_json != canonical_json:
        raise InstalledApplicationChainError("installed evidence snapshot is not canonical JSON")
    if snapshot_hash != canonical_document_sha256(document):
        raise InstalledApplicationChainError(
            "installed evidence snapshot hash differs from payload"
        )
    if not isinstance(document, dict) or not isinstance(document.get("tables"), list):
        raise InstalledApplicationChainError("installed evidence snapshot structure is invalid")
    snapshot_tables_list: list[str] = []
    for item in document["tables"]:
        if not isinstance(item, dict) or set(item) != {"row_count", "rows", "table"}:
            raise InstalledApplicationChainError("installed evidence table entry is invalid")
        rows = item["rows"]
        if not isinstance(rows, list) or not rows or item["row_count"] != len(rows):
            raise InstalledApplicationChainError("installed evidence row count is invalid")
        snapshot_tables_list.append(str(item["table"]))
    snapshot_tables = tuple(snapshot_tables_list)
    if snapshot_tables != tables_exercised:
        raise InstalledApplicationChainError("exercised tables differ from evidence snapshot")


def _capture_installed_evidence(
    connection: Connection[Any],
) -> tuple[str, str, tuple[str, ...]]:
    """Capture committed application rows before migration rollback destroys the schema."""

    connection.rollback()
    table_rows = connection.execute(
        """
        SELECT tablename
        FROM pg_catalog.pg_tables
        WHERE schemaname = 'public' AND tablename LIKE 'human_cos_%'
        ORDER BY tablename
        """
    ).fetchall()
    tables: list[dict[str, object]] = []
    exercised: list[str] = []
    for (table_name_raw,) in table_rows:
        table_name = str(table_name_raw)
        rows = connection.execute(
            sql.SQL(
                "SELECT to_jsonb(record) FROM {} AS record ORDER BY to_jsonb(record)::text"
            ).format(sql.Identifier(table_name))
        ).fetchall()
        if not rows:
            continue
        exercised.append(table_name)
        tables.append(
            {
                "table": table_name,
                "row_count": len(rows),
                "rows": [row[0] for row in rows],
            }
        )
    document: dict[str, object] = {
        "format": "human-cos-installed-application-evidence-v1",
        "tables": tables,
    }
    snapshot_json = json.dumps(document, sort_keys=True, separators=(",", ":"))
    snapshot_hash = canonical_document_sha256(document)
    return snapshot_json, snapshot_hash, tuple(exercised)


def _freeze_application_checkpoint(
    terminal_hashes: Sequence[str | None],
    *,
    tables_exercised: tuple[str, ...] = (),
    evidence_snapshot_json: str | None = None,
    evidence_snapshot_hash: str | None = None,
) -> InstalledApplicationChainCheckpoint:
    if len(terminal_hashes) != 4:
        raise InstalledApplicationChainError("application checkpoint requires four stage slots")
    if evidence_snapshot_json is None:
        empty_document: dict[str, object] = {
            "format": "human-cos-installed-application-evidence-v1",
            "tables": [],
        }
        evidence_snapshot_json = json.dumps(empty_document, sort_keys=True, separators=(",", ":"))
        evidence_snapshot_hash = canonical_document_sha256(empty_document)
    if evidence_snapshot_hash is None:
        raise InstalledApplicationChainError("application checkpoint lacks evidence hash")
    seed = InstalledApplicationChainCheckpoint(
        s5_terminal_hash=terminal_hashes[0],
        s6_terminal_hash=terminal_hashes[1],
        s7_terminal_hash=terminal_hashes[2],
        s8_terminal_hash=terminal_hashes[3],
        tables_exercised=tables_exercised,
        evidence_snapshot_json=evidence_snapshot_json,
        evidence_snapshot_hash=evidence_snapshot_hash,
        checkpoint_hash="",
    )
    checkpoint = InstalledApplicationChainCheckpoint(
        s5_terminal_hash=seed.s5_terminal_hash,
        s6_terminal_hash=seed.s6_terminal_hash,
        s7_terminal_hash=seed.s7_terminal_hash,
        s8_terminal_hash=seed.s8_terminal_hash,
        tables_exercised=seed.tables_exercised,
        evidence_snapshot_json=seed.evidence_snapshot_json,
        evidence_snapshot_hash=seed.evidence_snapshot_hash,
        checkpoint_hash=canonical_document_sha256(seed.to_document(include_hash=False)),
    )
    checkpoint.assert_integrity()
    return checkpoint


def _rollback_applied_migrations(connection: Connection[Any], applied: int) -> None:
    connection.rollback()
    failures: list[BaseException] = []
    for rollback in _ROLLBACKS[len(_ROLLBACKS) - applied :]:
        try:
            rollback(connection)
        except BaseException as exc:
            connection.rollback()
            failures.append(exc)
    if failures:
        raise InstalledApplicationCleanupError(
            "one or more installed application migrations could not be rolled back"
        ) from failures[0]


def _s5_records(
    connection: Connection[Any],
    progress: list[str | None],
    advance: Callable[[RuntimeState, dict[str, Any]], None] = lambda _target, _values: None,
) -> tuple[Any, Any, Any]:
    repository = PostgresRepository(connection)
    case = repository.create_case(
        {
            "case_id": _CASE_ID,
            "revision": 1,
            "case_mode": CaseMode.MECHANISM_BENCHMARK.value,
            "question": "How does a synthetic funding feedback loop propagate?",
            "protocol_version": "0.1",
            "phase_profile": {"civilization_stage": "STARTUP", "case_phase": "DISCOVERY"},
            "time_boundary": {"T0": _NOW.isoformat()},
            "domains": ["finance_market"],
            "publication_policy": "RESTRICTED",
        }
    )
    requirement = freeze_framing_requirement(
        FramingRequirementPayload(
            case_id=case.case_id,
            case_revision=case.revision,
            dual_framing_required=True,
            authority_ref="policy:trial-sbx5",
            protocol_version=case.protocol_version,
            frozen_at=_NOW,
        )
    )
    store_framing_requirement(connection, requirement)
    values: dict[str, Any] = {"case": case, "requirement": requirement}
    advance(RuntimeState.FRAMING_INDEPENDENT, values)

    profiles = tuple(
        parse_model_profile(
            {
                "model_id": model_id,
                "model_family": family,
                "provider": "mock",
                "status": "QUALIFIED",
                "role_eligibility": eligibility,
                **(
                    dict[str, Any](controller_qualification={})
                    if "meta_controller" in eligibility
                    else {
                        "domain_capabilities": [
                            {
                                "domain": "finance_market",
                                "task_type": "mechanism_analysis",
                                "eligibility": "QUALIFIED",
                            }
                        ]
                    }
                ),
            }
        )
        for model_id, family, eligibility in (
            ("mock-controller-a1", "mock-family-a1", {"meta_controller": True}),
            ("mock-controller-a2", "mock-family-a2", {"meta_controller": True}),
            ("mock-domain-worker", "mock-family-domain", {"domain_worker": ["finance_market"]}),
        )
    )
    registry = ModelRegistry(profiles)
    qualification = QualificationGate(registry)
    scheduler = TrustedScheduler(
        repository=repository,
        registry=registry,
        qualification=qualification,
        tool_policy=ToolPolicy(()),
    )
    framing_contents = (
        InitialFramingContent(
            problem_framing="Synthetic independent framing A1",
            actors=("synthetic-market",),
            domains=("finance_market",),
            initial_mechanism_hypotheses=("synthetic funding feedback",),
            key_unknowns=("synthetic liquidity response",),
        ),
        InitialFramingContent(
            problem_framing="Synthetic independent framing A2",
            actors=("synthetic-market",),
            domains=("finance_market",),
            initial_mechanism_hypotheses=("synthetic funding feedback",),
            key_unknowns=("synthetic liquidity response",),
        ),
    )
    framings = []
    for lane, profile, content in zip(("A1", "A2"), profiles[:2], framing_contents, strict=True):
        result = scheduler.run(
            case=case,
            position=CaseRuntimePosition(
                CaseMode.MECHANISM_BENCHMARK, RuntimeState.FRAMING_INDEPENDENT, case.revision
            ),
            task=WorkerTask(
                run_id=f"run:sbx5:{lane.lower()}",
                context_manifest_id=f"context:sbx5:{lane.lower()}",
                role_id=f"mock-framing-{lane.lower()}",
                model_id=profile.model_id,
                prompt_version="fft1a-s5-v1",
                input_text="Produce the frozen synthetic framing fixture.",
                requirement=EligibilityRequirement(role="meta_controller"),
                reference_time=_NOW,
            ),
            adapter=MockAdapter(
                ModelIdentity("mock", profile.model_id, profile.model_family),
                output_text=json.dumps(content.to_document(), sort_keys=True),
            ),
        )
        framing = bind_initial_framing(
            case=case,
            lane=lane,
            content=content,
            frozen_run=result.frozen_manifest,
            context_manifest=result.context.manifest,
        )
        store_initial_framing(connection, framing)
        framings.append(framing)
    frozen_framings = tuple(framings)
    review = build_framing_review(
        requirement=requirement, records=frozen_framings, reviewed_at=_NOW
    )
    store_framing_review(connection, review)
    values.update(
        records=frozen_framings, framings=frozen_framings, review=review, framing_review=review
    )
    advance(RuntimeState.FRAMING_REVIEWED, values)

    task = build_domain_task(
        case=case,
        task_id="domain-task:sbx5",
        domain_id="finance_market",
        domain_task_type="mechanism_analysis",
        allowed_evidence_ids=(),
        actor_scope=("synthetic-market",),
        assumptions=("synthetic liquidity remains observable",),
        requested_horizon="30d",
        framing_review_hash=review.review_hash,
        frozen_at=_NOW,
    )
    decision = route_domain_task(
        task=task, model_id=profiles[2].model_id, qualification=qualification, routed_at=_NOW
    )
    if decision.route is None:
        raise InstalledApplicationChainError("mock S5 domain route was not admitted")
    route = decision.route
    plan = build_domain_routing_plan(
        tasks=(task,), decisions=(decision,), framing_review_hash=review.review_hash, frozen_at=_NOW
    )
    store_domain_task(connection, task)
    store_domain_route(connection, route)
    store_domain_routing_plan(connection, plan)
    values.update(
        plan=plan,
        domain_plan=plan,
        tasks=(task,),
        domain_task=task,
        routes=(route,),
        domain_route=route,
    )
    advance(RuntimeState.DOMAIN_ROUTED, values)
    advance(RuntimeState.DOMAIN_INDEPENDENT_RUN, values)
    content = DomainOutputContent(
        mechanisms=("synthetic funding feedback",),
        critical_node_candidates=("synthetic-liquidity",),
        confidence=0.5,
    )
    result = _run_fft_domain_task(
        repository=repository,
        registry=registry,
        qualification=qualification,
        tool_policy=ToolPolicy(()),
        case=case,
        position=CaseRuntimePosition(
            CaseMode.MECHANISM_BENCHMARK, RuntimeState.DOMAIN_INDEPENDENT_RUN, case.revision
        ),
        task=task,
        route=route,
        run_id="run:sbx5:domain",
        context_manifest_id="context:sbx5:domain",
        role_id="mock-domain",
        prompt_version="fft1a-s5-v1",
        adapter=MockAdapter(
            ModelIdentity("mock", profiles[2].model_id, profiles[2].model_family),
            output_text=json.dumps(content.to_document(), sort_keys=True),
        ),
        reference_time=_NOW,
    )
    output = bind_domain_output(
        task=task,
        route=route,
        content=content,
        frozen_run=result.frozen_manifest,
        context_manifest=result.context.manifest,
    )
    store_domain_output(connection, output)
    values.update(outputs=(output,), domain_output=output, no_unresolved_protocol_invalid=True)
    advance(RuntimeState.DOMAIN_OUTPUT_FROZEN, values)
    progress[0] = output.record_hash
    artifact_sink = getattr(progress, "artifacts", None)
    if artifact_sink is not None:
        artifact_sink.update(values)
    return case, review, output


def _s6_records(
    connection: Connection[Any],
    case: Any,
    framing_review: Any,
    domain_output: Any,
    progress: list[str | None],
    advance: Callable[[RuntimeState, dict[str, Any]], None] = lambda _target, _values: None,
) -> tuple[Any, Any, Any, Any, Any]:
    source = SourceRef(
        kind=SourceKind.DOMAIN_OUTPUT,
        ref="domain-output:sbx5",
        sha256=domain_output.record_hash,
    )
    grant = freeze_disclosure_grant(
        DisclosureGrantPayload(
            grant_id="grant:sbx5",
            case_id=case.case_id,
            case_revision=case.revision,
            reviewer_id="mock-cross-examiner",
            allowed_sources=(source,),
            protocol_version=case.protocol_version,
            frozen_at=_NOW,
        )
    )
    task = build_cross_exam_task(
        grant=grant,
        task_id="cross-exam:sbx5",
        source_refs=(source,),
        prompt_types=(ReviewPromptType.CONFLICT,),
        frozen_at=_NOW,
    )
    advance(RuntimeState.CROSS_EXAMINATION, {"disclosure_grant": grant, "cross_exam_task": task})
    store_disclosure_grant(connection, grant)
    store_cross_exam_task(connection, task)
    response = freeze_cross_exam_response(
        grant=grant,
        task=task,
        response_id="cross-exam-response:sbx5",
        findings=(
            CrossExamFinding(
                finding_id="finding:sbx5",
                prompt_type=ReviewPromptType.CONFLICT,
                statement="A synthetic high-impact alternative remains plausible.",
                source_refs=(source,),
                high_impact=True,
            ),
        ),
        submitted_at=_NOW,
        frozen_at=_NOW,
    )
    disagreement = freeze_disagreement_node(
        DisagreementNodePayload(
            node_id="disagreement:sbx5",
            case_id=case.case_id,
            case_revision=case.revision,
            conflict_type=ConflictType.MECHANISM,
            positions=(
                DissentPosition(
                    position_id="base",
                    source_ref="cross-exam-response:sbx5",
                    source_hash=response.response_hash,
                    statement="Synthetic base mechanism.",
                    impact="MEDIUM",
                ),
                DissentPosition(
                    position_id="minority-high",
                    source_ref="cross-exam-response:sbx5",
                    source_hash=response.response_hash,
                    statement="Synthetic alternative mechanism.",
                    impact="HIGH",
                    minority=True,
                ),
            ),
            resolution_route=ResolutionRoute.PRESERVE_UNRESOLVED,
            unresolved=True,
            high_impact=True,
            source_response_hashes=(response.response_hash,),
            protocol_version=case.protocol_version,
            frozen_at=_NOW,
        )
    )
    advance(
        RuntimeState.WORLD_CAUSAL_INTEGRATION,
        {"cross_exam_response": response, "disagreement": disagreement},
    )
    store_cross_exam_response(connection, response)
    store_disagreement_node(connection, disagreement)
    provenance = ProvenanceRef(
        source_class=SourceClass.MODEL,
        ref="domain-output:sbx5",
        sha256=domain_output.record_hash,
    )
    actor = freeze_actor_state(
        ActorStateSnapshotPayload(
            actor_state_id="actor-state:sbx5",
            actor_id="synthetic-market",
            case_id=case.case_id,
            case_revision=case.revision,
            revision=1,
            timestamp=_NOW,
            observable_actions=("synthetic asset sale",),
            source_refs=(provenance,),
            protocol_version=case.protocol_version,
            frozen_at=_NOW,
        )
    )
    graph = freeze_causal_graph(
        CausalGraphPayload(
            graph_id="causal-graph:sbx5",
            case_id=case.case_id,
            case_revision=case.revision,
            revision=1,
            nodes=(
                CausalNode(
                    node_id="action",
                    node_type=CausalNodeType.ACTION,
                    label="synthetic asset sale",
                    source_refs=(provenance,),
                ),
                CausalNode(
                    node_id="pressure",
                    node_type=CausalNodeType.SYSTEM_STATE,
                    label="synthetic funding pressure",
                    source_refs=(provenance,),
                ),
            ),
            edges=(
                CausalEdge(
                    edge_id="edge:sbx5",
                    source_node_id="action",
                    target_node_id="pressure",
                    edge_type=CausalEdgeType.AMPLIFIES,
                    source_refs=(provenance,),
                ),
            ),
            dissent_node_hashes=(disagreement.node_hash,),
            protocol_version=case.protocol_version,
            frozen_at=_NOW,
        )
    )
    world = freeze_world_state(
        WorldStateSnapshotPayload(
            world_state_id="world-state:sbx5",
            case_id=case.case_id,
            case_revision=case.revision,
            revision=1,
            timestamp=_NOW,
            system_states=("synthetic funding pressure",),
            actor_state_hashes=(actor.state_hash,),
            causal_graph_hash=graph.graph_hash,
            dissent_node_hashes=(disagreement.node_hash,),
            source_refs=(provenance,),
            protocol_version=case.protocol_version,
            frozen_at=_NOW,
        )
    )
    integration_payload = CriticalIntegrationPayload(
        integration_id="critical-integration:sbx5",
        case_id=case.case_id,
        case_revision=case.revision,
        controller_model_id="mock-controller-b",
        controller_model_family="mock-family-b",
        controller_provider="mock",
        framing_review_hash=framing_review.review_hash,
        domain_output_hashes=(domain_output.record_hash,),
        cross_exam_response_hashes=(response.response_hash,),
        disagreement_node_hashes=(disagreement.node_hash,),
        actor_state_hashes=(actor.state_hash,),
        world_state_hash=world.world_state_hash,
        causal_graph_hash=graph.graph_hash,
        required_high_impact_position_ids=("minority-high",),
        content=CriticalIntegrationContent(
            preserved_dissent_node_hashes=(disagreement.node_hash,),
            critical_node_candidate_refs=("synthetic-liquidity",),
        ),
        protocol_version=case.protocol_version,
        frozen_at=_NOW,
    )
    integration_document = integration_payload.to_document()
    integration = CriticalIntegrationRecord(
        **integration_document,
        integration_hash=canonical_document_sha256(integration_document),
    )
    advance(RuntimeState.CRITICAL_NODE_DETECTION, {"critical_integration": integration})
    for store, record in (
        (store_actor_state, actor),
        (store_causal_graph, graph),
        (store_world_state, world),
        (store_critical_integration, integration),
    ):
        store(connection, record)
    detection_payload = CriticalNodeDetectionPayload(
        detection_id="critical-detection:sbx5",
        case_id=case.case_id,
        case_revision=case.revision,
        integration_hash=integration.integration_hash,
        origin_controller_model_id=integration.controller_model_id,
        origin_controller_model_family=integration.controller_model_family,
        world_state_hash=world.world_state_hash,
        causal_graph_hash=graph.graph_hash,
        dissent_node_hashes=(disagreement.node_hash,),
        candidate_refs=("synthetic-liquidity",),
        cross_family_review_required=True,
        domain_review_requirements=(),
        expert_review_required=False,
        challenger_review_required=True,
        protocol_version=case.protocol_version,
        frozen_at=_NOW,
    )
    detection_document = detection_payload.to_document()
    detection = CriticalNodeDetection(
        **detection_document,
        detection_hash=canonical_document_sha256(detection_document),
    )
    plan_payload = CriticalReviewPlanPayload(
        plan_id="critical-plan:sbx5",
        case_id=case.case_id,
        case_revision=case.revision,
        detection_hash=detection.detection_hash,
        routes=(
            CriticalReviewRoute(
                route_id="cross-family-controller",
                kind=ReviewRouteKind.CROSS_FAMILY_CONTROLLER,
                status=ReviewRouteStatus.READY,
                reviewer_id="mock-controller-reviewer",
                model_family="mock-family-reviewer",
                reason="mock-only installed rehearsal route",
            ),
            CriticalReviewRoute(
                route_id="challenger-review",
                kind=ReviewRouteKind.CHALLENGER,
                status=ReviewRouteStatus.PENDING_S7,
                reason="S7 Challenger remains pending",
            ),
        ),
        protocol_version=case.protocol_version,
        frozen_at=_NOW,
    )
    plan_document = plan_payload.to_document()
    plan = CriticalReviewPlan(**plan_document, plan_hash=canonical_document_sha256(plan_document))
    advance(
        RuntimeState.CRITICAL_NODE_REVIEW,
        {
            "detection": detection,
            "critical_plan": plan,
            "actor": actor,
            "world": world,
            "graph": graph,
        },
    )
    progress[1] = plan.plan_hash
    for store, record in (
        (store_critical_node_detection, detection),
        (store_critical_review_plan, plan),
    ):
        store(connection, record)
    artifact_sink = getattr(progress, "artifacts", None)
    if artifact_sink is not None:
        artifact_sink.update(
            disclosure_grant=grant,
            cross_exam_task=task,
            cross_exam_response=response,
            disagreement=disagreement,
            actor=actor,
            world=world,
            graph=graph,
            critical_integration=integration,
            detection=detection,
            critical_plan=plan,
        )
    return actor, world, graph, detection, plan


def _exercise_s8_evidence_sidecars(
    connection: Connection[Any],
    case: Any,
    progress: list[str | None],
    evaluator_result_hash: str,
    base_time: datetime,
) -> tuple[Any, Any]:
    observed_at = base_time
    source_frozen_at = base_time + timedelta(seconds=1)
    task_time = base_time + timedelta(seconds=2)
    packet_time = base_time + timedelta(seconds=3)
    prereg_time = base_time + timedelta(seconds=4)
    snapshot_time = base_time + timedelta(seconds=5)
    report_time = base_time + timedelta(seconds=6)
    binding_time = base_time + timedelta(seconds=7)

    def frozen_run(run_id: str, family: str, context_hash: str) -> RunManifest:
        return RunManifest(
            run_id=run_id,
            case_id=case.case_id,
            stage=RuntimeState.ADVERSARIAL_REVIEW.value,
            role_type="challenger" if run_id.endswith(":hc") else "baseline",
            model_id=f"mock-model:{run_id}",
            model_family=family,
            provider="mock",
            protocol_version=case.protocol_version,
            context_manifest_hash=context_hash,
            prompt_version="sbx5-s8-v1",
            tool_permissions=(),
            status="FROZEN",
            independence=RunIndependence(
                context=True,
                prompt=True,
                model_family=True,
                provider=False,
                evidence_path=True,
                expert=None,
            ),
        )

    hc_run = frozen_run("run:sbx5:hc", "mock-family-hc", "1" * 64)
    baseline_run = frozen_run("run:sbx5:baseline", "mock-family-baseline", "2" * 64)
    declarations = tuple(
        freeze_hc_regression_parity_declaration(
            HCRegressionParityDeclarationPayload(
                dimension=dimension,
                hc_descriptor=descriptor,
                baseline_descriptor=descriptor,
            )
        )
        for dimension, descriptor in (
            (RegressionParityDimension.INPUT, "same-synthetic-input"),
            (RegressionParityDimension.TOOL, "no-tools"),
            (RegressionParityDimension.BUDGET, "fixed-mock-budget"),
            (RegressionParityDimension.OUTPUT_CONTRACT, "structured-v1"),
        )
    )
    rules = (
        freeze_hc_regression_metric_rule(
            HCRegressionMetricRulePayload(
                metric_id="coverage",
                direction=RegressionMetricDirection.HIGHER_IS_BETTER,
                noninferiority_margin=0.05,
                rationale="Synthetic coverage may decline by at most five points.",
            )
        ),
        freeze_hc_regression_metric_rule(
            HCRegressionMetricRulePayload(
                metric_id="critical_error_rate",
                direction=RegressionMetricDirection.LOWER_IS_BETTER,
                noninferiority_margin=0.01,
                rationale="Synthetic critical error may rise by at most one point.",
            )
        ),
    )
    hc_origin = "3" * 64
    baseline_origin = "4" * 64

    def metric_source(
        track_kind: str,
        run: RunManifest,
        coverage: float,
        error_rate: float,
        origin: str,
    ) -> Any:
        return freeze_hc_regression_metric_source(
            HCRegressionMetricSourcePayload(
                source_id=f"hc-metric-source:{track_kind.lower()}:sbx5",
                case_id=case.case_id,
                case_revision=case.revision,
                track_kind=track_kind,
                run_id=run.run_id,
                run_manifest_hash=canonical_document_sha256(run.to_document()),
                metric_values=(
                    HCRegressionMetricObservation(metric_id="coverage", value=coverage),
                    HCRegressionMetricObservation(
                        metric_id="critical_error_rate", value=error_rate
                    ),
                ),
                source_hash_refs=(origin,),
                protocol_version=case.protocol_version,
                observed_at=observed_at,
                frozen_at=source_frozen_at,
            ),
            run_manifest=run,
        )

    hc_source = metric_source("HC", hc_run, 0.90, 0.03, hc_origin)
    baseline_source = metric_source("BASELINE", baseline_run, 0.88, 0.035, baseline_origin)
    hc_task = freeze_evaluator_task(
        EvaluatorTaskPayload(
            task_id="evaluator-task:hc-regression:sbx5",
            case_id=case.case_id,
            case_revision=case.revision,
            case_mode=CaseMode.MECHANISM_BENCHMARK,
            evaluation_type=EvaluationTaskType.HC_REGRESSION,
            evaluated_run_ids=(hc_run.run_id, baseline_run.run_id),
            requested_evaluator_model_id="mock-evaluator-hc",
            requested_evaluator_model_family="mock-family-evaluator",
            requested_evaluator_provider="mock",
            protocol_version=case.protocol_version,
            frozen_at=task_time,
        )
    )
    hc_packet = freeze_evaluator_input_packet(
        EvaluatorInputPacketPayload(
            packet_id="evaluator-packet:hc-regression:sbx5",
            task_hash=hc_task.task_hash,
            case_id=case.case_id,
            case_revision=case.revision,
            evaluation_type=hc_task.evaluation_type,
            evaluated_run_ids=hc_task.evaluated_run_ids,
            source_refs=(
                EvaluatorSourceRef(
                    layer=EvaluationSourceLayer.RUNTIME,
                    object_kind="run_manifest",
                    ref=hc_run.run_id,
                    sha256=canonical_document_sha256(hc_run.to_document()),
                    purpose="bind installed HC run",
                ),
                EvaluatorSourceRef(
                    layer=EvaluationSourceLayer.RUNTIME,
                    object_kind="run_manifest",
                    ref=baseline_run.run_id,
                    sha256=canonical_document_sha256(baseline_run.to_document()),
                    purpose="bind installed Baseline run",
                ),
                EvaluatorSourceRef(
                    layer=EvaluationSourceLayer.S7,
                    object_kind="hc_metric_source",
                    ref=hc_source.source_id,
                    sha256=hc_source.source_hash,
                    purpose="bind HC metric observations",
                ),
                EvaluatorSourceRef(
                    layer=EvaluationSourceLayer.S7,
                    object_kind="baseline_metric_source",
                    ref=baseline_source.source_id,
                    sha256=baseline_source.source_hash,
                    purpose="bind Baseline metric observations",
                ),
                EvaluatorSourceRef(
                    layer=EvaluationSourceLayer.S7,
                    object_kind="metric_origin",
                    ref="metric-origin:hc:sbx5",
                    sha256=hc_origin,
                    purpose="bind HC metric origin",
                ),
                EvaluatorSourceRef(
                    layer=EvaluationSourceLayer.S7,
                    object_kind="metric_origin",
                    ref="metric-origin:baseline:sbx5",
                    sha256=baseline_origin,
                    purpose="bind Baseline metric origin",
                ),
            ),
            protocol_version=case.protocol_version,
            frozen_at=packet_time,
        )
    )
    preregistration = freeze_hc_regression_preregistration(
        HCRegressionPreregistrationPayload(
            regression_id="hc-regression:sbx5",
            task_hash=hc_task.task_hash,
            packet_hash=hc_packet.packet_hash,
            case_id=case.case_id,
            case_revision=case.revision,
            hc_run_id=hc_run.run_id,
            baseline_run_id=baseline_run.run_id,
            parity_declaration_hashes=tuple(item.declaration_hash for item in declarations),
            metric_rule_hashes=tuple(item.rule_hash for item in rules),
            stopping_rule="Freeze after both preregistered snapshots exist.",
            failure_conditions=("parity mismatch", "source binding mismatch"),
            protocol_version=case.protocol_version,
            preregistered_at=prereg_time,
        ),
        task=hc_task,
        packet=hc_packet,
        declarations=declarations,
        metric_rules=rules,
    )

    def track_snapshot(track_kind: str, run: RunManifest, source: Any) -> Any:
        return freeze_hc_regression_track_snapshot(
            HCRegressionTrackSnapshotPayload(
                snapshot_id=f"hc-snapshot:{track_kind.lower()}:sbx5",
                preregistration_hash=preregistration.preregistration_hash,
                task_hash=hc_task.task_hash,
                packet_hash=hc_packet.packet_hash,
                track_kind=track_kind,
                run_id=run.run_id,
                run_manifest_hash=source.run_manifest_hash,
                metric_source_hash=source.source_hash,
                input_descriptor="same-synthetic-input",
                tool_descriptor="no-tools",
                budget_descriptor="fixed-mock-budget",
                output_contract_descriptor="structured-v1",
                metric_values=source.metric_values,
                protocol_version=case.protocol_version,
                frozen_at=snapshot_time,
            ),
            preregistration=preregistration,
            task=hc_task,
            packet=hc_packet,
            metric_rules=rules,
            run_manifest=run,
        )

    hc_snapshot = track_snapshot("HC", hc_run, hc_source)
    baseline_snapshot = track_snapshot("BASELINE", baseline_run, baseline_source)
    report = evaluate_hc_regression(
        preregistration=preregistration,
        task=hc_task,
        packet=hc_packet,
        declarations=declarations,
        metric_rules=rules,
        hc_snapshot=hc_snapshot,
        baseline_snapshot=baseline_snapshot,
        report_id="hc-regression-report:sbx5",
        frozen_at=report_time,
    )
    hc_binding = assert_hc_regression_evidence_binding(
        task=hc_task,
        packet=hc_packet,
        preregistration=preregistration,
        declarations=declarations,
        metric_rules=rules,
        hc_run_manifest=hc_run,
        baseline_run_manifest=baseline_run,
        hc_metric_source=hc_source,
        baseline_metric_source=baseline_source,
        hc_snapshot=hc_snapshot,
        baseline_snapshot=baseline_snapshot,
        report=report,
        binding_id="hc-regression-binding:sbx5",
        frozen_at=binding_time,
    )
    if hc_binding.subject is not EvaluationBindingSubject.HC_REGRESSION:
        raise InstalledApplicationChainError("HC Regression binding subject mismatch")
    store_evaluator_task(connection, hc_task)
    store_evaluator_input_packet(connection, hc_task, hc_packet)
    store_bound_hc_regression(
        connection,
        task=hc_task,
        packet=hc_packet,
        declarations=declarations,
        metric_rules=rules,
        preregistration=preregistration,
        hc_run_manifest=hc_run,
        baseline_run_manifest=baseline_run,
        hc_metric_source=hc_source,
        baseline_metric_source=baseline_source,
        hc_snapshot=hc_snapshot,
        baseline_snapshot=baseline_snapshot,
        report=report,
        binding=hc_binding,
    )

    exposure_origin = "5" * 64
    exposure_source = freeze_low_recognition_exposure_source(
        LowRecognitionExposureSourcePayload(
            source_id="low-recognition-source:sbx5",
            case_id=case.case_id,
            case_revision=case.revision,
            entity_system_identity_exposed=False,
            provenance_label_exposed=False,
            solver_controller_identity_exposed=False,
            comparison_label_exposed=False,
            material_revealed_before_freeze=(),
            same_session_or_inherited_knowledge=False,
            cross_evaluator_contamination=False,
            cross_comparison_contamination=False,
            unresolved_protocol_invalid=False,
            source_hash_refs=(exposure_origin,),
            protocol_version=case.protocol_version,
            observed_at=observed_at,
            frozen_at=source_frozen_at,
        )
    )
    low_task = freeze_evaluator_task(
        EvaluatorTaskPayload(
            task_id="evaluator-task:low-recognition:sbx5",
            case_id=case.case_id,
            case_revision=case.revision,
            case_mode=CaseMode.MECHANISM_BENCHMARK,
            evaluation_type=EvaluationTaskType.LOW_RECOGNITION,
            evaluated_run_ids=("run:challenger:sbx5",),
            requested_evaluator_model_id="mock-evaluator-low-recognition",
            requested_evaluator_model_family="mock-family-evaluator",
            requested_evaluator_provider="mock",
            protocol_version=case.protocol_version,
            frozen_at=task_time,
        )
    )
    low_packet = freeze_evaluator_input_packet(
        EvaluatorInputPacketPayload(
            packet_id="evaluator-packet:low-recognition:sbx5",
            task_hash=low_task.task_hash,
            case_id=case.case_id,
            case_revision=case.revision,
            evaluation_type=low_task.evaluation_type,
            evaluated_run_ids=low_task.evaluated_run_ids,
            source_refs=(
                EvaluatorSourceRef(
                    layer=EvaluationSourceLayer.S7,
                    object_kind="low_recognition_exposure_source",
                    ref=exposure_source.source_id,
                    sha256=exposure_source.source_hash,
                    purpose="bind explicit exposure observations",
                ),
                EvaluatorSourceRef(
                    layer=EvaluationSourceLayer.S7,
                    object_kind="exposure_origin",
                    ref="exposure-origin:sbx5",
                    sha256=exposure_origin,
                    purpose="bind exposure origin",
                ),
            ),
            protocol_version=case.protocol_version,
            frozen_at=packet_time,
        )
    )
    policy = freeze_low_recognition_visibility_policy(
        LowRecognitionVisibilityPolicyPayload(
            policy_id="low-recognition-policy:sbx5",
            task_hash=low_task.task_hash,
            packet_hash=low_packet.packet_hash,
            case_id=case.case_id,
            case_revision=case.revision,
            hide_entity_system_identity=True,
            hide_provenance_labels=True,
            hide_solver_controller_identity=True,
            hide_comparison_labels=True,
            material_hidden_until_freeze=(
                "entity/system identity",
                "provenance labels",
                "solver/controller identity",
                "comparison labels",
            ),
            post_freeze_reveal_plan=(
                "entity/system identity",
                "provenance labels",
                "solver/controller identity",
                "comparison labels",
            ),
            protocol_version=case.protocol_version,
            frozen_at=prereg_time,
        ),
        task=low_task,
        packet=low_packet,
    )
    exposure_snapshot = freeze_low_recognition_exposure_snapshot(
        LowRecognitionExposureSnapshotPayload(
            snapshot_id="low-recognition-snapshot:sbx5",
            task_hash=low_task.task_hash,
            packet_hash=low_packet.packet_hash,
            policy_hash=policy.policy_hash,
            exposure_evidence_hashes=(exposure_source.source_hash,),
            entity_system_identity_exposed=False,
            provenance_label_exposed=False,
            solver_controller_identity_exposed=False,
            comparison_label_exposed=False,
            material_revealed_before_freeze=(),
            same_session_or_inherited_knowledge=False,
            cross_evaluator_contamination=False,
            cross_comparison_contamination=False,
            unresolved_protocol_invalid=False,
            protocol_version=case.protocol_version,
            frozen_at=snapshot_time,
        ),
        task=low_task,
        packet=low_packet,
        policy=policy,
    )
    low_gate = evaluate_low_recognition_gate(
        task=low_task,
        packet=low_packet,
        policy=policy,
        snapshot=exposure_snapshot,
        gate_id="low-recognition-gate:sbx5",
        frozen_at=report_time,
    )
    low_binding = assert_low_recognition_evidence_binding(
        task=low_task,
        packet=low_packet,
        policy=policy,
        exposure_sources=(exposure_source,),
        exposure_snapshot=exposure_snapshot,
        gate=low_gate,
        binding_id="low-recognition-binding:sbx5",
        frozen_at=binding_time,
    )
    if low_binding.subject is not EvaluationBindingSubject.LOW_RECOGNITION:
        raise InstalledApplicationChainError("Low-recognition binding subject mismatch")
    progress[3] = canonical_document_sha256(
        {
            "evaluator_result_hash": evaluator_result_hash,
            "hc_regression_report_hash": report.report_hash,
            "low_recognition_gate_hash": low_gate.gate_hash,
        }
    )
    store_evaluator_task(connection, low_task)
    store_evaluator_input_packet(connection, low_task, low_packet)
    store_bound_low_recognition(
        connection,
        task=low_task,
        packet=low_packet,
        policy=policy,
        exposure_sources=(exposure_source,),
        exposure_snapshot=exposure_snapshot,
        gate=low_gate,
        binding=low_binding,
    )
    return report, low_gate


def _s7_s8_records(
    connection: Connection[Any],
    case: Any,
    actor: Any,
    world: Any,
    graph: Any,
    detection: Any,
    plan: Any,
    progress: list[str | None],
    advance: Callable[[RuntimeState, dict[str, Any]], None] = lambda _target, _values: None,
) -> tuple[Any, Any]:
    safety = freeze_research_safety_admission(
        ResearchSafetyAdmissionPayload(
            admission_id="research-safety:sbx5",
            case_id=case.case_id,
            case_revision=case.revision,
            parent_world_state_hash=world.world_state_hash,
            parent_causal_graph_hash=graph.graph_hash,
            critical_detection_hash=detection.detection_hash,
            critical_review_plan_hash=plan.plan_hash,
            required_safety_facts=("mock-only", "restricted-publication"),
            present_safety_facts=("mock-only", "restricted-publication"),
            protocol_version=case.protocol_version,
            frozen_at=_GEN_TIME,
        )
    )
    safety_result = evaluate_research_safety(
        safety, result_id="research-safety-result:sbx5", frozen_at=_GEN_TIME
    )
    if safety_result.outcome is not ResearchSafetyOutcome.PASS:
        raise InstalledApplicationChainError("mock Research Safety did not PASS")
    store_research_safety_admission(connection, safety)
    store_research_safety_result(connection, safety_result)

    admission_packet = build_scenario_generation_admission_packet(
        packet_id="scenario-generation-packet:sbx5",
        world_state=world,
        causal_graph=graph,
        detection=detection,
        review_plan=plan,
        research_safety_admission=safety,
        frozen_at=_GEN_TIME,
    )
    admission_result = decide_scenario_generation_admission(
        packet=admission_packet,
        research_safety_admission=safety,
        research_safety_result=safety_result,
        result_id="scenario-generation-result:sbx5",
        frozen_at=_GEN_TIME,
    )
    advance(
        RuntimeState.SCENARIO_GENERATION,
        {
            "research_safety_admission": safety,
            "research_safety_result": safety_result,
            "scenario_admission_packet": admission_packet,
            "scenario_admission_result": admission_result,
        },
    )
    store_scenario_generation_packet(connection, admission_packet)
    store_scenario_generation_result(connection, admission_packet, admission_result)

    profiles = (
        parse_model_profile(
            {
                "model_id": "mock-controller-c",
                "model_family": "mock-family-controller-c",
                "provider": "mock",
                "status": "QUALIFIED",
                "role_eligibility": {"meta_controller": True},
                "controller_qualification": {},
            }
        ),
        parse_model_profile(
            {
                "model_id": "mock-scenario-worker",
                "model_family": "mock-family-scenario",
                "provider": "mock",
                "status": "QUALIFIED",
                "role_eligibility": {"domain_worker": ["finance_market"]},
                "domain_capabilities": [
                    {
                        "domain": "finance_market",
                        "task_type": "scenario_analysis",
                        "eligibility": "QUALIFIED",
                    }
                ],
            }
        ),
        parse_model_profile(
            {
                "model_id": "mock-challenger",
                "model_family": "mock-family-challenger",
                "provider": "mock",
                "status": "QUALIFIED",
                "role_eligibility": {"challenger": True},
            }
        ),
        parse_model_profile(
            {
                "model_id": "mock-evaluator",
                "model_family": "mock-family-evaluator",
                "provider": "mock",
                "status": "QUALIFIED",
                "role_eligibility": {"evaluator": True},
            }
        ),
    )
    registry = ModelRegistry(profiles)
    qualification = QualificationGate(registry)
    repository = PostgresRepository(connection)
    tool_policy = ToolPolicy(())
    generation_position = CaseRuntimePosition(
        mode=CaseMode.MECHANISM_BENCHMARK,
        state=RuntimeState.SCENARIO_GENERATION,
        case_revision=case.revision,
    )
    controller_sources = ControllerCSourceBundle(
        world_state=world,
        causal_graph=graph,
        detection=detection,
        review_plan=plan,
        research_safety_admission=safety,
        research_safety_result=safety_result,
        scenario_admission_packet=admission_packet,
        scenario_admission_result=admission_result,
    )
    invocation = build_controller_c_invocation_packet(
        case=case,
        position=generation_position,
        qualification=qualification,
        controller_model_id="mock-controller-c",
        sources=controller_sources,
        invocation_packet_id="controller-c-invocation:sbx5",
        frozen_at=_GEN_TIME,
    )
    proposal = ControllerCProposal.model_validate(
        {
            "scenario_set_id": "scenario-set:sbx5",
            "paths": [
                {
                    "scenario_path_id": f"scenario-path:{path_type.value.lower()}:sbx5",
                    "path_type": path_type.value,
                    "assumptions": ["mock-only analytical path"],
                    "affected_actors": ["synthetic-market"],
                    "affected_nodes": ["pressure"],
                    "affected_domains": ["finance_market"],
                    "benefit_path": ["synthetic funding pressure may decline"],
                    "harm_path": ["synthetic liquidity friction may rise"],
                    "open_unknowns": ["synthetic response magnitude"],
                }
                for path_type in (
                    ScenarioPathType.IMPROVEMENT,
                    ScenarioPathType.BASE,
                    ScenarioPathType.DETERIORATION,
                )
            ],
        }
    )
    controller_run_result = ScenarioController(
        repository=repository,
        registry=registry,
        qualification=qualification,
        tool_policy=tool_policy,
    ).run(
        case=case,
        position=generation_position,
        sources=controller_sources,
        task=ControllerCTask(
            run_id="run:controller-c:sbx5",
            context_manifest_id="context:controller-c:sbx5",
            role_id="controller-c",
            model_id="mock-controller-c",
            prompt_version="sbx5-controller-c-v1",
            input_text="Generate mock-only bounded scenarios from frozen sources.",
            invocation_packet=invocation,
            output_id="controller-c-output:sbx5",
            reference_time=_GEN_TIME,
        ),
        adapter=MockAdapter(
            ModelIdentity("mock", "mock-controller-c", "mock-family-controller-c"),
            output_text=json.dumps(proposal.model_dump(mode="json"), sort_keys=True),
        ),
    )
    generation = controller_run_result.generation
    scenario_set = generation.scenario_set
    controller_output = generation.output
    controller_run = controller_run_result.frozen_manifest
    store_controller_c_invocation(connection, invocation)
    for scenario_path in scenario_set.paths:
        store_scenario_path(connection, scenario_path)
    store_scenario_set(connection, scenario_set)
    store_controller_c_output(connection, controller_output)

    resim_time = controller_output.frozen_at
    base_path = next(item for item in scenario_set.paths if item.path_type is ScenarioPathType.BASE)
    resim_safety = freeze_resimulation_safety_admission(
        ResimulationSafetyAdmissionPayload(
            admission_id="resimulation-safety:sbx5",
            case_id=case.case_id,
            case_revision=case.revision,
            scenario_set_hash=scenario_set.scenario_set_hash,
            scenario_path_hash=base_path.path_hash,
            parent_world_state_hash=world.world_state_hash,
            parent_causal_graph_hash=graph.graph_hash,
            required_safety_facts=("mock-only",),
            present_safety_facts=("mock-only",),
            protocol_version=case.protocol_version,
            frozen_at=resim_time,
        )
    )
    resim_safety_result = evaluate_resimulation_safety(
        resim_safety,
        result_id="resimulation-safety-result:sbx5",
        frozen_at=resim_time,
    )
    resim_build = build_scenario_resimulation_plan(
        case=case,
        position=generation_position,
        controller_output=controller_output,
        scenario_set=scenario_set,
        scenario_path_id=base_path.scenario_path_id,
        intervention_id=None,
        parent_world_state=world,
        parent_causal_graph=graph,
        parent_actor_states=(actor,),
        qualification=qualification,
        model_ids_by_domain={"finance_market": "mock-scenario-worker"},
        safety_admission=resim_safety,
        safety_result=resim_safety_result,
        plan_id="resimulation-plan:sbx5",
        frozen_at=resim_time,
    )
    advance(
        RuntimeState.SCENARIO_RESIMULATION,
        {
            "qualification": qualification,
            "controller_output": controller_output,
            "controller_run": controller_run,
            "scenario_set": scenario_set,
            "resimulation_safety_admission": resim_safety,
            "resimulation_safety_result": resim_safety_result,
            "resimulation_plan": resim_build.plan,
            "resimulation_routes": resim_build.routes,
        },
    )
    resim_position = CaseRuntimePosition(
        mode=CaseMode.MECHANISM_BENCHMARK,
        state=RuntimeState.SCENARIO_RESIMULATION,
        case_revision=case.revision,
    )
    rerun_sources = ScenarioRerunSourceBundle(
        controller_output=controller_output,
        scenario_set=scenario_set,
        parent_world_state=world,
        parent_causal_graph=graph,
        parent_actor_states=(actor,),
        safety_admission=resim_safety,
        safety_result=resim_safety_result,
        plan=resim_build.plan,
        routes=resim_build.routes,
    )
    rerun_executor = ScenarioDomainRerunExecutor(
        repository=repository,
        registry=registry,
        qualification=qualification,
        tool_policy=tool_policy,
    )
    rerun_outputs = []
    for rerun_task in resim_build.tasks:
        route = next(item for item in resim_build.routes if item.task_hash == rerun_task.task_hash)
        profile = registry.get(route.model_id)
        rerun_proposal = ScenarioDomainRerunProposal(
            system_state_deltas=("synthetic pressure re-simulated",),
            actor_state_deltas=(
                {
                    "actor_id": "synthetic-market",
                    "observable_actions": ("adjusts synthetic posture",),
                    "uncertainties": ("synthetic response remains uncertain",),
                },
            ),
            causal_effects=("synthetic dependency propagated",),
            benefit_path_deltas=("synthetic benefit remains plausible",),
            harm_path_deltas=("synthetic harm remains plausible",),
            unknowns=("synthetic residual unknown",),
            rollback_conditions=("discard synthetic modeled delta",),
            critical_node_refs=("pressure",),
        )
        rerun_result = rerun_executor.run(
            case=case,
            position=resim_position,
            sources=rerun_sources,
            task=ScenarioRerunRunTask(
                run_id=f"run:scenario-rerun:{rerun_task.domain_id}:sbx5",
                context_manifest_id=f"context:scenario-rerun:{rerun_task.domain_id}:sbx5",
                model_id=route.model_id,
                prompt_version="sbx5-scenario-rerun-v1",
                input_text="Re-simulate the frozen synthetic scenario domain.",
                rerun_task=rerun_task,
                route=route,
                output_id=f"scenario-rerun-output:{rerun_task.domain_id}:sbx5",
            ),
            adapter=MockAdapter(
                ModelIdentity(profile.provider, profile.model_id, profile.model_family),
                output_text=json.dumps(rerun_proposal.model_dump(mode="json"), sort_keys=True),
            ),
        )
        rerun_outputs.append(rerun_result.output)
    result_time = max(output.finished_at for output in rerun_outputs)
    artifacts = integrate_scenario_resimulation(
        plan=resim_build.plan,
        controller_output=controller_output,
        scenario_set=scenario_set,
        parent_world_state=world,
        parent_causal_graph=graph,
        parent_actor_states=(actor,),
        qualification=qualification,
        routes=resim_build.routes,
        outputs=tuple(rerun_outputs),
        safety_admission=resim_safety,
        safety_result=resim_safety_result,
        result_id="resimulation-result:sbx5",
        at17_evidence_id="at17:sbx5",
        frozen_at=result_time,
    )
    store_resimulation_safety_admission(connection, resim_safety)
    store_resimulation_safety_result(connection, resim_safety_result)
    for rerun_task in resim_build.tasks:
        store_rerun_task(connection, rerun_task)
    for route in resim_build.routes:
        store_rerun_route(connection, route)
    store_resimulation_plan(connection, resim_build.plan)
    for output in rerun_outputs:
        store_rerun_output(connection, output)
    for revised_actor in artifacts.revised_actor_states:
        store_actor_state(connection, revised_actor)
    store_causal_graph(connection, artifacts.causal_graph)
    store_world_state(connection, artifacts.world_state)
    store_resimulation_result(connection, artifacts.result)
    store_at17_evidence(connection, artifacts.result, artifacts.at17)

    challenger_time = artifacts.at17.frozen_at
    challenger_task = build_challenger_task(
        case=case,
        position=resim_position,
        qualification=qualification,
        challenger_model_id="mock-challenger",
        critical_review_plan=plan,
        controller_output=controller_output,
        controller_run=controller_run,
        scenario_set=scenario_set,
        resimulation_plan=resim_build.plan,
        resimulation_result=artifacts.result,
        at17=artifacts.at17,
        world_state=artifacts.world_state,
        causal_graph=artifacts.causal_graph,
        safety_admission=resim_safety,
        safety_result=resim_safety_result,
        task_id="challenger-task:sbx5",
        frozen_at=challenger_time,
    )
    challenger_packet = build_challenger_source_packet(
        task=challenger_task,
        critical_review_plan=plan,
        controller_output=controller_output,
        scenario_set=scenario_set,
        resimulation_plan=resim_build.plan,
        resimulation_result=artifacts.result,
        at17=artifacts.at17,
        world_state=artifacts.world_state,
        causal_graph=artifacts.causal_graph,
        packet_id="challenger-packet:sbx5",
        frozen_at=challenger_time,
    )
    advance(
        RuntimeState.ADVERSARIAL_REVIEW,
        {
            "challenger_task": challenger_task,
            "challenger_packet": challenger_packet,
            "resimulation_result": artifacts.result,
            "at17": artifacts.at17,
            "revised_world": artifacts.world_state,
            "revised_graph": artifacts.causal_graph,
        },
    )
    challenger_proposal = ChallengerProposal(
        findings=tuple(
            ChallengerFindingProposal(
                finding_id=f"challenger-finding:{attack.value.lower()}:sbx5",
                attack_type=attack,
                statement=f"Synthetic {attack.value} challenge exercised",
                rationale="Mock-only full installed-chain rehearsal",
                source_hash_refs=(scenario_set.scenario_set_hash,),
                wrong_if_candidates=(
                    ("wrong-if synthetic evidence reverses mechanism",)
                    if attack is ChallengerAttackType.FALSIFICATION
                    else ()
                ),
                blocking=False,
                unresolved=False,
            )
            for attack in FROZEN_CHALLENGER_ATTACK_TYPES
        )
    )
    challenger_position = CaseRuntimePosition(
        mode=CaseMode.MECHANISM_BENCHMARK,
        state=RuntimeState.ADVERSARIAL_REVIEW,
        case_revision=case.revision,
    )
    challenger_run_result = ChallengerExecutor(
        repository=repository,
        registry=registry,
        qualification=qualification,
        tool_policy=tool_policy,
    ).run(
        case=case,
        position=challenger_position,
        sources=ChallengerSourceBundle(
            critical_review_plan=plan,
            controller_output=controller_output,
            controller_run=controller_run,
            scenario_set=scenario_set,
            resimulation_plan=resim_build.plan,
            resimulation_result=artifacts.result,
            at17=artifacts.at17,
            world_state=artifacts.world_state,
            causal_graph=artifacts.causal_graph,
            safety_admission=resim_safety,
            safety_result=resim_safety_result,
        ),
        task=ChallengerRunTask(
            run_id="run:challenger:sbx5",
            context_manifest_id="context:challenger:sbx5",
            model_id="mock-challenger",
            prompt_version="sbx5-challenger-v1",
            input_text="Challenge the frozen synthetic S7 result.",
            challenger_task=challenger_task,
            source_packet=challenger_packet,
            response_id="challenger-response:sbx5",
        ),
        adapter=MockAdapter(
            ModelIdentity("mock", "mock-challenger", "mock-family-challenger"),
            output_text=json.dumps(challenger_proposal.model_dump(mode="json"), sort_keys=True),
        ),
    )
    challenger_response = challenger_run_result.challenger_response
    challenger_run = challenger_run_result.frozen_manifest
    challenger_gate_time = challenger_response.frozen_at
    satisfaction = freeze_pending_challenger_satisfaction(
        critical_review_plan=plan,
        task=challenger_task,
        packet=challenger_packet,
        response=challenger_response,
        satisfaction_id="challenger-satisfaction:sbx5",
        frozen_at=challenger_gate_time,
    )
    challenger_gate = evaluate_challenger_review_gate(
        response=challenger_response,
        satisfaction=satisfaction,
        gate_result_id="challenger-gate:sbx5",
        frozen_at=challenger_gate_time,
    )
    progress[2] = challenger_gate.gate_result_hash
    store_challenger_task(connection, challenger_task)
    store_challenger_packet(connection, challenger_packet)
    for finding in challenger_response.findings:
        store_challenger_finding(connection, challenger_packet, challenger_response, finding)
    store_challenger_response(connection, challenger_response)
    store_challenger_satisfaction(connection, satisfaction)
    store_challenger_gate(connection, satisfaction, challenger_gate)

    evaluator_time = challenger_gate.frozen_at
    evaluator_task = freeze_evaluator_task(
        EvaluatorTaskPayload(
            task_id="evaluator-task:sbx5",
            case_id=case.case_id,
            case_revision=case.revision,
            case_mode=CaseMode.MECHANISM_BENCHMARK,
            evaluation_type=EvaluationTaskType.INTEGRATED_RESULT,
            evaluated_run_ids=(controller_run.run_id, "run:challenger:sbx5"),
            requested_evaluator_model_id="mock-evaluator",
            requested_evaluator_model_family="mock-family-evaluator",
            requested_evaluator_provider="mock",
            protocol_version=case.protocol_version,
            frozen_at=evaluator_time,
        )
    )
    controller_run_hash = canonical_document_sha256(controller_run.to_document())
    challenger_run_hash = canonical_document_sha256(challenger_run.to_document())
    evaluator_source_refs = (
        EvaluatorSourceRef(
            layer=EvaluationSourceLayer.RUNTIME,
            object_kind="run_manifest",
            ref=controller_run.run_id,
            sha256=controller_run_hash,
            purpose="bind frozen Controller C run",
        ),
        EvaluatorSourceRef(
            layer=EvaluationSourceLayer.RUNTIME,
            object_kind="run_manifest",
            ref=challenger_run.run_id,
            sha256=challenger_run_hash,
            purpose="bind frozen Challenger run",
        ),
        EvaluatorSourceRef(
            layer=EvaluationSourceLayer.S7,
            object_kind="CHALLENGER_GATE",
            ref="challenger-gate:sbx5",
            sha256=challenger_gate.gate_result_hash,
            purpose="bind installed S8 exercise to the real S7 terminal gate",
        ),
    )
    evaluator_packet = freeze_evaluator_input_packet(
        EvaluatorInputPacketPayload(
            packet_id="evaluator-packet:sbx5",
            task_hash=evaluator_task.task_hash,
            case_id=case.case_id,
            case_revision=case.revision,
            evaluation_type=evaluator_task.evaluation_type,
            evaluated_run_ids=evaluator_task.evaluated_run_ids,
            source_refs=evaluator_source_refs,
            protocol_version=case.protocol_version,
            frozen_at=evaluator_time,
        )
    )
    evaluator_proposal = {
        "findings": [
            {
                "finding_kind": EvaluationFindingKind.SUPPORT.value,
                "statement": "Installed S7 terminal evidence is internally coherent.",
                "rationale": "The exact Challenger gate is bound in the evaluator packet.",
                "source_hash_refs": [challenger_gate.gate_result_hash],
                "uncertainty": "External validity remains outside this mock-only rehearsal.",
            }
        ],
        "uncertainty": "No Final Synthesis authority follows.",
    }
    evaluator_run_result = EvaluatorExecutor(
        repository=repository,
        registry=registry,
        qualification=qualification,
        tool_policy=tool_policy,
    ).run(
        case=case,
        position=CaseRuntimePosition(
            mode=CaseMode.MECHANISM_BENCHMARK,
            state=RuntimeState.ADVERSARIAL_REVIEW,
            case_revision=case.revision,
        ),
        sources=EvaluatorSourceBundle(
            documents=(
                EvaluatorSourceDocument(
                    source_ref=evaluator_source_refs[0],
                    document=controller_run.to_document(),
                ),
                EvaluatorSourceDocument(
                    source_ref=evaluator_source_refs[1],
                    document=challenger_run.to_document(),
                ),
                EvaluatorSourceDocument(
                    source_ref=evaluator_source_refs[2],
                    document=challenger_gate.model_dump(
                        mode="json", exclude={"gate_result_hash"}, exclude_none=True
                    ),
                ),
            )
        ),
        task=EvaluatorRunTask(
            run_id="run:evaluator:sbx5",
            context_manifest_id="context:evaluator:sbx5",
            model_id="mock-evaluator",
            prompt_version="sbx5-evaluator-v1",
            input_text="Evaluate the frozen synthetic adversarial result.",
            evaluator_task=evaluator_task,
            source_packet=evaluator_packet,
            result_id="evaluator-result:sbx5",
        ),
        adapter=MockAdapter(
            ModelIdentity("mock", "mock-evaluator", "mock-family-evaluator"),
            output_text=json.dumps(evaluator_proposal, sort_keys=True),
        ),
    )
    evaluator_findings = evaluator_run_result.findings
    evaluator_result = evaluator_run_result.evaluator_result
    store_evaluator_task(connection, evaluator_task)
    store_evaluator_input_packet(connection, evaluator_task, evaluator_packet)
    for evaluator_finding in evaluator_findings:
        store_evaluator_finding(connection, evaluator_task, evaluator_packet, evaluator_finding)
    store_evaluator_result(
        connection,
        evaluator_task,
        evaluator_packet,
        evaluator_findings,
        evaluator_result,
    )
    hc_report, low_recognition_gate = _exercise_s8_evidence_sidecars(
        connection,
        case,
        progress,
        evaluator_result.result_hash,
        evaluator_result.frozen_at,
    )
    s8_terminal_hash = canonical_document_sha256(
        {
            "evaluator_result_hash": evaluator_result.result_hash,
            "hc_regression_report_hash": hc_report.report_hash,
            "low_recognition_gate_hash": low_recognition_gate.gate_hash,
        }
    )
    artifact_sink = getattr(progress, "artifacts", None)
    if artifact_sink is not None:
        artifact_sink.update(
            research_safety_admission=safety,
            research_safety_result=safety_result,
            scenario_admission_packet=admission_packet,
            scenario_admission_result=admission_result,
            qualification=qualification,
            controller_output=controller_output,
            controller_run=controller_run,
            scenario_set=scenario_set,
            resimulation_safety_admission=resim_safety,
            resimulation_safety_result=resim_safety_result,
            resimulation_plan=resim_build.plan,
            resimulation_routes=resim_build.routes,
            resimulation_result=artifacts.result,
            at17=artifacts.at17,
            revised_world=artifacts.world_state,
            revised_graph=artifacts.causal_graph,
            challenger_task=challenger_task,
            challenger_packet=challenger_packet,
            challenger_gate=challenger_gate,
        )
    return challenger_gate, s8_terminal_hash


def _trace_item(sequence: int, decision: TransitionDecision) -> dict[str, object]:
    return {
        "sequence": sequence,
        "source": decision.source.value,
        "target": decision.target.value,
        "status": decision.status.value,
        "guards": [
            {"name": guard.name, "status": guard.status.value, "reason": guard.reason}
            for guard in decision.guard_results
        ],
    }


def _exercise_authorized_transition_trace(values: dict[str, Any]) -> tuple[dict[str, object], ...]:
    """Exercise the production guard for every authorized S5--S7 edge."""

    position = CaseRuntimePosition(
        mode=CaseMode.MECHANISM_BENCHMARK,
        state=RuntimeState.BOUNDARY_AND_POLICY_FROZEN,
        case_revision=values["case"].revision,
    )
    decisions: list[TransitionDecision] = []
    common_s5 = {
        "requirement": values["requirement"],
        "records": values["framings"],
        "review": values["framing_review"],
        "plan": values["domain_plan"],
        "tasks": (values["domain_task"],),
        "routes": (values["domain_route"],),
        "outputs": (values["domain_output"],),
        "no_unresolved_protocol_invalid": True,
    }
    for target in (
        RuntimeState.FRAMING_INDEPENDENT,
        RuntimeState.FRAMING_REVIEWED,
        RuntimeState.DOMAIN_ROUTED,
        RuntimeState.DOMAIN_INDEPENDENT_RUN,
        RuntimeState.DOMAIN_OUTPUT_FROZEN,
    ):
        result = transition_s5_cde3(position, target, **common_s5)
        decisions.append(result.decision)
        position = result.position

    s6_checks: tuple[Callable[[CaseRuntimePosition], TransitionDecision], ...] = (
        lambda current: can_s6_wci1_transition(
            current,
            RuntimeState.CROSS_EXAMINATION,
            grant=values["disclosure_grant"],
            tasks=(values["cross_exam_task"],),
        ),
        lambda current: can_s6_wci2_transition(
            current,
            RuntimeState.WORLD_CAUSAL_INTEGRATION,
            responses=(values["cross_exam_response"],),
            disagreement_nodes=(values["disagreement"],),
            required_high_impact_position_ids=("minority-high",),
        ),
        lambda current: can_s6_wci3_transition(
            current,
            RuntimeState.CRITICAL_NODE_DETECTION,
            integration=values["critical_integration"],
        ),
        lambda current: can_s6_wci4_transition(
            current,
            RuntimeState.CRITICAL_NODE_REVIEW,
            detection=values["detection"],
            review_plan=values["critical_plan"],
        ),
    )
    for check in s6_checks:
        decision = check(position)
        if not decision.allowed:
            raise TransitionRejected(decision)
        decisions.append(decision)
        position = CaseRuntimePosition(position.mode, decision.target, position.case_revision)

    generation = transition_s7_scs1(
        position,
        RuntimeState.SCENARIO_GENERATION,
        world_state=values["world"],
        causal_graph=values["graph"],
        detection=values["detection"],
        review_plan=values["critical_plan"],
        research_safety_admission=values["research_safety_admission"],
        research_safety_result=values["research_safety_result"],
        admission_packet=values["scenario_admission_packet"],
        admission_result=values["scenario_admission_result"],
    )
    decisions.append(generation.decision)
    position = generation.position
    resimulation = transition_s7_scs3(
        position,
        RuntimeState.SCENARIO_RESIMULATION,
        case=values["case"],
        controller_output=values["controller_output"],
        scenario_set=values["scenario_set"],
        parent_world_state=values["world"],
        parent_causal_graph=values["graph"],
        parent_actor_states=(values["actor"],),
        qualification=values["qualification"],
        routes=values["resimulation_routes"],
        safety_admission=values["resimulation_safety_admission"],
        safety_result=values["resimulation_safety_result"],
        plan=values["resimulation_plan"],
    )
    decisions.append(resimulation.decision)
    position = resimulation.position
    adversarial = transition_s7_scs4(
        position,
        RuntimeState.ADVERSARIAL_REVIEW,
        case=values["case"],
        task=values["challenger_task"],
        packet=values["challenger_packet"],
        qualification=values["qualification"],
        critical_review_plan=values["critical_plan"],
        controller_output=values["controller_output"],
        controller_run=values["controller_run"],
        scenario_set=values["scenario_set"],
        resimulation_plan=values["resimulation_plan"],
        resimulation_result=values["resimulation_result"],
        at17=values["at17"],
        world_state=values["revised_world"],
        causal_graph=values["revised_graph"],
        safety_admission=values["resimulation_safety_admission"],
        safety_result=values["resimulation_safety_result"],
    )
    decisions.append(adversarial.decision)
    if adversarial.position.state is not RuntimeState.ADVERSARIAL_REVIEW:
        raise InstalledApplicationChainError("transition trace escaped ADVERSARIAL_REVIEW")
    final_attempt = can_transition(adversarial.position, RuntimeState.FINAL_SYNTHESIS)
    if final_attempt.status is not TransitionStatus.AUTHORIZATION_REQUIRED:
        raise InstalledApplicationChainError("FINAL_SYNTHESIS was not rejected")
    return tuple(_trace_item(index, decision) for index, decision in enumerate(decisions, 1))


def exercise_installed_application_chain(
    connection: Connection[Any],
    *,
    preserve_evidence: Callable[
        [InstalledApplicationChainCheckpoint, tuple[dict[str, object], ...]], None
    ]
    | None = None,
) -> InstalledApplicationChainReceipt:
    """Apply 0001--0007, execute connected S5--S8 APIs/stores, then roll them back."""

    _assert_clean_database(connection)
    applied = 0
    terminal_hashes: tuple[str, str, str, str] | None = None
    progress = _ChainProgress()
    checkpoint: InstalledApplicationChainCheckpoint | None = None
    evidence_snapshot_json: str | None = None
    evidence_snapshot_hash: str | None = None
    tables_exercised: tuple[str, ...] = ()
    stage_trace: tuple[dict[str, object], ...] = ()
    transitions = _ChronologicalTransitions()
    try:
        for migration in _MIGRATIONS:
            migration(connection)
            applied += 1
        try:
            case, framing_review, domain_output = _call_stage(
                _s5_records, connection, progress, advance=transitions.advance
            )
            actor, world, graph, detection, plan = _call_stage(
                _s6_records,
                connection,
                case,
                framing_review,
                domain_output,
                progress,
                advance=transitions.advance,
            )
            challenger_gate, s8_terminal_hash = _call_stage(
                _s7_s8_records,
                connection,
                case,
                actor,
                world,
                graph,
                detection,
                plan,
                progress,
                advance=transitions.advance,
            )
            terminal_hashes = (
                domain_output.record_hash,
                plan.plan_hash,
                challenger_gate.gate_result_hash,
                s8_terminal_hash,
            )
            stage_trace = transitions.trace()
            counts = tuple(
                connection.execute(f"SELECT count(*) FROM {table}").fetchone() for table in _TABLES
            )
            if any(row is None or int(row[0]) < 1 for row in counts):
                raise InstalledApplicationChainError("a typed stage store was not exercised")
            (
                evidence_snapshot_json,
                evidence_snapshot_hash,
                tables_exercised,
            ) = _capture_installed_evidence(connection)
            checkpoint = _freeze_application_checkpoint(
                terminal_hashes,
                tables_exercised=tables_exercised,
                evidence_snapshot_json=evidence_snapshot_json,
                evidence_snapshot_hash=evidence_snapshot_hash,
            )
            if preserve_evidence is not None:
                preserve_evidence(checkpoint, stage_trace)
        except Exception as exc:
            try:
                (
                    evidence_snapshot_json,
                    evidence_snapshot_hash,
                    tables_exercised,
                ) = _capture_installed_evidence(connection)
                checkpoint = _freeze_application_checkpoint(
                    progress,
                    tables_exercised=tables_exercised,
                    evidence_snapshot_json=evidence_snapshot_json,
                    evidence_snapshot_hash=evidence_snapshot_hash,
                )
            except Exception as snapshot_exc:
                raise InstalledApplicationChainError(
                    "installed application evidence capture failed"
                ) from snapshot_exc
            reason = "installed S5--S8 application chain failed"
            if _is_n3_context_constraint(exc):
                reason = str(exc)
                if not reason.startswith("FFT1_BLOCKED_BY_N3:"):
                    reason = f"FFT1_BLOCKED_BY_N3: {reason}"
            raise InstalledApplicationChainError(reason, checkpoint=checkpoint) from exc
    finally:
        try:
            _rollback_applied_migrations(connection, applied)
        except InstalledApplicationCleanupError as exc:
            raise InstalledApplicationCleanupError(str(exc), checkpoint=checkpoint) from exc
    if terminal_hashes is None:
        raise InstalledApplicationChainError("installed application chain did not complete")
    if evidence_snapshot_json is None or evidence_snapshot_hash is None:
        raise InstalledApplicationChainError("installed application evidence was not preserved")
    try:
        assert_installed_application_resources_clean(connection)
    except InstalledApplicationCleanupError as exc:
        raise InstalledApplicationCleanupError(str(exc), checkpoint=checkpoint) from exc
    seed = InstalledApplicationChainReceipt(
        migration_names=("0001", "0002", "0003", "0004", "0005", "0006", "0007"),
        s5_terminal_hash=terminal_hashes[0],
        s6_terminal_hash=terminal_hashes[1],
        s7_terminal_hash=terminal_hashes[2],
        s8_terminal_hash=terminal_hashes[3],
        tables_exercised=tables_exercised,
        evidence_snapshot_json=evidence_snapshot_json,
        evidence_snapshot_hash=evidence_snapshot_hash,
        stage_trace=stage_trace,
        final_runtime_state=RuntimeState.ADVERSARIAL_REVIEW.value,
        migrations_rolled_back=True,
        receipt_hash="",
    )
    receipt = InstalledApplicationChainReceipt(
        migration_names=seed.migration_names,
        s5_terminal_hash=seed.s5_terminal_hash,
        s6_terminal_hash=seed.s6_terminal_hash,
        s7_terminal_hash=seed.s7_terminal_hash,
        s8_terminal_hash=seed.s8_terminal_hash,
        tables_exercised=seed.tables_exercised,
        evidence_snapshot_json=seed.evidence_snapshot_json,
        evidence_snapshot_hash=seed.evidence_snapshot_hash,
        stage_trace=seed.stage_trace,
        final_runtime_state=seed.final_runtime_state,
        migrations_rolled_back=seed.migrations_rolled_back,
        receipt_hash=canonical_document_sha256(seed.to_document(include_hash=False)),
    )
    receipt.assert_integrity()
    return receipt
