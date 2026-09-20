"""Authorized S3-N trusted-runtime substrate interfaces."""

from human_cos.runtime.state_machine import (
    PROTOCOL_VERSION,
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
    structural_targets,
    transition,
)

__all__ = [
    "PROTOCOL_VERSION",
    "CaseMode",
    "CaseRuntimePosition",
    "GateOutcome",
    "GuardCheck",
    "GuardFacts",
    "GuardStatus",
    "RuntimeState",
    "TransitionDecision",
    "TransitionKey",
    "TransitionRejected",
    "TransitionResult",
    "TransitionStatus",
    "can_transition",
    "structural_targets",
    "transition",
]
