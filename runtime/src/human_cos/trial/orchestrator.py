"""Mock-only TRIAL-SBX2 orchestration wrapper.

SBX2 proves the application-side sequencing and fail-closed stop engine without
creating a second cognitive engine. The package-owned bootstrap path below is a
control-plane rehearsal: it validates the exact canonical bundle/environment and
walks only the frozen common Runtime structure through ADVERSARIAL_REVIEW. It does
not manufacture S5-S8 semantic artifacts and is not a substantive Case result.
Full canonical semantic cases remain SBX4-owned.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from human_cos.runtime.state_machine import RuntimeState, structural_targets

from .bundle import (
    VerifiedTrialBundle,
    _AuthenticatedCanonicalAdmission,
    _canonical_is_authenticated,
)
from .contracts import (
    TrialAdmissionStatus,
    TrialCapabilityAcceptance,
    TrialEnvironmentAdmission,
    TrialOutcome,
    TrialResult,
    TrialRuntimePosition,
    TrialStop,
    TrialStopCondition,
    TrialStopPhase,
    assert_environment_admission_binding,
    assert_trial_result_binding,
)
from .stop_engine import TrialResourceMeter, TrialStopLedger, TrialStopSignal


class TrialOrchestrationError(ValueError):
    """The requested SBX2 orchestration is outside the frozen sandbox authority."""


@dataclass(frozen=True)
class TrialOrchestrationRecord:
    stop: TrialStop
    result: TrialResult
    stage_calls: int
    model_calls: int


_BOOTSTRAP_CONTROL_STATES: tuple[RuntimeState, ...] = (
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
)


def _assert_bootstrap_admitted(
    bundle: VerifiedTrialBundle,
    canonical_admission: _AuthenticatedCanonicalAdmission,
    environment: TrialEnvironmentAdmission,
) -> None:
    bundle.assert_integrity()
    canonical_admission.assert_integrity()
    environment.assert_integrity()
    if not _canonical_is_authenticated(canonical_admission):
        raise TrialOrchestrationError("SBX2 requires package-authenticated canonical admission")
    if environment.status is not TrialAdmissionStatus.PASS:
        raise TrialOrchestrationError("SBX2 cannot execute a rejected Environment Admission")
    record = canonical_admission.record
    if record.bundle_receipt_hash != bundle.receipt.bundle_receipt_hash:
        raise TrialOrchestrationError("canonical admission does not bind exact verified bundle")
    assert_environment_admission_binding(
        bundle.attempt,
        bundle.manifest,
        record,
        environment,
    )


def _assert_frozen_structural_path(bundle: VerifiedTrialBundle) -> None:
    mode = bundle.manifest.case_mode
    for source, target in zip(
        _BOOTSTRAP_CONTROL_STATES[:-1],
        _BOOTSTRAP_CONTROL_STATES[1:],
        strict=True,
    ):
        if target not in structural_targets(mode, source):
            raise TrialOrchestrationError(
                f"bootstrap structural path is not frozen for {source.value}->{target.value}"
            )


def run_bootstrap_control_rehearsal(
    *,
    bundle: VerifiedTrialBundle,
    canonical_admission: _AuthenticatedCanonicalAdmission,
    environment: TrialEnvironmentAdmission,
    recorded_at: datetime,
) -> TrialOrchestrationRecord:
    """Execute the package-owned SBX2 control-plane rehearsal.

    This path intentionally performs zero model calls and produces no cognitive
    artifacts. It demonstrates that exact canonical admission, resource accounting,
    ordered Runtime trajectory, terminal-boundary enforcement, and immutable stop /
    result freeze work together without opening Final Synthesis.
    """

    _assert_bootstrap_admitted(bundle, canonical_admission, environment)
    _assert_frozen_structural_path(bundle)
    meter = TrialResourceMeter(bundle.manifest)
    ledger = TrialStopLedger(
        attempt_receipt_hash=bundle.attempt.attempt_receipt_hash,
        manifest=bundle.manifest,
        environment=environment,
    )

    for state in _BOOTSTRAP_CONTROL_STATES:
        resource_stop = meter.record(stage_calls=1)
        if resource_stop is not None:
            ledger.signal(resource_stop)
            break
        ledger.record_position(
            TrialRuntimePosition(
                mode=bundle.manifest.case_mode,
                state=state,
                case_revision=bundle.manifest.case_revision,
            ),
            controlling_ref=f"sbx2:structural-control:{state.value}",
            recorded_at=recorded_at,
        )
    else:
        ledger.signal(
            TrialStopSignal(
                condition=TrialStopCondition.AUTHORIZED_BOUNDARY_REACHED,
                phase=TrialStopPhase.EXECUTION,
                reason=(
                    "package-owned Mock-only control rehearsal reached "
                    "ADVERSARIAL_REVIEW without semantic or execution authority"
                ),
            )
        )

    controlling = ledger.controlling_signal()
    accepted = (
        TrialCapabilityAcceptance.PASS
        if controlling.condition is TrialStopCondition.AUTHORIZED_BOUNDARY_REACHED
        else TrialCapabilityAcceptance.FAIL
    )
    stop, result = ledger.freeze_terminal(
        stop_id=f"stop:{bundle.attempt.attempt_id}",
        result_id=f"result:{bundle.attempt.attempt_id}",
        trial_capability_acceptance=accepted,
        substantive_case_outcome=None,
        limitations=(
            "SBX2 bootstrap is a control-plane rehearsal only; it does not claim "
            "that S5-S8 semantic stages were substantively executed.",
        ),
        stopped_at=recorded_at,
    )
    assert_trial_result_binding(
        bundle.attempt,
        bundle.manifest,
        environment,
        stop,
        result,
    )
    if result.outcome is TrialOutcome.COMPLETED_AT_AUTHORIZED_BOUNDARY:
        if result.final_runtime_position is None:
            raise TrialOrchestrationError("completed rehearsal lacks final Runtime position")
        if result.final_runtime_position.state is not RuntimeState.ADVERSARIAL_REVIEW:
            raise TrialOrchestrationError("SBX2 rehearsal escaped the authorized terminal state")
    return TrialOrchestrationRecord(
        stop=stop,
        result=result,
        stage_calls=meter.stage_calls,
        model_calls=meter.model_calls,
    )
