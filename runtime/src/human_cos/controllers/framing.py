"""S5-CDE1 immutable Initial Framing contracts and AT-12 readiness gate."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from human_cos.core.models import Case, ContextManifest
from human_cos.runtime.run import RunManifest, canonical_document_sha256

FramingLane = Literal["A1", "A2"]


class FramingIntegrityError(ValueError):
    """A framing sidecar is inconsistent with its immutable lineage."""


class DualFramingBlocked(RuntimeError):
    """AT-12 blocks progression because required independent framings are incomplete."""


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("S5-CDE1 timestamps require timezone-aware datetimes")
    return value


class _FrozenFramingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class FramingRequirementPayload(_FrozenFramingModel):
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    dual_framing_required: bool
    authority_ref: str = Field(min_length=1)
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class FramingRequirement(FramingRequirementPayload):
    record_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"record_hash"}, exclude_none=True)
        if self.record_hash != canonical_document_sha256(payload):
            raise FramingIntegrityError("FramingRequirement record_hash does not match payload")


class InitialFramingContent(_FrozenFramingModel):
    problem_framing: str = Field(min_length=1)
    actors: tuple[str, ...] = ()
    domains: tuple[str, ...] = ()
    initial_mechanism_hypotheses: tuple[str, ...] = ()
    key_unknowns: tuple[str, ...] = ()
    benefit_paths: tuple[str, ...] = ()
    harm_risk_paths: tuple[str, ...] = ()
    capability_gaps: tuple[str, ...] = ()


class InitialFramingPayload(_FrozenFramingModel):
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    lane: FramingLane
    run_id: str = Field(min_length=1)
    context_manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    independent_prior_run_ids: tuple[str, ...]
    model_id: str = Field(min_length=1)
    model_family: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    raw_output_ref: str = Field(min_length=1)
    raw_output_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    structured_output_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    protocol_version: str = Field(min_length=1)
    finished_at: datetime
    content: InitialFramingContent

    _finished_at_must_be_aware = field_validator("finished_at")(_aware)


class InitialFramingRecord(InitialFramingPayload):
    record_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"record_hash"}, exclude_none=True)
        if self.record_hash != canonical_document_sha256(payload):
            raise FramingIntegrityError("InitialFramingRecord record_hash does not match payload")
        if self.independent_prior_run_ids:
            raise FramingIntegrityError("Initial Framing must not contain prior-run disclosure")


class DualFramingReadiness(_FrozenFramingModel):
    ready: bool
    reason: str
    requirement_hash: str
    a1_record_hash: str | None = None
    a2_record_hash: str | None = None


def freeze_framing_requirement(payload: FramingRequirementPayload) -> FramingRequirement:
    document = payload.to_document()
    return FramingRequirement(**document, record_hash=canonical_document_sha256(document))


def freeze_initial_framing_payload(payload: InitialFramingPayload) -> InitialFramingRecord:
    if payload.independent_prior_run_ids:
        raise FramingIntegrityError("Initial Framing cannot freeze with prior-run disclosure")
    document = payload.to_document()
    return InitialFramingRecord(**document, record_hash=canonical_document_sha256(document))


def bind_initial_framing(
    *,
    case: Case,
    lane: FramingLane,
    content: InitialFramingContent,
    frozen_run: RunManifest,
    context_manifest: ContextManifest,
) -> InitialFramingRecord:
    """Bind structured framing to an already frozen trusted Controller run."""
    if frozen_run.case_id != case.case_id:
        raise FramingIntegrityError("Run Case does not match Initial Framing Case")
    if frozen_run.protocol_version != case.protocol_version:
        raise FramingIntegrityError("Run protocol version does not match Case")
    if frozen_run.stage != "FRAMING_INDEPENDENT":
        raise FramingIntegrityError("Initial Framing requires FRAMING_INDEPENDENT run")
    if frozen_run.role_type != "meta_controller":
        raise FramingIntegrityError("Initial Framing requires meta_controller run")
    if frozen_run.status != "FROZEN":
        raise FramingIntegrityError("Initial Framing requires a frozen Run Manifest")
    if (
        frozen_run.raw_output_ref is None
        or frozen_run.raw_output_hash is None
        or frozen_run.structured_output_hash is None
        or frozen_run.finished_at is None
    ):
        raise FramingIntegrityError("frozen Controller run is missing output lineage")
    if context_manifest.case_id != case.case_id or context_manifest.run_id != frozen_run.run_id:
        raise FramingIntegrityError("Context Manifest does not bind the same Case/Run")
    if context_manifest.stage != "FRAMING_INDEPENDENT":
        raise FramingIntegrityError("Context Manifest is not an Initial Framing context")
    if context_manifest.hash_sha256 != frozen_run.context_manifest_hash:
        raise FramingIntegrityError("Context hash does not match frozen Run Manifest")
    if context_manifest.prior_run_ids:
        raise FramingIntegrityError("A1/A2 independent framing cannot see prior runs")

    return freeze_initial_framing_payload(
        InitialFramingPayload(
            case_id=case.case_id,
            case_revision=case.revision,
            lane=lane,
            run_id=frozen_run.run_id,
            context_manifest_hash=frozen_run.context_manifest_hash,
            independent_prior_run_ids=context_manifest.prior_run_ids,
            model_id=frozen_run.model_id,
            model_family=frozen_run.model_family,
            provider=frozen_run.provider,
            raw_output_ref=frozen_run.raw_output_ref,
            raw_output_hash=frozen_run.raw_output_hash,
            structured_output_hash=frozen_run.structured_output_hash,
            protocol_version=frozen_run.protocol_version,
            finished_at=frozen_run.finished_at,
            content=content,
        )
    )


def evaluate_at12_dual_framing(
    requirement: FramingRequirement,
    records: tuple[InitialFramingRecord, ...],
) -> DualFramingReadiness:
    """Evaluate only the S5-CDE1 portion of AT-12; no state transition occurs here."""
    requirement.assert_integrity()
    for record in records:
        record.assert_integrity()
        if (record.case_id, record.case_revision) != (
            requirement.case_id,
            requirement.case_revision,
        ):
            raise FramingIntegrityError("Initial Framing belongs to a different Case revision")
        if record.protocol_version != requirement.protocol_version:
            raise FramingIntegrityError("Initial Framing protocol version differs from requirement")

    if not requirement.dual_framing_required:
        return DualFramingReadiness(
            ready=True,
            reason="explicit policy fact does not require Dual Framing",
            requirement_hash=requirement.record_hash,
        )

    a1 = tuple(record for record in records if record.lane == "A1")
    a2 = tuple(record for record in records if record.lane == "A2")
    if len(a1) != 1 or len(a2) != 1:
        return DualFramingReadiness(
            ready=False,
            reason="AT-12 requires exactly one frozen A1 and one frozen A2 framing",
            requirement_hash=requirement.record_hash,
        )
    left, right = a1[0], a2[0]
    if left.run_id == right.run_id or left.context_manifest_hash == right.context_manifest_hash:
        return DualFramingReadiness(
            ready=False,
            reason="AT-12 requires distinct independent A1/A2 runs and contexts",
            requirement_hash=requirement.record_hash,
            a1_record_hash=left.record_hash,
            a2_record_hash=right.record_hash,
        )
    return DualFramingReadiness(
        ready=True,
        reason="two distinct frozen independent A1/A2 framings satisfy the CDE1 AT-12 gate",
        requirement_hash=requirement.record_hash,
        a1_record_hash=left.record_hash,
        a2_record_hash=right.record_hash,
    )


def assert_at12_dual_framing_ready(
    requirement: FramingRequirement,
    records: tuple[InitialFramingRecord, ...],
) -> DualFramingReadiness:
    readiness = evaluate_at12_dual_framing(requirement, records)
    if not readiness.ready:
        raise DualFramingBlocked(readiness.reason)
    return readiness
