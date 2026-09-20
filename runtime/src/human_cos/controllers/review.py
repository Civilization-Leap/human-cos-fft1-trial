"""S5-CDE2 immutable Framing Review preserving both A1/A2 source frames."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from human_cos.runtime.run import canonical_document_sha256

from .framing import (
    FramingIntegrityError,
    FramingRequirement,
    InitialFramingRecord,
    assert_at12_dual_framing_ready,
)

ComparableField = Literal[
    "actors",
    "domains",
    "initial_mechanism_hypotheses",
    "key_unknowns",
    "benefit_paths",
    "harm_risk_paths",
    "capability_gaps",
]


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("S5-CDE2 timestamps require timezone-aware datetimes")
    return value


class _FrozenReviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class FramingFieldComparison(_FrozenReviewModel):
    field: ComparableField
    shared: tuple[str, ...]
    a1_only: tuple[str, ...]
    a2_only: tuple[str, ...]


class FramingReviewPayload(_FrozenReviewModel):
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    protocol_version: str = Field(min_length=1)
    requirement_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    a1_record_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    a2_record_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    a1_run_id: str = Field(min_length=1)
    a2_run_id: str = Field(min_length=1)
    problem_framing_a1: str = Field(min_length=1)
    problem_framing_a2: str = Field(min_length=1)
    problem_framing_same: bool
    field_comparisons: tuple[FramingFieldComparison, ...]
    omitted_by_a1: tuple[ComparableField, ...]
    omitted_by_a2: tuple[ComparableField, ...]
    unresolved_difference_fields: tuple[str, ...]
    reviewed_at: datetime

    _reviewed_at_must_be_aware = field_validator("reviewed_at")(_aware)


class FramingReview(FramingReviewPayload):
    review_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"review_hash"}, exclude_none=True)
        if self.review_hash != canonical_document_sha256(payload):
            raise FramingIntegrityError("FramingReview review_hash does not match payload")


_COMPARABLE_FIELDS: tuple[ComparableField, ...] = (
    "actors",
    "domains",
    "initial_mechanism_hypotheses",
    "key_unknowns",
    "benefit_paths",
    "harm_risk_paths",
    "capability_gaps",
)


def _compare_values(
    field: ComparableField,
    a1_values: tuple[str, ...],
    a2_values: tuple[str, ...],
) -> FramingFieldComparison:
    a1 = set(a1_values)
    a2 = set(a2_values)
    return FramingFieldComparison(
        field=field,
        shared=tuple(sorted(a1 & a2)),
        a1_only=tuple(sorted(a1 - a2)),
        a2_only=tuple(sorted(a2 - a1)),
    )


def _exact_a1_a2(
    records: tuple[InitialFramingRecord, ...],
) -> tuple[InitialFramingRecord, InitialFramingRecord]:
    a1 = tuple(record for record in records if record.lane == "A1")
    a2 = tuple(record for record in records if record.lane == "A2")
    if len(a1) != 1 or len(a2) != 1 or len(records) != 2:
        raise FramingIntegrityError(
            "Framing Review requires exactly one frozen A1 and one frozen A2"
        )
    return a1[0], a2[0]


def build_framing_review(
    *,
    requirement: FramingRequirement,
    records: tuple[InitialFramingRecord, ...],
    reviewed_at: datetime,
) -> FramingReview:
    """Create a deterministic comparison without voting away either source frame."""
    requirement.assert_integrity()
    a1, a2 = _exact_a1_a2(records)

    assert_at12_dual_framing_ready(requirement, records)
    if a1.run_id == a2.run_id or a1.context_manifest_hash == a2.context_manifest_hash:
        raise FramingIntegrityError("Framing Review requires distinct A1/A2 runs and contexts")

    comparisons = tuple(
        _compare_values(
            field,
            getattr(a1.content, field),
            getattr(a2.content, field),
        )
        for field in _COMPARABLE_FIELDS
    )
    omitted_by_a1 = tuple(
        comparison.field
        for comparison in comparisons
        if not getattr(a1.content, comparison.field) and bool(getattr(a2.content, comparison.field))
    )
    omitted_by_a2 = tuple(
        comparison.field
        for comparison in comparisons
        if not getattr(a2.content, comparison.field) and bool(getattr(a1.content, comparison.field))
    )
    unresolved: list[str] = []
    if a1.content.problem_framing != a2.content.problem_framing:
        unresolved.append("problem_framing")
    unresolved.extend(
        comparison.field for comparison in comparisons if comparison.a1_only or comparison.a2_only
    )

    payload = FramingReviewPayload(
        case_id=requirement.case_id,
        case_revision=requirement.case_revision,
        protocol_version=requirement.protocol_version,
        requirement_hash=requirement.record_hash,
        a1_record_hash=a1.record_hash,
        a2_record_hash=a2.record_hash,
        a1_run_id=a1.run_id,
        a2_run_id=a2.run_id,
        problem_framing_a1=a1.content.problem_framing,
        problem_framing_a2=a2.content.problem_framing,
        problem_framing_same=a1.content.problem_framing == a2.content.problem_framing,
        field_comparisons=comparisons,
        omitted_by_a1=omitted_by_a1,
        omitted_by_a2=omitted_by_a2,
        unresolved_difference_fields=tuple(unresolved),
        reviewed_at=reviewed_at,
    )
    document = payload.to_document()
    return FramingReview(**document, review_hash=canonical_document_sha256(document))


def assert_framing_review_binding(
    *,
    review: FramingReview,
    requirement: FramingRequirement,
    records: tuple[InitialFramingRecord, ...],
) -> None:
    """Fail closed unless Review binds the exact requirement and exact A1/A2 records."""
    review.assert_integrity()
    requirement.assert_integrity()
    a1, a2 = _exact_a1_a2(records)
    assert_at12_dual_framing_ready(requirement, records)
    for record in records:
        record.assert_integrity()

    if (review.case_id, review.case_revision, review.protocol_version) != (
        requirement.case_id,
        requirement.case_revision,
        requirement.protocol_version,
    ):
        raise FramingIntegrityError(
            "Framing Review Case/protocol binding does not match requirement"
        )
    if review.requirement_hash != requirement.record_hash:
        raise FramingIntegrityError("Framing Review requirement_hash does not match")
    if (review.a1_record_hash, review.a2_record_hash) != (
        a1.record_hash,
        a2.record_hash,
    ):
        raise FramingIntegrityError("Framing Review source record hashes do not match A1/A2")
    if (review.a1_run_id, review.a2_run_id) != (a1.run_id, a2.run_id):
        raise FramingIntegrityError("Framing Review source run IDs do not match A1/A2")
