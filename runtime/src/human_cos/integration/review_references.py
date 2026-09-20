"""RFC0002 reference-layer values; never a trusted scope or run receipt.

This first slice represents keys and declared references. It does not implement
S6ReviewScopeRegistrationV1, invocation/binding records, storage, or a fresh-
evidence gate. Hashes identify content; they do not prove existence or execution.
"""

from __future__ import annotations

import json
import math
from typing import Annotated, Any, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from human_cos.models.types import ModelIdentity
from human_cos.runtime.run import canonical_document_bytes, canonical_document_sha256

Hash = Annotated[str, Field(strict=True, pattern=r"^[a-f0-9]{64}$")]
Token = Annotated[str, Field(strict=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]
Revision = Annotated[int, Field(strict=True, ge=1)]
Attempt = Annotated[str, Field(strict=True, pattern=r"^[a-f0-9]{32}$")]
Lane = Literal["A1", "A2", "DOMAIN"]
# Safety ceiling for this small reference representation, not operator accounting.
MAX_REFERENCE_DOCUMENT_BYTES = 131_072


class ReviewReferenceError(ValueError):
    """Fixed reasons from explicit checks and the sanitized public byte parser.

    Internal value construction/revalidation may instead raise Pydantic
    ValidationError; callers must not treat this class as every rejection path.
    This is not a production runtime error taxonomy.
    """


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ReviewReferenceError(reason)


class _Value(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=False)


class ReviewScopeKey(_Value):
    case_id: Token
    case_revision: Revision
    attempt_id: Attempt

    def as_tuple(self) -> tuple[str, int, str]:
        return self.case_id, self.case_revision, self.attempt_id


class ReviewInvocationKey(ReviewScopeKey):
    task_hash: Hash

    def invocation_tuple(self) -> tuple[str, int, str, str]:
        return *self.as_tuple(), self.task_hash


class ReviewBindingKey(ReviewInvocationKey):
    response_hash: Hash

    def binding_tuple(self) -> tuple[str, int, str, str, str]:
        return *self.invocation_tuple(), self.response_hash


class ReviewMockIdentity(_Value):
    model_id: Token
    model_family: Annotated[str, Field(strict=True, min_length=1, max_length=256)]
    provider: Literal["mock"]

    @model_validator(mode="after")
    def _nonblank_family(self) -> ReviewMockIdentity:
        require(bool(self.model_family.strip()), "EMPTY_MODEL_FAMILY")
        return self

    def as_identity(self) -> ModelIdentity:
        return ModelIdentity(self.provider, self.model_id, self.model_family)


class ReviewProducerExpectation(_Value):
    """Declared anchors, NOT verifier-owned approved-input provenance.

    The future host bridge must derive these from approved immutable input bytes.
    Passing this value object never supplies that authority.
    """

    lane: Lane
    run_id: Token
    identity: ReviewMockIdentity
    profile_sha256: Hash
    raw_output_sha256: Hash


class ReviewProducerReference(ReviewProducerExpectation):
    """One generation edge; A1/A2 are lanes, not top-level SourceKind values."""

    record_hash: Hash
    frozen_run_version: Revision
    frozen_run_hash: Hash
    context_manifest_hash: Hash
    context_admission_hash: Hash
    raw_output_ref: Token


class ReviewDirectSource(_Value):
    kind: Literal["FRAMING", "DOMAIN_OUTPUT"]
    ref: Token
    sha256: Hash


class ReviewReferenceInventoryPayload(_Value):
    """Non-authoritative reference inventory, not a complete scope registration."""

    record_version: Literal["s6-review-reference-inventory-v1"]
    scope: ReviewScopeKey
    protocol_version: Literal["0.1"]
    plan_hash: Hash
    scope_hash: Hash
    task_hash: Hash
    reviewer_run_id: Token
    reviewer_context_manifest_hash: Hash
    reviewer: ReviewMockIdentity
    reviewer_profile_sha256: Hash
    direct_sources: Annotated[tuple[ReviewDirectSource, ...], Field(min_length=2, max_length=2)]
    producers: Annotated[tuple[ReviewProducerReference, ...], Field(min_length=3, max_length=3)]

    @model_validator(mode="after")
    def _exact_topology(self) -> ReviewReferenceInventoryPayload:
        require(
            tuple(source.kind for source in self.direct_sources) == ("FRAMING", "DOMAIN_OUTPUT"),
            "TWO_DIRECT_SOURCE_KINDS_REQUIRED",
        )
        require(
            tuple(item.lane for item in self.producers) == ("A1", "A2", "DOMAIN"),
            "THREE_PRODUCER_LANES_REQUIRED",
        )
        require(
            len({item.run_id for item in self.producers}) == 3,
            "DISTINCT_PRODUCER_RUNS_REQUIRED",
        )
        require(
            len({item.context_manifest_hash for item in self.producers}) == 3,
            "DISTINCT_PRODUCER_CONTEXTS_REQUIRED",
        )
        # These identify artifacts bound to the already-distinct Run/Context IDs.
        # Equal output bytes or shared profiles, unlike these identities, are legal.
        require(
            len({item.record_hash for item in self.producers}) == 3,
            "DISTINCT_PRODUCER_RECORDS_REQUIRED",
        )
        require(
            len({item.frozen_run_hash for item in self.producers}) == 3,
            "DISTINCT_PRODUCER_FROZEN_RUNS_REQUIRED",
        )
        require(
            len({item.context_admission_hash for item in self.producers}) == 3,
            "DISTINCT_PRODUCER_ADMISSIONS_REQUIRED",
        )
        require(
            len({item.raw_output_ref for item in self.producers}) == 3,
            "DISTINCT_PRODUCER_RAW_REFS_REQUIRED",
        )
        # FRAMING names a FramingReview, not either A1/A2 generation record.
        # Its actual A1/A2 links are deliberately unchecked without that payload.
        require(
            self.direct_sources[1].sha256 == self.producers[2].record_hash,
            "DIRECT_DOMAIN_REFERENCE_MISMATCH",
        )
        require(
            self.reviewer_run_id not in {item.run_id for item in self.producers},
            "REVIEWER_RUN_IS_A_PRODUCER",
        )
        require(
            self.reviewer_context_manifest_hash
            not in {item.context_manifest_hash for item in self.producers},
            "REVIEWER_CONTEXT_IS_A_PRODUCER_CONTEXT",
        )
        return self


class ReviewReferenceInventory(ReviewReferenceInventoryPayload):
    reference_hash: Hash

    def assert_integrity(self) -> None:
        # Revalidate even model_copy/model_construct or object.__setattr__ bypasses.
        # Validate Python values before JSON can normalize an invalid bool to int.
        claimed = self.reference_hash
        payload = ReviewReferenceInventoryPayload.model_validate(
            self.model_dump(mode="python", exclude={"reference_hash"})
        )
        require(
            claimed == canonical_document_sha256(payload.to_document()),
            "REFERENCE_HASH_MISMATCH",
        )
        require(
            len(canonical_document_bytes(self.to_document())) <= MAX_REFERENCE_DOCUMENT_BYTES,
            "REFERENCE_DOCUMENT_TOO_LARGE",
        )


def freeze_review_reference_inventory(
    payload: ReviewReferenceInventoryPayload,
) -> ReviewReferenceInventory:
    """Content freeze only: no file, model, environment, approval or DB operation."""
    checked = ReviewReferenceInventoryPayload.model_validate(payload.model_dump(mode="python"))
    document = checked.to_document()
    record = ReviewReferenceInventory(
        **document, reference_hash=canonical_document_sha256(document)
    )
    record.assert_integrity()
    return record


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in values, "DUPLICATE_JSON_KEY")
        values[key] = value
    return values


def _reject_constant(value: str) -> None:
    raise ReviewReferenceError("NONFINITE_JSON_VALUE")


TValue = TypeVar("TValue", bound=_Value)


def revalidate_value(value: TValue) -> TValue:
    # JSON serialization can coerce a validation-bypassed bool into an integer.
    return type(value).model_validate(value.model_dump(mode="python", exclude_none=False))


def parse_review_reference_inventory(data: bytes) -> ReviewReferenceInventory:
    """Strict bounded JSON loading; errors never echo input document bodies."""
    try:
        require(type(data) is bytes, "REFERENCE_BYTES_REQUIRED")
        require(0 < len(data) <= MAX_REFERENCE_DOCUMENT_BYTES, "REFERENCE_DOCUMENT_SIZE")
        document = json.loads(
            data.decode("utf-8"), object_pairs_hook=_unique_pairs, parse_constant=_reject_constant
        )
        require(type(document) is dict, "REFERENCE_OBJECT_REQUIRED")
        pending = [(document, 0)]
        while pending:
            item, depth = pending.pop()
            require(depth <= 16, "REFERENCE_DOCUMENT_DEPTH")
            if isinstance(item, dict):
                pending.extend((child, depth + 1) for child in item.values())
                pending.extend((key, depth + 1) for key in item)
            elif isinstance(item, list):
                pending.extend((child, depth + 1) for child in item)
            elif isinstance(item, str):
                item.encode("utf-8")  # Reject lone surrogates, including unknown fields.
            elif isinstance(item, float):
                require(math.isfinite(item), "NONFINITE_JSON_VALUE")
        record = ReviewReferenceInventory.model_validate(document)
        record.assert_integrity()
        return record
    except (ValueError, TypeError, RecursionError, OverflowError):
        raise ReviewReferenceError("INVALID_REVIEW_REFERENCE_DOCUMENT") from None
