"""Immutable application contracts for the authorized TRIAL-SBX1 slice.

The trial layer is an orchestration/audit sidecar. It does not add Runtime states,
open executable edges, create Final Claim authority, or permit reality execution.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from human_cos.runtime.run import canonical_document_sha256
from human_cos.runtime.state_machine import CaseMode, RuntimeState

_HASH_PATTERN = r"^[a-f0-9]{64}$"
_COMMIT_PATTERN = r"^[a-f0-9]{40}$"
_AUTHORIZED_TERMINAL_STATE = RuntimeState.ADVERSARIAL_REVIEW
_AUTHORIZED_TRIAL_STATES = frozenset(
    {
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
    }
)


class TrialContractError(ValueError):
    """A trial object violates the authorized closed-sandbox boundary."""


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("TRIAL-SBX timestamps require timezone-aware datetimes")
    return value


def _assert_unique(values: tuple[str, ...], *, name: str) -> None:
    if len(values) != len(set(values)):
        raise TrialContractError(f"{name} must not contain duplicates")


def _assert_no_authority(
    *,
    final_synthesis_authorized: bool,
    final_claim_authorized: bool,
    seal_authorized: bool,
    publication_authorized: bool,
    reality_execution_authorized: bool,
    object_name: str,
) -> None:
    if (
        final_synthesis_authorized
        or final_claim_authorized
        or seal_authorized
        or publication_authorized
        or reality_execution_authorized
    ):
        raise TrialContractError(
            f"{object_name} grants no synthesis, claim, seal, publication, or execution authority"
        )


class _FrozenTrialModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class TrialAdapterLane(str, Enum):
    MOCK = "MOCK"


class TrialDataClass(str, Enum):
    SYNTHETIC = "SYNTHETIC"
    PUBLIC_HISTORICAL = "PUBLIC_HISTORICAL"
    SENSITIVE_PRIVATE = "SENSITIVE_PRIVATE"


class TrialAdmissionStatus(str, Enum):
    PASS = "PASS"
    REJECTED = "REJECTED"


class TrialCanonicalAdmissionStatus(str, Enum):
    PASS = "PASS"
    REJECTED = "REJECTED"


class TrialCanonicalPurpose(str, Enum):
    BOOTSTRAP_AUTOMATED_TEST = "BOOTSTRAP_AUTOMATED_TEST"
    CANONICAL_CASE = "CANONICAL_CASE"
    SBX5_REHEARSAL = "SBX5_REHEARSAL"


class TrialCapabilityAcceptance(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_EVALUATED = "NOT_EVALUATED"


class TrialAuditExportStatus(str, Enum):
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class TrialCleanupDisposition(str, Enum):
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    RETAINED_FOR_AUDIT = "RETAINED_FOR_AUDIT"


class TrialDocumentKind(str, Enum):
    TRIAL_MANIFEST = "TRIAL_MANIFEST"
    CASE = "CASE"
    EVIDENCE = "EVIDENCE"
    MODEL_PROFILE = "MODEL_PROFILE"
    EXPERT_FIXTURE = "EXPERT_FIXTURE"
    MOCK_OUTPUT = "MOCK_OUTPUT"
    EXPECTED_OUTCOME = "EXPECTED_OUTCOME"
    OTHER = "OTHER"


class TrialOutcome(str, Enum):
    COMPLETED_AT_AUTHORIZED_BOUNDARY = "COMPLETED_AT_AUTHORIZED_BOUNDARY"
    INVALID_INPUT = "INVALID_INPUT"
    INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"
    CAPABILITY_GAP = "CAPABILITY_GAP"
    RESEARCH_SAFETY_BLOCK = "RESEARCH_SAFETY_BLOCK"
    MODEL_OUTPUT_INVALID = "MODEL_OUTPUT_INVALID"
    INTEGRITY_FAILURE = "INTEGRITY_FAILURE"
    CHALLENGER_BLOCK = "CHALLENGER_BLOCK"
    HC_REGRESSION_DETECTED = "HC_REGRESSION_DETECTED"
    LOW_RECOGNITION_COMPROMISED = "LOW_RECOGNITION_COMPROMISED"
    UNSUPPORTED_AUTHORIZED_PATH = "UNSUPPORTED_AUTHORIZED_PATH"
    RESOURCE_LIMIT_REACHED = "RESOURCE_LIMIT_REACHED"
    OPERATOR_ABORTED = "OPERATOR_ABORTED"


class TrialStopPhase(str, Enum):
    INPUT = "INPUT"
    ADMISSION = "ADMISSION"
    EXECUTION = "EXECUTION"
    PERSISTENCE = "PERSISTENCE"
    AUDIT_EXPORT = "AUDIT_EXPORT"
    CLEANUP = "CLEANUP"


class TrialStopCondition(str, Enum):
    AUTHORIZED_BOUNDARY_REACHED = "AUTHORIZED_BOUNDARY_REACHED"
    INPUT_INVALID = "INPUT_INVALID"
    ENVIRONMENT_REJECTED = "ENVIRONMENT_REJECTED"
    INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"
    CAPABILITY_GAP = "CAPABILITY_GAP"
    RESEARCH_SAFETY_BLOCK = "RESEARCH_SAFETY_BLOCK"
    MODEL_OUTPUT_INVALID = "MODEL_OUTPUT_INVALID"
    ARTIFACT_INTEGRITY_FAILURE = "ARTIFACT_INTEGRITY_FAILURE"
    AT17_INTEGRATION_FAILURE = "AT17_INTEGRATION_FAILURE"
    CHALLENGER_BLOCK = "CHALLENGER_BLOCK"
    HC_REGRESSION_DETECTED = "HC_REGRESSION_DETECTED"
    LOW_RECOGNITION_COMPROMISED = "LOW_RECOGNITION_COMPROMISED"
    UNSUPPORTED_AUTHORIZED_PATH = "UNSUPPORTED_AUTHORIZED_PATH"
    RESOURCE_LIMIT_REACHED = "RESOURCE_LIMIT_REACHED"
    OPERATOR_ABORTED = "OPERATOR_ABORTED"


_STOP_OUTCOME: dict[TrialStopCondition, TrialOutcome] = {
    TrialStopCondition.AUTHORIZED_BOUNDARY_REACHED: (TrialOutcome.COMPLETED_AT_AUTHORIZED_BOUNDARY),
    TrialStopCondition.INPUT_INVALID: TrialOutcome.INVALID_INPUT,
    TrialStopCondition.ENVIRONMENT_REJECTED: TrialOutcome.INVALID_INPUT,
    TrialStopCondition.INFRASTRUCTURE_FAILURE: TrialOutcome.INFRASTRUCTURE_FAILURE,
    TrialStopCondition.CAPABILITY_GAP: TrialOutcome.CAPABILITY_GAP,
    TrialStopCondition.RESEARCH_SAFETY_BLOCK: TrialOutcome.RESEARCH_SAFETY_BLOCK,
    TrialStopCondition.MODEL_OUTPUT_INVALID: TrialOutcome.MODEL_OUTPUT_INVALID,
    TrialStopCondition.ARTIFACT_INTEGRITY_FAILURE: TrialOutcome.INTEGRITY_FAILURE,
    TrialStopCondition.AT17_INTEGRATION_FAILURE: TrialOutcome.INTEGRITY_FAILURE,
    TrialStopCondition.CHALLENGER_BLOCK: TrialOutcome.CHALLENGER_BLOCK,
    TrialStopCondition.HC_REGRESSION_DETECTED: TrialOutcome.HC_REGRESSION_DETECTED,
    TrialStopCondition.LOW_RECOGNITION_COMPROMISED: (TrialOutcome.LOW_RECOGNITION_COMPROMISED),
    TrialStopCondition.UNSUPPORTED_AUTHORIZED_PATH: (TrialOutcome.UNSUPPORTED_AUTHORIZED_PATH),
    TrialStopCondition.RESOURCE_LIMIT_REACHED: TrialOutcome.RESOURCE_LIMIT_REACHED,
    TrialStopCondition.OPERATOR_ABORTED: TrialOutcome.OPERATOR_ABORTED,
}

_ALLOWED_STOP_PHASES: dict[TrialStopCondition, frozenset[TrialStopPhase]] = {
    TrialStopCondition.INPUT_INVALID: frozenset({TrialStopPhase.INPUT}),
    TrialStopCondition.ENVIRONMENT_REJECTED: frozenset({TrialStopPhase.ADMISSION}),
    TrialStopCondition.AUTHORIZED_BOUNDARY_REACHED: frozenset({TrialStopPhase.EXECUTION}),
    TrialStopCondition.CAPABILITY_GAP: frozenset({TrialStopPhase.EXECUTION}),
    TrialStopCondition.RESEARCH_SAFETY_BLOCK: frozenset({TrialStopPhase.EXECUTION}),
    TrialStopCondition.MODEL_OUTPUT_INVALID: frozenset({TrialStopPhase.EXECUTION}),
    TrialStopCondition.ARTIFACT_INTEGRITY_FAILURE: frozenset(
        {
            TrialStopPhase.EXECUTION,
            TrialStopPhase.PERSISTENCE,
            TrialStopPhase.AUDIT_EXPORT,
        }
    ),
    TrialStopCondition.AT17_INTEGRATION_FAILURE: frozenset({TrialStopPhase.EXECUTION}),
    TrialStopCondition.CHALLENGER_BLOCK: frozenset({TrialStopPhase.EXECUTION}),
    TrialStopCondition.HC_REGRESSION_DETECTED: frozenset({TrialStopPhase.EXECUTION}),
    TrialStopCondition.LOW_RECOGNITION_COMPROMISED: frozenset({TrialStopPhase.EXECUTION}),
    TrialStopCondition.UNSUPPORTED_AUTHORIZED_PATH: frozenset(
        {TrialStopPhase.ADMISSION, TrialStopPhase.EXECUTION}
    ),
    TrialStopCondition.RESOURCE_LIMIT_REACHED: frozenset(
        {
            TrialStopPhase.INPUT,
            TrialStopPhase.ADMISSION,
            TrialStopPhase.EXECUTION,
            TrialStopPhase.PERSISTENCE,
            TrialStopPhase.AUDIT_EXPORT,
        }
    ),
    TrialStopCondition.OPERATOR_ABORTED: frozenset(
        {
            TrialStopPhase.ADMISSION,
            TrialStopPhase.EXECUTION,
            TrialStopPhase.AUDIT_EXPORT,
        }
    ),
    TrialStopCondition.INFRASTRUCTURE_FAILURE: frozenset(TrialStopPhase),
}

TRIAL_STOP_PRECEDENCE: tuple[TrialStopCondition, ...] = (
    TrialStopCondition.INPUT_INVALID,
    TrialStopCondition.ENVIRONMENT_REJECTED,
    TrialStopCondition.INFRASTRUCTURE_FAILURE,
    TrialStopCondition.RESOURCE_LIMIT_REACHED,
    TrialStopCondition.OPERATOR_ABORTED,
    TrialStopCondition.CAPABILITY_GAP,
    TrialStopCondition.RESEARCH_SAFETY_BLOCK,
    TrialStopCondition.MODEL_OUTPUT_INVALID,
    TrialStopCondition.ARTIFACT_INTEGRITY_FAILURE,
    TrialStopCondition.AT17_INTEGRATION_FAILURE,
    TrialStopCondition.CHALLENGER_BLOCK,
    TrialStopCondition.HC_REGRESSION_DETECTED,
    TrialStopCondition.LOW_RECOGNITION_COMPROMISED,
    TrialStopCondition.UNSUPPORTED_AUTHORIZED_PATH,
    TrialStopCondition.AUTHORIZED_BOUNDARY_REACHED,
)


def stop_outcome_for(condition: TrialStopCondition) -> TrialOutcome:
    return _STOP_OUTCOME[condition]


def select_controlling_stop(
    conditions: tuple[TrialStopCondition, ...],
) -> TrialStopCondition:
    if not conditions:
        raise TrialContractError("at least one stop condition is required")
    _assert_unique(tuple(item.value for item in conditions), name="stop conditions")
    ranks = {condition: index for index, condition in enumerate(TRIAL_STOP_PRECEDENCE)}
    return min(conditions, key=ranks.__getitem__)


class TrialNamedHash(_FrozenTrialModel):
    name: str = Field(min_length=1)
    sha256: str = Field(pattern=_HASH_PATTERN)


class TrialArtifactRef(_FrozenTrialModel):
    kind: str = Field(min_length=1)
    ref: str = Field(min_length=1)
    sha256: str = Field(pattern=_HASH_PATTERN)


class TrialHardCaps(_FrozenTrialModel):
    max_payload_files: int = Field(ge=1)
    max_file_bytes: int = Field(ge=1)
    max_total_payload_bytes: int = Field(ge=1)
    max_mock_outputs: int = Field(ge=1)
    max_mock_output_bytes: int = Field(ge=1)
    max_stage_calls: int = Field(ge=1)
    max_model_calls: int = Field(ge=1)
    max_output_bytes: int = Field(ge=1)
    max_output_tokens: int = Field(ge=1)
    max_frozen_artifacts: int = Field(ge=1)
    max_audit_payload_bytes: int = Field(ge=1)
    max_wall_clock_seconds: int = Field(ge=1)
    max_retries: int = Field(ge=0)


TRIAL_HARD_CAPS = TrialHardCaps(
    max_payload_files=128,
    max_file_bytes=1_048_576,
    max_total_payload_bytes=8_388_608,
    max_mock_outputs=64,
    max_mock_output_bytes=524_288,
    max_stage_calls=64,
    max_model_calls=64,
    max_output_bytes=2_097_152,
    max_output_tokens=1_000_000,
    max_frozen_artifacts=2_048,
    max_audit_payload_bytes=16_777_216,
    max_wall_clock_seconds=1_800,
    max_retries=0,
)


class TrialResourceLimits(TrialHardCaps):
    @model_validator(mode="after")
    def _within_hard_caps(self) -> TrialResourceLimits:
        for name in TrialHardCaps.model_fields:
            value = getattr(self, name)
            cap = getattr(TRIAL_HARD_CAPS, name)
            if value > cap:
                raise ValueError(f"{name} exceeds code-owned hard cap {cap}")
        return self


class TrialRuntimePosition(_FrozenTrialModel):
    mode: CaseMode
    state: RuntimeState
    case_revision: int = Field(ge=1)

    @model_validator(mode="after")
    def _authorized_state(self) -> TrialRuntimePosition:
        if self.state not in _AUTHORIZED_TRIAL_STATES:
            raise ValueError(
                f"trial Runtime position cannot use unauthorized state {self.state.value}"
            )
        return self


class TrialAttemptReceiptPayload(_FrozenTrialModel):
    attempt_id: str = Field(min_length=1)
    sanitized_input_root_fingerprint: str = Field(min_length=1)
    detached_input_address: str | None = Field(default=None, pattern=_HASH_PATTERN)
    started_at: datetime

    _started_at_must_be_aware = field_validator("started_at")(_aware)


class TrialAttemptReceipt(TrialAttemptReceiptPayload):
    attempt_receipt_hash: str = Field(pattern=_HASH_PATTERN)

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"attempt_receipt_hash"}, exclude_none=True)
        if self.attempt_receipt_hash != canonical_document_sha256(payload):
            raise TrialContractError("TrialAttemptReceipt hash does not match payload")


def freeze_trial_attempt_receipt(
    payload: TrialAttemptReceiptPayload,
) -> TrialAttemptReceipt:
    document = payload.to_document()
    receipt = TrialAttemptReceipt.model_validate(
        {
            **document,
            "attempt_receipt_hash": canonical_document_sha256(document),
        }
    )
    receipt.assert_integrity()
    return receipt


class TrialInputFileReceipt(_FrozenTrialModel):
    path: str = Field(min_length=1)
    document_kind: TrialDocumentKind
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=_HASH_PATTERN)


class TrialInputBundleReceiptPayload(_FrozenTrialModel):
    receipt_id: str = Field(min_length=1)
    attempt_receipt_hash: str = Field(pattern=_HASH_PATTERN)
    detached_input_address: str = Field(pattern=_HASH_PATTERN)
    checksum_index_sha256: str = Field(pattern=_HASH_PATTERN)
    files: tuple[TrialInputFileReceipt, ...] = Field(min_length=1)
    total_payload_bytes: int = Field(ge=1)
    inventory_policy_version: str = Field(min_length=1)
    verified_at: datetime

    _verified_at_must_be_aware = field_validator("verified_at")(_aware)


class TrialInputBundleReceipt(TrialInputBundleReceiptPayload):
    bundle_receipt_hash: str = Field(pattern=_HASH_PATTERN)

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"bundle_receipt_hash"}, exclude_none=True)
        if self.bundle_receipt_hash != canonical_document_sha256(payload):
            raise TrialContractError("TrialInputBundleReceipt hash does not match payload")
        paths = tuple(item.path for item in self.files)
        _assert_unique(paths, name="TrialInputBundleReceipt paths")
        if self.total_payload_bytes != sum(item.size_bytes for item in self.files):
            raise TrialContractError("TrialInputBundleReceipt byte total is inconsistent")
        if len(self.files) > TRIAL_HARD_CAPS.max_payload_files:
            raise TrialContractError("TrialInputBundleReceipt exceeds payload file hard cap")
        if self.total_payload_bytes > TRIAL_HARD_CAPS.max_total_payload_bytes:
            raise TrialContractError("TrialInputBundleReceipt exceeds payload byte hard cap")


def freeze_trial_input_bundle_receipt(
    payload: TrialInputBundleReceiptPayload,
) -> TrialInputBundleReceipt:
    document = payload.to_document()
    receipt = TrialInputBundleReceipt.model_validate(
        {
            **document,
            "bundle_receipt_hash": canonical_document_sha256(document),
        }
    )
    receipt.assert_integrity()
    return receipt


class TrialManifestPayload(_FrozenTrialModel):
    trial_id: str = Field(min_length=1)
    trial_protocol_version: str = Field(min_length=1)
    source_commit_sha: str = Field(pattern=_COMMIT_PATTERN)
    protocol_version: str = Field(min_length=1)
    frozen_contract_hashes: tuple[TrialNamedHash, ...] = Field(min_length=1)
    migration_ceiling: Literal["0007"] = "0007"
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    case_mode: CaseMode
    adapter_lane: Literal[TrialAdapterLane.MOCK] = TrialAdapterLane.MOCK
    data_class: TrialDataClass
    publication_policy: Literal["RESTRICTED"] = "RESTRICTED"
    database_target: str = Field(min_length=1)
    output_root: str = Field(min_length=1)
    resource_limits: TrialResourceLimits
    allowed_terminal_outcomes: tuple[TrialOutcome, ...] = Field(min_length=1)
    inventory_policy_version: str = Field(min_length=1)
    authorized_terminal_state: RuntimeState = RuntimeState.ADVERSARIAL_REVIEW
    final_synthesis_authorized: Literal[False] = False
    final_claim_authorized: Literal[False] = False
    seal_authorized: Literal[False] = False
    publication_authorized: Literal[False] = False
    reality_execution_authorized: Literal[False] = False
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class TrialManifest(TrialManifestPayload):
    manifest_hash: str = Field(pattern=_HASH_PATTERN)

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"manifest_hash"}, exclude_none=True)
        if self.manifest_hash != canonical_document_sha256(payload):
            raise TrialContractError("TrialManifest hash does not match payload")
        hash_names = tuple(item.name for item in self.frozen_contract_hashes)
        _assert_unique(hash_names, name="TrialManifest frozen contract names")
        outcomes = tuple(item.value for item in self.allowed_terminal_outcomes)
        _assert_unique(outcomes, name="TrialManifest allowed outcomes")
        if self.authorized_terminal_state is not _AUTHORIZED_TERMINAL_STATE:
            raise TrialContractError("Trial Manifest terminal state must remain ADVERSARIAL_REVIEW")
        if self.case_mode is CaseMode.HISTORICAL_BLIND_EVAL:
            raise TrialContractError("TRIAL-SBX common path excludes HISTORICAL_BLIND_EVAL")
        if not self.database_target.startswith("trial_"):
            raise TrialContractError("Trial database target must be a logical trial_* target")
        if self.output_root.startswith("/") or ".." in self.output_root.split("/"):
            raise TrialContractError("Trial output root must be a bounded relative target")
        _assert_no_authority(
            final_synthesis_authorized=self.final_synthesis_authorized,
            final_claim_authorized=self.final_claim_authorized,
            seal_authorized=self.seal_authorized,
            publication_authorized=self.publication_authorized,
            reality_execution_authorized=self.reality_execution_authorized,
            object_name="TrialManifest",
        )


def freeze_trial_manifest(payload: TrialManifestPayload) -> TrialManifest:
    document = payload.to_document()
    manifest = TrialManifest.model_validate(
        {**document, "manifest_hash": canonical_document_sha256(document)}
    )
    manifest.assert_integrity()
    return manifest


class TrialCanonicalAdmissionPayload(_FrozenTrialModel):
    admission_id: str = Field(min_length=1)
    bundle_receipt_hash: str = Field(pattern=_HASH_PATTERN)
    detached_input_address: str = Field(pattern=_HASH_PATTERN)
    registry_entry_id: str = Field(min_length=1)
    purpose: TrialCanonicalPurpose
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    case_mode: CaseMode
    adapter_lane: Literal[TrialAdapterLane.MOCK] = TrialAdapterLane.MOCK
    data_class: Literal[TrialDataClass.SYNTHETIC] = TrialDataClass.SYNTHETIC
    publication_policy: Literal["RESTRICTED"] = "RESTRICTED"
    source_commit_sha: str = Field(pattern=_COMMIT_PATTERN)
    protocol_version: str = Field(min_length=1)
    pre_freeze_admitted: bool
    status: TrialCanonicalAdmissionStatus
    reasons: tuple[str, ...]
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class TrialCanonicalAdmission(TrialCanonicalAdmissionPayload):
    canonical_admission_hash: str = Field(pattern=_HASH_PATTERN)

    def assert_integrity(self) -> None:
        payload = self.model_dump(
            mode="json",
            exclude={"canonical_admission_hash"},
            exclude_none=True,
        )
        if self.canonical_admission_hash != canonical_document_sha256(payload):
            raise TrialContractError("TrialCanonicalAdmission hash does not match payload")
        _assert_unique(self.reasons, name="TrialCanonicalAdmission reasons")
        expected = (
            TrialCanonicalAdmissionStatus.PASS
            if self.pre_freeze_admitted and not self.reasons
            else TrialCanonicalAdmissionStatus.REJECTED
        )
        if self.status is not expected:
            raise TrialContractError("canonical admission status is not derivable from facts")
        if self.status is TrialCanonicalAdmissionStatus.PASS and self.purpose not in {
            TrialCanonicalPurpose.BOOTSTRAP_AUTOMATED_TEST,
            TrialCanonicalPurpose.CANONICAL_CASE,
        }:
            raise TrialContractError(
                "current TRIAL-SBX admits only the private bootstrap or canonical-case purpose"
            )


def freeze_trial_canonical_admission(
    payload: TrialCanonicalAdmissionPayload,
) -> TrialCanonicalAdmission:
    document = payload.to_document()
    admission = TrialCanonicalAdmission.model_validate(
        {
            **document,
            "canonical_admission_hash": canonical_document_sha256(document),
        }
    )
    admission.assert_integrity()
    return admission


class TrialEnvironmentAdmissionPayload(_FrozenTrialModel):
    admission_id: str = Field(min_length=1)
    attempt_receipt_hash: str = Field(pattern=_HASH_PATTERN)
    manifest_hash: str = Field(pattern=_HASH_PATTERN)
    canonical_admission_hash: str = Field(pattern=_HASH_PATTERN)
    canonical_registry_entry_id: str = Field(min_length=1)
    detached_input_address: str = Field(pattern=_HASH_PATTERN)
    observed_source_commit_sha: str | None = Field(default=None, pattern=_COMMIT_PATTERN)
    observed_database_target: str | None = None
    observed_output_root: str | None = None
    sandbox_mode: bool
    mock_only: bool
    live_provider_disabled: bool
    outbound_network_disabled: bool
    external_tools_disabled: bool
    reality_execution_disabled: bool
    sensitive_data_absent: bool
    real_experts_disabled: bool
    provider_secrets_disabled: bool
    trial_database_disposable: bool
    database_ownership_marker_present: bool
    output_root_disposable: bool
    output_root_ownership_marker_present: bool
    resource_limits_admitted: bool
    final_synthesis_authorized: Literal[False] = False
    final_claim_authorized: Literal[False] = False
    seal_authorized: Literal[False] = False
    publication_authorized: Literal[False] = False
    reality_execution_authorized: Literal[False] = False
    status: TrialAdmissionStatus
    reasons: tuple[str, ...]
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class TrialEnvironmentAdmission(TrialEnvironmentAdmissionPayload):
    environment_admission_hash: str = Field(pattern=_HASH_PATTERN)

    def assert_integrity(self) -> None:
        payload = self.model_dump(
            mode="json",
            exclude={"environment_admission_hash"},
            exclude_none=True,
        )
        if self.environment_admission_hash != canonical_document_sha256(payload):
            raise TrialContractError("TrialEnvironmentAdmission hash does not match payload")
        _assert_unique(self.reasons, name="TrialEnvironmentAdmission reasons")
        required = (
            self.sandbox_mode,
            self.mock_only,
            self.live_provider_disabled,
            self.outbound_network_disabled,
            self.external_tools_disabled,
            self.reality_execution_disabled,
            self.sensitive_data_absent,
            self.real_experts_disabled,
            self.provider_secrets_disabled,
            self.trial_database_disposable,
            self.database_ownership_marker_present,
            self.output_root_disposable,
            self.output_root_ownership_marker_present,
            self.resource_limits_admitted,
            self.observed_source_commit_sha is not None,
            self.observed_database_target is not None,
            self.observed_output_root is not None,
        )
        expected = (
            TrialAdmissionStatus.PASS
            if all(required) and not self.reasons
            else TrialAdmissionStatus.REJECTED
        )
        if self.status is not expected:
            raise TrialContractError("Environment Admission status is not derivable from facts")
        _assert_no_authority(
            final_synthesis_authorized=self.final_synthesis_authorized,
            final_claim_authorized=self.final_claim_authorized,
            seal_authorized=self.seal_authorized,
            publication_authorized=self.publication_authorized,
            reality_execution_authorized=self.reality_execution_authorized,
            object_name="TrialEnvironmentAdmission",
        )


def freeze_trial_environment_admission(
    payload: TrialEnvironmentAdmissionPayload,
) -> TrialEnvironmentAdmission:
    document = payload.to_document()
    admission = TrialEnvironmentAdmission.model_validate(
        {
            **document,
            "environment_admission_hash": canonical_document_sha256(document),
        }
    )
    admission.assert_integrity()
    return admission


def assert_environment_admission_binding(
    attempt: TrialAttemptReceipt,
    manifest: TrialManifest,
    canonical_admission: TrialCanonicalAdmission,
    environment: TrialEnvironmentAdmission,
) -> None:
    attempt.assert_integrity()
    manifest.assert_integrity()
    canonical_admission.assert_integrity()
    environment.assert_integrity()
    if canonical_admission.status is not TrialCanonicalAdmissionStatus.PASS:
        raise TrialContractError("Environment PASS requires a canonical PASS decision")
    if not canonical_admission.pre_freeze_admitted:
        raise TrialContractError("Environment PASS requires pre-freeze canonical admission")
    expected = (
        attempt.attempt_receipt_hash,
        manifest.manifest_hash,
        canonical_admission.canonical_admission_hash,
        canonical_admission.registry_entry_id,
        canonical_admission.detached_input_address,
    )
    actual = (
        environment.attempt_receipt_hash,
        environment.manifest_hash,
        environment.canonical_admission_hash,
        environment.canonical_registry_entry_id,
        environment.detached_input_address,
    )
    if actual != expected:
        raise TrialContractError(
            "Environment Admission does not bind exact attempt/manifest/canonical PASS"
        )
    if environment.observed_source_commit_sha != manifest.source_commit_sha:
        raise TrialContractError("observed source commit differs from Trial Manifest")
    if environment.observed_database_target != manifest.database_target:
        raise TrialContractError("observed database target differs from Trial Manifest")
    if environment.observed_output_root != manifest.output_root:
        raise TrialContractError("observed output root differs from Trial Manifest")
    if (
        canonical_admission.case_id,
        canonical_admission.case_revision,
        canonical_admission.case_mode,
        canonical_admission.source_commit_sha,
        canonical_admission.protocol_version,
    ) != (
        manifest.case_id,
        manifest.case_revision,
        manifest.case_mode,
        manifest.source_commit_sha,
        manifest.protocol_version,
    ):
        raise TrialContractError("canonical PASS identity differs from Trial Manifest")


class TrialRuntimeStepPayload(_FrozenTrialModel):
    step_id: str = Field(min_length=1)
    step_index: int = Field(ge=1)
    position: TrialRuntimePosition
    controlling_ref: str = Field(min_length=1)
    recorded_at: datetime

    _recorded_at_must_be_aware = field_validator("recorded_at")(_aware)


class TrialRuntimeStep(TrialRuntimeStepPayload):
    step_hash: str = Field(pattern=_HASH_PATTERN)

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"step_hash"}, exclude_none=True)
        if self.step_hash != canonical_document_sha256(payload):
            raise TrialContractError("TrialRuntimeStep hash does not match payload")
        if self.position.state not in _AUTHORIZED_TRIAL_STATES:
            raise TrialContractError("TrialRuntimeStep contains an unauthorized Runtime state")


def freeze_trial_runtime_step(
    payload: TrialRuntimeStepPayload,
) -> TrialRuntimeStep:
    document = payload.to_document()
    step = TrialRuntimeStep.model_validate(
        {**document, "step_hash": canonical_document_sha256(document)}
    )
    step.assert_integrity()
    return step


def _assert_trajectory(
    trajectory: tuple[TrialRuntimeStep, ...],
    *,
    case_mode: CaseMode | None,
    case_revision: int | None,
    final_position: TrialRuntimePosition | None,
) -> None:
    for index, step in enumerate(trajectory, start=1):
        step.assert_integrity()
        if step.step_index != index:
            raise TrialContractError("Runtime trajectory indices must be contiguous from one")
        if case_mode is not None and step.position.mode is not case_mode:
            raise TrialContractError("Runtime trajectory Case Mode differs from Trial Result")
        if case_revision is not None and step.position.case_revision != case_revision:
            raise TrialContractError("Runtime trajectory Case revision differs from Trial Result")
    if trajectory:
        if final_position != trajectory[-1].position:
            raise TrialContractError("final Runtime position must equal final trajectory entry")
    elif final_position is not None:
        raise TrialContractError("empty trajectory cannot declare a final Runtime position")


class TrialStopPayload(_FrozenTrialModel):
    stop_id: str = Field(min_length=1)
    attempt_receipt_hash: str = Field(pattern=_HASH_PATTERN)
    trial_manifest_hash: str | None = Field(default=None, pattern=_HASH_PATTERN)
    environment_admission_hash: str | None = Field(default=None, pattern=_HASH_PATTERN)
    case_id: str | None = None
    case_revision: int | None = Field(default=None, ge=1)
    case_mode: CaseMode | None = None
    outcome: TrialOutcome
    stop_condition: TrialStopCondition
    stop_phase: TrialStopPhase
    runtime_trajectory: tuple[TrialRuntimeStep, ...]
    final_runtime_position: TrialRuntimePosition | None = None
    controlling_artifact_refs: tuple[TrialArtifactRef, ...] = ()
    reasons: tuple[str, ...]
    produced_artifacts: tuple[TrialArtifactRef, ...] = ()
    stopped_at: datetime

    _stopped_at_must_be_aware = field_validator("stopped_at")(_aware)


class TrialStop(TrialStopPayload):
    stop_hash: str = Field(pattern=_HASH_PATTERN)

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"stop_hash"}, exclude_none=True)
        if self.stop_hash != canonical_document_sha256(payload):
            raise TrialContractError("TrialStop hash does not match payload")
        if self.outcome is not stop_outcome_for(self.stop_condition):
            raise TrialContractError("TrialStop outcome does not match stop condition")
        if self.stop_phase not in _ALLOWED_STOP_PHASES[self.stop_condition]:
            raise TrialContractError("TrialStop condition is invalid for the declared phase")
        _assert_unique(self.reasons, name="TrialStop reasons")
        if not self.reasons:
            raise TrialContractError("TrialStop requires at least one reason")
        _assert_trajectory(
            self.runtime_trajectory,
            case_mode=self.case_mode,
            case_revision=self.case_revision,
            final_position=self.final_runtime_position,
        )
        if self.stop_phase is TrialStopPhase.INPUT:
            if self.runtime_trajectory:
                raise TrialContractError("input-phase stop must have an empty trajectory")
            if (
                self.stop_condition is TrialStopCondition.INPUT_INVALID
                and self.environment_admission_hash is not None
            ):
                raise TrialContractError("invalid input cannot invent Environment Admission")
        elif self.stop_phase is TrialStopPhase.ADMISSION:
            if self.trial_manifest_hash is None or self.environment_admission_hash is None:
                raise TrialContractError(
                    "admission-phase stop requires Manifest and Admission hashes"
                )
            if self.runtime_trajectory:
                raise TrialContractError("admission-phase stop must have an empty trajectory")
        else:
            if self.trial_manifest_hash is None or self.environment_admission_hash is None:
                raise TrialContractError(
                    "post-admission stop requires Manifest and Admission hashes"
                )
            if not self.runtime_trajectory:
                raise TrialContractError("post-admission stop requires a non-empty trajectory")
        if self.stop_condition is TrialStopCondition.AT17_INTEGRATION_FAILURE:
            refs = {item.kind for item in self.controlling_artifact_refs}
            required = {
                "AT17_EVIDENCE",
                "RESIMULATION_RESULT",
                "PARENT_LINEAGE",
            }
            if not required.issubset(refs):
                raise TrialContractError(
                    "AT-17 stop must preserve evidence, re-simulation, and parent lineage"
                )


def freeze_trial_stop(payload: TrialStopPayload) -> TrialStop:
    document = payload.to_document()
    stop = TrialStop.model_validate({**document, "stop_hash": canonical_document_sha256(document)})
    stop.assert_integrity()
    return stop


class TrialResultPayload(_FrozenTrialModel):
    result_id: str = Field(min_length=1)
    attempt_receipt_hash: str = Field(pattern=_HASH_PATTERN)
    trial_manifest_hash: str | None = Field(default=None, pattern=_HASH_PATTERN)
    environment_admission_hash: str | None = Field(default=None, pattern=_HASH_PATTERN)
    trial_stop_hash: str = Field(pattern=_HASH_PATTERN)
    case_id: str | None = None
    case_revision: int | None = Field(default=None, ge=1)
    case_mode: CaseMode | None = None
    outcome: TrialOutcome
    stop_condition: TrialStopCondition
    stop_phase: TrialStopPhase
    trial_capability_acceptance: TrialCapabilityAcceptance
    substantive_case_outcome: TrialOutcome | None = None
    runtime_trajectory: tuple[TrialRuntimeStep, ...]
    final_runtime_position: TrialRuntimePosition | None = None
    controlling_artifact_refs: tuple[TrialArtifactRef, ...] = ()
    reasons: tuple[str, ...]
    limitations: tuple[str, ...] = ()
    dissent_refs: tuple[str, ...] = ()
    unresolved_condition_refs: tuple[str, ...] = ()
    produced_artifacts: tuple[TrialArtifactRef, ...] = ()
    audit_export_status: TrialAuditExportStatus
    cleanup_disposition: TrialCleanupDisposition
    final_synthesis_authorized: Literal[False] = False
    final_claim_authorized: Literal[False] = False
    seal_authorized: Literal[False] = False
    publication_authorized: Literal[False] = False
    reality_execution_authorized: Literal[False] = False
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class TrialResult(TrialResultPayload):
    result_hash: str = Field(pattern=_HASH_PATTERN)

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"result_hash"}, exclude_none=True)
        if self.result_hash != canonical_document_sha256(payload):
            raise TrialContractError("TrialResult hash does not match payload")
        if self.outcome is not stop_outcome_for(self.stop_condition):
            raise TrialContractError("TrialResult outcome does not match stop condition")
        if self.stop_phase not in _ALLOWED_STOP_PHASES[self.stop_condition]:
            raise TrialContractError("TrialResult stop condition is invalid for declared phase")
        _assert_unique(self.reasons, name="TrialResult reasons")
        _assert_unique(self.dissent_refs, name="TrialResult dissent refs")
        _assert_unique(
            self.unresolved_condition_refs,
            name="TrialResult unresolved refs",
        )
        if not self.reasons:
            raise TrialContractError("TrialResult requires at least one reason")
        _assert_trajectory(
            self.runtime_trajectory,
            case_mode=self.case_mode,
            case_revision=self.case_revision,
            final_position=self.final_runtime_position,
        )
        if self.stop_phase is TrialStopPhase.INPUT:
            if self.runtime_trajectory or self.environment_admission_hash is not None:
                raise TrialContractError(
                    "invalid-input result cannot contain execution/admission facts"
                )
        elif self.stop_phase is TrialStopPhase.ADMISSION:
            if self.trial_manifest_hash is None or self.environment_admission_hash is None:
                raise TrialContractError("admission result requires Manifest and Admission hashes")
            if self.runtime_trajectory:
                raise TrialContractError("admission result must have an empty trajectory")
        else:
            if self.trial_manifest_hash is None or self.environment_admission_hash is None:
                raise TrialContractError(
                    "execution/later result requires Manifest and Admission hashes"
                )
            if not self.runtime_trajectory:
                raise TrialContractError("execution/later result requires a non-empty trajectory")
        if self.outcome is TrialOutcome.COMPLETED_AT_AUTHORIZED_BOUNDARY:
            if (
                self.final_runtime_position is None
                or self.final_runtime_position.state is not _AUTHORIZED_TERMINAL_STATE
            ):
                raise TrialContractError("completed trial must stop exactly at ADVERSARIAL_REVIEW")
        if (
            self.outcome in {TrialOutcome.INVALID_INPUT, TrialOutcome.INFRASTRUCTURE_FAILURE}
            and self.substantive_case_outcome is not None
        ):
            raise TrialContractError(
                "invalid-input/infrastructure failure is not a substantive Case outcome"
            )
        _assert_no_authority(
            final_synthesis_authorized=self.final_synthesis_authorized,
            final_claim_authorized=self.final_claim_authorized,
            seal_authorized=self.seal_authorized,
            publication_authorized=self.publication_authorized,
            reality_execution_authorized=self.reality_execution_authorized,
            object_name="TrialResult",
        )


def freeze_trial_result(payload: TrialResultPayload) -> TrialResult:
    document = payload.to_document()
    result = TrialResult.model_validate(
        {**document, "result_hash": canonical_document_sha256(document)}
    )
    result.assert_integrity()
    return result


def assert_trial_result_binding(
    attempt: TrialAttemptReceipt,
    manifest: TrialManifest | None,
    environment: TrialEnvironmentAdmission | None,
    stop: TrialStop,
    result: TrialResult,
) -> None:
    attempt.assert_integrity()
    if manifest is not None:
        manifest.assert_integrity()
    if environment is not None:
        environment.assert_integrity()
    stop.assert_integrity()
    result.assert_integrity()
    if stop.attempt_receipt_hash != attempt.attempt_receipt_hash:
        raise TrialContractError("TrialStop does not bind exact Attempt Receipt")
    if result.attempt_receipt_hash != attempt.attempt_receipt_hash:
        raise TrialContractError("TrialResult does not bind exact Attempt Receipt")
    manifest_hash = manifest.manifest_hash if manifest is not None else None
    environment_hash = environment.environment_admission_hash if environment is not None else None
    if stop.trial_manifest_hash != manifest_hash or result.trial_manifest_hash != manifest_hash:
        raise TrialContractError("Trial Stop/Result Manifest binding differs")
    if (
        stop.environment_admission_hash != environment_hash
        or result.environment_admission_hash != environment_hash
    ):
        raise TrialContractError("Trial Stop/Result Environment binding differs")
    if result.trial_stop_hash != stop.stop_hash:
        raise TrialContractError("TrialResult does not bind exact TrialStop")
    if (
        result.case_id,
        result.case_revision,
        result.case_mode,
        result.outcome,
        result.stop_condition,
        result.stop_phase,
        result.runtime_trajectory,
        result.final_runtime_position,
        result.controlling_artifact_refs,
        result.produced_artifacts,
        result.reasons,
    ) != (
        stop.case_id,
        stop.case_revision,
        stop.case_mode,
        stop.outcome,
        stop.stop_condition,
        stop.stop_phase,
        stop.runtime_trajectory,
        stop.final_runtime_position,
        stop.controlling_artifact_refs,
        stop.produced_artifacts,
        stop.reasons,
    ):
        raise TrialContractError("TrialResult terminal facts differ from TrialStop")
    if manifest is not None:
        expected_case_identity = (
            manifest.case_id,
            manifest.case_revision,
            manifest.case_mode,
        )
        if (
            result.case_id,
            result.case_revision,
            result.case_mode,
        ) != expected_case_identity:
            raise TrialContractError("TrialResult Case identity differs from Manifest")
        if (
            stop.case_id,
            stop.case_revision,
            stop.case_mode,
        ) != expected_case_identity:
            raise TrialContractError("TrialStop Case identity differs from Manifest")
    if result.runtime_trajectory:
        if environment is None or environment.status is not TrialAdmissionStatus.PASS:
            raise TrialContractError("execution result requires a PASS Environment Admission")
        if manifest is None:
            raise TrialContractError("execution result requires a frozen Trial Manifest")


class TrialAcceptanceOraclePayload(_FrozenTrialModel):
    oracle_id: str = Field(min_length=1)
    expected_outcome: TrialOutcome
    expected_stop_condition: TrialStopCondition
    expected_terminal_state: RuntimeState | None = None
    expected_capability_acceptance: TrialCapabilityAcceptance
    notes: tuple[str, ...] = ()
    disclosed_to_cognitive_wrappers: Literal[False] = False
    grants_canonical_status: Literal[False] = False
    grants_execution_authority: Literal[False] = False
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class TrialAcceptanceOracle(TrialAcceptanceOraclePayload):
    oracle_hash: str = Field(pattern=_HASH_PATTERN)

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"oracle_hash"}, exclude_none=True)
        if self.oracle_hash != canonical_document_sha256(payload):
            raise TrialContractError("TrialAcceptanceOracle hash does not match payload")
        if self.expected_outcome is not stop_outcome_for(self.expected_stop_condition):
            raise TrialContractError("acceptance oracle outcome differs from stop condition")
        if (
            self.disclosed_to_cognitive_wrappers
            or self.grants_canonical_status
            or self.grants_execution_authority
        ):
            raise TrialContractError("acceptance oracle has no disclosure or authority role")


def freeze_trial_acceptance_oracle(
    payload: TrialAcceptanceOraclePayload,
) -> TrialAcceptanceOracle:
    document = payload.to_document()
    oracle = TrialAcceptanceOracle.model_validate(
        {**document, "oracle_hash": canonical_document_sha256(document)}
    )
    oracle.assert_integrity()
    return oracle


class TrialMockOutputFixturePayload(_FrozenTrialModel):
    fixture_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    model_family: str = Field(min_length=1)
    provider: Literal["mock"] = "mock"
    output_text: str
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class TrialMockOutputFixture(TrialMockOutputFixturePayload):
    output_sha256: str = Field(pattern=_HASH_PATTERN)
    fixture_hash: str = Field(pattern=_HASH_PATTERN)

    def assert_integrity(self) -> None:
        import hashlib

        expected_output = hashlib.sha256(self.output_text.encode("utf-8")).hexdigest()
        if self.output_sha256 != expected_output:
            raise TrialContractError("Mock output hash does not match output_text")
        payload = self.model_dump(mode="json", exclude={"fixture_hash"}, exclude_none=True)
        if self.fixture_hash != canonical_document_sha256(payload):
            raise TrialContractError("TrialMockOutputFixture hash does not match payload")


def freeze_trial_mock_output_fixture(
    payload: TrialMockOutputFixturePayload,
) -> TrialMockOutputFixture:
    import hashlib

    document = payload.to_document()
    output_hash = hashlib.sha256(payload.output_text.encode("utf-8")).hexdigest()
    with_output = {**document, "output_sha256": output_hash}
    fixture = TrialMockOutputFixture.model_validate(
        {
            **with_output,
            "fixture_hash": canonical_document_sha256(with_output),
        }
    )
    fixture.assert_integrity()
    return fixture
