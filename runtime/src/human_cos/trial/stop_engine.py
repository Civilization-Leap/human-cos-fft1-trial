"""Deterministic stop ledger for the authorized TRIAL-SBX2 slice.

The ledger owns only trial sequencing metadata, resource accounting, stop
precedence, and immutable TrialStop/TrialResult freeze. It does not make any
S5-S8 semantic judgment and cannot grant downstream authority.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from human_cos.runtime.state_machine import RuntimeState, structural_targets

from .contracts import (
    TrialArtifactRef,
    TrialAuditExportStatus,
    TrialCapabilityAcceptance,
    TrialCleanupDisposition,
    TrialEnvironmentAdmission,
    TrialManifest,
    TrialOutcome,
    TrialResult,
    TrialResultPayload,
    TrialRuntimePosition,
    TrialRuntimeStep,
    TrialRuntimeStepPayload,
    TrialStop,
    TrialStopCondition,
    TrialStopPayload,
    TrialStopPhase,
    freeze_trial_result,
    freeze_trial_runtime_step,
    freeze_trial_stop,
    select_controlling_stop,
    stop_outcome_for,
)


class TrialStopEngineError(ValueError):
    """Trial orchestration facts violate the frozen sandbox boundary."""


@dataclass(frozen=True)
class TrialStopSignal:
    condition: TrialStopCondition
    phase: TrialStopPhase
    reason: str
    controlling_artifact_refs: tuple[TrialArtifactRef, ...] = ()

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise TrialStopEngineError("stop signal reason must be non-empty")


@dataclass
class TrialResourceMeter:
    """Code-owned counters bounded by the frozen Trial Manifest limits."""

    manifest: TrialManifest
    stage_calls: int = 0
    model_calls: int = 0
    output_bytes: int = 0
    output_tokens: int = 0
    frozen_artifacts: int = 0
    elapsed_seconds: float = 0.0
    retries: int = 0
    clock: Callable[[], float] = field(default=time.monotonic, repr=False, compare=False)
    _started_at: float = field(init=False, repr=False)
    _recorded_once: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        started_at = self.clock()
        if not math.isfinite(started_at):
            raise TrialStopEngineError("resource clock must return a finite value")
        self._started_at = started_at

    def _exceeded(self) -> bool:
        limits = self.manifest.resource_limits
        return (
            self.stage_calls > limits.max_stage_calls
            or self.model_calls > limits.max_model_calls
            or self.output_bytes > limits.max_output_bytes
            or self.output_tokens > limits.max_output_tokens
            or self.frozen_artifacts > limits.max_frozen_artifacts
            or self.elapsed_seconds > limits.max_wall_clock_seconds
            or self.retries > limits.max_retries
        )

    def _non_wall_clock_exceeded(self) -> bool:
        limits = self.manifest.resource_limits
        return (
            self.stage_calls > limits.max_stage_calls
            or self.model_calls > limits.max_model_calls
            or self.output_bytes > limits.max_output_bytes
            or self.output_tokens > limits.max_output_tokens
            or self.frozen_artifacts > limits.max_frozen_artifacts
            or self.retries > limits.max_retries
        )

    def record(
        self,
        *,
        stage_calls: int = 0,
        model_calls: int = 0,
        output_bytes: int = 0,
        output_tokens: int = 0,
        frozen_artifacts: int = 0,
        elapsed_seconds: float | None = None,
        retries: int = 0,
    ) -> TrialStopSignal | None:
        values = (
            stage_calls,
            model_calls,
            output_bytes,
            output_tokens,
            frozen_artifacts,
            retries,
        )
        if any(value < 0 for value in values):
            raise TrialStopEngineError("resource deltas must be non-negative")
        if elapsed_seconds is None:
            elapsed_seconds = self.clock() - self._started_at
        if not math.isfinite(elapsed_seconds) or elapsed_seconds < 0:
            raise TrialStopEngineError("elapsed seconds must be finite and non-negative")
        if elapsed_seconds < self.elapsed_seconds:
            raise TrialStopEngineError("elapsed seconds must be monotonic")
        self.elapsed_seconds = elapsed_seconds
        self.stage_calls += stage_calls
        self.model_calls += model_calls
        self.output_bytes += output_bytes
        self.output_tokens += output_tokens
        self.frozen_artifacts += frozen_artifacts
        self.retries += retries
        first_record = not self._recorded_once
        self._recorded_once = True
        wall_clock_exceeded = (
            self.elapsed_seconds > self.manifest.resource_limits.max_wall_clock_seconds
        )
        defer_initial_wall_clock_only_stop = (
            first_record and wall_clock_exceeded and not self._non_wall_clock_exceeded()
        )
        if not self._exceeded() or defer_initial_wall_clock_only_stop:
            return None
        return TrialStopSignal(
            condition=TrialStopCondition.RESOURCE_LIMIT_REACHED,
            phase=TrialStopPhase.EXECUTION,
            reason="code-owned trial resource ceiling was exceeded",
        )


@dataclass
class TrialStopLedger:
    """Append-only in-memory ledger for one SBX2 attempt.

    Durable/export representation remains SBX3-owned. The ledger freezes all
    terminal facts into the existing SBX1 immutable contracts.
    """

    attempt_receipt_hash: str
    manifest: TrialManifest
    environment: TrialEnvironmentAdmission
    clock: Callable[[], float] = field(default=time.monotonic, repr=False, compare=False)
    _steps: list[TrialRuntimeStep] = field(default_factory=list, init=False, repr=False)
    _produced_artifacts: list[TrialArtifactRef] = field(
        default_factory=list, init=False, repr=False
    )
    _signals: list[TrialStopSignal] = field(default_factory=list, init=False, repr=False)
    _terminal_frozen: bool = field(default=False, init=False, repr=False)
    _started_at: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        started_at = self.clock()
        if not math.isfinite(started_at):
            raise TrialStopEngineError("ledger clock must return a finite value")
        self._started_at = started_at

    @property
    def steps(self) -> tuple[TrialRuntimeStep, ...]:
        return tuple(self._steps)

    @property
    def produced_artifacts(self) -> tuple[TrialArtifactRef, ...]:
        return tuple(self._produced_artifacts)

    @property
    def signals(self) -> tuple[TrialStopSignal, ...]:
        return tuple(self._signals)

    def _assert_open(self) -> None:
        if self._terminal_frozen:
            raise TrialStopEngineError("terminal Trial ledger is frozen")

    def record_position(
        self,
        position: TrialRuntimePosition,
        *,
        controlling_ref: str,
        recorded_at: datetime,
    ) -> TrialRuntimeStep:
        self._assert_open()
        if not controlling_ref.strip():
            raise TrialStopEngineError("Runtime step controlling_ref must be non-empty")
        if (
            position.mode is not self.manifest.case_mode
            or position.case_revision != self.manifest.case_revision
        ):
            raise TrialStopEngineError("Runtime trajectory Case identity changed")
        if not self._steps:
            if position.state is not RuntimeState.CASE_CREATED:
                raise TrialStopEngineError("Runtime trajectory must start at CASE_CREATED")
        else:
            previous = self._steps[-1].position
            if position.state not in structural_targets(previous.mode, previous.state):
                raise TrialStopEngineError(
                    f"illegal Runtime transition {previous.state.value}->{position.state.value}"
                )
        step = freeze_trial_runtime_step(
            TrialRuntimeStepPayload(
                step_id=f"trial-step:{len(self._steps) + 1}",
                step_index=len(self._steps) + 1,
                position=position,
                controlling_ref=controlling_ref,
                recorded_at=recorded_at,
            )
        )
        self._steps.append(step)
        return step

    def record_artifacts(self, artifacts: tuple[TrialArtifactRef, ...]) -> None:
        self._assert_open()
        existing = {(item.kind, item.ref, item.sha256) for item in self._produced_artifacts}
        for item in artifacts:
            key = (item.kind, item.ref, item.sha256)
            if key not in existing:
                self._produced_artifacts.append(item)
                existing.add(key)

    def signal(self, signal: TrialStopSignal) -> None:
        self._assert_open()
        if signal.condition is TrialStopCondition.AUTHORIZED_BOUNDARY_REACHED:
            elapsed_seconds = self.clock() - self._started_at
            if not math.isfinite(elapsed_seconds) or elapsed_seconds < 0:
                raise TrialStopEngineError("ledger elapsed seconds must be finite and non-negative")
            if elapsed_seconds > self.manifest.resource_limits.max_wall_clock_seconds:
                signal = TrialStopSignal(
                    condition=TrialStopCondition.RESOURCE_LIMIT_REACHED,
                    phase=TrialStopPhase.EXECUTION,
                    reason="code-owned trial wall-clock ceiling was exceeded at terminal boundary",
                )
        self._signals.append(signal)

    def controlling_signal(self) -> TrialStopSignal:
        if not self._signals:
            raise TrialStopEngineError("terminal freeze requires at least one stop signal")
        conditions = tuple(signal.condition for signal in self._signals)
        controlling = select_controlling_stop(tuple(dict.fromkeys(conditions)))
        return next(signal for signal in self._signals if signal.condition is controlling)

    def freeze_terminal(
        self,
        *,
        stop_id: str,
        result_id: str,
        trial_capability_acceptance: TrialCapabilityAcceptance,
        stopped_at: datetime,
        substantive_case_outcome: TrialOutcome | None = None,
        limitations: tuple[str, ...] = (),
        dissent_refs: tuple[str, ...] = (),
        unresolved_condition_refs: tuple[str, ...] = (),
    ) -> tuple[TrialStop, TrialResult]:
        self._assert_open()
        controlling = self.controlling_signal()
        outcome = stop_outcome_for(controlling.condition)
        trajectory = tuple(self._steps)
        final_position = trajectory[-1].position if trajectory else None
        artifact_refs = tuple(self._produced_artifacts)
        reasons = tuple(
            dict.fromkeys(
                signal.reason
                for signal in self._signals
                if signal.condition is controlling.condition
            )
        )
        controlling_refs: list[TrialArtifactRef] = []
        seen: set[tuple[str, str, str]] = set()
        for signal in self._signals:
            if signal.condition is not controlling.condition:
                continue
            for ref in signal.controlling_artifact_refs:
                key = (ref.kind, ref.ref, ref.sha256)
                if key not in seen:
                    seen.add(key)
                    controlling_refs.append(ref)

        stop = freeze_trial_stop(
            TrialStopPayload(
                stop_id=stop_id,
                attempt_receipt_hash=self.attempt_receipt_hash,
                trial_manifest_hash=self.manifest.manifest_hash,
                environment_admission_hash=self.environment.environment_admission_hash,
                case_id=self.manifest.case_id,
                case_revision=self.manifest.case_revision,
                case_mode=self.manifest.case_mode,
                outcome=outcome,
                stop_condition=controlling.condition,
                stop_phase=controlling.phase,
                runtime_trajectory=trajectory,
                final_runtime_position=final_position,
                controlling_artifact_refs=tuple(controlling_refs),
                reasons=reasons,
                produced_artifacts=artifact_refs,
                stopped_at=stopped_at,
            )
        )
        result = freeze_trial_result(
            TrialResultPayload(
                result_id=result_id,
                attempt_receipt_hash=self.attempt_receipt_hash,
                trial_manifest_hash=self.manifest.manifest_hash,
                environment_admission_hash=self.environment.environment_admission_hash,
                trial_stop_hash=stop.stop_hash,
                case_id=self.manifest.case_id,
                case_revision=self.manifest.case_revision,
                case_mode=self.manifest.case_mode,
                outcome=outcome,
                stop_condition=controlling.condition,
                stop_phase=controlling.phase,
                trial_capability_acceptance=trial_capability_acceptance,
                substantive_case_outcome=substantive_case_outcome,
                runtime_trajectory=trajectory,
                final_runtime_position=final_position,
                controlling_artifact_refs=tuple(controlling_refs),
                reasons=reasons,
                limitations=limitations,
                dissent_refs=dissent_refs,
                unresolved_condition_refs=unresolved_condition_refs,
                produced_artifacts=artifact_refs,
                audit_export_status=TrialAuditExportStatus.NOT_ATTEMPTED,
                cleanup_disposition=TrialCleanupDisposition.NOT_ATTEMPTED,
                frozen_at=stopped_at,
            )
        )
        self._terminal_frozen = True
        return stop, result
