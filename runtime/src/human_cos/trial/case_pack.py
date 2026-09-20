"""Package-owned canonical structural cases for the TRIAL-SBX4 slice.

The case pack is immutable and hash-bound.  Replay receives only a plan; the
separate expectation is consulted after TrialStop and TrialResult have frozen.
Nothing in this module grants cognitive, provider, publication, synthesis, or
reality-execution authority.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import cast

from human_cos.challengers.review import (
    FROZEN_CHALLENGER_ATTACK_TYPES,
    ChallengerFinding,
    ChallengerResponse,
    ChallengerReviewGateResult,
    ChallengerReviewOutcome,
    ChallengerSourceKind,
    ChallengerSourcePacket,
    ChallengerSourcePacketPayload,
    ChallengerSourceRef,
    ChallengerTask,
    ChallengerTaskPayload,
    PendingChallengerSatisfaction,
    assert_challenger_packet_binding,
    evaluate_challenger_review_gate,
)
from human_cos.evaluation.hc_regression import (
    RegressionDisposition,
    RegressionMetricDirection,
    RegressionParityDimension,
)
from human_cos.evaluation.low_recognition import (
    LowRecognitionGateStatus,
    LowRecognitionInvalidFact,
)
from human_cos.runtime.run import canonical_document_bytes, canonical_document_sha256
from human_cos.runtime.state_machine import CaseMode, RuntimeState, structural_targets
from human_cos.safety.research import (
    ResearchSafetyAdmission,
    ResearchSafetyAdmissionPayload,
    ResearchSafetyOutcome,
    ResearchSafetyResult,
    assert_research_safety_result_binding,
    evaluate_research_safety,
    freeze_research_safety_admission,
)

from .bundle import (
    VerifiedTrialBundle,
    _assert_environment_provenance,
    _AuthenticatedCanonicalAdmission,
)
from .contracts import (
    TrialArtifactRef,
    TrialCanonicalAdmission,
    TrialCanonicalAdmissionPayload,
    TrialCanonicalAdmissionStatus,
    TrialCanonicalPurpose,
    TrialCapabilityAcceptance,
    TrialCleanupDisposition,
    TrialEnvironmentAdmission,
    TrialEnvironmentAdmissionPayload,
    TrialManifest,
    TrialManifestPayload,
    TrialOutcome,
    TrialResult,
    TrialRuntimePosition,
    TrialStop,
    TrialStopCondition,
    TrialStopPhase,
    assert_environment_admission_binding,
    assert_trial_result_binding,
    freeze_trial_canonical_admission,
    freeze_trial_environment_admission,
    freeze_trial_manifest,
    stop_outcome_for,
)
from .orchestrator import (
    _BOOTSTRAP_CONTROL_STATES,
    _assert_bootstrap_admitted,
    _assert_frozen_structural_path,
)
from .stop_engine import TrialResourceMeter, TrialStopLedger, TrialStopSignal


class TrialCasePackError(ValueError):
    """The canonical case pack or its observed replay is inconsistent."""


@dataclass(frozen=True)
class TrialCanonicalCaseAdmission:
    """Package-bound per-case identity derived from the authenticated SBX root."""

    case_key: str
    case_hash: str
    pack_hash: str
    root_canonical_admission_hash: str
    attempt_receipt_hash: str
    root_bundle_receipt_hash: str
    root_detached_input_address: str
    root_payload_documents_sha256: str
    root_semantic_fingerprint: str
    derived_case_sha256: str
    case_derivation_hash: str
    manifest: TrialManifest
    canonical_admission: TrialCanonicalAdmission
    environment: TrialEnvironmentAdmission
    admission_hash: str

    def assert_integrity(
        self,
        *,
        root_admission: _AuthenticatedCanonicalAdmission | None = None,
        root_bundle: VerifiedTrialBundle | None = None,
        root_environment: TrialEnvironmentAdmission | None = None,
    ) -> None:
        if root_admission is None or root_bundle is None or root_environment is None:
            raise TrialCasePackError(
                "package-authenticated root admission, bundle, and Environment are required"
            )
        root_admission.assert_integrity()
        root_bundle.assert_integrity()
        assert_environment_admission_binding(
            root_bundle.attempt,
            root_bundle.manifest,
            root_admission.record,
            root_environment,
        )
        _assert_environment_provenance(root_environment, root_admission)
        expected_inventory_sha256 = canonical_document_sha256(
            [
                item.model_dump(mode="json", exclude_none=True)
                for item in sorted(root_bundle.receipt.files, key=lambda item: item.path)
            ]
        )
        if (
            root_admission.manifest_hash != root_bundle.manifest.manifest_hash
            or root_admission.attempt_receipt_hash != root_bundle.attempt.attempt_receipt_hash
            or root_admission.bundle_receipt_hash != root_bundle.receipt.bundle_receipt_hash
            or root_admission.receipt_inventory_sha256 != expected_inventory_sha256
            or root_admission.payload_documents_sha256 != root_bundle.payload_documents_sha256
        ):
            raise TrialCasePackError("authenticated root does not bind the verified bundle")
        self.manifest.assert_integrity()
        self.canonical_admission.assert_integrity()
        self.environment.assert_integrity()
        pack = _load_canonical_case_pack()
        matching = tuple(
            case
            for case in pack.cases
            if (case.case_key, case.case_hash) == (self.case_key, self.case_hash)
        )
        if len(matching) != 1 or self.pack_hash != pack.pack_hash:
            raise TrialCasePackError("case admission is absent from the package-owned pack")
        if (
            self.root_canonical_admission_hash,
            self.attempt_receipt_hash,
            self.root_bundle_receipt_hash,
            self.root_detached_input_address,
            self.root_payload_documents_sha256,
            self.root_semantic_fingerprint,
        ) != (
            root_admission.record.canonical_admission_hash,
            root_admission.attempt_receipt_hash,
            root_admission.bundle_receipt_hash,
            root_admission.record.detached_input_address,
            root_admission.payload_documents_sha256,
            root_admission.semantic_fingerprint,
        ):
            raise TrialCasePackError(
                "case admission root differs from package-authenticated provenance"
            )
        expected_manifest_document = root_bundle.manifest.model_dump(
            mode="python", exclude={"manifest_hash"}, exclude_none=True
        )
        expected_manifest_document.update(
            {
                "trial_id": f"{root_bundle.manifest.trial_id}:sbx4:{self.case_key}",
                "case_id": self.case_key,
                "frozen_at": self.manifest.frozen_at,
            }
        )
        expected_manifest = freeze_trial_manifest(
            TrialManifestPayload.model_validate(expected_manifest_document)
        )
        if self.manifest != expected_manifest:
            raise TrialCasePackError(
                "derived Manifest differs from the authenticated root derivation"
            )
        expected_registry = f"{pack.pack_id}:{pack.pack_hash}:{self.case_hash}"
        expected_case_sha256 = canonical_document_sha256(
            {
                "case_id": self.case_key,
                "case_revision": self.manifest.case_revision,
                "case_mode": self.manifest.case_mode.value,
                "protocol_version": self.manifest.protocol_version,
                "canonical_case_hash": self.case_hash,
                "root_semantic_fingerprint": self.root_semantic_fingerprint,
            }
        )
        expected_derivation_hash = canonical_document_sha256(
            {
                "root_canonical_admission_hash": self.root_canonical_admission_hash,
                "root_bundle_receipt_hash": self.root_bundle_receipt_hash,
                "root_detached_input_address": self.root_detached_input_address,
                "root_payload_documents_sha256": self.root_payload_documents_sha256,
                "root_semantic_fingerprint": self.root_semantic_fingerprint,
                "pack_hash": self.pack_hash,
                "case_hash": self.case_hash,
                "derived_manifest": self.manifest.model_dump(
                    mode="json", exclude={"manifest_hash"}, exclude_none=True
                ),
                "derived_case_sha256": self.derived_case_sha256,
            }
        )
        expected_address = canonical_document_sha256(
            {
                "case_derivation_hash": expected_derivation_hash,
                "manifest_hash": self.manifest.manifest_hash,
                "case_sha256": expected_case_sha256,
            }
        )
        if (
            self.manifest.case_id,
            self.canonical_admission.case_id,
            self.canonical_admission.purpose,
            self.canonical_admission.registry_entry_id,
        ) != (
            self.case_key,
            self.case_key,
            TrialCanonicalPurpose.CANONICAL_CASE,
            expected_registry,
        ):
            raise TrialCasePackError("case admission identity differs from its canonical case")
        if (
            self.derived_case_sha256,
            self.case_derivation_hash,
            self.canonical_admission.bundle_receipt_hash,
            self.canonical_admission.detached_input_address,
        ) != (
            expected_case_sha256,
            expected_derivation_hash,
            expected_derivation_hash,
            expected_address,
        ):
            raise TrialCasePackError(
                "case admission is not byte-derivation-bound to the authenticated root"
            )
        if self.environment.attempt_receipt_hash != self.attempt_receipt_hash:
            raise TrialCasePackError("case admission differs from its Attempt Receipt")
        assert_environment_admission_binding(
            root_bundle.attempt,
            self.manifest,
            self.canonical_admission,
            self.environment,
        )
        expected_environment_document = root_environment.model_dump(
            mode="python",
            exclude={"environment_admission_hash"},
            exclude_none=True,
        )
        expected_environment_document.update(
            {
                "admission_id": (
                    f"environment:sbx4:{self.case_key}:{root_bundle.attempt.attempt_id}"
                ),
                "manifest_hash": self.manifest.manifest_hash,
                "canonical_admission_hash": (self.canonical_admission.canonical_admission_hash),
                "canonical_registry_entry_id": self.canonical_admission.registry_entry_id,
                "detached_input_address": expected_address,
                "frozen_at": self.manifest.frozen_at,
            }
        )
        expected_environment = freeze_trial_environment_admission(
            TrialEnvironmentAdmissionPayload.model_validate(expected_environment_document)
        )
        if self.environment != expected_environment:
            raise TrialCasePackError(
                "derived Environment differs from the authenticated root derivation"
            )
        if (
            self.environment.manifest_hash,
            self.environment.canonical_admission_hash,
            self.environment.canonical_registry_entry_id,
        ) != (
            self.manifest.manifest_hash,
            self.canonical_admission.canonical_admission_hash,
            self.canonical_admission.registry_entry_id,
        ):
            raise TrialCasePackError("case Environment does not bind the case admission")
        if self.admission_hash != canonical_document_sha256(_case_admission_document(self)):
            raise TrialCasePackError("canonical case admission hash does not match its payload")


class TrialCasePolarity(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"


@dataclass(frozen=True)
class TrialHCMetricFact:
    metric_id: str
    direction: RegressionMetricDirection
    noninferiority_margin: float
    hc_value: float
    baseline_value: float

    @property
    def regression_detected(self) -> bool:
        if self.direction is RegressionMetricDirection.HIGHER_IS_BETTER:
            return self.hc_value < self.baseline_value - self.noninferiority_margin
        return self.hc_value > self.baseline_value + self.noninferiority_margin


@dataclass(frozen=True)
class TrialObservedEvidence:
    """An immutable, parseable payload bound to one produced artifact."""

    artifact: TrialArtifactRef
    payload_bytes: bytes
    evidence_hash: str

    def payload(self) -> dict[str, object]:
        value = json.loads(self.payload_bytes.decode("utf-8"))
        if not isinstance(value, dict):
            raise TrialCasePackError("observed evidence payload must be an object")
        return value

    def assert_integrity(self) -> None:
        payload = self.payload()
        expected_artifact = _fixture_ref(
            self.artifact.kind,
            self.artifact.ref,
            payload=payload,
        )
        if self.artifact != expected_artifact:
            raise TrialCasePackError("observed evidence payload differs from artifact hash")
        if self.evidence_hash != canonical_document_sha256(_observed_evidence_document(self)):
            raise TrialCasePackError("observed evidence hash does not match its payload")


@dataclass(frozen=True)
class TrialObservedStopFacts:
    """Frozen fixture facts from which replay derives its terminal condition."""

    capability_gap_id: str | None
    research_safety_blocked: bool
    challenger_blocked: bool
    hc_parity_dimensions: tuple[RegressionParityDimension, ...]
    hc_metric_facts: tuple[TrialHCMetricFact, ...]
    hc_disposition: RegressionDisposition | None
    low_invalid_facts: tuple[LowRecognitionInvalidFact, ...]
    low_status: LowRecognitionGateStatus | None
    evidence_artifact_hashes: tuple[str, ...]
    facts_hash: str

    def assert_integrity(self) -> None:
        if self.hc_disposition is None:
            if self.hc_parity_dimensions or self.hc_metric_facts:
                raise TrialCasePackError("HC facts require a frozen disposition")
        else:
            if (
                len(self.hc_parity_dimensions) != 4
                or set(self.hc_parity_dimensions) != set(RegressionParityDimension)
                or not self.hc_metric_facts
            ):
                raise TrialCasePackError("HC facts require four parity dimensions and metrics")
            expected_hc = (
                RegressionDisposition.REGRESSION_DETECTED
                if any(item.regression_detected for item in self.hc_metric_facts)
                else RegressionDisposition.NO_REGRESSION_DETECTED
            )
            if self.hc_disposition is not expected_hc:
                raise TrialCasePackError("HC disposition is not recomputable from metric facts")
        if self.low_status is None:
            if self.low_invalid_facts:
                raise TrialCasePackError("Low-recognition invalid facts require a frozen status")
        else:
            expected_low = (
                LowRecognitionGateStatus.BLOCK
                if self.low_invalid_facts
                else LowRecognitionGateStatus.PASS
            )
            if self.low_status is not expected_low:
                raise TrialCasePackError(
                    "Low-recognition status is not recomputable from exposure facts"
                )
        blockers = (
            bool(self.capability_gap_id),
            self.research_safety_blocked,
            self.challenger_blocked,
            self.hc_disposition is RegressionDisposition.REGRESSION_DETECTED,
            self.low_status is LowRecognitionGateStatus.BLOCK,
        )
        if sum(blockers) > 1:
            raise TrialCasePackError("one structural case may freeze only one terminal blocker")
        if len(self.evidence_artifact_hashes) != len(set(self.evidence_artifact_hashes)):
            raise TrialCasePackError("observed stop evidence hashes must be unique")
        if self.facts_hash != canonical_document_sha256(_observed_facts_document(self)):
            raise TrialCasePackError("observed stop-facts hash does not match its payload")

    def derive_stop_condition(self) -> TrialStopCondition:
        self.assert_integrity()
        if self.capability_gap_id:
            return TrialStopCondition.CAPABILITY_GAP
        if self.research_safety_blocked:
            return TrialStopCondition.RESEARCH_SAFETY_BLOCK
        if self.challenger_blocked:
            return TrialStopCondition.CHALLENGER_BLOCK
        if self.hc_disposition is RegressionDisposition.REGRESSION_DETECTED:
            return TrialStopCondition.HC_REGRESSION_DETECTED
        if self.low_status is LowRecognitionGateStatus.BLOCK:
            return TrialStopCondition.LOW_RECOGNITION_COMPROMISED
        return TrialStopCondition.AUTHORIZED_BOUNDARY_REACHED


@dataclass(frozen=True)
class TrialReplayPlan:
    case_key: str
    case_mode: CaseMode
    runtime_states: tuple[RuntimeState, ...]
    terminal_phase: TrialStopPhase
    terminal_reason: str
    observed_stop_facts: TrialObservedStopFacts
    observed_evidence: tuple[TrialObservedEvidence, ...]
    produced_artifacts: tuple[TrialArtifactRef, ...]
    controlling_artifact_refs: tuple[TrialArtifactRef, ...]
    dissent_refs: tuple[str, ...]
    unresolved_condition_refs: tuple[str, ...]
    plan_hash: str

    def assert_integrity(self) -> None:
        self.observed_stop_facts.assert_integrity()
        for evidence in self.observed_evidence:
            evidence.assert_integrity()
        if not self.observed_evidence:
            raise TrialCasePackError("structural replay requires observed evidence payloads")
        evidence_condition = _derive_stop_from_evidence(self.observed_evidence)
        if evidence_condition is not self.observed_stop_facts.derive_stop_condition():
            raise TrialCasePackError("observed evidence and stop-facts disposition differ")
        if not self.case_key or not self.terminal_reason.strip():
            raise TrialCasePackError("replay plan identifiers and reasons must be non-empty")
        if not self.runtime_states or self.runtime_states[0] is not RuntimeState.CASE_CREATED:
            raise TrialCasePackError("structural replay must start at CASE_CREATED")
        for source, target in zip(self.runtime_states[:-1], self.runtime_states[1:], strict=True):
            if target not in structural_targets(self.case_mode, source):
                raise TrialCasePackError(
                    f"case pack contains illegal Runtime transition {source.value}->{target.value}"
                )
        if self.terminal_phase is not TrialStopPhase.EXECUTION:
            raise TrialCasePackError("SBX4 structural cases must stop during execution")
        for name, artifacts in (
            ("replay artifacts", self.produced_artifacts),
            ("controlling relations", self.controlling_artifact_refs),
        ):
            keys = tuple((item.kind, item.ref, item.sha256) for item in artifacts)
            if len(keys) != len(set(keys)):
                raise TrialCasePackError(f"{name} must be unique")
        produced_hashes = {item.sha256 for item in self.produced_artifacts}
        evidence_hashes = {item.artifact.sha256 for item in self.observed_evidence}
        if len(evidence_hashes) != len(self.observed_evidence):
            raise TrialCasePackError("observed evidence artifacts must be unique")
        if not evidence_hashes.issubset(produced_hashes):
            raise TrialCasePackError("observed evidence is outside replay artifacts")
        if not set(self.observed_stop_facts.evidence_artifact_hashes).issubset(evidence_hashes):
            raise TrialCasePackError("observed stop facts cite absent observed evidence")
        if evidence_condition is not TrialStopCondition.AUTHORIZED_BOUNDARY_REACHED and not {
            item.sha256 for item in self.controlling_artifact_refs
        }.issubset(evidence_hashes):
            raise TrialCasePackError(
                "protective stop facts must bind the exact controlling artifacts"
            )
        if (
            evidence_condition is TrialStopCondition.AUTHORIZED_BOUNDARY_REACHED
            and self.runtime_states[-1] is not RuntimeState.ADVERSARIAL_REVIEW
        ):
            raise TrialCasePackError("authorized completion must stop at ADVERSARIAL_REVIEW")
        if self.plan_hash != canonical_document_sha256(_plan_document(self)):
            raise TrialCasePackError("replay plan hash does not match its canonical payload")


@dataclass(frozen=True)
class TrialCaseExpectation:
    expected_outcome: TrialOutcome
    expected_stop_condition: TrialStopCondition
    expected_stop_phase: TrialStopPhase
    expected_runtime_states: tuple[RuntimeState, ...]
    expected_terminal_state: RuntimeState
    expected_capability_acceptance: TrialCapabilityAcceptance
    required_artifacts: tuple[TrialArtifactRef, ...]
    forbidden_artifact_kinds: tuple[str, ...]
    required_controlling_artifact_refs: tuple[TrialArtifactRef, ...]
    expected_dissent_refs: tuple[str, ...]
    expected_unresolved_condition_refs: tuple[str, ...]
    expected_cleanup_disposition: TrialCleanupDisposition
    expectation_hash: str

    def assert_integrity(self) -> None:
        if self.expected_outcome is not stop_outcome_for(self.expected_stop_condition):
            raise TrialCasePackError("case expectation outcome differs from stop condition")
        if not self.expected_runtime_states:
            raise TrialCasePackError("case expectation requires an observed trajectory")
        if self.expected_terminal_state is not self.expected_runtime_states[-1]:
            raise TrialCasePackError("expected terminal state differs from expected trajectory")
        required_kinds = {item.kind for item in self.required_artifacts}
        if required_kinds.intersection(self.forbidden_artifact_kinds):
            raise TrialCasePackError("required and forbidden artifact expectations overlap")
        if self.expectation_hash != canonical_document_sha256(_expectation_document(self)):
            raise TrialCasePackError("case expectation hash does not match its canonical payload")


@dataclass(frozen=True)
class TrialCanonicalCase:
    case_key: str
    polarity: TrialCasePolarity
    replay_plan: TrialReplayPlan
    expectation: TrialCaseExpectation
    case_hash: str

    def assert_integrity(self) -> None:
        self.replay_plan.assert_integrity()
        self.expectation.assert_integrity()
        if self.case_key != self.replay_plan.case_key:
            raise TrialCasePackError("case identity differs from replay-plan identity")
        expected = self.expectation
        plan = self.replay_plan
        if (
            expected.expected_outcome,
            expected.expected_stop_condition,
            expected.expected_stop_phase,
            expected.expected_runtime_states,
            expected.expected_terminal_state,
            expected.required_artifacts,
            expected.required_controlling_artifact_refs,
            expected.expected_dissent_refs,
            expected.expected_unresolved_condition_refs,
        ) != (
            stop_outcome_for(plan.observed_stop_facts.derive_stop_condition()),
            plan.observed_stop_facts.derive_stop_condition(),
            plan.terminal_phase,
            plan.runtime_states,
            plan.runtime_states[-1],
            plan.produced_artifacts,
            plan.controlling_artifact_refs,
            plan.dissent_refs,
            plan.unresolved_condition_refs,
        ):
            raise TrialCasePackError("case expectation differs from its immutable replay plan")
        is_completion = (
            plan.observed_stop_facts.derive_stop_condition()
            is TrialStopCondition.AUTHORIZED_BOUNDARY_REACHED
        )
        if (self.polarity is TrialCasePolarity.POSITIVE) is not is_completion:
            raise TrialCasePackError("case polarity differs from its terminal condition")
        if self.case_hash != canonical_document_sha256(_case_document(self)):
            raise TrialCasePackError("canonical case hash does not match its payload")


@dataclass(frozen=True)
class TrialDeferredFixture:
    fixture_key: str
    expected_stop_condition: TrialStopCondition
    expected_stop_phase: TrialStopPhase
    required_artifacts: tuple[TrialArtifactRef, ...]
    forbidden_artifact_kinds: tuple[str, ...]
    required_controlling_artifact_refs: tuple[TrialArtifactRef, ...]
    expected_cleanup_disposition: TrialCleanupDisposition
    exercise_owner: str
    resource_stage_call_deltas: tuple[int, ...]
    fixture_hash: str

    def assert_integrity(self) -> None:
        if not self.fixture_key or not self.exercise_owner:
            raise TrialCasePackError("deferred fixture identity and owner must be non-empty")
        if any(value <= 0 for value in self.resource_stage_call_deltas):
            raise TrialCasePackError("resource fixture deltas must be positive")
        if (self.expected_stop_condition is TrialStopCondition.RESOURCE_LIMIT_REACHED) is not bool(
            self.resource_stage_call_deltas
        ):
            raise TrialCasePackError("only the resource fixture may declare meter deltas")
        if self.fixture_hash != canonical_document_sha256(_deferred_fixture_document(self)):
            raise TrialCasePackError("deferred fixture hash does not match its payload")


@dataclass(frozen=True)
class TrialCanonicalCasePack:
    pack_id: str
    pack_version: str
    cases: tuple[TrialCanonicalCase, ...]
    additional_fixtures: tuple[TrialDeferredFixture, ...]
    pack_hash: str

    def assert_integrity(self) -> None:
        if not self.pack_id or not self.pack_version or not self.cases:
            raise TrialCasePackError("canonical case pack metadata must be non-empty")
        for case in self.cases:
            case.assert_integrity()
        keys = tuple(case.case_key for case in self.cases)
        if len(keys) != len(set(keys)):
            raise TrialCasePackError("canonical case keys must be unique")
        if {case.polarity for case in self.cases} != {
            TrialCasePolarity.POSITIVE,
            TrialCasePolarity.NEGATIVE,
        }:
            raise TrialCasePackError("canonical pack requires positive and negative cases")
        required_conditions = {
            TrialStopCondition.AUTHORIZED_BOUNDARY_REACHED,
            TrialStopCondition.CAPABILITY_GAP,
            TrialStopCondition.RESEARCH_SAFETY_BLOCK,
            TrialStopCondition.CHALLENGER_BLOCK,
            TrialStopCondition.HC_REGRESSION_DETECTED,
            TrialStopCondition.LOW_RECOGNITION_COMPROMISED,
        }
        if (
            len(self.cases) != 6
            or {case.replay_plan.observed_stop_facts.derive_stop_condition() for case in self.cases}
            != required_conditions
        ):
            raise TrialCasePackError("canonical pack must contain the six authorized cases")
        for fixture in self.additional_fixtures:
            fixture.assert_integrity()
        all_keys = (*keys, *(fixture.fixture_key for fixture in self.additional_fixtures))
        if len(all_keys) != len(set(all_keys)):
            raise TrialCasePackError("canonical and additional fixture keys must be unique")
        if self.pack_hash != canonical_document_sha256(_pack_document(self)):
            raise TrialCasePackError("canonical case-pack hash does not match its payload")


@dataclass(frozen=True)
class TrialCaseAcceptance:
    accepted: bool
    mismatches: tuple[str, ...]
    expectation_hash: str
    observed_result_hash: str
    acceptance_hash: str

    def assert_integrity(self) -> None:
        if self.accepted is bool(self.mismatches):
            raise TrialCasePackError("acceptance status differs from mismatch facts")
        if not self.expectation_hash or not self.observed_result_hash:
            raise TrialCasePackError("acceptance must bind exact expectation and observed Result")
        if self.acceptance_hash != canonical_document_sha256(_acceptance_document(self)):
            raise TrialCasePackError("case acceptance hash does not match its payload")


@dataclass(frozen=True)
class TrialCaseReplayRecord:
    case_key: str
    case_hash: str
    case_admission: TrialCanonicalCaseAdmission
    stop: TrialStop
    result: TrialResult
    acceptance: TrialCaseAcceptance
    record_hash: str

    def assert_integrity(
        self,
        *,
        root_admission: _AuthenticatedCanonicalAdmission | None = None,
        root_bundle: VerifiedTrialBundle | None = None,
        root_environment: TrialEnvironmentAdmission | None = None,
    ) -> None:
        if root_bundle is None:
            raise TrialCasePackError("authenticated root verified bundle is required")
        self.stop.assert_integrity()
        self.result.assert_integrity()
        self.acceptance.assert_integrity()
        self.case_admission.assert_integrity(
            root_admission=root_admission,
            root_bundle=root_bundle,
            root_environment=root_environment,
        )
        assert_trial_result_binding(
            root_bundle.attempt,
            self.case_admission.manifest,
            self.case_admission.environment,
            self.stop,
            self.result,
        )
        if (
            self.stop.attempt_receipt_hash,
            self.result.attempt_receipt_hash,
        ) != (
            self.case_admission.attempt_receipt_hash,
            self.case_admission.attempt_receipt_hash,
        ):
            raise TrialCasePackError(
                "case replay Stop/Result differ from the admitted Attempt Receipt"
            )
        if self.result.trial_stop_hash != self.stop.stop_hash:
            raise TrialCasePackError("case replay Result does not bind its exact Stop")
        if (
            self.result.outcome,
            self.result.stop_condition,
            self.result.stop_phase,
            self.result.runtime_trajectory,
            self.result.final_runtime_position,
            self.result.reasons,
        ) != (
            self.stop.outcome,
            self.stop.stop_condition,
            self.stop.stop_phase,
            self.stop.runtime_trajectory,
            self.stop.final_runtime_position,
            self.stop.reasons,
        ):
            raise TrialCasePackError("case replay Result terminal facts differ from Stop")
        pack = _load_canonical_case_pack()
        matching = tuple(
            case
            for case in pack.cases
            if (case.case_key, case.case_hash) == (self.case_key, self.case_hash)
        )
        if len(matching) != 1:
            raise TrialCasePackError("case replay record does not bind one canonical case")
        if (
            self.case_admission.case_key,
            self.case_admission.case_hash,
            self.result.case_id,
            self.result.trial_manifest_hash,
            self.result.environment_admission_hash,
        ) != (
            self.case_key,
            self.case_hash,
            self.case_key,
            self.case_admission.manifest.manifest_hash,
            self.case_admission.environment.environment_admission_hash,
        ):
            raise TrialCasePackError("case replay Result does not bind its canonical admission")
        if self.acceptance != _compare_observed(matching[0].expectation, self.result):
            raise TrialCasePackError("case replay acceptance differs from recomputed verdict")
        if self.record_hash != canonical_document_sha256(_record_document(self)):
            raise TrialCasePackError("case replay record hash does not match its payload")


@dataclass(frozen=True)
class TrialCasePackRun:
    pack_id: str
    pack_hash: str
    records: tuple[TrialCaseReplayRecord, ...]
    all_accepted: bool
    run_hash: str

    def assert_integrity(
        self,
        *,
        root_admission: _AuthenticatedCanonicalAdmission | None = None,
        root_bundle: VerifiedTrialBundle | None = None,
        root_environment: TrialEnvironmentAdmission | None = None,
    ) -> None:
        for record in self.records:
            record.assert_integrity(
                root_admission=root_admission,
                root_bundle=root_bundle,
                root_environment=root_environment,
            )
        pack = _load_canonical_case_pack()
        expected_cases = tuple((case.case_key, case.case_hash) for case in pack.cases)
        observed_cases = tuple((record.case_key, record.case_hash) for record in self.records)
        if (self.pack_id, self.pack_hash, observed_cases) != (
            pack.pack_id,
            pack.pack_hash,
            expected_cases,
        ):
            raise TrialCasePackError("case-pack run does not bind the exact package-owned pack")
        if self.all_accepted is not all(record.acceptance.accepted for record in self.records):
            raise TrialCasePackError("case-pack run status differs from case acceptances")
        if self.run_hash != canonical_document_sha256(_run_document(self)):
            raise TrialCasePackError("case-pack run hash does not match its payload")


def _plan_document(plan: TrialReplayPlan) -> dict[str, object]:
    return {
        "case_key": plan.case_key,
        "case_mode": plan.case_mode.value,
        "runtime_states": [state.value for state in plan.runtime_states],
        "terminal_phase": plan.terminal_phase.value,
        "terminal_reason": plan.terminal_reason,
        "observed_stop_facts": {
            **_observed_facts_document(plan.observed_stop_facts),
            "facts_hash": plan.observed_stop_facts.facts_hash,
        },
        "observed_evidence": [
            {
                **_observed_evidence_document(item),
                "evidence_hash": item.evidence_hash,
            }
            for item in plan.observed_evidence
        ],
        "produced_artifacts": [_artifact_document(item) for item in plan.produced_artifacts],
        "controlling_artifact_refs": [
            _artifact_document(item) for item in plan.controlling_artifact_refs
        ],
        "dissent_refs": list(plan.dissent_refs),
        "unresolved_condition_refs": list(plan.unresolved_condition_refs),
    }


def _expectation_document(expectation: TrialCaseExpectation) -> dict[str, object]:
    return {
        "expected_outcome": expectation.expected_outcome.value,
        "expected_stop_condition": expectation.expected_stop_condition.value,
        "expected_stop_phase": expectation.expected_stop_phase.value,
        "expected_runtime_states": [state.value for state in expectation.expected_runtime_states],
        "expected_terminal_state": expectation.expected_terminal_state.value,
        "expected_capability_acceptance": expectation.expected_capability_acceptance.value,
        "required_artifacts": [_artifact_document(item) for item in expectation.required_artifacts],
        "forbidden_artifact_kinds": list(expectation.forbidden_artifact_kinds),
        "required_controlling_artifact_refs": [
            _artifact_document(item) for item in expectation.required_controlling_artifact_refs
        ],
        "expected_dissent_refs": list(expectation.expected_dissent_refs),
        "expected_unresolved_condition_refs": list(expectation.expected_unresolved_condition_refs),
        "expected_cleanup_disposition": expectation.expected_cleanup_disposition.value,
    }


def _case_document(case: TrialCanonicalCase) -> dict[str, object]:
    return {
        "case_key": case.case_key,
        "polarity": case.polarity.value,
        "replay_plan": {
            **_plan_document(case.replay_plan),
            "plan_hash": case.replay_plan.plan_hash,
        },
        "expectation": {
            **_expectation_document(case.expectation),
            "expectation_hash": case.expectation.expectation_hash,
        },
    }


def _pack_document(pack: TrialCanonicalCasePack) -> dict[str, object]:
    return {
        "pack_id": pack.pack_id,
        "pack_version": pack.pack_version,
        "cases": [{**_case_document(case), "case_hash": case.case_hash} for case in pack.cases],
        "additional_fixtures": [
            {**_deferred_fixture_document(item), "fixture_hash": item.fixture_hash}
            for item in pack.additional_fixtures
        ],
    }


def _artifact_document(artifact: TrialArtifactRef) -> dict[str, str]:
    return {"kind": artifact.kind, "ref": artifact.ref, "sha256": artifact.sha256}


def _observed_facts_document(facts: TrialObservedStopFacts) -> dict[str, object]:
    return {
        "capability_gap_id": facts.capability_gap_id,
        "research_safety_blocked": facts.research_safety_blocked,
        "challenger_blocked": facts.challenger_blocked,
        "hc_parity_dimensions": [item.value for item in facts.hc_parity_dimensions],
        "hc_metric_facts": [
            {
                "metric_id": item.metric_id,
                "direction": item.direction.value,
                "noninferiority_margin": item.noninferiority_margin,
                "hc_value": item.hc_value,
                "baseline_value": item.baseline_value,
                "regression_detected": item.regression_detected,
            }
            for item in facts.hc_metric_facts
        ],
        "hc_disposition": facts.hc_disposition.value if facts.hc_disposition else None,
        "low_invalid_facts": [item.value for item in facts.low_invalid_facts],
        "low_status": facts.low_status.value if facts.low_status else None,
        "evidence_artifact_hashes": list(facts.evidence_artifact_hashes),
    }


def _observed_evidence_document(evidence: TrialObservedEvidence) -> dict[str, object]:
    return {
        "artifact": _artifact_document(evidence.artifact),
        "payload": evidence.payload(),
    }


def _deferred_fixture_document(fixture: TrialDeferredFixture) -> dict[str, object]:
    return {
        "fixture_key": fixture.fixture_key,
        "expected_stop_condition": fixture.expected_stop_condition.value,
        "expected_stop_phase": fixture.expected_stop_phase.value,
        "required_artifacts": [_artifact_document(item) for item in fixture.required_artifacts],
        "forbidden_artifact_kinds": list(fixture.forbidden_artifact_kinds),
        "required_controlling_artifact_refs": [
            _artifact_document(item) for item in fixture.required_controlling_artifact_refs
        ],
        "expected_cleanup_disposition": fixture.expected_cleanup_disposition.value,
        "exercise_owner": fixture.exercise_owner,
        "resource_stage_call_deltas": list(fixture.resource_stage_call_deltas),
    }


def _record_document(record: TrialCaseReplayRecord) -> dict[str, object]:
    return {
        "case_key": record.case_key,
        "case_hash": record.case_hash,
        "case_admission_hash": record.case_admission.admission_hash,
        "stop_hash": record.stop.stop_hash,
        "result_hash": record.result.result_hash,
        "acceptance_hash": record.acceptance.acceptance_hash,
    }


def _case_admission_document(admission: TrialCanonicalCaseAdmission) -> dict[str, object]:
    return {
        "case_key": admission.case_key,
        "case_hash": admission.case_hash,
        "pack_hash": admission.pack_hash,
        "root_canonical_admission_hash": admission.root_canonical_admission_hash,
        "attempt_receipt_hash": admission.attempt_receipt_hash,
        "root_bundle_receipt_hash": admission.root_bundle_receipt_hash,
        "root_detached_input_address": admission.root_detached_input_address,
        "root_payload_documents_sha256": admission.root_payload_documents_sha256,
        "root_semantic_fingerprint": admission.root_semantic_fingerprint,
        "derived_case_sha256": admission.derived_case_sha256,
        "case_derivation_hash": admission.case_derivation_hash,
        "manifest_hash": admission.manifest.manifest_hash,
        "canonical_admission_hash": admission.canonical_admission.canonical_admission_hash,
        "environment_admission_hash": admission.environment.environment_admission_hash,
    }


def _acceptance_document(acceptance: TrialCaseAcceptance) -> dict[str, object]:
    return {
        "accepted": acceptance.accepted,
        "mismatches": list(acceptance.mismatches),
        "expectation_hash": acceptance.expectation_hash,
        "observed_result_hash": acceptance.observed_result_hash,
    }


def _run_document(run: TrialCasePackRun) -> dict[str, object]:
    return {
        "pack_id": run.pack_id,
        "pack_hash": run.pack_hash,
        "record_hashes": [record.record_hash for record in run.records],
        "all_accepted": run.all_accepted,
    }


def _freeze_plan(
    case_key: str,
    states: tuple[RuntimeState, ...],
    reason: str,
    observed_stop_facts: TrialObservedStopFacts,
    observed_evidence: tuple[TrialObservedEvidence, ...],
    produced_artifacts: tuple[TrialArtifactRef, ...],
    controlling_artifact_refs: tuple[TrialArtifactRef, ...] = (),
    dissent_refs: tuple[str, ...] = (),
    unresolved_condition_refs: tuple[str, ...] = (),
) -> TrialReplayPlan:
    seed = TrialReplayPlan(
        case_key=case_key,
        case_mode=CaseMode.MECHANISM_BENCHMARK,
        runtime_states=states,
        terminal_phase=TrialStopPhase.EXECUTION,
        terminal_reason=reason,
        observed_stop_facts=observed_stop_facts,
        observed_evidence=observed_evidence,
        produced_artifacts=produced_artifacts,
        controlling_artifact_refs=controlling_artifact_refs,
        dissent_refs=dissent_refs,
        unresolved_condition_refs=unresolved_condition_refs,
        plan_hash="",
    )
    plan = TrialReplayPlan(
        **{**seed.__dict__, "plan_hash": canonical_document_sha256(_plan_document(seed))}
    )
    plan.assert_integrity()
    return plan


def _freeze_expectation(
    plan: TrialReplayPlan,
    expected_condition: TrialStopCondition,
) -> TrialCaseExpectation:
    seed = TrialCaseExpectation(
        expected_outcome=stop_outcome_for(expected_condition),
        expected_stop_condition=expected_condition,
        expected_stop_phase=plan.terminal_phase,
        expected_runtime_states=plan.runtime_states,
        expected_terminal_state=plan.runtime_states[-1],
        # Reproducing an expected protective stop is a successful capability test;
        # it is not a substantive Case PASS.
        expected_capability_acceptance=TrialCapabilityAcceptance.PASS,
        required_artifacts=plan.produced_artifacts,
        forbidden_artifact_kinds=_FORBIDDEN_DOWNSTREAM_ARTIFACT_KINDS,
        required_controlling_artifact_refs=plan.controlling_artifact_refs,
        expected_dissent_refs=plan.dissent_refs,
        expected_unresolved_condition_refs=plan.unresolved_condition_refs,
        expected_cleanup_disposition=TrialCleanupDisposition.NOT_ATTEMPTED,
        expectation_hash="",
    )
    expectation = TrialCaseExpectation(
        **{
            **seed.__dict__,
            "expectation_hash": canonical_document_sha256(_expectation_document(seed)),
        }
    )
    expectation.assert_integrity()
    return expectation


def _freeze_case(
    case_key: str,
    polarity: TrialCasePolarity,
    states: tuple[RuntimeState, ...],
    condition: TrialStopCondition,
    reason: str,
    observed_stop_facts: TrialObservedStopFacts,
    observed_evidence: tuple[TrialObservedEvidence, ...],
    produced_artifacts: tuple[TrialArtifactRef, ...],
    controlling_artifact_refs: tuple[TrialArtifactRef, ...] = (),
    dissent_refs: tuple[str, ...] = (),
    unresolved_condition_refs: tuple[str, ...] = (),
) -> TrialCanonicalCase:
    plan = _freeze_plan(
        case_key,
        states,
        reason,
        observed_stop_facts,
        observed_evidence,
        produced_artifacts,
        controlling_artifact_refs,
        dissent_refs,
        unresolved_condition_refs,
    )
    expectation = _freeze_expectation(plan, condition)
    seed = TrialCanonicalCase(case_key, polarity, plan, expectation, "")
    case = TrialCanonicalCase(
        case_key,
        polarity,
        plan,
        expectation,
        canonical_document_sha256(_case_document(seed)),
    )
    case.assert_integrity()
    return case


_FORBIDDEN_DOWNSTREAM_ARTIFACT_KINDS = (
    "FINAL_SYNTHESIS",
    "FINAL_CLAIM",
    "HUMAN_REVIEW",
    "SEAL",
)


def _fixture_ref(
    kind: str,
    ref: str,
    *,
    payload: dict[str, object] | None = None,
) -> TrialArtifactRef:
    document: dict[str, object] = {"kind": kind, "ref": ref, "fixture": "SBX4"}
    if payload is not None:
        document["payload"] = payload
    native_hash_fields = {
        "RESEARCH_SAFETY_ADMISSION": "admission_hash",
        "RESEARCH_SAFETY_RESULT": "result_hash",
        "CHALLENGER_FINDING": "finding_hash",
        "CHALLENGER_RESPONSE": "response_hash",
        "CHALLENGER_SATISFACTION": "satisfaction_hash",
        "CHALLENGER_GATE": "gate_result_hash",
        "CHALLENGER_TASK": "task_hash",
        "CHALLENGER_PACKET": "packet_hash",
    }
    native_hash = payload.get(native_hash_fields.get(kind, "")) if payload is not None else None
    return TrialArtifactRef(
        kind=kind,
        ref=ref,
        sha256=(
            native_hash if isinstance(native_hash, str) else canonical_document_sha256(document)
        ),
    )


def _linked_fixture_ref(
    kind: str,
    fixture_id: str,
    *parents: TrialArtifactRef,
    payload: dict[str, object] | None = None,
) -> TrialArtifactRef:
    lineage = ",".join(parent.sha256 for parent in parents) or "case-revision"
    return _fixture_ref(kind, f"{fixture_id}<-{lineage}", payload=payload)


def _direct_parent_hashes(artifact: TrialArtifactRef) -> tuple[str, ...]:
    _, separator, lineage = artifact.ref.partition("<-")
    if not separator or not lineage or "<-" in lineage:
        raise TrialCasePackError("artifact ref lacks one canonical direct-parent list")
    parents = tuple(lineage.split(","))
    if any(len(parent) != 64 for parent in parents):
        raise TrialCasePackError("artifact direct-parent list is malformed")
    return parents


def _freeze_observed_evidence(
    artifact: TrialArtifactRef,
    payload: dict[str, object],
) -> TrialObservedEvidence:
    seed = TrialObservedEvidence(artifact, canonical_document_bytes(payload), "")
    evidence = TrialObservedEvidence(
        artifact,
        seed.payload_bytes,
        canonical_document_sha256(_observed_evidence_document(seed)),
    )
    evidence.assert_integrity()
    return evidence


def _hc_report_fixture_payload(
    metric: TrialHCMetricFact,
    parity_hashes: tuple[str, ...],
    rule_hash: str,
    hc_snapshot_hash: str,
    baseline_snapshot_hash: str,
) -> dict[str, object]:
    if len(parity_hashes) != 4 or len(set(parity_hashes)) != 4:
        raise TrialCasePackError("HC report fixture requires four parity declaration hashes")
    disposition = (
        RegressionDisposition.REGRESSION_DETECTED
        if metric.regression_detected
        else RegressionDisposition.NO_REGRESSION_DETECTED
    )
    return {
        "hc_snapshot_hash": hc_snapshot_hash,
        "baseline_snapshot_hash": baseline_snapshot_hash,
        "validity": "VALID",
        "disposition": disposition.value,
        "parity_results": [
            {
                "dimension": dimension.value,
                "declaration_hash": declaration_hash,
                "hc_matches_preregistration": True,
                "baseline_matches_preregistration": True,
            }
            for dimension, declaration_hash in zip(
                RegressionParityDimension,
                parity_hashes,
                strict=True,
            )
        ],
        "metric_results": [
            {
                "metric_id": metric.metric_id,
                "rule_hash": rule_hash,
                "direction": metric.direction.value,
                "noninferiority_margin": metric.noninferiority_margin,
                "hc_value": metric.hc_value,
                "baseline_value": metric.baseline_value,
                "regression_detected": metric.regression_detected,
            }
        ],
    }


def _low_exposure_fixture_payload(*, compromised: bool) -> dict[str, object]:
    return {
        "entity_system_identity_exposed": compromised,
        "provenance_label_exposed": False,
        "solver_controller_identity_exposed": False,
        "comparison_label_exposed": False,
        "material_revealed_before_freeze": [],
        "same_session_or_inherited_knowledge": False,
        "cross_evaluator_contamination": False,
        "cross_comparison_contamination": False,
        "unresolved_protocol_invalid": False,
    }


def _low_snapshot_fixture_payload(
    *,
    compromised: bool,
    source_hash: str,
) -> dict[str, object]:
    return {
        **_low_exposure_fixture_payload(compromised=compromised),
        "exposure_source_hash": source_hash,
    }


def _low_gate_fixture_payload(
    *,
    compromised: bool,
    source_hash: str,
    snapshot_hash: str,
) -> dict[str, object]:
    invalid = (
        [LowRecognitionInvalidFact.ENTITY_SYSTEM_IDENTITY_EXPOSED.value] if compromised else []
    )
    return {
        **_low_exposure_fixture_payload(compromised=compromised),
        "exposure_source_hash": source_hash,
        "exposure_snapshot_hash": snapshot_hash,
        "invalid_facts": invalid,
        "status": (
            LowRecognitionGateStatus.BLOCK.value
            if compromised
            else LowRecognitionGateStatus.PASS.value
        ),
    }


def _research_safety_fixture(
    *,
    case_id: str,
    fixture_label: str,
    blocked: bool,
    world_state_hash: str,
    causal_graph_hash: str,
    critical_detection_hash: str,
    critical_review_plan_hash: str,
) -> tuple[ResearchSafetyAdmission, ResearchSafetyResult]:
    frozen_at = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
    admission = freeze_research_safety_admission(
        ResearchSafetyAdmissionPayload(
            admission_id=f"research-safety-admission:sbx4:{fixture_label}",
            case_id=case_id,
            case_revision=1,
            parent_world_state_hash=world_state_hash,
            parent_causal_graph_hash=causal_graph_hash,
            critical_detection_hash=critical_detection_hash,
            critical_review_plan_hash=critical_review_plan_hash,
            required_safety_facts=("authorized-read-only-scope",),
            present_safety_facts=("authorized-read-only-scope",) if not blocked else (),
            blocked_path_refs=("SCENARIO_GENERATION",) if blocked else (),
            protocol_version="human-cos-v1",
            frozen_at=frozen_at,
        )
    )
    result = evaluate_research_safety(
        admission,
        result_id=f"research-safety-result:sbx4:{fixture_label}",
        frozen_at=frozen_at,
    )
    assert_research_safety_result_binding(admission, result)
    return admission, result


def _challenger_parent_fixture(
    *,
    case_id: str,
    fixture_label: str,
    critical_review_plan_hash: str,
    controller_c_output_hash: str,
    scenario_set_hash: str,
    resimulation_plan_hash: str,
    resimulation_result_hash: str,
    at17_evidence_hash: str,
    resulting_world_state_hash: str,
    resulting_causal_graph_hash: str,
    resimulation_safety_result_hash: str,
) -> tuple[ChallengerTask, ChallengerSourcePacket]:
    frozen_at = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
    pending_route_id = f"challenger-route:{critical_review_plan_hash}"
    task_payload = ChallengerTaskPayload(
        task_id=f"challenger-task:sbx4:{fixture_label}",
        case_id=case_id,
        case_revision=1,
        pending_s6_route_id=pending_route_id,
        critical_review_plan_hash=critical_review_plan_hash,
        controller_c_output_hash=controller_c_output_hash,
        generator_run_id="generator-run",
        generator_context_manifest_hash=canonical_document_sha256({"fixture": "generator-context"}),
        generator_model_id="mock-generator",
        generator_model_family="mock-generator-family",
        generator_provider="mock",
        scenario_set_hash=scenario_set_hash,
        resimulation_plan_hash=resimulation_plan_hash,
        resimulation_result_hash=resimulation_result_hash,
        at17_evidence_hash=at17_evidence_hash,
        resulting_world_state_hash=resulting_world_state_hash,
        resulting_causal_graph_hash=resulting_causal_graph_hash,
        resimulation_safety_result_hash=resimulation_safety_result_hash,
        requested_challenger_model_id="mock-challenger",
        requested_challenger_model_family="mock-challenger-family",
        requested_challenger_provider="mock",
        attack_types=FROZEN_CHALLENGER_ATTACK_TYPES,
        require_model_family_independence=True,
        requested_model_family_independent=True,
        requested_provider_independent=False,
        protocol_version="human-cos-v1",
        frozen_at=frozen_at,
    )
    task_document = task_payload.to_document()
    task = ChallengerTask(
        **task_document,
        task_hash=canonical_document_sha256(task_document),
    )
    task.assert_integrity()
    source_hashes = (
        critical_review_plan_hash,
        controller_c_output_hash,
        scenario_set_hash,
        resimulation_plan_hash,
        resimulation_result_hash,
        at17_evidence_hash,
        resulting_world_state_hash,
        resulting_causal_graph_hash,
    )
    source_refs = tuple(
        ChallengerSourceRef(kind=kind, ref=f"{kind.value.lower()}:sbx4", sha256=sha256)
        for kind, sha256 in zip(ChallengerSourceKind, source_hashes, strict=True)
    )
    packet_payload = ChallengerSourcePacketPayload(
        packet_id=f"challenger-packet:sbx4:{fixture_label}",
        case_id=case_id,
        case_revision=1,
        task_hash=task.task_hash,
        pending_s6_route_id=pending_route_id,
        source_refs=source_refs,
        protocol_version="human-cos-v1",
        frozen_at=frozen_at,
    )
    packet_document = packet_payload.to_document()
    packet = ChallengerSourcePacket(
        **packet_document,
        packet_hash=canonical_document_sha256(packet_document),
    )
    packet.assert_integrity()
    return task, packet


def _challenger_fixture(
    *,
    case_id: str,
    fixture_label: str,
    blocking: bool,
    task_hash: str,
    packet_hash: str,
    critical_review_plan_hash: str,
    source_hash: str,
    raw_output_hash: str,
) -> tuple[
    tuple[ChallengerFinding, ...],
    ChallengerResponse,
    PendingChallengerSatisfaction,
    ChallengerReviewGateResult,
]:
    frozen_at = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
    findings: list[ChallengerFinding] = []
    for index, attack_type in enumerate(FROZEN_CHALLENGER_ATTACK_TYPES):
        finding_document: dict[str, object] = {
            "finding_id": f"challenger-{fixture_label}:{attack_type.value.lower()}",
            "task_hash": task_hash,
            "packet_hash": packet_hash,
            "challenger_run_id": f"challenger-{fixture_label}-run",
            "challenger_model_id": "mock-challenger",
            "challenger_model_family": "mock-challenger-family",
            "challenger_provider": "mock",
            "attack_type": attack_type.value,
            "statement": f"frozen {attack_type.value} finding",
            "rationale": "synthetic structural Challenger fixture",
            "source_hash_refs": [source_hash],
            "falsifier_refs": [],
            "missing_falsifier_refs": [],
            "wrong_if_candidates": [],
            "blocking": blocking and index == 0,
            "unresolved": False,
            "protocol_version": "human-cos-v1",
            "frozen_at": "2026-01-01T00:00:00Z",
        }
        finding_document["finding_hash"] = canonical_document_sha256(finding_document)
        finding = ChallengerFinding.model_validate(finding_document)
        finding.assert_integrity()
        findings.append(finding)
    response_document: dict[str, object] = {
        "response_id": f"challenger-response:sbx4:{fixture_label}",
        "task_hash": task_hash,
        "packet_hash": packet_hash,
        "case_id": case_id,
        "case_revision": 1,
        "challenger_run_id": f"challenger-{fixture_label}-run",
        "challenger_context_manifest_hash": canonical_document_sha256(
            {"fixture": f"challenger-{fixture_label}-context"}
        ),
        "generator_run_id": "generator-run",
        "generator_context_manifest_hash": canonical_document_sha256(
            {"fixture": "generator-context"}
        ),
        "generator_model_id": "mock-generator",
        "generator_model_family": "mock-generator-family",
        "generator_provider": "mock",
        "requested_challenger_model_id": "mock-challenger",
        "challenger_model_id": "mock-challenger",
        "challenger_model_family": "mock-challenger-family",
        "challenger_provider": "mock",
        "run_independent": True,
        "context_independent": True,
        "model_family_independent": True,
        "provider_independent": False,
        "raw_output_ref": "challenger-block-raw-output",
        "raw_output_hash": raw_output_hash,
        "findings": [item.model_dump(mode="json", exclude_none=True) for item in findings],
        "attack_types_covered": [item.value for item in FROZEN_CHALLENGER_ATTACK_TYPES],
        "process_authority": False,
        "evaluator_authority": False,
        "reality_execution_authorized": False,
        "protocol_version": "human-cos-v1",
        "frozen_at": "2026-01-01T00:00:00Z",
    }
    response_document["response_hash"] = canonical_document_sha256(response_document)
    response = ChallengerResponse.model_validate(response_document)
    response.assert_integrity()
    satisfaction_document: dict[str, object] = {
        "satisfaction_id": f"challenger-satisfaction:sbx4:{fixture_label}",
        "case_id": case_id,
        "case_revision": 1,
        "critical_review_plan_hash": critical_review_plan_hash,
        "pending_s6_route_id": f"challenger-route:{critical_review_plan_hash}",
        "challenger_task_hash": task_hash,
        "challenger_packet_hash": packet_hash,
        "challenger_response_hash": response.response_hash,
        "challenger_finding_hashes": [item.finding_hash for item in findings],
        "status": "SATISFIED",
        "blocking_or_unresolved_present": blocking,
        "protocol_version": "human-cos-v1",
        "frozen_at": "2026-01-01T00:00:00Z",
    }
    satisfaction_document["satisfaction_hash"] = canonical_document_sha256(satisfaction_document)
    satisfaction = PendingChallengerSatisfaction.model_validate(satisfaction_document)
    satisfaction.assert_integrity()
    gate = evaluate_challenger_review_gate(
        response=response,
        satisfaction=satisfaction,
        gate_result_id=f"challenger-gate:sbx4:{fixture_label}",
        frozen_at=frozen_at,
    )
    return tuple(findings), response, satisfaction, gate


def _derive_stop_from_evidence(
    evidence_items: tuple[TrialObservedEvidence, ...],
) -> TrialStopCondition:
    blockers: list[TrialStopCondition] = []
    parity_sources = {
        item.artifact.sha256: item.payload()
        for item in evidence_items
        if item.artifact.kind == "HC_REGRESSION_PARITY_DECLARATION"
    }
    rule_sources = {
        item.artifact.sha256: item.payload()
        for item in evidence_items
        if item.artifact.kind == "HC_REGRESSION_METRIC_RULE"
    }
    metric_sources = {
        item.artifact.sha256: item.payload()
        for item in evidence_items
        if item.artifact.kind == "HC_REGRESSION_METRIC_SOURCE"
    }
    track_snapshots = {
        item.artifact.sha256: item.payload()
        for item in evidence_items
        if item.artifact.kind == "HC_REGRESSION_TRACK_SNAPSHOT"
    }
    low_sources = {
        item.artifact.sha256: item.payload()
        for item in evidence_items
        if item.artifact.kind == "LOW_RECOGNITION_EXPOSURE_SOURCE"
    }
    low_snapshots = {
        item.artifact.sha256: item.payload()
        for item in evidence_items
        if item.artifact.kind == "LOW_RECOGNITION_EXPOSURE_SNAPSHOT"
    }
    safety_admissions = {
        str(item.payload().get("admission_hash")): item
        for item in evidence_items
        if item.artifact.kind == "RESEARCH_SAFETY_ADMISSION"
    }
    challenger_tasks = {
        str(item.payload().get("task_hash")): item
        for item in evidence_items
        if item.artifact.kind == "CHALLENGER_TASK"
    }
    challenger_packets = {
        str(item.payload().get("packet_hash")): item
        for item in evidence_items
        if item.artifact.kind == "CHALLENGER_PACKET"
    }
    challenger_responses = {
        str(item.payload().get("response_hash")): item
        for item in evidence_items
        if item.artifact.kind == "CHALLENGER_RESPONSE"
    }
    challenger_satisfactions = {
        str(item.payload().get("satisfaction_hash")): item
        for item in evidence_items
        if item.artifact.kind == "CHALLENGER_SATISFACTION"
    }
    challenger_findings = {
        str(item.payload().get("finding_hash")): item
        for item in evidence_items
        if item.artifact.kind == "CHALLENGER_FINDING"
    }
    safety_results: list[ResearchSafetyResult] = []
    for evidence in evidence_items:
        evidence.assert_integrity()
        payload = evidence.payload()
        if evidence.artifact.kind == "CAPABILITY_GAP":
            if not payload.get("capability_gap_id") or payload.get("route") is not None:
                raise TrialCasePackError("Capability Gap evidence payload is malformed")
            blockers.append(TrialStopCondition.CAPABILITY_GAP)
        elif evidence.artifact.kind == "RESEARCH_SAFETY_RESULT":
            result = ResearchSafetyResult.model_validate(payload)
            admission_evidence = safety_admissions.get(result.admission_hash)
            if admission_evidence is None:
                raise TrialCasePackError(
                    "Research Safety result does not resolve its distinct admission"
                )
            admission = ResearchSafetyAdmission.model_validate(admission_evidence.payload())
            assert_research_safety_result_binding(admission, result)
            safety_results.append(result)
            if any(
                parent_hash not in evidence.artifact.ref
                for parent_hash in (
                    admission_evidence.artifact.sha256,
                    result.parent_world_state_hash,
                    result.parent_causal_graph_hash,
                    result.critical_detection_hash,
                    result.critical_review_plan_hash,
                )
            ):
                raise TrialCasePackError(
                    "Research Safety result does not bind its produced parent artifacts"
                )
            if result.outcome is ResearchSafetyOutcome.BLOCK:
                blockers.append(TrialStopCondition.RESEARCH_SAFETY_BLOCK)
        elif evidence.artifact.kind == "CHALLENGER_GATE":
            gate = ChallengerReviewGateResult.model_validate(payload)
            response_evidence = challenger_responses.get(gate.challenger_response_hash)
            satisfaction_evidence = challenger_satisfactions.get(gate.satisfaction_hash)
            if response_evidence is None or satisfaction_evidence is None:
                raise TrialCasePackError(
                    "Challenger gate does not resolve its distinct response and satisfaction"
                )
            response = ChallengerResponse.model_validate(response_evidence.payload())
            satisfaction = PendingChallengerSatisfaction.model_validate(
                satisfaction_evidence.payload()
            )
            task_evidence = challenger_tasks.get(response.task_hash)
            packet_evidence = challenger_packets.get(response.packet_hash)
            if task_evidence is None or packet_evidence is None:
                raise TrialCasePackError(
                    "Challenger response does not resolve its typed Task and packet"
                )
            task = ChallengerTask.model_validate(task_evidence.payload())
            packet = ChallengerSourcePacket.model_validate(packet_evidence.payload())
            assert_challenger_packet_binding(task=task, packet=packet)
            task_parent_hashes = (
                task.critical_review_plan_hash,
                task.controller_c_output_hash,
                task.scenario_set_hash,
                task.resimulation_plan_hash,
                task.resimulation_result_hash,
                task.at17_evidence_hash,
                task.resulting_world_state_hash,
                task.resulting_causal_graph_hash,
                task.resimulation_safety_result_hash,
            )
            if _direct_parent_hashes(task_evidence.artifact) != task_parent_hashes:
                raise TrialCasePackError("Challenger Task direct-parent topology differs")
            if _direct_parent_hashes(packet_evidence.artifact) != (
                task.task_hash,
                *(item.sha256 for item in packet.source_refs),
            ):
                raise TrialCasePackError("Challenger packet direct-parent topology differs")
            response_task_fields = (
                response.case_id,
                response.case_revision,
                response.generator_run_id,
                response.generator_context_manifest_hash,
                response.generator_model_id,
                response.generator_model_family,
                response.generator_provider,
                response.requested_challenger_model_id,
                response.challenger_model_id,
                response.challenger_model_family,
                response.challenger_provider,
                response.model_family_independent,
                response.provider_independent,
                response.expert_independent,
                response.protocol_version,
            )
            expected_response_task_fields = (
                task.case_id,
                task.case_revision,
                task.generator_run_id,
                task.generator_context_manifest_hash,
                task.generator_model_id,
                task.generator_model_family,
                task.generator_provider,
                task.requested_challenger_model_id,
                task.requested_challenger_model_id,
                task.requested_challenger_model_family,
                task.requested_challenger_provider,
                task.requested_model_family_independent,
                task.requested_provider_independent,
                task.expert_independent,
                task.protocol_version,
            )
            if response.fallback_from is not None or (
                response_task_fields != expected_response_task_fields
            ):
                raise TrialCasePackError("Challenger response metadata differs from typed Task")
            if (
                satisfaction.case_id,
                satisfaction.case_revision,
                satisfaction.critical_review_plan_hash,
                satisfaction.pending_s6_route_id,
                satisfaction.challenger_task_hash,
                satisfaction.challenger_packet_hash,
                satisfaction.challenger_response_hash,
                satisfaction.challenger_finding_hashes,
                satisfaction.protocol_version,
            ) != (
                task.case_id,
                task.case_revision,
                task.critical_review_plan_hash,
                task.pending_s6_route_id,
                task.task_hash,
                packet.packet_hash,
                response.response_hash,
                tuple(item.finding_hash for item in response.findings),
                task.protocol_version,
            ):
                raise TrialCasePackError("Challenger satisfaction differs from typed parents")
            for finding in response.findings:
                finding_evidence = challenger_findings.get(finding.finding_hash)
                if (
                    finding_evidence is None
                    or ChallengerFinding.model_validate(finding_evidence.payload()) != finding
                ):
                    raise TrialCasePackError(
                        "Challenger response does not resolve its produced findings"
                    )
                packet_source_hashes = {item.sha256 for item in packet.source_refs}
                if not set(finding.source_hash_refs).issubset(packet_source_hashes):
                    raise TrialCasePackError(
                        "Challenger finding cites a source outside the resolved packet"
                    )
                if _direct_parent_hashes(finding_evidence.artifact) != (
                    finding.task_hash,
                    finding.packet_hash,
                    *finding.source_hash_refs,
                ):
                    raise TrialCasePackError("Challenger finding direct-parent topology differs")
            if _direct_parent_hashes(response_evidence.artifact) != (
                task.task_hash,
                packet.packet_hash,
                response.raw_output_hash,
                *(item.finding_hash for item in response.findings),
            ):
                raise TrialCasePackError("Challenger response direct-parent topology differs")
            if _direct_parent_hashes(satisfaction_evidence.artifact) != (
                task.critical_review_plan_hash,
                task.task_hash,
                packet.packet_hash,
                response.response_hash,
                *(item.finding_hash for item in response.findings),
            ):
                raise TrialCasePackError("Challenger satisfaction direct-parent topology differs")
            if _direct_parent_hashes(evidence.artifact) != (
                response.response_hash,
                satisfaction.satisfaction_hash,
                *gate.blocking_finding_hashes,
                *gate.unresolved_finding_hashes,
            ):
                raise TrialCasePackError("Challenger gate direct-parent topology differs")
            expected_gate = evaluate_challenger_review_gate(
                response=response,
                satisfaction=satisfaction,
                gate_result_id=gate.gate_result_id,
                frozen_at=gate.frozen_at,
            )
            if gate != expected_gate:
                raise TrialCasePackError(
                    "Challenger gate differs from its produced blocking lineage"
                )
            if gate.outcome is ChallengerReviewOutcome.BLOCK:
                blockers.append(TrialStopCondition.CHALLENGER_BLOCK)
        elif evidence.artifact.kind == "HC_REGRESSION_REPORT":
            parity = payload.get("parity_results")
            metrics = payload.get("metric_results")
            if not isinstance(parity, list) or not isinstance(metrics, list):
                raise TrialCasePackError("HC report evidence omits parity or metric results")
            hc_snapshot = track_snapshots.get(str(payload.get("hc_snapshot_hash")))
            baseline_snapshot = track_snapshots.get(str(payload.get("baseline_snapshot_hash")))
            if (
                hc_snapshot is None
                or baseline_snapshot is None
                or hc_snapshot.get("track_kind") != "HC"
                or baseline_snapshot.get("track_kind") != "BASELINE"
            ):
                raise TrialCasePackError("HC report does not resolve its exact track snapshots")
            dimensions = {
                item.get("dimension")
                for item in parity
                if isinstance(item, dict)
                and item.get("hc_matches_preregistration") is True
                and item.get("baseline_matches_preregistration") is True
            }
            declaration_hashes = {
                item.get("declaration_hash")
                for item in parity
                if isinstance(item, dict)
                and isinstance(item.get("declaration_hash"), str)
                and len(str(item.get("declaration_hash"))) == 64
            }
            if (
                len(parity) != 4
                or dimensions != {item.value for item in RegressionParityDimension}
                or len(declaration_hashes) != 4
                or declaration_hashes != set(parity_sources)
            ):
                raise TrialCasePackError("HC report evidence parity is invalid")
            for result in parity:
                if not isinstance(result, dict):
                    raise TrialCasePackError("HC parity result is malformed")
                declaration = parity_sources.get(str(result.get("declaration_hash")))
                if declaration is None or declaration.get("dimension") != result.get("dimension"):
                    raise TrialCasePackError(
                        "HC parity result does not resolve to its cited declaration"
                    )
                descriptor_fields = {
                    RegressionParityDimension.INPUT.value: "input_descriptor",
                    RegressionParityDimension.TOOL.value: "tool_descriptor",
                    RegressionParityDimension.BUDGET.value: "budget_descriptor",
                    RegressionParityDimension.OUTPUT_CONTRACT.value: ("output_contract_descriptor"),
                }
                descriptor_field = descriptor_fields.get(str(result.get("dimension")))
                if descriptor_field is None or (
                    result.get("hc_matches_preregistration"),
                    result.get("baseline_matches_preregistration"),
                ) != (
                    declaration.get("hc_descriptor") == hc_snapshot.get(descriptor_field),
                    declaration.get("baseline_descriptor")
                    == baseline_snapshot.get(descriptor_field),
                ):
                    raise TrialCasePackError(
                        "HC parity flags are not recomputable from frozen descriptors"
                    )
            recomputed: list[bool] = []
            for metric in metrics:
                if not isinstance(metric, dict):
                    raise TrialCasePackError("HC report metric result is malformed")
                if not isinstance(metric.get("rule_hash"), str) or len(metric["rule_hash"]) != 64:
                    raise TrialCasePackError("HC report metric rule hash is malformed")
                rule = rule_sources.get(str(metric["rule_hash"]))
                if rule is None or (
                    rule.get("metric_id"),
                    rule.get("direction"),
                    rule.get("noninferiority_margin"),
                ) != (
                    metric.get("metric_id"),
                    metric.get("direction"),
                    metric.get("noninferiority_margin"),
                ):
                    raise TrialCasePackError("HC metric result does not resolve to its cited rule")
                direction = RegressionMetricDirection(str(metric.get("direction")))
                margin_raw = metric.get("noninferiority_margin")
                hc_source = metric_sources.get(str(hc_snapshot.get("metric_source_hash")))
                baseline_source = metric_sources.get(
                    str(baseline_snapshot.get("metric_source_hash"))
                )
                source_fields = (
                    "track_kind",
                    "metric_id",
                    "value",
                    "input_descriptor",
                    "tool_descriptor",
                    "budget_descriptor",
                    "output_contract_descriptor",
                )
                if (
                    hc_source is None
                    or baseline_source is None
                    or any(
                        hc_snapshot.get(field) != hc_source.get(field) for field in source_fields
                    )
                    or any(
                        baseline_snapshot.get(field) != baseline_source.get(field)
                        for field in source_fields
                    )
                    or hc_snapshot.get("metric_id") != metric.get("metric_id")
                    or baseline_snapshot.get("metric_id") != metric.get("metric_id")
                ):
                    raise TrialCasePackError(
                        "HC metric result does not resolve to its produced source snapshots"
                    )
                hc_value_raw = hc_snapshot.get("value")
                baseline_value_raw = baseline_snapshot.get("value")
                if not all(
                    isinstance(value, (int, float)) and not isinstance(value, bool)
                    for value in (margin_raw, hc_value_raw, baseline_value_raw)
                ):
                    raise TrialCasePackError("HC report metric values are malformed")
                assert isinstance(margin_raw, (int, float))
                assert isinstance(hc_value_raw, (int, float))
                assert isinstance(baseline_value_raw, (int, float))
                margin = float(margin_raw)
                hc_value = float(hc_value_raw)
                baseline_value = float(baseline_value_raw)
                if (metric.get("hc_value"), metric.get("baseline_value")) != (
                    hc_value_raw,
                    baseline_value_raw,
                ):
                    raise TrialCasePackError("HC report values differ from produced tracks")
                detected = (
                    hc_value < baseline_value - margin
                    if direction is RegressionMetricDirection.HIGHER_IS_BETTER
                    else hc_value > baseline_value + margin
                )
                if metric.get("regression_detected") is not detected:
                    raise TrialCasePackError("HC report metric disposition is not recomputable")
                recomputed.append(detected)
            disposition = (
                RegressionDisposition.REGRESSION_DETECTED
                if any(recomputed)
                else RegressionDisposition.NO_REGRESSION_DETECTED
            )
            if (
                payload.get("validity") != "VALID"
                or payload.get("disposition") != disposition.value
            ):
                raise TrialCasePackError("HC report disposition is not recomputable")
            if disposition is RegressionDisposition.REGRESSION_DETECTED:
                blockers.append(TrialStopCondition.HC_REGRESSION_DETECTED)
        elif evidence.artifact.kind == "LOW_RECOGNITION_GATE":
            snapshot = low_snapshots.get(str(payload.get("exposure_snapshot_hash")))
            source = low_sources.get(str(payload.get("exposure_source_hash")))
            exposure_fields = (
                "entity_system_identity_exposed",
                "provenance_label_exposed",
                "solver_controller_identity_exposed",
                "comparison_label_exposed",
                "material_revealed_before_freeze",
                "same_session_or_inherited_knowledge",
                "cross_evaluator_contamination",
                "cross_comparison_contamination",
                "unresolved_protocol_invalid",
            )
            if (
                snapshot is None
                or source is None
                or snapshot.get("exposure_source_hash") != payload.get("exposure_source_hash")
                or any(snapshot.get(field) != source.get(field) for field in exposure_fields)
                or any(payload.get(field) != snapshot.get(field) for field in exposure_fields)
            ):
                raise TrialCasePackError(
                    "Low-recognition gate does not resolve to its produced exposure source"
                )
            field_map = (
                (
                    "entity_system_identity_exposed",
                    LowRecognitionInvalidFact.ENTITY_SYSTEM_IDENTITY_EXPOSED,
                ),
                ("provenance_label_exposed", LowRecognitionInvalidFact.PROVENANCE_LABEL_EXPOSED),
                (
                    "solver_controller_identity_exposed",
                    LowRecognitionInvalidFact.SOLVER_CONTROLLER_IDENTITY_EXPOSED,
                ),
                ("comparison_label_exposed", LowRecognitionInvalidFact.COMPARISON_LABEL_EXPOSED),
                (
                    "same_session_or_inherited_knowledge",
                    LowRecognitionInvalidFact.SAME_SESSION_OR_INHERITED_KNOWLEDGE,
                ),
                (
                    "cross_evaluator_contamination",
                    LowRecognitionInvalidFact.CROSS_EVALUATOR_CONTAMINATION,
                ),
                (
                    "cross_comparison_contamination",
                    LowRecognitionInvalidFact.CROSS_COMPARISON_CONTAMINATION,
                ),
                (
                    "unresolved_protocol_invalid",
                    LowRecognitionInvalidFact.UNRESOLVED_PROTOCOL_INVALID,
                ),
            )
            invalid = [fact.value for field, fact in field_map if payload.get(field) is True]
            revealed = payload.get("material_revealed_before_freeze")
            if not isinstance(revealed, list):
                raise TrialCasePackError("Low-recognition evidence omits revealed-material facts")
            if revealed:
                invalid.append(LowRecognitionInvalidFact.MATERIAL_REVEALED_BEFORE_FREEZE.value)
            if payload.get("invalid_facts") != invalid:
                raise TrialCasePackError("Low-recognition invalid facts are not recomputable")
            status = LowRecognitionGateStatus.BLOCK if invalid else LowRecognitionGateStatus.PASS
            if payload.get("status") != status.value:
                raise TrialCasePackError("Low-recognition gate status is not recomputable")
            if status is LowRecognitionGateStatus.BLOCK:
                blockers.append(TrialStopCondition.LOW_RECOGNITION_COMPROMISED)
    if len(safety_results) > 1:
        raise TrialCasePackError("observed evidence contains multiple Research Safety results")
    if not blockers and (
        len(safety_results) != 1 or safety_results[0].outcome is not ResearchSafetyOutcome.PASS
    ):
        raise TrialCasePackError(
            "authorized-boundary completion requires one observed Research Safety PASS"
        )
    if len(blockers) > 1:
        raise TrialCasePackError("observed evidence produced multiple terminal blockers")
    return blockers[0] if blockers else TrialStopCondition.AUTHORIZED_BOUNDARY_REACHED


def _freeze_observed_stop_facts(
    *,
    capability_gap_id: str | None = None,
    research_safety_blocked: bool = False,
    challenger_blocked: bool = False,
    hc_metric_facts: tuple[TrialHCMetricFact, ...] = (),
    hc_disposition: RegressionDisposition | None = None,
    low_invalid_facts: tuple[LowRecognitionInvalidFact, ...] = (),
    low_status: LowRecognitionGateStatus | None = None,
    evidence_artifact_hashes: tuple[str, ...] = (),
) -> TrialObservedStopFacts:
    dimensions = tuple(RegressionParityDimension) if hc_disposition is not None else ()
    seed = TrialObservedStopFacts(
        capability_gap_id,
        research_safety_blocked,
        challenger_blocked,
        dimensions,
        hc_metric_facts,
        hc_disposition,
        low_invalid_facts,
        low_status,
        evidence_artifact_hashes,
        "",
    )
    facts = TrialObservedStopFacts(
        capability_gap_id,
        research_safety_blocked,
        challenger_blocked,
        dimensions,
        hc_metric_facts,
        hc_disposition,
        low_invalid_facts,
        low_status,
        evidence_artifact_hashes,
        canonical_document_sha256(_observed_facts_document(seed)),
    )
    facts.assert_integrity()
    return facts


def _freeze_deferred_fixture(
    fixture_key: str,
    condition: TrialStopCondition,
    *,
    exercise_owner: str,
    phase: TrialStopPhase = TrialStopPhase.EXECUTION,
    resource_stage_call_deltas: tuple[int, ...] = (),
) -> TrialDeferredFixture:
    controlling = (_fixture_ref("STOP_EVIDENCE", f"{fixture_key}:control"),)
    seed = TrialDeferredFixture(
        fixture_key=fixture_key,
        expected_stop_condition=condition,
        expected_stop_phase=phase,
        required_artifacts=controlling,
        forbidden_artifact_kinds=_FORBIDDEN_DOWNSTREAM_ARTIFACT_KINDS,
        required_controlling_artifact_refs=controlling,
        expected_cleanup_disposition=TrialCleanupDisposition.NOT_ATTEMPTED,
        exercise_owner=exercise_owner,
        resource_stage_call_deltas=resource_stage_call_deltas,
        fixture_hash="",
    )
    fixture = TrialDeferredFixture(
        **{
            **seed.__dict__,
            "fixture_hash": canonical_document_sha256(_deferred_fixture_document(seed)),
        }
    )
    fixture.assert_integrity()
    return fixture


def _build_canonical_case_pack() -> TrialCanonicalCasePack:
    closure: list[TrialArtifactRef] = []

    def add(
        kind: str,
        fixture_id: str,
        *parents: TrialArtifactRef,
        payload: dict[str, object] | None = None,
    ) -> TrialArtifactRef:
        item = _linked_fixture_ref(
            kind,
            fixture_id,
            *(parents or tuple(closure[-1:])),
            payload=payload,
        )
        closure.append(item)
        return item

    def add_root(
        kind: str,
        fixture_id: str,
        *,
        payload: dict[str, object] | None = None,
    ) -> TrialArtifactRef:
        item = _linked_fixture_ref(kind, fixture_id, payload=payload)
        closure.append(item)
        return item

    def add_persistence_edge(
        target: TrialArtifactRef,
        relation: str,
        source: TrialArtifactRef,
        source_layer: str,
    ) -> TrialArtifactRef:
        edge = _fixture_ref(
            "PERSISTENCE_LINEAGE_EDGE",
            f"{target.sha256}:{relation}<-{source.sha256}@{source_layer}",
        )
        closure.append(edge)
        return edge

    # Actual S5 persistence closure.
    framing_requirement = add("FRAMING_REQUIREMENT", "framing-requirement:fixture")
    initial_framing_a1 = add("INITIAL_FRAMING", "initial-framing-a1:fixture", framing_requirement)
    initial_framing_a2 = add("INITIAL_FRAMING", "initial-framing-a2:fixture", framing_requirement)
    framing_review = add(
        "FRAMING_REVIEW",
        "framing-review:fixture",
        framing_requirement,
        initial_framing_a1,
        initial_framing_a2,
    )
    domain_task = add("DOMAIN_TASK", "domain-task:fixture", framing_review)
    capability_prefix = tuple(closure)
    domain_route = add("DOMAIN_ROUTE", "domain-route:fixture", domain_task)
    add(
        "DOMAIN_ROUTING_PLAN",
        "domain-routing-plan:fixture",
        framing_review,
        domain_task,
        domain_route,
    )
    domain_output = add("DOMAIN_OUTPUT", "domain-output:fixture", domain_task, domain_route)
    capability_gap = _linked_fixture_ref(
        "CAPABILITY_GAP",
        "capability-gap:fixture",
        domain_task,
        payload={"capability_gap_id": "capability-gap:fixture", "route": None},
    )
    capability_routing_plan = _linked_fixture_ref(
        "DOMAIN_ROUTING_PLAN",
        "domain-routing-plan:capability-gap",
        framing_review,
        domain_task,
        capability_gap,
        payload={
            "task_hash": domain_task.sha256,
            "capability_gap_id": "capability-gap:fixture",
            "route_hash": None,
        },
    )

    # Actual S6-WCI persistence closure.
    disclosure = add("DISCLOSURE_GRANT", "disclosure-grant:fixture", domain_output)
    cross_exam_task = add("CROSS_EXAM_TASK", "cross-exam-task:fixture", disclosure)
    cross_exam_response = add(
        "CROSS_EXAM_RESPONSE", "cross-exam-response:fixture", cross_exam_task, disclosure
    )
    disagreement = add("DISAGREEMENT_NODE", "disagreement-node:fixture", cross_exam_response)
    actor_state = add("ACTOR_STATE", "actor-state:fixture", domain_output, disagreement)
    causal_graph = add("CAUSAL_GRAPH", "causal-graph:fixture", actor_state, disagreement)
    world_state = add("WORLD_STATE", "world-state:fixture", actor_state, causal_graph)
    critical_integration = add(
        "CRITICAL_INTEGRATION", "critical-integration:fixture", world_state, causal_graph
    )
    critical_detection = add(
        "CRITICAL_NODE_DETECTION", "critical-node-detection:fixture", critical_integration
    )
    critical_plan = add("CRITICAL_REVIEW_PLAN", "critical-review-plan:fixture", critical_detection)
    critical_packet = add(
        "CRITICAL_REVIEW_PACKET",
        "critical-review-packet:fixture",
        critical_detection,
        critical_plan,
    )
    critical_evidence = add(
        "CRITICAL_REVIEW_EVIDENCE",
        "critical-review-evidence:fixture",
        critical_detection,
        critical_plan,
        critical_packet,
    )

    # Actual S7 scenario/resimulation/AT-17/Challenger persistence closure.
    safety_admission_model, safety_result_model = _research_safety_fixture(
        case_id="positive:authorized-boundary",
        fixture_label="pass",
        blocked=False,
        world_state_hash=world_state.sha256,
        causal_graph_hash=causal_graph.sha256,
        critical_detection_hash=critical_detection.sha256,
        critical_review_plan_hash=critical_plan.sha256,
    )
    safety_admission = add(
        "RESEARCH_SAFETY_ADMISSION",
        f"research-safety-admission:pass:{safety_admission_model.admission_hash}",
        world_state,
        causal_graph,
        critical_detection,
        critical_plan,
        payload=cast(
            dict[str, object],
            safety_admission_model.model_dump(mode="json", exclude_none=True),
        ),
    )
    safety_result = add(
        "RESEARCH_SAFETY_RESULT",
        f"research-safety-result:pass:{safety_result_model.result_hash}",
        safety_admission,
        world_state,
        causal_graph,
        critical_detection,
        critical_plan,
        payload=cast(
            dict[str, object],
            safety_result_model.model_dump(mode="json", exclude_none=True),
        ),
    )
    research_safety_closure = tuple(closure)
    scenario_packet = add(
        "SCENARIO_GENERATION_PACKET",
        "scenario-generation-packet:fixture",
        safety_admission,
        world_state,
        causal_graph,
        critical_detection,
        critical_plan,
    )
    scenario_result = add(
        "SCENARIO_GENERATION_RESULT",
        "scenario-generation-result:fixture",
        scenario_packet,
        safety_result,
    )
    controller_c_invocation = add(
        "CONTROLLER_C_INVOCATION",
        "controller-c-invocation:fixture",
        world_state,
        causal_graph,
        critical_detection,
        critical_plan,
        safety_result,
        scenario_packet,
        scenario_result,
    )
    scenario_path = add(
        "SCENARIO_PATH",
        "scenario-path:fixture",
        world_state,
        causal_graph,
        critical_detection,
        critical_plan,
    )
    intervention = add_root("INTERVENTION", "intervention:fixture")
    scenario_set = add(
        "SCENARIO_SET",
        "scenario-set:fixture",
        world_state,
        causal_graph,
        critical_detection,
        critical_plan,
        scenario_path,
        intervention,
    )
    controller_c_output = add(
        "CONTROLLER_C_OUTPUT",
        "controller-c-output:fixture",
        controller_c_invocation,
        scenario_set,
        scenario_path,
        intervention,
    )
    resim_safety_admission = add(
        "RESIMULATION_SAFETY_ADMISSION",
        "resimulation-safety-admission:fixture",
        scenario_set,
        scenario_path,
        intervention,
        world_state,
        causal_graph,
    )
    resim_safety_result = add(
        "RESIMULATION_SAFETY_RESULT",
        "resimulation-safety-result:fixture",
        resim_safety_admission,
        scenario_set,
        scenario_path,
        intervention,
        world_state,
        causal_graph,
    )
    rerun_task = add(
        "RERUN_TASK",
        "rerun-task:fixture",
        scenario_set,
        scenario_path,
        intervention,
        world_state,
        causal_graph,
    )
    rerun_route = add("RERUN_ROUTE", "rerun-route:fixture", rerun_task)
    rerun_raw_output = add_root("RAW_OUTPUT", "rerun-raw-output:fixture")
    rerun_output = add(
        "RERUN_OUTPUT",
        "rerun-output:fixture",
        rerun_task,
        rerun_route,
        scenario_set,
        scenario_path,
        intervention,
        world_state,
        causal_graph,
        rerun_raw_output,
    )
    resimulation_plan = add(
        "RESIMULATION_PLAN",
        "resimulation-plan:fixture",
        controller_c_output,
        scenario_set,
        scenario_path,
        intervention,
        world_state,
        causal_graph,
        resim_safety_admission,
        resim_safety_result,
        actor_state,
        rerun_task,
        rerun_route,
    )
    revised_actor_state = add(
        "ACTOR_STATE",
        "actor-state:post-resimulation:fixture",
        actor_state,
    )
    resulting_causal_graph = add(
        "CAUSAL_GRAPH",
        "causal-graph:post-resimulation:fixture",
        causal_graph,
    )
    resulting_world_state = add(
        "WORLD_STATE",
        "world-state:post-resimulation:fixture",
        world_state,
        resulting_causal_graph,
    )
    resimulation = add(
        "RESIMULATION_RESULT",
        "resimulation-result:fixture",
        resimulation_plan,
        scenario_set,
        scenario_path,
        intervention,
        rerun_output,
        world_state,
        resulting_world_state,
        causal_graph,
        resulting_causal_graph,
        actor_state,
        rerun_task,
        rerun_route,
        revised_actor_state,
    )
    at17 = add(
        "AT17_EVIDENCE",
        "at17-evidence:fixture",
        resimulation,
        world_state,
        resulting_world_state,
        causal_graph,
        resulting_causal_graph,
        revised_actor_state,
    )
    challenger_task_model, challenger_packet_model = _challenger_parent_fixture(
        case_id="positive:authorized-boundary",
        fixture_label="pass",
        critical_review_plan_hash=critical_plan.sha256,
        controller_c_output_hash=controller_c_output.sha256,
        scenario_set_hash=scenario_set.sha256,
        resimulation_plan_hash=resimulation_plan.sha256,
        resimulation_result_hash=resimulation.sha256,
        at17_evidence_hash=at17.sha256,
        resulting_world_state_hash=resulting_world_state.sha256,
        resulting_causal_graph_hash=resulting_causal_graph.sha256,
        resimulation_safety_result_hash=resim_safety_result.sha256,
    )
    challenger_task = add(
        "CHALLENGER_TASK",
        f"challenger-task:pass:{challenger_task_model.task_hash}",
        critical_plan,
        controller_c_output,
        scenario_set,
        resimulation_plan,
        resimulation,
        at17,
        resulting_world_state,
        resulting_causal_graph,
        resim_safety_result,
        payload=cast(
            dict[str, object],
            challenger_task_model.model_dump(mode="json", exclude_none=True),
        ),
    )
    challenger_packet = add(
        "CHALLENGER_PACKET",
        f"challenger-packet:pass:{challenger_packet_model.packet_hash}",
        challenger_task,
        critical_plan,
        controller_c_output,
        scenario_set,
        resimulation_plan,
        resimulation,
        at17,
        resulting_world_state,
        resulting_causal_graph,
        payload=cast(
            dict[str, object],
            challenger_packet_model.model_dump(mode="json", exclude_none=True),
        ),
    )
    challenger_raw_output = add_root("RAW_OUTPUT", "challenger-raw-output:fixture")
    (
        challenger_finding_models,
        challenger_response_model,
        challenger_satisfaction_model,
        challenger_gate_model,
    ) = _challenger_fixture(
        case_id="positive:authorized-boundary",
        fixture_label="pass",
        blocking=False,
        task_hash=challenger_task.sha256,
        packet_hash=challenger_packet.sha256,
        critical_review_plan_hash=critical_plan.sha256,
        source_hash=scenario_set.sha256,
        raw_output_hash=challenger_raw_output.sha256,
    )
    challenger_findings = tuple(
        add(
            "CHALLENGER_FINDING",
            f"challenger-finding:pass:{finding.finding_hash}",
            challenger_task,
            challenger_packet,
            scenario_set,
            payload=cast(
                dict[str, object],
                finding.model_dump(mode="json", exclude_none=True),
            ),
        )
        for finding in challenger_finding_models
    )
    challenger_response = add(
        "CHALLENGER_RESPONSE",
        f"challenger-response:pass:{challenger_response_model.response_hash}",
        challenger_task,
        challenger_packet,
        challenger_raw_output,
        *challenger_findings,
        payload=cast(
            dict[str, object],
            challenger_response_model.model_dump(mode="json", exclude_none=True),
        ),
    )
    challenger_satisfaction = add(
        "CHALLENGER_SATISFACTION",
        f"challenger-satisfaction:pass:{challenger_satisfaction_model.satisfaction_hash}",
        critical_plan,
        challenger_task,
        challenger_packet,
        challenger_response,
        *challenger_findings,
        payload=cast(
            dict[str, object],
            challenger_satisfaction_model.model_dump(mode="json", exclude_none=True),
        ),
    )
    challenger_gate = add(
        "CHALLENGER_GATE",
        f"challenger-gate:pass:{challenger_gate_model.gate_result_hash}",
        challenger_response,
        challenger_satisfaction,
        payload=cast(
            dict[str, object],
            challenger_gate_model.model_dump(mode="json", exclude_none=True),
        ),
    )
    challenger_closure = tuple(closure)

    # Actual S8 evaluator, HC-regression and Low-recognition persistence closure.
    evaluator_task = add_root("EVALUATOR_TASK", "evaluator-task:fixture")
    evaluator_packet = add(
        "EVALUATOR_INPUT_PACKET",
        "evaluator-input-packet:fixture",
        evaluator_task,
        critical_evidence,
        scenario_set,
        at17,
        challenger_gate,
    )
    evaluator_finding = add(
        "EVALUATOR_FINDING",
        "evaluator-finding:fixture",
        evaluator_task,
        evaluator_packet,
        critical_evidence,
        scenario_set,
        at17,
        challenger_gate,
    )
    evaluator = add(
        "EVALUATOR_RESULT",
        "evaluator-result:fixture",
        evaluator_task,
        evaluator_packet,
        evaluator_finding,
    )
    positive_metric = TrialHCMetricFact(
        "structural-coverage",
        RegressionMetricDirection.HIGHER_IS_BETTER,
        0.05,
        0.95,
        0.95,
    )
    negative_metric = TrialHCMetricFact(
        "structural-coverage",
        RegressionMetricDirection.HIGHER_IS_BETTER,
        0.05,
        0.70,
        0.95,
    )
    hc_task = add_root("EVALUATOR_TASK", "hc-evaluator-task:fixture")
    hc_run_manifest = add_root(
        "RUN_MANIFEST",
        "hc-run-manifest:fixture",
        payload={"run_id": "hc-positive", "status": "FROZEN"},
    )
    baseline_run_manifest = add_root(
        "RUN_MANIFEST",
        "baseline-run-manifest:fixture",
        payload={"run_id": "baseline-positive", "status": "FROZEN"},
    )
    hc_source = add(
        "HC_REGRESSION_METRIC_SOURCE",
        "hc-metric-source:fixture",
        hc_task,
        hc_run_manifest,
        evaluator,
        at17,
        payload={
            "track_kind": "HC",
            "metric_id": positive_metric.metric_id,
            "value": positive_metric.hc_value,
            "input_descriptor": "mock-only-equal",
            "tool_descriptor": "mock-only-equal",
            "budget_descriptor": "mock-only-equal",
            "output_contract_descriptor": "mock-only-equal",
        },
    )
    baseline_source = add(
        "HC_REGRESSION_METRIC_SOURCE",
        "baseline-metric-source:fixture",
        hc_task,
        baseline_run_manifest,
        evaluator,
        at17,
        payload={
            "track_kind": "BASELINE",
            "metric_id": positive_metric.metric_id,
            "value": positive_metric.baseline_value,
            "input_descriptor": "mock-only-equal",
            "tool_descriptor": "mock-only-equal",
            "budget_descriptor": "mock-only-equal",
            "output_contract_descriptor": "mock-only-equal",
        },
    )
    hc_packet = add(
        "EVALUATOR_INPUT_PACKET",
        "hc-evaluator-input-packet:fixture",
        hc_task,
        hc_source,
        baseline_source,
        hc_run_manifest,
        baseline_run_manifest,
        evaluator,
        at17,
        critical_evidence,
        scenario_set,
        challenger_gate,
    )
    add_persistence_edge(hc_source, "evaluator_packet", hc_packet, "S8")
    add_persistence_edge(baseline_source, "evaluator_packet", hc_packet, "S8")
    hc_parity = tuple(
        add(
            "HC_REGRESSION_PARITY_DECLARATION",
            f"hc-parity-declaration:{dimension.value.lower()}:fixture",
            hc_task,
            payload={
                "dimension": dimension.value,
                "hc_descriptor": "mock-only-equal",
                "baseline_descriptor": "mock-only-equal",
            },
        )
        for dimension in RegressionParityDimension
    )
    hc_rule = add(
        "HC_REGRESSION_METRIC_RULE",
        "hc-metric-rule:fixture",
        hc_task,
        payload={
            "metric_id": positive_metric.metric_id,
            "direction": positive_metric.direction.value,
            "noninferiority_margin": positive_metric.noninferiority_margin,
        },
    )
    hc_prereg = add(
        "HC_REGRESSION_PREREGISTRATION",
        "hc-preregistration:fixture",
        hc_task,
        hc_packet,
        *hc_parity,
        hc_rule,
    )
    hc_snapshot = add(
        "HC_REGRESSION_TRACK_SNAPSHOT",
        "hc-track-snapshot:fixture",
        hc_task,
        hc_packet,
        hc_prereg,
        hc_run_manifest,
        hc_source,
        payload={
            "track_kind": "HC",
            "metric_source_hash": hc_source.sha256,
            "metric_id": positive_metric.metric_id,
            "value": positive_metric.hc_value,
            "input_descriptor": "mock-only-equal",
            "tool_descriptor": "mock-only-equal",
            "budget_descriptor": "mock-only-equal",
            "output_contract_descriptor": "mock-only-equal",
        },
    )
    baseline_snapshot = add(
        "HC_REGRESSION_TRACK_SNAPSHOT",
        "baseline-track-snapshot:fixture",
        hc_task,
        hc_packet,
        hc_prereg,
        baseline_run_manifest,
        baseline_source,
        payload={
            "track_kind": "BASELINE",
            "metric_source_hash": baseline_source.sha256,
            "metric_id": positive_metric.metric_id,
            "value": positive_metric.baseline_value,
            "input_descriptor": "mock-only-equal",
            "tool_descriptor": "mock-only-equal",
            "budget_descriptor": "mock-only-equal",
            "output_contract_descriptor": "mock-only-equal",
        },
    )
    hc_regression = add(
        "HC_REGRESSION_REPORT",
        "hc-regression-report:fixture",
        hc_task,
        hc_packet,
        hc_prereg,
        hc_snapshot,
        baseline_snapshot,
        payload=_hc_report_fixture_payload(
            positive_metric,
            tuple(item.sha256 for item in hc_parity),
            hc_rule.sha256,
            hc_snapshot.sha256,
            baseline_snapshot.sha256,
        ),
    )
    add(
        "EVALUATION_EVIDENCE_BINDING",
        "hc-evidence-binding:fixture",
        hc_task,
        hc_packet,
        hc_regression,
        hc_source,
        baseline_source,
        payload={
            "subject": "HC_REGRESSION",
            "recomputed_disposition": RegressionDisposition.NO_REGRESSION_DETECTED.value,
            "status": "PASS",
        },
    )
    low_task = add_root("EVALUATOR_TASK", "low-recognition-evaluator-task:fixture")
    low_source = add(
        "LOW_RECOGNITION_EXPOSURE_SOURCE",
        "low-recognition-source:fixture",
        low_task,
        evaluator,
        at17,
        payload=_low_exposure_fixture_payload(compromised=False),
    )
    low_packet = add(
        "EVALUATOR_INPUT_PACKET",
        "low-recognition-evaluator-input-packet:fixture",
        low_task,
        low_source,
        evaluator,
        at17,
        critical_evidence,
        scenario_set,
        challenger_gate,
    )
    add_persistence_edge(low_source, "evaluator_packet", low_packet, "S8")
    low_policy = add(
        "LOW_RECOGNITION_VISIBILITY_POLICY",
        "low-recognition-policy:fixture",
        low_task,
        low_packet,
    )
    low_snapshot = add(
        "LOW_RECOGNITION_EXPOSURE_SNAPSHOT",
        "low-recognition-snapshot:fixture",
        low_task,
        low_packet,
        low_policy,
        low_source,
        payload=_low_snapshot_fixture_payload(
            compromised=False,
            source_hash=low_source.sha256,
        ),
    )
    low_recognition = add(
        "LOW_RECOGNITION_GATE",
        "low-recognition-gate:fixture",
        low_task,
        low_packet,
        low_policy,
        low_snapshot,
        payload=_low_gate_fixture_payload(
            compromised=False,
            source_hash=low_source.sha256,
            snapshot_hash=low_snapshot.sha256,
        ),
    )
    add(
        "EVALUATION_EVIDENCE_BINDING",
        "low-recognition-evidence-binding:fixture",
        low_task,
        low_packet,
        low_recognition,
        low_source,
        payload={
            "subject": "LOW_RECOGNITION",
            "recomputed_status": LowRecognitionGateStatus.PASS.value,
            "status": "PASS",
        },
    )
    positive_closure = tuple(closure)

    # Negative sidecars are independently frozen evidence, not a positive PASS
    # report/gate paired with a separately injected stop condition.
    hc_negative_task = _linked_fixture_ref(
        "EVALUATOR_TASK", "hc-evaluator-task:regression-detected"
    )
    hc_negative_run_manifest = _linked_fixture_ref(
        "RUN_MANIFEST",
        "hc-run-manifest:regression-detected",
        hc_negative_task,
        payload={"run_id": "hc-regression-detected", "status": "FROZEN"},
    )
    baseline_negative_run_manifest = _linked_fixture_ref(
        "RUN_MANIFEST",
        "baseline-run-manifest:regression-detected",
        hc_negative_task,
        payload={"run_id": "baseline-regression-detected", "status": "FROZEN"},
    )
    hc_negative_source = _linked_fixture_ref(
        "HC_REGRESSION_METRIC_SOURCE",
        "hc-metric-source:regression-detected",
        hc_negative_task,
        hc_negative_run_manifest,
        evaluator,
        at17,
        payload={
            "track_kind": "HC",
            "metric_id": negative_metric.metric_id,
            "value": negative_metric.hc_value,
            "input_descriptor": "mock-only-equal",
            "tool_descriptor": "mock-only-equal",
            "budget_descriptor": "mock-only-equal",
            "output_contract_descriptor": "mock-only-equal",
        },
    )
    baseline_negative_source = _linked_fixture_ref(
        "HC_REGRESSION_METRIC_SOURCE",
        "baseline-metric-source:regression-detected",
        hc_negative_task,
        baseline_negative_run_manifest,
        evaluator,
        at17,
        payload={
            "track_kind": "BASELINE",
            "metric_id": negative_metric.metric_id,
            "value": negative_metric.baseline_value,
            "input_descriptor": "mock-only-equal",
            "tool_descriptor": "mock-only-equal",
            "budget_descriptor": "mock-only-equal",
            "output_contract_descriptor": "mock-only-equal",
        },
    )
    hc_negative_packet = _linked_fixture_ref(
        "EVALUATOR_INPUT_PACKET",
        "hc-evaluator-input-packet:regression-detected",
        hc_negative_task,
        hc_negative_source,
        baseline_negative_source,
        hc_negative_run_manifest,
        baseline_negative_run_manifest,
        evaluator,
        at17,
        critical_evidence,
        scenario_set,
        challenger_gate,
    )
    hc_negative_source_edge = _fixture_ref(
        "PERSISTENCE_LINEAGE_EDGE",
        f"{hc_negative_source.sha256}:evaluator_packet<-{hc_negative_packet.sha256}@S8",
    )
    baseline_negative_source_edge = _fixture_ref(
        "PERSISTENCE_LINEAGE_EDGE",
        f"{baseline_negative_source.sha256}:evaluator_packet<-{hc_negative_packet.sha256}@S8",
    )
    hc_negative_parity = tuple(
        _linked_fixture_ref(
            "HC_REGRESSION_PARITY_DECLARATION",
            f"hc-parity-declaration:{dimension.value.lower()}:regression-detected",
            hc_negative_task,
            payload={
                "dimension": dimension.value,
                "hc_descriptor": "mock-only-equal",
                "baseline_descriptor": "mock-only-equal",
            },
        )
        for dimension in RegressionParityDimension
    )
    hc_negative_rule = _linked_fixture_ref(
        "HC_REGRESSION_METRIC_RULE",
        "hc-metric-rule:regression-detected",
        hc_negative_task,
        payload={
            "metric_id": negative_metric.metric_id,
            "direction": negative_metric.direction.value,
            "noninferiority_margin": negative_metric.noninferiority_margin,
        },
    )
    hc_negative_prereg = _linked_fixture_ref(
        "HC_REGRESSION_PREREGISTRATION",
        "hc-preregistration:regression-detected",
        hc_negative_task,
        hc_negative_packet,
        *hc_negative_parity,
        hc_negative_rule,
    )
    hc_negative_snapshot = _linked_fixture_ref(
        "HC_REGRESSION_TRACK_SNAPSHOT",
        "hc-track-snapshot:regression-detected",
        hc_negative_task,
        hc_negative_packet,
        hc_negative_prereg,
        hc_negative_run_manifest,
        hc_negative_source,
        payload={
            "track_kind": "HC",
            "metric_source_hash": hc_negative_source.sha256,
            "metric_id": negative_metric.metric_id,
            "value": negative_metric.hc_value,
            "input_descriptor": "mock-only-equal",
            "tool_descriptor": "mock-only-equal",
            "budget_descriptor": "mock-only-equal",
            "output_contract_descriptor": "mock-only-equal",
        },
    )
    baseline_negative_snapshot = _linked_fixture_ref(
        "HC_REGRESSION_TRACK_SNAPSHOT",
        "baseline-track-snapshot:regression-detected",
        hc_negative_task,
        hc_negative_packet,
        hc_negative_prereg,
        baseline_negative_run_manifest,
        baseline_negative_source,
        payload={
            "track_kind": "BASELINE",
            "metric_source_hash": baseline_negative_source.sha256,
            "metric_id": negative_metric.metric_id,
            "value": negative_metric.baseline_value,
            "input_descriptor": "mock-only-equal",
            "tool_descriptor": "mock-only-equal",
            "budget_descriptor": "mock-only-equal",
            "output_contract_descriptor": "mock-only-equal",
        },
    )
    hc_negative_regression = _linked_fixture_ref(
        "HC_REGRESSION_REPORT",
        "hc-regression-report:regression-detected",
        hc_negative_task,
        hc_negative_packet,
        hc_negative_prereg,
        hc_negative_snapshot,
        baseline_negative_snapshot,
        payload=_hc_report_fixture_payload(
            negative_metric,
            tuple(item.sha256 for item in hc_negative_parity),
            hc_negative_rule.sha256,
            hc_negative_snapshot.sha256,
            baseline_negative_snapshot.sha256,
        ),
    )
    hc_negative_binding = _linked_fixture_ref(
        "EVALUATION_EVIDENCE_BINDING",
        "hc-evidence-binding:regression-detected",
        hc_negative_task,
        hc_negative_packet,
        hc_negative_regression,
        hc_negative_source,
        baseline_negative_source,
        payload={
            "subject": "HC_REGRESSION",
            "recomputed_disposition": RegressionDisposition.REGRESSION_DETECTED.value,
            "status": "PASS",
        },
    )

    low_negative_task = _linked_fixture_ref(
        "EVALUATOR_TASK", "low-recognition-evaluator-task:compromised"
    )
    low_negative_source = _linked_fixture_ref(
        "LOW_RECOGNITION_EXPOSURE_SOURCE",
        "low-recognition-source:compromised",
        low_negative_task,
        evaluator,
        at17,
        payload=_low_exposure_fixture_payload(compromised=True),
    )
    low_negative_packet = _linked_fixture_ref(
        "EVALUATOR_INPUT_PACKET",
        "low-recognition-evaluator-input-packet:compromised",
        low_negative_task,
        low_negative_source,
        evaluator,
        at17,
        critical_evidence,
        scenario_set,
        challenger_gate,
    )
    low_negative_source_edge = _fixture_ref(
        "PERSISTENCE_LINEAGE_EDGE",
        f"{low_negative_source.sha256}:evaluator_packet<-{low_negative_packet.sha256}@S8",
    )
    low_negative_policy = _linked_fixture_ref(
        "LOW_RECOGNITION_VISIBILITY_POLICY",
        "low-recognition-policy:compromised",
        low_negative_task,
        low_negative_packet,
    )
    low_negative_snapshot = _linked_fixture_ref(
        "LOW_RECOGNITION_EXPOSURE_SNAPSHOT",
        "low-recognition-snapshot:compromised",
        low_negative_task,
        low_negative_packet,
        low_negative_policy,
        low_negative_source,
        payload=_low_snapshot_fixture_payload(
            compromised=True,
            source_hash=low_negative_source.sha256,
        ),
    )
    low_negative_recognition = _linked_fixture_ref(
        "LOW_RECOGNITION_GATE",
        "low-recognition-gate:compromised-block",
        low_negative_task,
        low_negative_packet,
        low_negative_policy,
        low_negative_snapshot,
        payload=_low_gate_fixture_payload(
            compromised=True,
            source_hash=low_negative_source.sha256,
            snapshot_hash=low_negative_snapshot.sha256,
        ),
    )
    low_negative_binding = _linked_fixture_ref(
        "EVALUATION_EVIDENCE_BINDING",
        "low-recognition-evidence-binding:compromised",
        low_negative_task,
        low_negative_packet,
        low_negative_recognition,
        low_negative_source,
        payload={
            "subject": "LOW_RECOGNITION",
            "recomputed_status": LowRecognitionGateStatus.BLOCK.value,
            "status": "PASS",
        },
    )
    safety_block_admission_model, safety_block_result_model = _research_safety_fixture(
        case_id="negative:research-safety-block",
        fixture_label="block",
        blocked=True,
        world_state_hash=world_state.sha256,
        causal_graph_hash=causal_graph.sha256,
        critical_detection_hash=critical_detection.sha256,
        critical_review_plan_hash=critical_plan.sha256,
    )
    safety_block_admission_payload = cast(
        dict[str, object],
        safety_block_admission_model.model_dump(mode="json", exclude_none=True),
    )
    safety_block_payload = cast(
        dict[str, object],
        safety_block_result_model.model_dump(mode="json", exclude_none=True),
    )
    safety_block_admission = _linked_fixture_ref(
        "RESEARCH_SAFETY_ADMISSION",
        f"research-safety-admission:block:{safety_block_admission_model.admission_hash}",
        world_state,
        causal_graph,
        critical_detection,
        critical_plan,
        payload=safety_block_admission_payload,
    )
    safety_block = _linked_fixture_ref(
        "RESEARCH_SAFETY_RESULT",
        f"research-safety-result:block:{safety_block_result_model.result_hash}",
        safety_block_admission,
        world_state,
        causal_graph,
        critical_detection,
        critical_plan,
        payload=safety_block_payload,
    )
    challenger_block_task_model, challenger_block_packet_model = _challenger_parent_fixture(
        case_id="negative:challenger-block",
        fixture_label="block",
        critical_review_plan_hash=critical_plan.sha256,
        controller_c_output_hash=controller_c_output.sha256,
        scenario_set_hash=scenario_set.sha256,
        resimulation_plan_hash=resimulation_plan.sha256,
        resimulation_result_hash=resimulation.sha256,
        at17_evidence_hash=at17.sha256,
        resulting_world_state_hash=resulting_world_state.sha256,
        resulting_causal_graph_hash=resulting_causal_graph.sha256,
        resimulation_safety_result_hash=resim_safety_result.sha256,
    )
    challenger_block_task = _linked_fixture_ref(
        "CHALLENGER_TASK",
        f"challenger-task:block:{challenger_block_task_model.task_hash}",
        critical_plan,
        controller_c_output,
        scenario_set,
        resimulation_plan,
        resimulation,
        at17,
        resulting_world_state,
        resulting_causal_graph,
        resim_safety_result,
        payload=cast(
            dict[str, object],
            challenger_block_task_model.model_dump(mode="json", exclude_none=True),
        ),
    )
    challenger_block_packet = _linked_fixture_ref(
        "CHALLENGER_PACKET",
        f"challenger-packet:block:{challenger_block_packet_model.packet_hash}",
        challenger_block_task,
        critical_plan,
        controller_c_output,
        scenario_set,
        resimulation_plan,
        resimulation,
        at17,
        resulting_world_state,
        resulting_causal_graph,
        payload=cast(
            dict[str, object],
            challenger_block_packet_model.model_dump(mode="json", exclude_none=True),
        ),
    )
    challenger_block_raw_output = _linked_fixture_ref("RAW_OUTPUT", "challenger-raw-output:block")
    (
        challenger_block_finding_models,
        challenger_block_response_model,
        challenger_block_satisfaction_model,
        challenger_block_gate_model,
    ) = _challenger_fixture(
        case_id="negative:challenger-block",
        fixture_label="block",
        blocking=True,
        task_hash=challenger_block_task.sha256,
        packet_hash=challenger_block_packet.sha256,
        critical_review_plan_hash=critical_plan.sha256,
        source_hash=scenario_set.sha256,
        raw_output_hash=challenger_block_raw_output.sha256,
    )
    challenger_block_findings = tuple(
        _linked_fixture_ref(
            "CHALLENGER_FINDING",
            f"challenger-finding:block:{finding.finding_hash}",
            challenger_block_task,
            challenger_block_packet,
            scenario_set,
            payload=cast(
                dict[str, object],
                finding.model_dump(mode="json", exclude_none=True),
            ),
        )
        for finding in challenger_block_finding_models
    )
    challenger_block_response = _linked_fixture_ref(
        "CHALLENGER_RESPONSE",
        f"challenger-response:block:{challenger_block_response_model.response_hash}",
        challenger_block_task,
        challenger_block_packet,
        challenger_block_raw_output,
        *challenger_block_findings,
        payload=cast(
            dict[str, object],
            challenger_block_response_model.model_dump(mode="json", exclude_none=True),
        ),
    )
    challenger_block_satisfaction = _linked_fixture_ref(
        "CHALLENGER_SATISFACTION",
        (f"challenger-satisfaction:block:{challenger_block_satisfaction_model.satisfaction_hash}"),
        critical_plan,
        challenger_block_task,
        challenger_block_packet,
        challenger_block_response,
        *challenger_block_findings,
        payload=cast(
            dict[str, object],
            challenger_block_satisfaction_model.model_dump(mode="json", exclude_none=True),
        ),
    )
    challenger_block = _linked_fixture_ref(
        "CHALLENGER_GATE",
        f"challenger-gate:block:{challenger_block_gate_model.gate_result_hash}",
        challenger_block_response,
        challenger_block_satisfaction,
        challenger_block_findings[0],
        payload=cast(
            dict[str, object],
            challenger_block_gate_model.model_dump(mode="json", exclude_none=True),
        ),
    )
    positive_evidence = (
        _freeze_observed_evidence(
            safety_admission,
            cast(
                dict[str, object],
                safety_admission_model.model_dump(mode="json", exclude_none=True),
            ),
        ),
        _freeze_observed_evidence(
            safety_result,
            cast(
                dict[str, object],
                safety_result_model.model_dump(mode="json", exclude_none=True),
            ),
        ),
        _freeze_observed_evidence(
            challenger_task,
            cast(
                dict[str, object],
                challenger_task_model.model_dump(mode="json", exclude_none=True),
            ),
        ),
        _freeze_observed_evidence(
            challenger_packet,
            cast(
                dict[str, object],
                challenger_packet_model.model_dump(mode="json", exclude_none=True),
            ),
        ),
        *(
            _freeze_observed_evidence(
                artifact,
                cast(
                    dict[str, object],
                    finding.model_dump(mode="json", exclude_none=True),
                ),
            )
            for artifact, finding in zip(
                challenger_findings,
                challenger_finding_models,
                strict=True,
            )
        ),
        _freeze_observed_evidence(
            challenger_response,
            cast(
                dict[str, object],
                challenger_response_model.model_dump(mode="json", exclude_none=True),
            ),
        ),
        _freeze_observed_evidence(
            challenger_satisfaction,
            cast(
                dict[str, object],
                challenger_satisfaction_model.model_dump(mode="json", exclude_none=True),
            ),
        ),
        _freeze_observed_evidence(
            challenger_gate,
            cast(
                dict[str, object],
                challenger_gate_model.model_dump(mode="json", exclude_none=True),
            ),
        ),
        *(
            _freeze_observed_evidence(
                artifact,
                {
                    "dimension": dimension.value,
                    "hc_descriptor": "mock-only-equal",
                    "baseline_descriptor": "mock-only-equal",
                },
            )
            for dimension, artifact in zip(
                RegressionParityDimension,
                hc_parity,
                strict=True,
            )
        ),
        _freeze_observed_evidence(
            hc_rule,
            {
                "metric_id": positive_metric.metric_id,
                "direction": positive_metric.direction.value,
                "noninferiority_margin": positive_metric.noninferiority_margin,
            },
        ),
        _freeze_observed_evidence(
            hc_source,
            {
                "track_kind": "HC",
                "metric_id": positive_metric.metric_id,
                "value": positive_metric.hc_value,
                "input_descriptor": "mock-only-equal",
                "tool_descriptor": "mock-only-equal",
                "budget_descriptor": "mock-only-equal",
                "output_contract_descriptor": "mock-only-equal",
            },
        ),
        _freeze_observed_evidence(
            baseline_source,
            {
                "track_kind": "BASELINE",
                "metric_id": positive_metric.metric_id,
                "value": positive_metric.baseline_value,
                "input_descriptor": "mock-only-equal",
                "tool_descriptor": "mock-only-equal",
                "budget_descriptor": "mock-only-equal",
                "output_contract_descriptor": "mock-only-equal",
            },
        ),
        _freeze_observed_evidence(
            hc_snapshot,
            {
                "track_kind": "HC",
                "metric_source_hash": hc_source.sha256,
                "metric_id": positive_metric.metric_id,
                "value": positive_metric.hc_value,
                "input_descriptor": "mock-only-equal",
                "tool_descriptor": "mock-only-equal",
                "budget_descriptor": "mock-only-equal",
                "output_contract_descriptor": "mock-only-equal",
            },
        ),
        _freeze_observed_evidence(
            baseline_snapshot,
            {
                "track_kind": "BASELINE",
                "metric_source_hash": baseline_source.sha256,
                "metric_id": positive_metric.metric_id,
                "value": positive_metric.baseline_value,
                "input_descriptor": "mock-only-equal",
                "tool_descriptor": "mock-only-equal",
                "budget_descriptor": "mock-only-equal",
                "output_contract_descriptor": "mock-only-equal",
            },
        ),
        _freeze_observed_evidence(
            hc_regression,
            _hc_report_fixture_payload(
                positive_metric,
                tuple(item.sha256 for item in hc_parity),
                hc_rule.sha256,
                hc_snapshot.sha256,
                baseline_snapshot.sha256,
            ),
        ),
        _freeze_observed_evidence(
            low_source,
            _low_exposure_fixture_payload(compromised=False),
        ),
        _freeze_observed_evidence(
            low_snapshot,
            _low_snapshot_fixture_payload(
                compromised=False,
                source_hash=low_source.sha256,
            ),
        ),
        _freeze_observed_evidence(
            low_recognition,
            _low_gate_fixture_payload(
                compromised=False,
                source_hash=low_source.sha256,
                snapshot_hash=low_snapshot.sha256,
            ),
        ),
    )
    capability_evidence = (
        _freeze_observed_evidence(
            capability_gap,
            {"capability_gap_id": "capability-gap:fixture", "route": None},
        ),
    )
    safety_evidence = (
        _freeze_observed_evidence(
            safety_block_admission,
            safety_block_admission_payload,
        ),
        _freeze_observed_evidence(safety_block, safety_block_payload),
    )
    challenger_evidence = (
        _freeze_observed_evidence(
            challenger_block_task,
            cast(
                dict[str, object],
                challenger_block_task_model.model_dump(mode="json", exclude_none=True),
            ),
        ),
        _freeze_observed_evidence(
            challenger_block_packet,
            cast(
                dict[str, object],
                challenger_block_packet_model.model_dump(mode="json", exclude_none=True),
            ),
        ),
        *(
            _freeze_observed_evidence(
                artifact,
                cast(
                    dict[str, object],
                    finding.model_dump(mode="json", exclude_none=True),
                ),
            )
            for artifact, finding in zip(
                challenger_block_findings,
                challenger_block_finding_models,
                strict=True,
            )
        ),
        _freeze_observed_evidence(
            challenger_block_response,
            cast(
                dict[str, object],
                challenger_block_response_model.model_dump(mode="json", exclude_none=True),
            ),
        ),
        _freeze_observed_evidence(
            challenger_block_satisfaction,
            cast(
                dict[str, object],
                challenger_block_satisfaction_model.model_dump(mode="json", exclude_none=True),
            ),
        ),
        _freeze_observed_evidence(
            challenger_block,
            cast(
                dict[str, object],
                challenger_block_gate_model.model_dump(mode="json", exclude_none=True),
            ),
        ),
    )
    hc_negative_evidence = (
        *(
            _freeze_observed_evidence(
                artifact,
                {
                    "dimension": dimension.value,
                    "hc_descriptor": "mock-only-equal",
                    "baseline_descriptor": "mock-only-equal",
                },
            )
            for dimension, artifact in zip(
                RegressionParityDimension,
                hc_negative_parity,
                strict=True,
            )
        ),
        _freeze_observed_evidence(
            hc_negative_rule,
            {
                "metric_id": negative_metric.metric_id,
                "direction": negative_metric.direction.value,
                "noninferiority_margin": negative_metric.noninferiority_margin,
            },
        ),
        _freeze_observed_evidence(
            hc_negative_source,
            {
                "track_kind": "HC",
                "metric_id": negative_metric.metric_id,
                "value": negative_metric.hc_value,
                "input_descriptor": "mock-only-equal",
                "tool_descriptor": "mock-only-equal",
                "budget_descriptor": "mock-only-equal",
                "output_contract_descriptor": "mock-only-equal",
            },
        ),
        _freeze_observed_evidence(
            baseline_negative_source,
            {
                "track_kind": "BASELINE",
                "metric_id": negative_metric.metric_id,
                "value": negative_metric.baseline_value,
                "input_descriptor": "mock-only-equal",
                "tool_descriptor": "mock-only-equal",
                "budget_descriptor": "mock-only-equal",
                "output_contract_descriptor": "mock-only-equal",
            },
        ),
        _freeze_observed_evidence(
            hc_negative_snapshot,
            {
                "track_kind": "HC",
                "metric_source_hash": hc_negative_source.sha256,
                "metric_id": negative_metric.metric_id,
                "value": negative_metric.hc_value,
                "input_descriptor": "mock-only-equal",
                "tool_descriptor": "mock-only-equal",
                "budget_descriptor": "mock-only-equal",
                "output_contract_descriptor": "mock-only-equal",
            },
        ),
        _freeze_observed_evidence(
            baseline_negative_snapshot,
            {
                "track_kind": "BASELINE",
                "metric_source_hash": baseline_negative_source.sha256,
                "metric_id": negative_metric.metric_id,
                "value": negative_metric.baseline_value,
                "input_descriptor": "mock-only-equal",
                "tool_descriptor": "mock-only-equal",
                "budget_descriptor": "mock-only-equal",
                "output_contract_descriptor": "mock-only-equal",
            },
        ),
        _freeze_observed_evidence(
            hc_negative_regression,
            _hc_report_fixture_payload(
                negative_metric,
                tuple(item.sha256 for item in hc_negative_parity),
                hc_negative_rule.sha256,
                hc_negative_snapshot.sha256,
                baseline_negative_snapshot.sha256,
            ),
        ),
    )
    low_negative_evidence = (
        _freeze_observed_evidence(
            low_negative_source,
            _low_exposure_fixture_payload(compromised=True),
        ),
        _freeze_observed_evidence(
            low_negative_snapshot,
            _low_snapshot_fixture_payload(
                compromised=True,
                source_hash=low_negative_source.sha256,
            ),
        ),
        _freeze_observed_evidence(
            low_negative_recognition,
            _low_gate_fixture_payload(
                compromised=True,
                source_hash=low_negative_source.sha256,
                snapshot_hash=low_negative_snapshot.sha256,
            ),
        ),
    )
    positive_facts = _freeze_observed_stop_facts(
        hc_metric_facts=(positive_metric,),
        hc_disposition=RegressionDisposition.NO_REGRESSION_DETECTED,
        low_status=LowRecognitionGateStatus.PASS,
        evidence_artifact_hashes=(
            safety_result.sha256,
            hc_regression.sha256,
            low_recognition.sha256,
        ),
    )
    capability_facts = _freeze_observed_stop_facts(
        capability_gap_id="capability-gap:fixture",
        evidence_artifact_hashes=(capability_gap.sha256,),
    )
    safety_facts = _freeze_observed_stop_facts(
        research_safety_blocked=True,
        evidence_artifact_hashes=(safety_block.sha256,),
    )
    challenger_facts = _freeze_observed_stop_facts(
        challenger_blocked=True,
        evidence_artifact_hashes=(challenger_block.sha256,),
    )
    hc_negative_facts = _freeze_observed_stop_facts(
        hc_metric_facts=(negative_metric,),
        hc_disposition=RegressionDisposition.REGRESSION_DETECTED,
        evidence_artifact_hashes=(hc_negative_regression.sha256,),
    )
    low_negative_facts = _freeze_observed_stop_facts(
        low_invalid_facts=(LowRecognitionInvalidFact.ENTITY_SYSTEM_IDENTITY_EXPOSED,),
        low_status=LowRecognitionGateStatus.BLOCK,
        evidence_artifact_hashes=(low_negative_recognition.sha256,),
    )
    cases = (
        _freeze_case(
            "positive:authorized-boundary",
            TrialCasePolarity.POSITIVE,
            _BOOTSTRAP_CONTROL_STATES,
            TrialStopCondition.AUTHORIZED_BOUNDARY_REACHED,
            "canonical positive structural fixture reached ADVERSARIAL_REVIEW",
            positive_facts,
            positive_evidence,
            positive_closure,
        ),
        _freeze_case(
            "negative:capability-gap",
            TrialCasePolarity.NEGATIVE,
            _BOOTSTRAP_CONTROL_STATES[:7],
            TrialStopCondition.CAPABILITY_GAP,
            "canonical structural fixture preserved a required Capability Gap",
            capability_facts,
            capability_evidence,
            (*capability_prefix, capability_routing_plan, capability_gap),
            (capability_gap,),
        ),
        _freeze_case(
            "negative:research-safety-block",
            TrialCasePolarity.NEGATIVE,
            _BOOTSTRAP_CONTROL_STATES[:13],
            TrialStopCondition.RESEARCH_SAFETY_BLOCK,
            "canonical structural fixture preserved Research Safety BLOCK",
            safety_facts,
            safety_evidence,
            (*research_safety_closure[:-2], safety_block_admission, safety_block),
            (safety_block,),
            unresolved_condition_refs=("research-safety:block",),
        ),
        _freeze_case(
            "negative:challenger-block",
            TrialCasePolarity.NEGATIVE,
            _BOOTSTRAP_CONTROL_STATES,
            TrialStopCondition.CHALLENGER_BLOCK,
            "canonical structural fixture preserved Challenger BLOCK",
            challenger_facts,
            challenger_evidence,
            (
                *challenger_closure[:-12],
                challenger_block_task,
                challenger_block_packet,
                challenger_block_raw_output,
                *challenger_block_findings,
                challenger_block_response,
                challenger_block_satisfaction,
                challenger_block,
            ),
            (challenger_block,),
            dissent_refs=("challenger:dissent",),
            unresolved_condition_refs=("challenger:block",),
        ),
        _freeze_case(
            "negative:hc-regression-detected",
            TrialCasePolarity.NEGATIVE,
            _BOOTSTRAP_CONTROL_STATES,
            TrialStopCondition.HC_REGRESSION_DETECTED,
            "canonical structural fixture preserved evidence-bound HC Regression",
            hc_negative_facts,
            hc_negative_evidence,
            (
                *challenger_closure,
                evaluator_task,
                evaluator_packet,
                evaluator_finding,
                evaluator,
                hc_negative_task,
                hc_negative_run_manifest,
                baseline_negative_run_manifest,
                hc_negative_source,
                baseline_negative_source,
                hc_negative_packet,
                hc_negative_source_edge,
                baseline_negative_source_edge,
                *hc_negative_parity,
                hc_negative_rule,
                hc_negative_prereg,
                hc_negative_snapshot,
                baseline_negative_snapshot,
                hc_negative_regression,
                hc_negative_binding,
            ),
            (hc_negative_regression,),
            unresolved_condition_refs=("hc-regression:detected",),
        ),
        _freeze_case(
            "negative:low-recognition-compromised",
            TrialCasePolarity.NEGATIVE,
            _BOOTSTRAP_CONTROL_STATES,
            TrialStopCondition.LOW_RECOGNITION_COMPROMISED,
            "canonical structural fixture preserved Low-recognition compromise",
            low_negative_facts,
            low_negative_evidence,
            (
                *challenger_closure,
                evaluator_task,
                evaluator_packet,
                evaluator_finding,
                evaluator,
                low_negative_task,
                low_negative_source,
                low_negative_packet,
                low_negative_source_edge,
                low_negative_policy,
                low_negative_snapshot,
                low_negative_recognition,
                low_negative_binding,
            ),
            (low_negative_recognition,),
            unresolved_condition_refs=("low-recognition:compromised",),
        ),
    )
    additional = (
        _freeze_deferred_fixture(
            "additional:model-output-invalid",
            TrialStopCondition.MODEL_OUTPUT_INVALID,
            exercise_owner="TRIAL-SBX5",
        ),
        _freeze_deferred_fixture(
            "additional:infrastructure-failure",
            TrialStopCondition.INFRASTRUCTURE_FAILURE,
            exercise_owner="TRIAL-SBX5",
        ),
        _freeze_deferred_fixture(
            "additional:checksum-address-tamper",
            TrialStopCondition.INPUT_INVALID,
            exercise_owner="TRIAL-SBX1-VERIFICATION",
            phase=TrialStopPhase.INPUT,
        ),
        _freeze_deferred_fixture(
            "additional:persistence-duplicate",
            TrialStopCondition.ARTIFACT_INTEGRITY_FAILURE,
            exercise_owner="TRIAL-SBX5",
            phase=TrialStopPhase.PERSISTENCE,
        ),
        _freeze_deferred_fixture(
            "additional:resource-ceiling",
            TrialStopCondition.RESOURCE_LIMIT_REACHED,
            exercise_owner="TRIAL-SBX4-METER-PROBE",
            resource_stage_call_deltas=(1, 16),
        ),
        _freeze_deferred_fixture(
            "additional:operator-abort",
            TrialStopCondition.OPERATOR_ABORTED,
            exercise_owner="TRIAL-SBX5",
        ),
        _freeze_deferred_fixture(
            "additional:audit-bundle-tamper",
            TrialStopCondition.ARTIFACT_INTEGRITY_FAILURE,
            exercise_owner="TRIAL-SBX3-VERIFICATION",
            phase=TrialStopPhase.AUDIT_EXPORT,
        ),
        _freeze_deferred_fixture(
            "additional:replay-mismatch",
            TrialStopCondition.ARTIFACT_INTEGRITY_FAILURE,
            exercise_owner="TRIAL-SBX4-COMPARATOR",
        ),
        _freeze_deferred_fixture(
            "additional:cleanup-refusal-non-trial-target",
            TrialStopCondition.INFRASTRUCTURE_FAILURE,
            exercise_owner="TRIAL-SBX5",
            phase=TrialStopPhase.CLEANUP,
        ),
    )
    seed = TrialCanonicalCasePack("human-cos:trial-sbx4", "trial-sbx4-v1", cases, additional, "")
    pack = TrialCanonicalCasePack(
        seed.pack_id,
        seed.pack_version,
        seed.cases,
        seed.additional_fixtures,
        canonical_document_sha256(_pack_document(seed)),
    )
    pack.assert_integrity()
    return pack


_CANONICAL_CASE_PACK_SHA256 = "4621606a5dd6ad59b1bfa9a758a34091eec87f10e6af5d62245d1be2c4c3b2f9"


def _load_canonical_case_pack() -> TrialCanonicalCasePack:
    """Rebuild the code-owned pack instead of trusting a caller-rebindable export."""

    pack = _build_canonical_case_pack()
    if pack.pack_hash != _CANONICAL_CASE_PACK_SHA256:
        raise TrialCasePackError(
            f"package-owned canonical case-pack identity drifted: {pack.pack_hash}"
        )
    return pack


CANONICAL_TRIAL_CASE_PACK = _load_canonical_case_pack()


def _admit_canonical_case(
    *,
    case: TrialCanonicalCase,
    pack: TrialCanonicalCasePack,
    bundle: VerifiedTrialBundle,
    root_admission: _AuthenticatedCanonicalAdmission,
    root_environment: TrialEnvironmentAdmission,
    frozen_at: datetime,
) -> TrialCanonicalCaseAdmission:
    """Derive one package-owned CANONICAL_CASE identity from the admitted root."""

    root_admission.assert_integrity()
    case.assert_integrity()
    manifest_document = bundle.manifest.model_dump(
        mode="python", exclude={"manifest_hash"}, exclude_none=True
    )
    manifest_document.update(
        {
            "trial_id": f"{bundle.manifest.trial_id}:sbx4:{case.case_key}",
            "case_id": case.case_key,
            "frozen_at": frozen_at,
        }
    )
    manifest = freeze_trial_manifest(TrialManifestPayload.model_validate(manifest_document))
    registry_entry_id = f"{pack.pack_id}:{pack.pack_hash}:{case.case_hash}"
    derived_case_sha256 = canonical_document_sha256(
        {
            "case_id": case.case_key,
            "case_revision": manifest.case_revision,
            "case_mode": manifest.case_mode.value,
            "protocol_version": manifest.protocol_version,
            "canonical_case_hash": case.case_hash,
            "root_semantic_fingerprint": root_admission.semantic_fingerprint,
        }
    )
    case_derivation_hash = canonical_document_sha256(
        {
            "root_canonical_admission_hash": root_admission.record.canonical_admission_hash,
            "root_bundle_receipt_hash": root_admission.bundle_receipt_hash,
            "root_detached_input_address": root_admission.record.detached_input_address,
            "root_payload_documents_sha256": root_admission.payload_documents_sha256,
            "root_semantic_fingerprint": root_admission.semantic_fingerprint,
            "pack_hash": pack.pack_hash,
            "case_hash": case.case_hash,
            "derived_manifest": manifest.model_dump(
                mode="json", exclude={"manifest_hash"}, exclude_none=True
            ),
            "derived_case_sha256": derived_case_sha256,
        }
    )
    derived_input_address = canonical_document_sha256(
        {
            "case_derivation_hash": case_derivation_hash,
            "manifest_hash": manifest.manifest_hash,
            "case_sha256": derived_case_sha256,
        }
    )
    canonical = freeze_trial_canonical_admission(
        TrialCanonicalAdmissionPayload(
            admission_id=f"canonical:sbx4:{case.case_key}:{bundle.attempt.attempt_id}",
            bundle_receipt_hash=case_derivation_hash,
            detached_input_address=derived_input_address,
            registry_entry_id=registry_entry_id,
            purpose=TrialCanonicalPurpose.CANONICAL_CASE,
            case_id=case.case_key,
            case_revision=manifest.case_revision,
            case_mode=manifest.case_mode,
            source_commit_sha=manifest.source_commit_sha,
            protocol_version=manifest.protocol_version,
            pre_freeze_admitted=True,
            status=TrialCanonicalAdmissionStatus.PASS,
            reasons=(),
            frozen_at=frozen_at,
        )
    )
    environment_document = root_environment.model_dump(
        mode="python", exclude={"environment_admission_hash"}, exclude_none=True
    )
    environment_document.update(
        {
            "admission_id": f"environment:sbx4:{case.case_key}:{bundle.attempt.attempt_id}",
            "manifest_hash": manifest.manifest_hash,
            "canonical_admission_hash": canonical.canonical_admission_hash,
            "canonical_registry_entry_id": registry_entry_id,
            "detached_input_address": derived_input_address,
            "frozen_at": frozen_at,
        }
    )
    environment = freeze_trial_environment_admission(
        TrialEnvironmentAdmissionPayload.model_validate(environment_document)
    )
    assert_environment_admission_binding(bundle.attempt, manifest, canonical, environment)
    seed = TrialCanonicalCaseAdmission(
        case.case_key,
        case.case_hash,
        pack.pack_hash,
        root_admission.record.canonical_admission_hash,
        bundle.attempt.attempt_receipt_hash,
        root_admission.bundle_receipt_hash,
        root_admission.record.detached_input_address,
        root_admission.payload_documents_sha256,
        root_admission.semantic_fingerprint,
        derived_case_sha256,
        case_derivation_hash,
        manifest,
        canonical,
        environment,
        "",
    )
    admission = TrialCanonicalCaseAdmission(
        seed.case_key,
        seed.case_hash,
        seed.pack_hash,
        seed.root_canonical_admission_hash,
        seed.attempt_receipt_hash,
        seed.root_bundle_receipt_hash,
        seed.root_detached_input_address,
        seed.root_payload_documents_sha256,
        seed.root_semantic_fingerprint,
        seed.derived_case_sha256,
        seed.case_derivation_hash,
        seed.manifest,
        seed.canonical_admission,
        seed.environment,
        canonical_document_sha256(_case_admission_document(seed)),
    )
    admission.assert_integrity(
        root_admission=root_admission,
        root_bundle=bundle,
        root_environment=root_environment,
    )
    return admission


def _execute_replay_plan(
    *,
    plan: TrialReplayPlan,
    bundle: VerifiedTrialBundle,
    root_admission: _AuthenticatedCanonicalAdmission,
    root_environment: TrialEnvironmentAdmission,
    case_admission: TrialCanonicalCaseAdmission,
    recorded_at: datetime,
) -> tuple[TrialStop, TrialResult]:
    """Replay structural facts without receiving an expectation or oracle."""

    plan.assert_integrity()
    case_admission.assert_integrity(
        root_admission=root_admission,
        root_bundle=bundle,
        root_environment=root_environment,
    )
    matching = tuple(
        case
        for case in _load_canonical_case_pack().cases
        if (case.case_key, case.replay_plan.plan_hash) == (plan.case_key, plan.plan_hash)
    )
    if len(matching) != 1 or matching[0].case_hash != case_admission.case_hash:
        raise TrialCasePackError("replay requires the exact package-owned case plan")
    manifest = case_admission.manifest
    environment = case_admission.environment
    if plan.case_key != case_admission.case_key:
        raise TrialCasePackError("replay plan differs from its canonical case admission")
    if plan.case_mode is not manifest.case_mode:
        raise TrialCasePackError("case-plan mode differs from admitted Manifest")
    observed_condition = _derive_stop_from_evidence(plan.observed_evidence)
    if stop_outcome_for(observed_condition) not in manifest.allowed_terminal_outcomes:
        raise TrialCasePackError("observed fixture outcome is absent from the admitted Manifest")
    ledger = TrialStopLedger(
        attempt_receipt_hash=bundle.attempt.attempt_receipt_hash,
        manifest=manifest,
        environment=environment,
        clock=lambda: 0.0,
    )
    meter = TrialResourceMeter(manifest, clock=lambda: 0.0)
    for state in plan.runtime_states:
        resource_stop = meter.record(stage_calls=1, elapsed_seconds=0.0)
        if resource_stop is not None:
            ledger.signal(resource_stop)
            break
        ledger.record_position(
            TrialRuntimePosition(
                mode=manifest.case_mode,
                state=state,
                case_revision=manifest.case_revision,
            ),
            controlling_ref=f"sbx4:{plan.case_key}:{state.value}",
            recorded_at=recorded_at,
        )
    else:
        ledger.record_artifacts(plan.produced_artifacts)
        ledger.signal(
            TrialStopSignal(
                condition=observed_condition,
                phase=plan.terminal_phase,
                reason=plan.terminal_reason,
                controlling_artifact_refs=plan.controlling_artifact_refs,
            )
        )
    observed_acceptance = (
        TrialCapabilityAcceptance.PASS
        if ledger.controlling_signal().condition is observed_condition
        else TrialCapabilityAcceptance.FAIL
    )
    return ledger.freeze_terminal(
        stop_id=f"stop:sbx4:{plan.case_key}:{bundle.attempt.attempt_id}",
        result_id=f"result:sbx4:{plan.case_key}:{bundle.attempt.attempt_id}",
        trial_capability_acceptance=observed_acceptance,
        substantive_case_outcome=None,
        limitations=(
            "SBX4 is deterministic structural replay only; no cognitive stage, model, "
            "provider, Final Synthesis, publication, or reality execution is authorized.",
        ),
        dissent_refs=plan.dissent_refs,
        unresolved_condition_refs=plan.unresolved_condition_refs,
        stopped_at=recorded_at,
    )


def _compare_observed(
    expectation: TrialCaseExpectation,
    result: TrialResult,
) -> TrialCaseAcceptance:
    """Compare only after observed terminal facts have frozen."""

    expectation.assert_integrity()
    result.assert_integrity()
    observed_states = tuple(step.position.state for step in result.runtime_trajectory)
    observed_terminal = (
        result.final_runtime_position.state if result.final_runtime_position is not None else None
    )
    checks = (
        ("outcome", result.outcome, expectation.expected_outcome),
        ("stop_condition", result.stop_condition, expectation.expected_stop_condition),
        ("stop_phase", result.stop_phase, expectation.expected_stop_phase),
        ("runtime_states", observed_states, expectation.expected_runtime_states),
        ("terminal_state", observed_terminal, expectation.expected_terminal_state),
        ("required_artifacts", result.produced_artifacts, expectation.required_artifacts),
        (
            "controlling_artifact_refs",
            result.controlling_artifact_refs,
            expectation.required_controlling_artifact_refs,
        ),
        ("dissent_refs", result.dissent_refs, expectation.expected_dissent_refs),
        (
            "unresolved_condition_refs",
            result.unresolved_condition_refs,
            expectation.expected_unresolved_condition_refs,
        ),
        (
            "cleanup_disposition",
            result.cleanup_disposition,
            expectation.expected_cleanup_disposition,
        ),
        (
            "capability_acceptance",
            result.trial_capability_acceptance,
            expectation.expected_capability_acceptance,
        ),
    )
    mismatches = [name for name, observed, expected in checks if observed != expected]
    observed_artifact_kinds = {
        item.kind for item in (*result.produced_artifacts, *result.controlling_artifact_refs)
    }
    if observed_artifact_kinds.intersection(expectation.forbidden_artifact_kinds):
        mismatches.append("forbidden_artifacts")
    frozen_mismatches = tuple(mismatches)
    acceptance = TrialCaseAcceptance(
        accepted=not frozen_mismatches,
        mismatches=frozen_mismatches,
        expectation_hash=expectation.expectation_hash,
        observed_result_hash=result.result_hash,
        acceptance_hash="",
    )
    acceptance = TrialCaseAcceptance(
        accepted=acceptance.accepted,
        mismatches=acceptance.mismatches,
        expectation_hash=acceptance.expectation_hash,
        observed_result_hash=acceptance.observed_result_hash,
        acceptance_hash=canonical_document_sha256(_acceptance_document(acceptance)),
    )
    acceptance.assert_integrity()
    return acceptance


def run_canonical_case_pack(
    *,
    bundle: VerifiedTrialBundle,
    canonical_admission: _AuthenticatedCanonicalAdmission,
    environment: TrialEnvironmentAdmission,
    recorded_at: datetime,
) -> TrialCasePackRun:
    """Run the exact package-owned SBX4 cases against an admitted Mock-only bundle."""

    _assert_bootstrap_admitted(bundle, canonical_admission, environment)
    _assert_frozen_structural_path(bundle)
    pack = _load_canonical_case_pack()
    pack.assert_integrity()
    records: list[TrialCaseReplayRecord] = []
    for case in pack.cases:
        case_admission = _admit_canonical_case(
            case=case,
            pack=pack,
            bundle=bundle,
            root_admission=canonical_admission,
            root_environment=environment,
            frozen_at=recorded_at,
        )
        stop, result = _execute_replay_plan(
            plan=case.replay_plan,
            bundle=bundle,
            root_admission=canonical_admission,
            root_environment=environment,
            case_admission=case_admission,
            recorded_at=recorded_at,
        )
        assert_trial_result_binding(
            bundle.attempt,
            case_admission.manifest,
            case_admission.environment,
            stop,
            result,
        )
        acceptance = _compare_observed(case.expectation, result)
        seed = TrialCaseReplayRecord(
            case.case_key, case.case_hash, case_admission, stop, result, acceptance, ""
        )
        record = TrialCaseReplayRecord(
            case.case_key,
            case.case_hash,
            case_admission,
            stop,
            result,
            acceptance,
            canonical_document_sha256(_record_document(seed)),
        )
        record.assert_integrity(
            root_admission=canonical_admission,
            root_bundle=bundle,
            root_environment=environment,
        )
        records.append(record)
    all_accepted = all(record.acceptance.accepted for record in records)
    run = TrialCasePackRun(
        pack.pack_id,
        pack.pack_hash,
        tuple(records),
        all_accepted,
        canonical_document_sha256(
            _run_document(
                TrialCasePackRun(pack.pack_id, pack.pack_hash, tuple(records), all_accepted, "")
            )
        ),
    )
    run.assert_integrity(
        root_admission=canonical_admission,
        root_bundle=bundle,
        root_environment=environment,
    )
    return run
