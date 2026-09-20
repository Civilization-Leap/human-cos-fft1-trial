"""Deterministic S3-N control-plane state machine.

The frozen V0.1 Case Mode/state vocabulary and structural graph live here.
Future S4+ stages are represented for continuity but have no executable
business handlers in S3-N. Future edges therefore fail closed unless a later
authorized runtime layer explicitly activates the exact edge.
"""

from __future__ import annotations

from collections.abc import Set
from dataclasses import dataclass
from enum import Enum

PROTOCOL_VERSION = "0.1"


class CaseMode(str, Enum):
    HISTORICAL_BLIND_EVAL = "HISTORICAL_BLIND_EVAL"
    LIVE_FORESIGHT = "LIVE_FORESIGHT"
    MECHANISM_BENCHMARK = "MECHANISM_BENCHMARK"
    SCENARIO_STRESS_TEST = "SCENARIO_STRESS_TEST"


class RuntimeState(str, Enum):
    CASE_CREATED = "CASE_CREATED"
    EVIDENCE_RESEARCH = "EVIDENCE_RESEARCH"
    EVIDENCE_VERIFIED = "EVIDENCE_VERIFIED"
    BOUNDARY_AND_POLICY_FROZEN = "BOUNDARY_AND_POLICY_FROZEN"
    FRAMING_INDEPENDENT = "FRAMING_INDEPENDENT"
    FRAMING_REVIEWED = "FRAMING_REVIEWED"
    DOMAIN_ROUTED = "DOMAIN_ROUTED"
    DOMAIN_INDEPENDENT_RUN = "DOMAIN_INDEPENDENT_RUN"
    DOMAIN_OUTPUT_FROZEN = "DOMAIN_OUTPUT_FROZEN"
    CROSS_EXAMINATION = "CROSS_EXAMINATION"
    WORLD_CAUSAL_INTEGRATION = "WORLD_CAUSAL_INTEGRATION"
    CRITICAL_NODE_DETECTION = "CRITICAL_NODE_DETECTION"
    CRITICAL_NODE_REVIEW = "CRITICAL_NODE_REVIEW"
    SCENARIO_GENERATION = "SCENARIO_GENERATION"
    SCENARIO_RESIMULATION = "SCENARIO_RESIMULATION"
    ADVERSARIAL_REVIEW = "ADVERSARIAL_REVIEW"
    FINAL_SYNTHESIS = "FINAL_SYNTHESIS"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    SEALED = "SEALED"

    EXPERIMENT_PREREGISTERED = "EXPERIMENT_PREREGISTERED"
    RECOGNITION_PRECHECK = "RECOGNITION_PRECHECK"
    HC_TRACK_RUN = "HC_TRACK_RUN"
    BASELINE_TRACK_RUN = "BASELINE_TRACK_RUN"
    TRACK_OUTPUT_FROZEN = "TRACK_OUTPUT_FROZEN"
    BLIND_JUDGING = "BLIND_JUDGING"
    T1_T5_REVEAL = "T1_T5_REVEAL"
    EVIDENCE_STATUS_DECISION = "EVIDENCE_STATUS_DECISION"

    MONITORING = "MONITORING"
    NEW_EVIDENCE_INGESTED = "NEW_EVIDENCE_INGESTED"
    DELTA_ASSESSMENT = "DELTA_ASSESSMENT"
    SELECTIVE_RERUN = "SELECTIVE_RERUN"
    UPDATE_REVIEW = "UPDATE_REVIEW"
    UPDATED_RECORD = "UPDATED_RECORD"


class GateOutcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


class GuardStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNAVAILABLE = "UNAVAILABLE"


class TransitionStatus(str, Enum):
    ALLOWED = "ALLOWED"
    ILLEGAL_TRANSITION = "ILLEGAL_TRANSITION"
    AUTHORIZATION_REQUIRED = "AUTHORIZATION_REQUIRED"
    GUARD_FAILED = "GUARD_FAILED"
    GUARD_UNAVAILABLE = "GUARD_UNAVAILABLE"


@dataclass(frozen=True)
class CaseRuntimePosition:
    mode: CaseMode
    state: RuntimeState
    case_revision: int

    def __post_init__(self) -> None:
        if self.case_revision < 1:
            raise ValueError("case_revision must be >= 1")


@dataclass(frozen=True)
class TransitionKey:
    mode: CaseMode
    source: RuntimeState
    target: RuntimeState


@dataclass(frozen=True)
class GuardFacts:
    all_required_runs_finished: bool | None = None
    no_unresolved_protocol_invalid: bool | None = None

    claim_provenance_passed: bool | None = None
    falsification_contract_present: bool | None = None
    high_impact_dissent_recorded: bool | None = None
    safety_status_valid: bool | None = None

    contamination_gate: GateOutcome | None = None
    parity_guard: GateOutcome | None = None

    delta_reason: str | None = None
    affected_claims: tuple[str, ...] | None = None
    update_contract_result: str | None = None


@dataclass(frozen=True)
class GuardCheck:
    name: str
    status: GuardStatus
    reason: str


@dataclass(frozen=True)
class TransitionDecision:
    allowed: bool
    status: TransitionStatus
    mode: CaseMode
    source: RuntimeState
    target: RuntimeState
    protocol_version: str
    guard_results: tuple[GuardCheck, ...]
    reason: str

    def to_audit_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode.value,
            "from": self.source.value,
            "to": self.target.value,
            "protocol_version": self.protocol_version,
            "status": self.status.value,
            "allowed": self.allowed,
            "reason": self.reason,
            "guards": [
                {
                    "name": guard.name,
                    "status": guard.status.value,
                    "reason": guard.reason,
                }
                for guard in self.guard_results
            ],
        }


@dataclass(frozen=True)
class TransitionResult:
    position: CaseRuntimePosition
    decision: TransitionDecision


class TransitionRejected(RuntimeError):
    def __init__(self, decision: TransitionDecision) -> None:
        self.decision = decision
        super().__init__(f"{decision.status.value}: {decision.reason}")


_COMMON_SEQUENCE = (
    RuntimeState.CASE_CREATED,
    RuntimeState.EVIDENCE_RESEARCH,
    RuntimeState.EVIDENCE_VERIFIED,
    RuntimeState.BOUNDARY_AND_POLICY_FROZEN,
    RuntimeState.FRAMING_INDEPENDENT,
    RuntimeState.FRAMING_REVIEWED,
    RuntimeState.DOMAIN_ROUTED,
    RuntimeState.DOMAIN_INDEPENDENT_RUN,
    RuntimeState.DOMAIN_OUTPUT_FROZEN,
    RuntimeState.CROSS_EXAMINATION,
    RuntimeState.WORLD_CAUSAL_INTEGRATION,
    RuntimeState.CRITICAL_NODE_DETECTION,
    RuntimeState.CRITICAL_NODE_REVIEW,
    RuntimeState.SCENARIO_GENERATION,
    RuntimeState.SCENARIO_RESIMULATION,
    RuntimeState.ADVERSARIAL_REVIEW,
    RuntimeState.FINAL_SYNTHESIS,
    RuntimeState.HUMAN_REVIEW,
    RuntimeState.SEALED,
)

_COMMON_GRAPH: dict[RuntimeState, frozenset[RuntimeState]] = {
    source: frozenset({_COMMON_SEQUENCE[index + 1]})
    for index, source in enumerate(_COMMON_SEQUENCE[:-1])
}

_HISTORICAL_GRAPH: dict[RuntimeState, frozenset[RuntimeState]] = {
    RuntimeState.CASE_CREATED: frozenset({RuntimeState.EVIDENCE_RESEARCH}),
    RuntimeState.EVIDENCE_RESEARCH: frozenset({RuntimeState.EVIDENCE_VERIFIED}),
    RuntimeState.EVIDENCE_VERIFIED: frozenset({RuntimeState.EXPERIMENT_PREREGISTERED}),
    RuntimeState.EXPERIMENT_PREREGISTERED: frozenset({RuntimeState.RECOGNITION_PRECHECK}),
    RuntimeState.RECOGNITION_PRECHECK: frozenset(
        {RuntimeState.HC_TRACK_RUN, RuntimeState.BASELINE_TRACK_RUN}
    ),
    RuntimeState.HC_TRACK_RUN: frozenset({RuntimeState.TRACK_OUTPUT_FROZEN}),
    RuntimeState.BASELINE_TRACK_RUN: frozenset({RuntimeState.TRACK_OUTPUT_FROZEN}),
    RuntimeState.TRACK_OUTPUT_FROZEN: frozenset({RuntimeState.BLIND_JUDGING}),
    RuntimeState.BLIND_JUDGING: frozenset({RuntimeState.T1_T5_REVEAL}),
    RuntimeState.T1_T5_REVEAL: frozenset({RuntimeState.EVIDENCE_STATUS_DECISION}),
    RuntimeState.EVIDENCE_STATUS_DECISION: frozenset({RuntimeState.SEALED}),
}

_LIVE_EXTRA_GRAPH: dict[RuntimeState, frozenset[RuntimeState]] = {
    RuntimeState.SEALED: frozenset({RuntimeState.MONITORING}),
    RuntimeState.MONITORING: frozenset({RuntimeState.NEW_EVIDENCE_INGESTED}),
    RuntimeState.NEW_EVIDENCE_INGESTED: frozenset({RuntimeState.DELTA_ASSESSMENT}),
    RuntimeState.DELTA_ASSESSMENT: frozenset({RuntimeState.SELECTIVE_RERUN}),
    RuntimeState.SELECTIVE_RERUN: frozenset({RuntimeState.UPDATE_REVIEW}),
    RuntimeState.UPDATE_REVIEW: frozenset({RuntimeState.UPDATED_RECORD}),
    RuntimeState.UPDATED_RECORD: frozenset({RuntimeState.MONITORING}),
}

# S3-N can execute only pre-cognition control-plane transitions by default.
# All other structural edges require a later authorized layer to activate the
# exact mode/source/target edge.
_S3_N_NATIVE_TARGETS = frozenset(
    {
        RuntimeState.EVIDENCE_RESEARCH,
        RuntimeState.EVIDENCE_VERIFIED,
        RuntimeState.BOUNDARY_AND_POLICY_FROZEN,
    }
)
_NO_TRANSITIONS: frozenset[TransitionKey] = frozenset()


def _graph_for_mode(mode: CaseMode) -> dict[RuntimeState, frozenset[RuntimeState]]:
    if mode is CaseMode.HISTORICAL_BLIND_EVAL:
        return _HISTORICAL_GRAPH
    if mode is CaseMode.LIVE_FORESIGHT:
        return {**_COMMON_GRAPH, **_LIVE_EXTRA_GRAPH}
    return _COMMON_GRAPH


def structural_targets(mode: CaseMode, state: RuntimeState) -> frozenset[RuntimeState]:
    """Return frozen structural successors without granting execution authority."""
    return _graph_for_mode(mode).get(state, frozenset())


def _bool_guard(name: str, value: bool | None) -> GuardCheck:
    if value is None:
        return GuardCheck(name, GuardStatus.UNAVAILABLE, f"{name} was not supplied")
    if value:
        return GuardCheck(name, GuardStatus.PASS, f"{name} is true")
    return GuardCheck(name, GuardStatus.FAIL, f"{name} is false")


def _gate_guard(name: str, value: GateOutcome | None) -> GuardCheck:
    if value is None:
        return GuardCheck(name, GuardStatus.UNAVAILABLE, f"{name} was not supplied")
    if value is GateOutcome.PASS:
        return GuardCheck(name, GuardStatus.PASS, f"{name} == PASS")
    return GuardCheck(name, GuardStatus.FAIL, f"{name} != PASS")


def _nonempty_text_guard(name: str, value: str | None) -> GuardCheck:
    if value is None:
        return GuardCheck(name, GuardStatus.UNAVAILABLE, f"{name} was not supplied")
    if value.strip():
        return GuardCheck(name, GuardStatus.PASS, f"{name} is present")
    return GuardCheck(name, GuardStatus.FAIL, f"{name} is empty")


def _nonempty_items_guard(name: str, value: tuple[str, ...] | None) -> GuardCheck:
    if value is None:
        return GuardCheck(name, GuardStatus.UNAVAILABLE, f"{name} was not supplied")
    if value:
        return GuardCheck(name, GuardStatus.PASS, f"{name} is non-empty")
    return GuardCheck(name, GuardStatus.FAIL, f"{name} is empty")


def _guard_results(
    source: RuntimeState,
    target: RuntimeState,
    facts: GuardFacts,
) -> tuple[GuardCheck, ...]:
    if (
        source is RuntimeState.DOMAIN_INDEPENDENT_RUN
        and target is RuntimeState.DOMAIN_OUTPUT_FROZEN
    ):
        return (
            _bool_guard("all_required_runs_finished", facts.all_required_runs_finished),
            _bool_guard(
                "no_unresolved_protocol_invalid",
                facts.no_unresolved_protocol_invalid,
            ),
        )

    if source is RuntimeState.FINAL_SYNTHESIS and target is RuntimeState.HUMAN_REVIEW:
        return (
            _bool_guard("claim_provenance_passed", facts.claim_provenance_passed),
            _bool_guard(
                "falsification_contract_present",
                facts.falsification_contract_present,
            ),
            _bool_guard(
                "high_impact_dissent_recorded",
                facts.high_impact_dissent_recorded,
            ),
            _bool_guard("safety_status_valid", facts.safety_status_valid),
        )

    if source is RuntimeState.TRACK_OUTPUT_FROZEN and target is RuntimeState.BLIND_JUDGING:
        return (
            _gate_guard("contamination_gate", facts.contamination_gate),
            _gate_guard("parity_guard", facts.parity_guard),
        )

    if source is RuntimeState.UPDATE_REVIEW and target is RuntimeState.UPDATED_RECORD:
        return (
            _nonempty_text_guard("delta_reason", facts.delta_reason),
            _nonempty_items_guard("affected_claims", facts.affected_claims),
            _nonempty_text_guard(
                "update_contract_result",
                facts.update_contract_result,
            ),
        )

    return ()


def _decision(
    *,
    allowed: bool,
    status: TransitionStatus,
    position: CaseRuntimePosition,
    target: RuntimeState,
    protocol_version: str,
    reason: str,
    guards: tuple[GuardCheck, ...] = (),
) -> TransitionDecision:
    return TransitionDecision(
        allowed=allowed,
        status=status,
        mode=position.mode,
        source=position.state,
        target=target,
        protocol_version=protocol_version,
        guard_results=guards,
        reason=reason,
    )


def can_transition(
    position: CaseRuntimePosition,
    target: RuntimeState,
    *,
    guard_facts: GuardFacts | None = None,
    authorized_future_transitions: Set[TransitionKey] = _NO_TRANSITIONS,
    protocol_version: str = PROTOCOL_VERSION,
) -> TransitionDecision:
    """Decide a state change without mutating state or invoking a handler."""
    if not protocol_version:
        raise ValueError("protocol_version must be non-empty")

    if target not in structural_targets(position.mode, position.state):
        return _decision(
            allowed=False,
            status=TransitionStatus.ILLEGAL_TRANSITION,
            position=position,
            target=target,
            protocol_version=protocol_version,
            reason="target is not a frozen structural successor for this Case Mode",
        )

    key = TransitionKey(position.mode, position.state, target)
    if target not in _S3_N_NATIVE_TARGETS and key not in authorized_future_transitions:
        return _decision(
            allowed=False,
            status=TransitionStatus.AUTHORIZATION_REQUIRED,
            position=position,
            target=target,
            protocol_version=protocol_version,
            reason=(
                "future-stage edge is represented structurally but has no authorized "
                "S3-N executable handler"
            ),
        )

    facts = guard_facts if guard_facts is not None else GuardFacts()
    guards = _guard_results(position.state, target, facts)
    if any(guard.status is GuardStatus.FAIL for guard in guards):
        return _decision(
            allowed=False,
            status=TransitionStatus.GUARD_FAILED,
            position=position,
            target=target,
            protocol_version=protocol_version,
            reason="one or more frozen transition guards failed",
            guards=guards,
        )
    if any(guard.status is GuardStatus.UNAVAILABLE for guard in guards):
        return _decision(
            allowed=False,
            status=TransitionStatus.GUARD_UNAVAILABLE,
            position=position,
            target=target,
            protocol_version=protocol_version,
            reason="one or more frozen transition guard facts are unavailable",
            guards=guards,
        )

    return _decision(
        allowed=True,
        status=TransitionStatus.ALLOWED,
        position=position,
        target=target,
        protocol_version=protocol_version,
        reason="transition is structurally valid, authorized, and guard-clean",
        guards=guards,
    )


def transition(
    position: CaseRuntimePosition,
    target: RuntimeState,
    *,
    guard_facts: GuardFacts | None = None,
    authorized_future_transitions: Set[TransitionKey] = _NO_TRANSITIONS,
    protocol_version: str = PROTOCOL_VERSION,
) -> TransitionResult:
    """Return a new immutable position or raise with the audit decision."""
    decision = can_transition(
        position,
        target,
        guard_facts=guard_facts,
        authorized_future_transitions=authorized_future_transitions,
        protocol_version=protocol_version,
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
