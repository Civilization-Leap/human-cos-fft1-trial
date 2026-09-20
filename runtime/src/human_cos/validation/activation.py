"""S4-V4 exact HISTORICAL_BLIND_EVAL state activation through T1_T5_REVEAL."""

from __future__ import annotations

from dataclasses import dataclass

from human_cos.runtime.state_machine import (
    CaseMode,
    CaseRuntimePosition,
    GateOutcome,
    GuardCheck,
    GuardFacts,
    GuardStatus,
    RuntimeState,
    TransitionDecision,
    TransitionKey,
    TransitionRejected,
    TransitionResult,
    TransitionStatus,
    can_transition,
)

S4_V_HISTORICAL_TRANSITIONS: frozenset[TransitionKey] = frozenset(
    {
        TransitionKey(
            CaseMode.HISTORICAL_BLIND_EVAL,
            RuntimeState.EVIDENCE_VERIFIED,
            RuntimeState.EXPERIMENT_PREREGISTERED,
        ),
        TransitionKey(
            CaseMode.HISTORICAL_BLIND_EVAL,
            RuntimeState.EXPERIMENT_PREREGISTERED,
            RuntimeState.RECOGNITION_PRECHECK,
        ),
        TransitionKey(
            CaseMode.HISTORICAL_BLIND_EVAL,
            RuntimeState.RECOGNITION_PRECHECK,
            RuntimeState.HC_TRACK_RUN,
        ),
        TransitionKey(
            CaseMode.HISTORICAL_BLIND_EVAL,
            RuntimeState.RECOGNITION_PRECHECK,
            RuntimeState.BASELINE_TRACK_RUN,
        ),
        TransitionKey(
            CaseMode.HISTORICAL_BLIND_EVAL,
            RuntimeState.HC_TRACK_RUN,
            RuntimeState.TRACK_OUTPUT_FROZEN,
        ),
        TransitionKey(
            CaseMode.HISTORICAL_BLIND_EVAL,
            RuntimeState.BASELINE_TRACK_RUN,
            RuntimeState.TRACK_OUTPUT_FROZEN,
        ),
        TransitionKey(
            CaseMode.HISTORICAL_BLIND_EVAL,
            RuntimeState.TRACK_OUTPUT_FROZEN,
            RuntimeState.BLIND_JUDGING,
        ),
        TransitionKey(
            CaseMode.HISTORICAL_BLIND_EVAL,
            RuntimeState.BLIND_JUDGING,
            RuntimeState.T1_T5_REVEAL,
        ),
    }
)


@dataclass(frozen=True)
class HistoricalActivationFacts:
    recognition_precheck: GateOutcome | None = None
    frozen_output_binding_present: bool | None = None
    contamination_gate: GateOutcome | None = None
    parity_guard: GateOutcome | None = None
    judge_submission_frozen: bool | None = None


def _explicit_guard(name: str, value: bool | None) -> GuardCheck:
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


def _decision_with_guard(
    base: TransitionDecision,
    guard: GuardCheck,
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
        reason="S4-V historical transition prerequisite was not satisfied",
    )


def can_s4_v_historical_transition(
    position: CaseRuntimePosition,
    target: RuntimeState,
    *,
    facts: HistoricalActivationFacts | None = None,
) -> TransitionDecision:
    """Authorize only the eight formally granted historical edges and their explicit facts."""
    supplied = facts if facts is not None else HistoricalActivationFacts()
    base = can_transition(
        position,
        target,
        guard_facts=GuardFacts(
            contamination_gate=supplied.contamination_gate,
            parity_guard=supplied.parity_guard,
        ),
        authorized_future_transitions=S4_V_HISTORICAL_TRANSITIONS,
    )
    if not base.allowed:
        return base

    if position.state is RuntimeState.RECOGNITION_PRECHECK and target in {
        RuntimeState.HC_TRACK_RUN,
        RuntimeState.BASELINE_TRACK_RUN,
    }:
        return _decision_with_guard(
            base,
            _gate_guard("recognition_precheck", supplied.recognition_precheck),
        )
    if position.state in {RuntimeState.HC_TRACK_RUN, RuntimeState.BASELINE_TRACK_RUN} and (
        target is RuntimeState.TRACK_OUTPUT_FROZEN
    ):
        return _decision_with_guard(
            base,
            _explicit_guard(
                "frozen_output_binding_present",
                supplied.frozen_output_binding_present,
            ),
        )
    if position.state is RuntimeState.BLIND_JUDGING and target is RuntimeState.T1_T5_REVEAL:
        return _decision_with_guard(
            base,
            _explicit_guard("judge_submission_frozen", supplied.judge_submission_frozen),
        )
    return base


def transition_s4_v_historical(
    position: CaseRuntimePosition,
    target: RuntimeState,
    *,
    facts: HistoricalActivationFacts | None = None,
) -> TransitionResult:
    decision = can_s4_v_historical_transition(position, target, facts=facts)
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
