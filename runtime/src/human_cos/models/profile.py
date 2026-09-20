"""Frozen-contract Model Profile application model for S2-L."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from human_cos.core.models import ContractValidationError
from human_cos.protocols.schema_loader import validate_instance

DomainTaskType = Literal[
    "evidence_interpretation",
    "mechanism_analysis",
    "causal_inference",
    "quantitative_reasoning",
    "scenario_analysis",
    "policy_constraint_analysis",
    "source_research",
]
ModelStatus = Literal["CANDIDATE", "QUALIFIED", "RESTRICTED", "DISABLED"]
CapabilityStatus = Literal["CANDIDATE", "QUALIFIED", "RESTRICTED"]


class FrozenProfileModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class RoleEligibility(FrozenProfileModel):
    meta_controller: bool = False
    challenger: bool = False
    evaluator: bool = False
    domain_worker: tuple[str, ...] = ()


class ControllerQualification(FrozenProfileModel):
    framing_recall: float | None = None
    cross_domain_coverage: float | None = None
    causal_integration: float | None = None
    critical_node_detection: float | None = None
    dissent_preservation: float | None = None
    evidence_discipline: float | None = None
    falsification_quality: float | None = None
    calibration: float | None = None
    adversarial_robustness: float | None = None
    tool_reasoning: float | None = None
    benchmark_version: str | None = None


class DomainCapability(FrozenProfileModel):
    domain: str = Field(min_length=1)
    task_type: DomainTaskType
    eval_set_version: str | None = None
    expert_review_status: str | None = None
    calibration_error: float | None = None
    known_failure_modes: tuple[str, ...] = ()
    tool_requirements: tuple[str, ...] = ()
    freshness_requirement: str | None = None
    eligibility: CapabilityStatus


class ModelProfile(FrozenProfileModel):
    model_id: str = Field(min_length=1)
    model_family: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    status: ModelStatus
    role_eligibility: RoleEligibility
    controller_qualification: ControllerQualification | None = None
    domain_capabilities: tuple[DomainCapability, ...] = ()


def parse_model_profile(data: dict[str, Any]) -> ModelProfile:
    errors = validate_instance(data, "model-profile.schema.json")
    if errors:
        raise ContractValidationError("model-profile.schema.json: " + "; ".join(errors))
    model = ModelProfile.model_validate(data)
    normalized = model.to_document()
    normalized_errors = validate_instance(normalized, "model-profile.schema.json")
    if normalized_errors:
        raise ContractValidationError(
            "normalized model-profile.schema.json: " + "; ".join(normalized_errors)
        )
    return model
