"""FFT-1A Mock-only one-click S5--S8 narrow full-function candidate."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg

from human_cos.challengers import (
    ChallengerContractError,
    ChallengerReviewGateResult,
    ChallengerReviewGateResultPayload,
    ChallengerReviewOutcome,
    assert_challenger_clear_for_downstream,
)
from human_cos.core.models import parse_case
from human_cos.domains import build_domain_task, route_domain_task
from human_cos.evaluation import (
    EvaluationSourceLayer,
    EvaluationTaskType,
    EvaluatorContractError,
    EvaluatorInputPacketPayload,
    EvaluatorSourceRef,
    EvaluatorTaskPayload,
    assert_evaluator_packet_binding,
    freeze_evaluator_input_packet,
    freeze_evaluator_task,
)
from human_cos.models import ModelRegistry, QualificationGate, parse_model_profile
from human_cos.runtime.run import canonical_document_sha256
from human_cos.runtime.state_machine import (
    CaseMode,
    CaseRuntimePosition,
    RuntimeState,
    TransitionRejected,
    TransitionStatus,
    can_transition,
)
from human_cos.runtime.tool_policy import ToolCapability, ToolCapabilityClass, ToolPolicy
from human_cos.safety import (
    ResearchSafetyOutcome,
)
from human_cos.scenario import transition_s7_scs1

from .integrated_chain import (
    EXPECTED_STAGE_TRANSITIONS,
    InstalledApplicationChainCheckpoint,
    InstalledApplicationChainReceipt,
    build_synthetic_s7_admission_lineage,
    exercise_installed_application_chain,
)

_RESULT_NAME = "full_function_trial_result.json"
_OWNER_NAME = ".human-cos-fft1a-owner"
_OWNER_VALUE = "human-cos-runtime:FFT-1A:v1\n"
_PROBE_TIME = datetime(2026, 9, 15, tzinfo=timezone.utc)
_NEGATIVE_SEMANTICS = {
    "challenger_block": ("BLOCK", "REJECTED", "Challenger downstream-clearance gate"),
    "capability_gap": ("CAPABILITY_GAP", "OPEN", "qualified Domain route required"),
    "evidence_mismatch_or_forgery": (
        "REJECT",
        "REJECTED",
        "S8 exact evaluator task/packet evidence binding",
    ),
    "invalid_evaluator_or_independence": ("REJECT", "REJECTED", "Evaluator qualification gate"),
    "final_synthesis_attempt": (
        "AUTHORIZATION_REQUIRED",
        "AUTHORIZATION_REQUIRED",
        "ADVERSARIAL_REVIEW -> FINAL_SYNTHESIS authorization gate",
    ),
    "reality_execution_attempt": ("DENIED", "DENIED", "ToolPolicy REALITY_EXECUTION global deny"),
}


class FullFunctionTrialError(ValueError):
    """The FFT-1A candidate could not prove execution, evidence, or cleanup."""


def _assert_negative_matrix(rows: object, matrix_passed: object) -> None:
    if (
        not isinstance(rows, list)
        or len(rows) != 7
        or not all(isinstance(row, dict) for row in rows)
    ):
        raise FullFunctionTrialError("FFT-1A negative matrix coverage differs")
    by_case = {str(row.get("case")): row for row in rows}
    expected_cases = {"research_safety_block", *_NEGATIVE_SEMANTICS}
    if len(by_case) != 7 or set(by_case) != expected_cases or matrix_passed is not True:
        raise FullFunctionTrialError("FFT-1A negative matrix coverage differs")
    for case, (expected, observed, boundary) in _NEGATIVE_SEMANTICS.items():
        row = by_case[case]
        reason = row.get("decision_reason")
        if not (
            row.get("expected") == expected
            and row.get("observed") == observed
            and row.get("boundary") == boundary
            and row.get("passed") is True
            and isinstance(reason, str)
            and reason.strip()
        ):
            raise FullFunctionTrialError(f"FFT-1A negative semantics invalid: {case}")
    safety = by_case["research_safety_block"]
    reason = safety.get("decision_reason")
    if not (
        safety.get("expected") == "BLOCK"
        and safety.get("observed") == "BLOCK;S7_ENTRY_GUARD_FAILED"
        and safety.get("boundary") == "code-owned S7 Research Safety admission"
        and safety.get("guard_name") == "scenario_generation_admission_frozen"
        and safety.get("guard_status") == "FAIL"
        and isinstance(reason, str)
        and "BLOCK" in reason
        and safety.get("downstream_invocation_count") == 1
        and safety.get("blocked_downstream_invocation_count") == 0
        and safety.get("passed") is True
    ):
        raise FullFunctionTrialError("FFT-1A Research Safety control invalid")


@dataclass(frozen=True)
class FullFunctionTrialResult:
    document: dict[str, Any]
    output_root: Path

    def assert_integrity(self) -> None:
        expected = canonical_document_sha256(
            {key: value for key, value in self.document.items() if key != "result_hash"}
        )
        if self.document.get("result_hash") != expected:
            raise FullFunctionTrialError("FFT-1A result hash differs from payload")
        if self.document.get("final_runtime_state") != RuntimeState.ADVERSARIAL_REVIEW.value:
            raise FullFunctionTrialError("FFT-1A did not stop at ADVERSARIAL_REVIEW")
        trace = self.document.get("stage_trace", ())
        observed = tuple((item.get("source"), item.get("target")) for item in trace)
        if observed != EXPECTED_STAGE_TRANSITIONS:
            raise FullFunctionTrialError("FFT-1A result lacks the exact ordered stage trace")
        _assert_negative_matrix(
            self.document.get("negative_matrix"), self.document.get("negative_matrix_passed")
        )
        stage_hashes = self.document.get("stage_terminal_hashes")
        sidecars = self.document.get("s8_narrow_sidecars")
        persistence = self.document.get("persistence")
        if not (
            isinstance(stage_hashes, dict)
            and isinstance(sidecars, dict)
            and sidecars.get("terminal_hash") == stage_hashes.get("S8_EVAL_NARROW")
            and isinstance(persistence, dict)
            and isinstance(persistence.get("tables_exercised"), list)
            and bool(persistence["tables_exercised"])
        ):
            raise FullFunctionTrialError("FFT-1A result evidence bindings are incomplete")
        authority = self.document.get("authority")
        if not isinstance(authority, dict) or not authority or any(authority.values()):
            raise FullFunctionTrialError("FFT-1A result claims unauthorized authority")


def _canonical_bytes(document: object) -> bytes:
    return (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _write_exclusive(path: Path, content: bytes, *, directory_fd: int | None = None) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
        dir_fd=directory_fd,
    )
    try:
        remaining = memoryview(content)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("FFT-1A evidence write made no progress")
            remaining = remaining[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _clear_owned_directory(descriptor: int, *, owned_directories: set[tuple[int, int]]) -> None:
    """Recursively remove contents through the retained directory, never its path."""

    with os.scandir(descriptor) as entries:
        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                child = os.open(
                    entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
                )
                try:
                    identity = os.fstat(child)
                    if (identity.st_dev, identity.st_ino) not in owned_directories:
                        raise FullFunctionTrialError("FFT-1A cleanup directory is not owned")
                    if not os.path.samestat(entry.stat(follow_symlinks=False), identity):
                        raise FullFunctionTrialError("FFT-1A cleanup child identity changed")
                    _clear_owned_directory(child, owned_directories=owned_directories)
                    current = os.stat(entry.name, dir_fd=descriptor, follow_symlinks=False)
                    if not os.path.samestat(current, identity):
                        raise FullFunctionTrialError("FFT-1A cleanup child identity changed")
                    # Non-recursive removal cannot delete a replacement tree's contents.
                    os.rmdir(entry.name, dir_fd=descriptor)
                finally:
                    os.close(child)
            else:
                os.unlink(entry.name, dir_fd=descriptor)


def _probe_research_safety_block(
    transition: Any = transition_s7_scs1,
) -> dict[str, object]:
    passed_lineage = build_synthetic_s7_admission_lineage(blocked=False)
    blocked_lineage = build_synthetic_s7_admission_lineage(blocked=True)
    downstream_invocations = 0

    def invoke_downstream() -> None:
        nonlocal downstream_invocations
        downstream_invocations += 1

    def enter(lineage: Any) -> Any:
        return transition(
            CaseRuntimePosition(
                CaseMode.MECHANISM_BENCHMARK,
                RuntimeState.CRITICAL_NODE_REVIEW,
                1,
            ),
            RuntimeState.SCENARIO_GENERATION,
            world_state=lineage.world_state,
            causal_graph=lineage.causal_graph,
            detection=lineage.detection,
            review_plan=lineage.review_plan,
            research_safety_admission=lineage.safety_admission,
            research_safety_result=lineage.safety_result,
            admission_packet=lineage.admission_packet,
            admission_result=lineage.admission_result,
        )

    pass_transition = enter(passed_lineage)
    invoke_downstream()
    guard_name = ""
    guard_status = ""
    guard_reason = ""
    blocked_downstream_before = downstream_invocations
    try:
        enter(blocked_lineage)
        invoke_downstream()
        transition_observed = "ALLOWED"
    except TransitionRejected as exc:
        transition_observed = exc.decision.status.value
        guard = exc.decision.guard_results[-1]
        guard_name = guard.name
        guard_status = guard.status.value
        guard_reason = guard.reason
    passed = (
        passed_lineage.safety_result.outcome is ResearchSafetyOutcome.PASS
        and pass_transition.decision.allowed
        and blocked_lineage.safety_result.outcome is ResearchSafetyOutcome.BLOCK
        and transition_observed == TransitionStatus.GUARD_FAILED.value
        and guard_name == "scenario_generation_admission_frozen"
        and guard_status == "FAIL"
        and "BLOCK" in guard_reason
        and downstream_invocations == blocked_downstream_before == 1
    )
    return {
        "case": "research_safety_block",
        "expected": "BLOCK",
        "observed": (
            f"{blocked_lineage.safety_result.outcome.value};S7_ENTRY_{transition_observed}"
        ),
        "passed": passed,
        "boundary": "code-owned S7 Research Safety admission",
        "decision_reason": guard_reason,
        "guard_name": guard_name,
        "guard_status": guard_status,
        "downstream_invocation_count": downstream_invocations,
        "blocked_downstream_invocation_count": downstream_invocations - blocked_downstream_before,
    }


def _probe_challenger_block() -> dict[str, object]:
    payload = ChallengerReviewGateResultPayload(
        gate_result_id="fft1a-negative:challenger-gate",
        challenger_response_hash="5" * 64,
        satisfaction_hash="6" * 64,
        outcome=ChallengerReviewOutcome.BLOCK,
        blocking_finding_hashes=("7" * 64,),
        unresolved_finding_hashes=(),
        reasons=("synthetic blocking Challenger finding",),
        protocol_version="0.1",
        frozen_at=_PROBE_TIME,
    )
    document = payload.to_document()
    gate = ChallengerReviewGateResult.model_validate(
        {**document, "gate_result_hash": canonical_document_sha256(document)}
    )
    gate.assert_integrity()
    try:
        assert_challenger_clear_for_downstream(gate)
    except ChallengerContractError as exc:
        return {
            "case": "challenger_block",
            "expected": "BLOCK",
            "observed": "REJECTED",
            "passed": True,
            "boundary": "Challenger downstream-clearance gate",
            "decision_reason": str(exc),
        }
    return {
        "case": "challenger_block",
        "expected": "BLOCK",
        "observed": "ALLOWED",
        "passed": False,
        "boundary": "Challenger downstream-clearance gate",
        "decision_reason": "blocking Challenger gate unexpectedly cleared downstream",
    }


def _probe_capability_gap() -> dict[str, object]:
    case = parse_case(
        {
            "case_id": "fft1a-negative:capability-gap",
            "revision": 1,
            "case_mode": CaseMode.MECHANISM_BENCHMARK.value,
            "question": "exercise fail-closed domain capability routing",
            "protocol_version": "0.1",
            "phase_profile": {"civilization_stage": "STARTUP", "case_phase": "DISCOVERY"},
            "time_boundary": {"T0": _PROBE_TIME.isoformat()},
            "domains": ["finance_market"],
            "publication_policy": "RESTRICTED",
        }
    )
    task = build_domain_task(
        case=case,
        task_id="fft1a-negative:domain-task",
        domain_id="finance_market",
        domain_task_type="mechanism_analysis",
        allowed_evidence_ids=(),
        actor_scope=("synthetic-market",),
        assumptions=(),
        requested_horizon="7d",
        framing_review_hash="8" * 64,
        frozen_at=_PROBE_TIME,
    )
    profile = parse_model_profile(
        {
            "model_id": "fft1a-negative-domain-worker",
            "model_family": "fft1a-negative-family",
            "provider": "mock",
            "status": "QUALIFIED",
            "role_eligibility": {"domain_worker": ["finance_market"]},
            "domain_capabilities": [],
        }
    )
    decision = route_domain_task(
        task=task,
        model_id=profile.model_id,
        qualification=QualificationGate(ModelRegistry([profile])),
        routed_at=_PROBE_TIME,
    )
    gap = decision.capability_gap
    passed = decision.allowed is False and decision.route is None and gap is not None
    return {
        "case": "capability_gap",
        "expected": "CAPABILITY_GAP",
        "observed": (
            gap.status if gap is not None else ("ALLOWED" if decision.allowed else "REJECTED")
        ),
        "passed": passed,
        "boundary": "qualified Domain route required",
        "decision_reason": decision.reason,
    }


def _probe_evidence_binding_mismatch() -> dict[str, object]:
    task = freeze_evaluator_task(
        EvaluatorTaskPayload(
            task_id="fft1a-negative:evaluator-task",
            case_id="fft1a-negative",
            case_revision=1,
            case_mode=CaseMode.MECHANISM_BENCHMARK,
            evaluation_type=EvaluationTaskType.INTEGRATED_RESULT,
            evaluated_run_ids=("run:fft1a-negative",),
            requested_evaluator_model_id="fft1a-evaluator",
            requested_evaluator_model_family="fft1a-evaluator-family",
            requested_evaluator_provider="mock",
            protocol_version="0.1",
            frozen_at=_PROBE_TIME,
        )
    )
    packet = freeze_evaluator_input_packet(
        EvaluatorInputPacketPayload(
            packet_id="fft1a-negative:evaluator-packet",
            task_hash="9" * 64,
            case_id=task.case_id,
            case_revision=task.case_revision,
            evaluation_type=task.evaluation_type,
            evaluated_run_ids=task.evaluated_run_ids,
            source_refs=(
                EvaluatorSourceRef(
                    layer=EvaluationSourceLayer.RUNTIME,
                    object_kind="run_manifest",
                    ref="run:fft1a-negative",
                    sha256="a" * 64,
                    purpose="exercise exact evaluator task/packet binding",
                ),
            ),
            protocol_version=task.protocol_version,
            frozen_at=_PROBE_TIME,
        )
    )
    try:
        assert_evaluator_packet_binding(task, packet)
    except EvaluatorContractError as exc:
        return {
            "case": "evidence_mismatch_or_forgery",
            "expected": "REJECT",
            "observed": "REJECTED",
            "passed": True,
            "boundary": "S8 exact evaluator task/packet evidence binding",
            "decision_reason": str(exc),
        }
    return {
        "case": "evidence_mismatch_or_forgery",
        "expected": "REJECT",
        "observed": "ALLOWED",
        "passed": False,
        "boundary": "S8 exact evaluator task/packet evidence binding",
        "decision_reason": "mismatched evaluator packet unexpectedly accepted",
    }


def _probe_invalid_evaluator() -> dict[str, object]:
    profile = parse_model_profile(
        {
            "model_id": "fft1a-invalid-evaluator",
            "model_family": "fft1a-evaluator-family",
            "provider": "mock",
            "status": "QUALIFIED",
            "role_eligibility": {
                "meta_controller": False,
                "challenger": False,
                "evaluator": False,
                "domain_worker": [],
            },
            "domain_capabilities": [],
        }
    )
    decision = QualificationGate(ModelRegistry([profile])).evaluator_decision(profile.model_id)
    return {
        "case": "invalid_evaluator_or_independence",
        "expected": "REJECT",
        "observed": "REJECTED" if not decision.allowed else "ALLOWED",
        "passed": decision.allowed is False,
        "boundary": "Evaluator qualification gate",
        "decision_reason": decision.reason,
    }


def _probe_final_synthesis_denial() -> dict[str, object]:
    decision = can_transition(
        CaseRuntimePosition(
            mode=CaseMode.MECHANISM_BENCHMARK,
            state=RuntimeState.ADVERSARIAL_REVIEW,
            case_revision=1,
        ),
        RuntimeState.FINAL_SYNTHESIS,
    )
    passed = (
        decision.allowed is False and decision.status is TransitionStatus.AUTHORIZATION_REQUIRED
    )
    return {
        "case": "final_synthesis_attempt",
        "expected": "AUTHORIZATION_REQUIRED",
        "observed": decision.status.value,
        "passed": passed,
        "boundary": "ADVERSARIAL_REVIEW -> FINAL_SYNTHESIS authorization gate",
        "decision_reason": decision.reason,
    }


def _probe_reality_execution_denial() -> dict[str, object]:
    policy = ToolPolicy(
        (
            ToolCapability(
                name="fft1a-reality-action",
                capability_class=ToolCapabilityClass.REALITY_EXECUTION,
            ),
        )
    )
    decision = policy.decision(
        "fft1a-reality-action",
        allowed_tools=("fft1a-reality-action",),
        forbidden_scopes=(),
    )
    return {
        "case": "reality_execution_attempt",
        "expected": "DENIED",
        "observed": "DENIED" if not decision.allowed else "ALLOWED",
        "passed": decision.allowed is False,
        "boundary": "ToolPolicy REALITY_EXECUTION global deny",
        "decision_reason": decision.reason,
    }


def _negative_matrix() -> list[dict[str, object]]:
    """Execute deterministic production fail-closed probes for FFT-1A."""

    return [
        _probe_research_safety_block(),
        _probe_challenger_block(),
        _probe_capability_gap(),
        _probe_evidence_binding_mismatch(),
        _probe_invalid_evaluator(),
        _probe_final_synthesis_denial(),
        _probe_reality_execution_denial(),
    ]


def _valid_commit_sha(value: str | None) -> bool:
    return bool(
        value
        and len(value) == 40
        and value != "0" * 40
        and all(character in "0123456789abcdef" for character in value)
    )


def _package_identity() -> dict[str, str] | None:
    """Return package/source identity only from an explicit exact SHA channel."""

    path = Path(__file__).parents[1] / "_build_commit.txt"
    try:
        packaged = path.read_text(encoding="ascii").strip()
    except OSError:
        packaged = None
    if _valid_commit_sha(packaged):
        assert packaged is not None
        return {"kind": "package_build_commit", "commit_sha": packaged}

    explicit = os.getenv("HUMAN_COS_BUILD_COMMIT_SHA")
    if _valid_commit_sha(explicit):
        assert explicit is not None
        return {"kind": "explicit_build_commit_env", "commit_sha": explicit}
    return None


def _result_document(receipt: InstalledApplicationChainReceipt) -> dict[str, Any]:
    identity = _package_identity()
    if identity is None:
        raise FullFunctionTrialError(
            "FFT-1A requires an exact package build commit or HUMAN_COS_BUILD_COMMIT_SHA"
        )
    negative_matrix = _negative_matrix()
    seed: dict[str, Any] = {
        "format": "human-cos-fft1a-full-function-result-v1",
        "candidate": "FFT-1A",
        "status": "PASS",
        "adapter_lane": "MOCK_ONLY",
        "migrations_applied": list(receipt.migration_names),
        "stage_trace": list(receipt.stage_trace),
        "transition_count": len(receipt.stage_trace),
        "final_runtime_state": receipt.final_runtime_state,
        "s8_narrow_sidecars": {
            "persisted": True,
            "terminal_hash": receipt.s8_terminal_hash,
        },
        "stage_terminal_hashes": {
            "S5_CDE": receipt.s5_terminal_hash,
            "S6_WCI": receipt.s6_terminal_hash,
            "S7_SCS_NARROW": receipt.s7_terminal_hash,
            "S8_EVAL_NARROW": receipt.s8_terminal_hash,
        },
        "persistence": {
            "readback_verified": True,
            "cleanup_verified": receipt.migrations_rolled_back,
            "tables_exercised": list(receipt.tables_exercised),
            "snapshot_hash": receipt.evidence_snapshot_hash,
        },
        "negative_matrix": negative_matrix,
        "negative_matrix_passed": all(row["passed"] is True for row in negative_matrix),
        "authority": {
            "controller_d": False,
            "final_synthesis": False,
            "final_claim": False,
            "human_seal": False,
            "publication": False,
            "reality_execution": False,
            "s8_full": False,
            "s9_plus": False,
        },
        "n3_status": "OPEN",
        "sbx7_freeze": False,
        "real_case_effectiveness": "NOT_DEMONSTRATED",
        "limitations": [
            "Mock-only synthetic full-function trial; no real-case effectiveness claim.",
            "N-3 remains OPEN; Domain Context and allowlist equivalence are unchanged.",
        ],
        "application_chain_receipt_hash": receipt.receipt_hash,
    }
    seed["package_source_identity"] = identity
    return {**seed, "result_hash": canonical_document_sha256(seed)}


def _verify_package(root: Path, manifest: dict[str, str]) -> None:
    for relative, expected in manifest.items():
        path = root / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise FullFunctionTrialError(f"FFT-1A evidence readback failed: {relative}")


def _verify_owned_package(root_fd: int, evidence_fd: int, manifest: dict[str, str]) -> None:
    for relative, expected in manifest.items():
        parts = relative.split("/")
        if len(parts) == 1 and parts[0] not in {"", ".", ".."}:
            parent, name = root_fd, parts[0]
        elif len(parts) == 2 and parts[0] == "evidence_package" and parts[1] not in {"", ".", ".."}:
            parent, name = evidence_fd, parts[1]
        else:
            raise FullFunctionTrialError("FFT-1A invalid owned evidence path")
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        with os.fdopen(descriptor, "rb") as source:
            if hashlib.sha256(source.read()).hexdigest() != expected:
                raise FullFunctionTrialError(f"FFT-1A evidence readback failed: {relative}")


def run_full_function_trial(
    output_root: str | Path,
    *,
    database_url: str | None = None,
) -> FullFunctionTrialResult:
    """Run 0001--0007 and the Mock S5--S8 chain, preserve evidence, and prove cleanup."""

    root = Path(output_root)
    if root.exists() or root.is_symlink():
        raise FullFunctionTrialError("FFT-1A output root must not already exist")
    url = database_url or os.getenv("HUMAN_COS_TRIAL_DATABASE_URL")
    if not url:
        raise FullFunctionTrialError("HUMAN_COS_TRIAL_DATABASE_URL is required")
    if not {os.open, os.stat, os.mkdir, os.unlink, os.rmdir}.issubset(os.supports_dir_fd):
        raise FullFunctionTrialError("FFT-1A requires descriptor-relative filesystem cleanup")
    root_descriptor = None
    try:
        root.mkdir(mode=0o700)
        created_root = root.lstat()
        root_descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        owned_root = os.fstat(root_descriptor)
        if not os.path.samestat(created_root, owned_root) or os.listdir(root_descriptor):
            raise FullFunctionTrialError("FFT-1A output ownership acquisition changed")
    except BaseException as exc:
        if root_descriptor is not None:
            try:
                os.close(root_descriptor)
            except BaseException as close_error:
                raise FullFunctionTrialError(
                    "FFT-1A output ownership acquisition failed; handle closure unverified"
                ) from close_error
        raise FullFunctionTrialError(
            f"FFT-1A output root creation failed; cleanup not verified: {type(exc).__name__}: {exc}"
        ) from exc
    owner_written = False
    evidence_descriptor = None
    owned_directories: set[tuple[int, int]] = set()
    try:
        _write_exclusive(Path(_OWNER_NAME), _OWNER_VALUE.encode(), directory_fd=root_descriptor)
        owner_written = True
        os.mkdir("evidence_package", mode=0o700, dir_fd=root_descriptor)
        created_evidence = os.stat(
            "evidence_package", dir_fd=root_descriptor, follow_symlinks=False
        )
        evidence_descriptor = os.open(
            "evidence_package", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_descriptor
        )
        owned_evidence = os.fstat(evidence_descriptor)
        if not os.path.samestat(created_evidence, owned_evidence) or os.listdir(
            evidence_descriptor
        ):
            raise FullFunctionTrialError("FFT-1A evidence directory acquisition changed")
        owned_directories.add((owned_evidence.st_dev, owned_evidence.st_ino))
        manifest: dict[str, str] = {}

        def preserve_before_cleanup(
            checkpoint: InstalledApplicationChainCheckpoint,
            stage_trace: tuple[dict[str, object], ...],
        ) -> None:
            pre_cleanup = {
                "application_chain_checkpoint.json": checkpoint.to_document(),
                "persistence_snapshot.json": json.loads(checkpoint.evidence_snapshot_json),
                "stage_trace.json": list(stage_trace),
            }
            for name, payload in pre_cleanup.items():
                content = _canonical_bytes(payload)
                _write_exclusive(Path(name), content, directory_fd=evidence_descriptor)
                manifest[f"evidence_package/{name}"] = hashlib.sha256(content).hexdigest()
            _verify_owned_package(root_descriptor, evidence_descriptor, manifest)

        try:
            with psycopg.connect(url) as connection:
                receipt = exercise_installed_application_chain(
                    connection, preserve_evidence=preserve_before_cleanup
                )
        except psycopg.Error as exc:
            raise FullFunctionTrialError(f"FFT-1A PostgreSQL connection failed: {exc}") from exc
        receipt.assert_integrity()
        documents: dict[str, object] = {
            "application_chain_receipt.json": receipt.to_document(),
        }
        for name, document in documents.items():
            content = _canonical_bytes(document)
            _write_exclusive(Path(name), content, directory_fd=evidence_descriptor)
            manifest[f"evidence_package/{name}"] = hashlib.sha256(content).hexdigest()
        manifest_bytes = _canonical_bytes(manifest)
        _write_exclusive(
            Path("evidence_manifest.json"), manifest_bytes, directory_fd=root_descriptor
        )
        _verify_owned_package(root_descriptor, evidence_descriptor, manifest)
        document = _result_document(receipt)
        result_bytes = _canonical_bytes(document)
        _write_exclusive(Path(_RESULT_NAME), result_bytes, directory_fd=root_descriptor)
        _verify_owned_package(
            root_descriptor,
            evidence_descriptor,
            {
                "evidence_manifest.json": hashlib.sha256(manifest_bytes).hexdigest(),
                _RESULT_NAME: hashlib.sha256(result_bytes).hexdigest(),
            },
        )
        result = FullFunctionTrialResult(document=document, output_root=root)
        result.assert_integrity()
        if not os.path.samestat(root.lstat(), owned_root) or not os.path.samestat(
            os.stat("evidence_package", dir_fd=root_descriptor, follow_symlinks=False),
            owned_evidence,
        ):
            raise FullFunctionTrialError("FFT-1A output path changed before completion")
        return result
    except BaseException as original:
        try:
            current_root = root.lstat()
            if root.is_symlink() or (current_root.st_dev, current_root.st_ino) != (
                owned_root.st_dev,
                owned_root.st_ino,
            ):
                raise FullFunctionTrialError(
                    "FFT-1A output ownership changed; cleanup could not be verified"
                ) from original
            if owner_written:
                marker = os.open(_OWNER_NAME, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=root_descriptor)
                with os.fdopen(marker, "rb") as marker_file:
                    if marker_file.read() != _OWNER_VALUE.encode():
                        raise FullFunctionTrialError("FFT-1A owner marker changed")
            _clear_owned_directory(root_descriptor, owned_directories=owned_directories)
            if not os.path.samestat(root.lstat(), owned_root):
                raise FullFunctionTrialError("FFT-1A output path changed during cleanup")
            # Only remove an empty root by name; recursive work was anchored to its fd.
            root.rmdir()
        except BaseException as cleanup_error:
            raise FullFunctionTrialError(
                f"FFT-1A failed and output cleanup could not be verified: {cleanup_error}"
            ) from original
        if root.exists() or root.is_symlink():
            raise FullFunctionTrialError(
                "FFT-1A failed and output cleanup could not be verified"
            ) from original
        if isinstance(original, OSError):
            raise FullFunctionTrialError(
                f"FFT-1A filesystem operation failed: {original}"
            ) from original
        raise
    finally:
        handle_error: BaseException | None = None
        for descriptor in (evidence_descriptor, root_descriptor):
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except BaseException as exc:
                    handle_error = exc
        if handle_error is not None:
            raise FullFunctionTrialError(
                "FFT-1A output handle closure could not be verified"
            ) from handle_error
