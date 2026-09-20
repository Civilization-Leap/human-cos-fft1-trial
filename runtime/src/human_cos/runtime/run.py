"""Immutable S3-N Run/RawOutput lineage application models and hash helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from human_cos.core.models import ContractValidationError
from human_cos.protocols.schema_loader import validate_instance

RunStatus = Literal["CREATED", "RUNNING", "FROZEN", "INVALID", "FAILED"]
ActorType = Literal["SYSTEM", "MODEL", "HUMAN"]


def _require_optional_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Human-COS runtime timestamps require timezone-aware datetimes")
    return value


class _FrozenRuntimeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class RunIndependence(_FrozenRuntimeModel):
    context: bool
    prompt: bool
    model_family: bool
    provider: bool
    evidence_path: bool
    expert: bool | None = None


class RunManifest(_FrozenRuntimeModel):
    run_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    role_type: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    model_family: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    protocol_version: str = Field(min_length=1)
    context_manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    prompt_version: str | None = None
    tool_permissions: tuple[str, ...] | None = None
    status: RunStatus
    parent_run_id: str | None = None
    fallback_from: str | None = None
    raw_output_ref: str | None = None
    raw_output_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    structured_output_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    independence: RunIndependence
    started_at: datetime | None = None
    finished_at: datetime | None = None

    _started_at_must_be_aware = field_validator("started_at")(_require_optional_aware)
    _finished_at_must_be_aware = field_validator("finished_at")(_require_optional_aware)


class AuditEvent(_FrozenRuntimeModel):
    event_id: str = Field(min_length=1)
    timestamp: datetime
    actor_type: ActorType
    actor_id: str = Field(min_length=1)
    case_id: str | None = None
    run_id: str | None = None
    event_type: str = Field(min_length=1)
    object_ref: str = Field(min_length=1)
    before_hash: str | None = None
    after_hash: str | None = None
    metadata: dict[str, Any] | None = None
    signature_or_attestation_ref: str | None = None

    @field_validator("timestamp")
    @classmethod
    def _timestamp_must_be_aware(cls, value: datetime) -> datetime:
        checked = _require_optional_aware(value)
        assert checked is not None
        return checked


@dataclass(frozen=True)
class RawOutputRecord:
    output_ref: str
    run_id: str
    content: bytes
    sha256: str


@dataclass(frozen=True)
class ReplayLineage:
    run_id: str
    run_chain: tuple[str, ...]
    snapshots: tuple[RunManifest, ...]
    audit_events: tuple[AuditEvent, ...]


@dataclass(frozen=True)
class LineageComparison:
    same_control_plane: bool
    changed_control_fields: tuple[str, ...]
    changed_output_fields: tuple[str, ...]


class RunTransitionError(ValueError):
    """Run lifecycle or lineage mutation would violate append-only semantics."""


class RunIntegrityError(ValueError):
    """A stored Run snapshot is inconsistent with its bound immutable artifacts."""


def _validate_normalized_contract(
    document: dict[str, Any],
    *,
    schema_name: str,
) -> None:
    errors = validate_instance(document, schema_name)
    if errors:
        raise ContractValidationError(f"normalized {schema_name}: " + "; ".join(errors))


def parse_run_manifest(data: dict[str, Any]) -> RunManifest:
    errors = validate_instance(data, "run-manifest.schema.json")
    if errors:
        raise ContractValidationError("run-manifest.schema.json: " + "; ".join(errors))
    model = RunManifest.model_validate(data)
    _validate_normalized_contract(model.to_document(), schema_name="run-manifest.schema.json")
    return model


def parse_audit_event(data: dict[str, Any]) -> AuditEvent:
    errors = validate_instance(data, "audit-event.schema.json")
    if errors:
        raise ContractValidationError("audit-event.schema.json: " + "; ".join(errors))
    model = AuditEvent.model_validate(data)
    _validate_normalized_contract(model.to_document(), schema_name="audit-event.schema.json")
    return model


def canonical_document_bytes(document: dict[str, Any]) -> bytes:
    return json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_document_sha256(document: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_document_bytes(document)).hexdigest()


def structured_output_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def make_raw_output_record(
    *,
    run_id: str,
    output_ref: str,
    content: str | bytes,
) -> RawOutputRecord:
    if not run_id:
        raise ValueError("run_id must be non-empty")
    if not output_ref:
        raise ValueError("output_ref must be non-empty")
    raw = content.encode("utf-8") if isinstance(content, str) else bytes(content)
    return RawOutputRecord(
        output_ref=output_ref,
        run_id=run_id,
        content=raw,
        sha256=hashlib.sha256(raw).hexdigest(),
    )


_ALLOWED_STATUS_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    "CREATED": frozenset({"RUNNING", "INVALID", "FAILED"}),
    "RUNNING": frozenset({"FROZEN", "INVALID", "FAILED"}),
    "FROZEN": frozenset(),
    "INVALID": frozenset(),
    "FAILED": frozenset(),
}

_STABLE_FIELDS = (
    "case_id",
    "stage",
    "role_type",
    "protocol_version",
    "context_manifest_hash",
    "prompt_version",
    "tool_permissions",
    "parent_run_id",
    "independence",
)


def _identity(manifest: RunManifest) -> tuple[str, str, str]:
    return manifest.model_id, manifest.model_family, manifest.provider


def _assert_progressive_optional(
    previous: str | datetime | None,
    current: str | datetime | None,
    *,
    field_name: str,
) -> None:
    if previous is not None and current != previous:
        raise RunTransitionError(f"{field_name} cannot change after it is recorded")


def validate_run_snapshot_transition(previous: RunManifest, current: RunManifest) -> None:
    if current.run_id != previous.run_id:
        raise RunTransitionError("run_id cannot change across lifecycle snapshots")
    allowed = _ALLOWED_STATUS_TRANSITIONS[previous.status]
    if current.status not in allowed:
        raise RunTransitionError(
            f"invalid Run lifecycle transition: {previous.status} -> {current.status}"
        )

    for field_name in _STABLE_FIELDS:
        if getattr(previous, field_name) != getattr(current, field_name):
            raise RunTransitionError(f"{field_name} cannot change across Run snapshots")

    previous_identity = _identity(previous)
    current_identity = _identity(current)
    if current_identity != previous_identity:
        if current.fallback_from != previous.model_id:
            raise RunTransitionError(
                "model identity replacement requires explicit fallback_from matching "
                "the prior model_id"
            )
        if previous.fallback_from is not None and current.fallback_from != previous.fallback_from:
            raise RunTransitionError("fallback_from cannot be rewritten")
    elif current.fallback_from != previous.fallback_from:
        raise RunTransitionError("fallback_from cannot appear without an identity replacement")

    _assert_progressive_optional(
        previous.raw_output_ref,
        current.raw_output_ref,
        field_name="raw_output_ref",
    )
    _assert_progressive_optional(
        previous.raw_output_hash,
        current.raw_output_hash,
        field_name="raw_output_hash",
    )
    _assert_progressive_optional(
        previous.structured_output_hash,
        current.structured_output_hash,
        field_name="structured_output_hash",
    )
    _assert_progressive_optional(
        previous.started_at,
        current.started_at,
        field_name="started_at",
    )
    _assert_progressive_optional(
        previous.finished_at,
        current.finished_at,
        field_name="finished_at",
    )


_CONTROL_FIELDS = (
    "case_id",
    "stage",
    "role_type",
    "model_id",
    "model_family",
    "provider",
    "protocol_version",
    "context_manifest_hash",
    "prompt_version",
    "tool_permissions",
    "parent_run_id",
    "fallback_from",
    "independence",
)
_OUTPUT_FIELDS = ("raw_output_hash", "structured_output_hash")


def compare_replay_manifests(left: RunManifest, right: RunManifest) -> LineageComparison:
    changed_control = tuple(
        field_name
        for field_name in _CONTROL_FIELDS
        if getattr(left, field_name) != getattr(right, field_name)
    )
    changed_output = tuple(
        field_name
        for field_name in _OUTPUT_FIELDS
        if getattr(left, field_name) != getattr(right, field_name)
    )
    return LineageComparison(
        same_control_plane=not changed_control,
        changed_control_fields=changed_control,
        changed_output_fields=changed_output,
    )
