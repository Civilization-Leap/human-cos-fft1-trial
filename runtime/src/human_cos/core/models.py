"""Validated deeply immutable application models for S1 frozen data contracts.

The JSON Schemas in ``schemas/`` remain the source of truth. Internal tuples
provide deep immutability while Pydantic's JSON serialization still emits the
arrays required by the frozen contracts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from human_cos.protocols.schema_loader import validate_instance


class ContractValidationError(ValueError):
    """Raised when an application document violates a frozen JSON contract."""


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Human-COS temporal boundaries require timezone-aware datetimes")
    return value


def _require_optional_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return _require_aware(value)


class Visibility(FrozenModel):
    public: bool
    actor_ids: tuple[str, ...]
    role_ids: tuple[str, ...]


class PhaseProfile(FrozenModel):
    civilization_stage: Literal["STARTUP", "TRANSITION", "STABLE", "SELF_MAINTAINING"]
    case_phase: Literal["DISCOVERY", "ESCALATION", "CRITICAL", "RECOVERY", "OTHER"]
    policy_constraints_profile: str | None = None
    reversibility_priority: str | None = None
    rights_and_governance_constraints: tuple[str, ...] | None = None
    emergency_scope: str | None = None


class TimeBoundary(FrozenModel):
    T0: datetime
    timezone: str | None = None

    _t0_must_be_aware = field_validator("T0")(_require_aware)


class Case(FrozenModel):
    case_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    case_mode: Literal[
        "HISTORICAL_BLIND_EVAL",
        "LIVE_FORESIGHT",
        "MECHANISM_BENCHMARK",
        "SCENARIO_STRESS_TEST",
    ]
    question: str = Field(min_length=1)
    protocol_version: str
    phase_profile: PhaseProfile
    time_boundary: TimeBoundary
    actors: tuple[str, ...] | None = None
    domains: tuple[str, ...] | None = None
    publication_policy: Literal["PUBLIC", "RESTRICTED", "WITHHELD"]
    state: str | None = None
    owner: str | None = None


class Evidence(FrozenModel):
    evidence_id: str
    case_id: str
    content: str | None = None
    source_type: str
    source_uri_or_ref: str | None = None
    source_timestamp: datetime
    ingested_at: datetime
    available_from: datetime
    available_until: datetime | None = None
    visibility: Visibility
    temporal_class: Literal["PRE_T0", "POST_T0", "LATER_VERIFICATION_OF_PRE_T0_FACT"]
    fact_status: Literal["OBSERVED", "REPORTED", "INFERRED", "DISPUTED"]
    source_quality: float = Field(ge=0, le=1)
    fact_confidence: float = Field(ge=0, le=1)
    snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    supersedes: tuple[str, ...] | None = None
    tags: tuple[str, ...] | None = None
    evidence_conflict_ids: tuple[str, ...] | None = None

    _timestamps_must_be_aware = field_validator(
        "source_timestamp", "ingested_at", "available_from"
    )(_require_aware)
    _available_until_must_be_aware = field_validator("available_until")(_require_optional_aware)


class ContextManifest(FrozenModel):
    context_manifest_id: str
    case_id: str
    run_id: str
    stage: str
    role_id: str
    evidence_ids: tuple[str, ...]
    prior_run_ids: tuple[str, ...]
    tool_permissions: tuple[str, ...]
    protocol_version: str
    model_id: str
    prompt_version: str
    forbidden_scopes: tuple[str, ...]
    time_boundary: datetime | None = None
    hash_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    _time_boundary_must_be_aware = field_validator("time_boundary")(_require_optional_aware)


TModel = TypeVar("TModel", bound=FrozenModel)


def _parse_frozen(model_type: type[TModel], schema_name: str, data: dict[str, Any]) -> TModel:
    errors = validate_instance(data, schema_name)
    if errors:
        raise ContractValidationError(f"{schema_name}: " + "; ".join(errors))
    model = model_type.model_validate(data)
    normalized = model.to_document()
    normalized_errors = validate_instance(normalized, schema_name)
    if normalized_errors:
        raise ContractValidationError(f"normalized {schema_name}: " + "; ".join(normalized_errors))
    return model


def parse_case(data: dict[str, Any]) -> Case:
    return _parse_frozen(Case, "case.schema.json", data)


def parse_evidence(data: dict[str, Any]) -> Evidence:
    return _parse_frozen(Evidence, "evidence.schema.json", data)


def parse_context_manifest(data: dict[str, Any]) -> ContextManifest:
    return _parse_frozen(ContextManifest, "context-manifest.schema.json", data)
