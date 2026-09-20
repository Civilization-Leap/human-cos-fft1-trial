"""S7-SCS3 code-owned Research Safety gate for Scenario re-simulation."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from human_cos.runtime.run import canonical_document_sha256
from human_cos.runtime.tool_policy import ToolCapabilityClass


class ResimulationSafetyContractError(ValueError):
    """Scenario re-simulation Safety data violates the authorized S7-SCS3 boundary."""


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("S7-SCS3 Safety timestamps require timezone-aware datetimes")
    return value


class _FrozenSafetyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class ResimulationSafetyOutcome(str, Enum):
    PASS = "PASS"
    BLOCK = "BLOCK"


class ResimulationSafetyAdmissionPayload(_FrozenSafetyModel):
    admission_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    scenario_set_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    scenario_path_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    intervention_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    parent_world_state_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    parent_causal_graph_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    required_safety_facts: tuple[str, ...]
    present_safety_facts: tuple[str, ...]
    requested_capability_refs: tuple[str, ...] = ()
    requested_capability_classes: tuple[ToolCapabilityClass, ...] = ()
    reality_execution_required: bool = False
    dangerous_detail_findings: tuple[str, ...] = ()
    protocol_invalid_findings: tuple[str, ...] = ()
    blocked_path_refs: tuple[str, ...] = ()
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class ResimulationSafetyAdmission(ResimulationSafetyAdmissionPayload):
    admission_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(
            mode="json",
            exclude={"admission_hash"},
            exclude_none=True,
        )
        if self.admission_hash != canonical_document_sha256(payload):
            raise ResimulationSafetyContractError(
                "ResimulationSafetyAdmission hash does not match payload"
            )
        for name, values in (
            ("required_safety_facts", self.required_safety_facts),
            ("present_safety_facts", self.present_safety_facts),
            ("requested_capability_refs", self.requested_capability_refs),
            ("dangerous_detail_findings", self.dangerous_detail_findings),
            ("protocol_invalid_findings", self.protocol_invalid_findings),
            ("blocked_path_refs", self.blocked_path_refs),
        ):
            if len(values) != len(set(values)):
                raise ResimulationSafetyContractError(f"{name} must not contain duplicates")
            if any(not item.strip() for item in values):
                raise ResimulationSafetyContractError(f"{name} must not contain empty values")


class ResimulationSafetyResultPayload(_FrozenSafetyModel):
    result_id: str = Field(min_length=1)
    admission_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    scenario_set_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    scenario_path_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    intervention_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    parent_world_state_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    parent_causal_graph_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    outcome: ResimulationSafetyOutcome
    missing_required_safety_facts: tuple[str, ...]
    prohibited_capability_classes: tuple[ToolCapabilityClass, ...]
    dangerous_detail_findings: tuple[str, ...]
    protocol_invalid_findings: tuple[str, ...]
    blocked_path_refs: tuple[str, ...]
    reasons: tuple[str, ...]
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class ResimulationSafetyResult(ResimulationSafetyResultPayload):
    result_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(
            mode="json",
            exclude={"result_hash"},
            exclude_none=True,
        )
        if self.result_hash != canonical_document_sha256(payload):
            raise ResimulationSafetyContractError(
                "ResimulationSafetyResult hash does not match payload"
            )
        if not self.reasons:
            raise ResimulationSafetyContractError(
                "ResimulationSafetyResult requires deterministic reasons"
            )
        if self.outcome is ResimulationSafetyOutcome.PASS and self.blocked_path_refs:
            raise ResimulationSafetyContractError(
                "PASS ResimulationSafetyResult cannot block paths"
            )


def freeze_resimulation_safety_admission(
    payload: ResimulationSafetyAdmissionPayload,
) -> ResimulationSafetyAdmission:
    document = payload.to_document()
    admission = ResimulationSafetyAdmission(
        **document,
        admission_hash=canonical_document_sha256(document),
    )
    admission.assert_integrity()
    return admission


def _evaluation_fields(
    admission: ResimulationSafetyAdmission,
) -> tuple[
    ResimulationSafetyOutcome,
    tuple[str, ...],
    tuple[ToolCapabilityClass, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
]:
    admission.assert_integrity()
    missing = tuple(
        sorted(set(admission.required_safety_facts) - set(admission.present_safety_facts))
    )
    prohibited_classes = tuple(
        sorted(
            {
                capability_class
                for capability_class in admission.requested_capability_classes
                if capability_class is ToolCapabilityClass.REALITY_EXECUTION
            },
            key=lambda item: item.value,
        )
    )
    reasons: list[str] = []
    if missing:
        reasons.append("missing required re-simulation safety facts: " + ", ".join(missing))
    if admission.reality_execution_required:
        reasons.append("reality execution is globally denied")
    if prohibited_classes:
        reasons.append("requested REALITY_EXECUTION capability class is denied")
    if admission.dangerous_detail_findings:
        reasons.append("dangerous re-simulation research-detail finding is present")
    if admission.protocol_invalid_findings:
        reasons.append("protocol-invalid re-simulation finding is present")
    if admission.blocked_path_refs:
        reasons.append("Research Safety admission explicitly blocks one or more paths")

    blocked = bool(reasons)
    outcome = ResimulationSafetyOutcome.BLOCK if blocked else ResimulationSafetyOutcome.PASS
    blocked_path_refs = admission.blocked_path_refs
    if blocked and not blocked_path_refs:
        blocked_path_refs = ("SCENARIO_RESIMULATION",)
    if not blocked:
        reasons.append("read-only Scenario re-simulation path is safety-clean")

    return (
        outcome,
        missing,
        prohibited_classes,
        admission.dangerous_detail_findings,
        admission.protocol_invalid_findings,
        blocked_path_refs,
        tuple(reasons),
    )


def evaluate_resimulation_safety(
    admission: ResimulationSafetyAdmission,
    *,
    result_id: str,
    frozen_at: datetime,
) -> ResimulationSafetyResult:
    (
        outcome,
        missing,
        prohibited_classes,
        dangerous_findings,
        protocol_invalid_findings,
        blocked_path_refs,
        reasons,
    ) = _evaluation_fields(admission)
    payload = ResimulationSafetyResultPayload(
        result_id=result_id,
        admission_hash=admission.admission_hash,
        case_id=admission.case_id,
        case_revision=admission.case_revision,
        scenario_set_hash=admission.scenario_set_hash,
        scenario_path_hash=admission.scenario_path_hash,
        intervention_hash=admission.intervention_hash,
        parent_world_state_hash=admission.parent_world_state_hash,
        parent_causal_graph_hash=admission.parent_causal_graph_hash,
        outcome=outcome,
        missing_required_safety_facts=missing,
        prohibited_capability_classes=prohibited_classes,
        dangerous_detail_findings=dangerous_findings,
        protocol_invalid_findings=protocol_invalid_findings,
        blocked_path_refs=blocked_path_refs,
        reasons=reasons,
        protocol_version=admission.protocol_version,
        frozen_at=frozen_at,
    )
    document = payload.to_document()
    result = ResimulationSafetyResult(
        **document,
        result_hash=canonical_document_sha256(document),
    )
    result.assert_integrity()
    return result


def assert_resimulation_safety_result_binding(
    admission: ResimulationSafetyAdmission,
    result: ResimulationSafetyResult,
) -> None:
    admission.assert_integrity()
    result.assert_integrity()
    if (
        result.admission_hash,
        result.case_id,
        result.case_revision,
        result.scenario_set_hash,
        result.scenario_path_hash,
        result.intervention_hash,
        result.parent_world_state_hash,
        result.parent_causal_graph_hash,
        result.protocol_version,
    ) != (
        admission.admission_hash,
        admission.case_id,
        admission.case_revision,
        admission.scenario_set_hash,
        admission.scenario_path_hash,
        admission.intervention_hash,
        admission.parent_world_state_hash,
        admission.parent_causal_graph_hash,
        admission.protocol_version,
    ):
        raise ResimulationSafetyContractError(
            "ResimulationSafetyResult source lineage does not match admission"
        )

    (
        expected_outcome,
        expected_missing,
        expected_prohibited,
        expected_dangerous,
        expected_protocol_invalid,
        expected_blocked_refs,
        expected_reasons,
    ) = _evaluation_fields(admission)
    if (
        result.outcome,
        result.missing_required_safety_facts,
        result.prohibited_capability_classes,
        result.dangerous_detail_findings,
        result.protocol_invalid_findings,
        result.blocked_path_refs,
        result.reasons,
    ) != (
        expected_outcome,
        expected_missing,
        expected_prohibited,
        expected_dangerous,
        expected_protocol_invalid,
        expected_blocked_refs,
        expected_reasons,
    ):
        raise ResimulationSafetyContractError(
            "ResimulationSafetyResult does not match deterministic code-owned evaluation"
        )
