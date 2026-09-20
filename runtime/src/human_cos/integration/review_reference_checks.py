"""Pure checks of declared RFC0002 references; never fresh-evidence admission.

A self-consistent fabricated inventory can pass. This API does NOT authenticate
its supplied pins/expectations or inspect full S5/Run/Context payloads. Future
source-payload, host-scope and runtime/typed-store gates remain mandatory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import TypeAdapter

from human_cos.models.independence import compare_identity_independence
from human_cos.runtime.run import RunIndependence

from .review_references import (
    Hash,
    ReviewBindingKey,
    ReviewInvocationKey,
    ReviewProducerExpectation,
    ReviewReferenceInventory,
    _Value,
    require,
    revalidate_value,
)

_HASH_ADAPTER: TypeAdapter[str] = TypeAdapter(Hash)


class ReviewReferencePins(_Value):
    """Caller-supplied content pins, not an authenticated launch-control handle."""

    plan_hash: Hash
    scope_hash: Hash
    reference_hash: Hash


@dataclass(frozen=True)
class ReviewIdentityRelation:
    lane: str
    producer_run_id: str
    producer_record_hash: str
    model_id_different: bool
    family_label_different: bool
    provider_label_different: bool  # Structurally false for these Mock-only identities.
    identity_basis: Literal["DECLARED_MOCK_IDENTITIES"] = field(
        default="DECLARED_MOCK_IDENTITIES", init=False
    )
    independent_execution_established: Literal[False] = field(default=False, init=False)


@dataclass(frozen=True)
class ReviewReferenceCheck:
    reference_hash: str
    relations: tuple[ReviewIdentityRelation, ...]
    status: Literal["REFERENCE_CONSISTENCY_ONLY"] = field(
        default="REFERENCE_CONSISTENCY_ONLY", init=False
    )
    input_approval_verified: Literal[False] = field(default=False, init=False)
    scope_origin_verified: Literal[False] = field(default=False, init=False)
    full_source_payloads_verified: Literal[False] = field(default=False, init=False)
    fresh_execution_verified: Literal[False] = field(default=False, init=False)
    execution_authorized: Literal[False] = field(default=False, init=False)


def verify_review_references(
    inventory: ReviewReferenceInventory,
    *,
    expected: tuple[ReviewProducerExpectation, ...],
    pins: ReviewReferencePins,
) -> ReviewReferenceCheck:
    """Compare every declared producer, not a favorable selected comparator.

    Production expectations must come from approved immutable input, not runtime
    return values. This slice neither supplies nor proves that derivation. It has
    no runtime caller and never issues a VerifiedS6ReviewScope or admission token.
    """
    inventory = revalidate_value(inventory)
    inventory.assert_integrity()
    pins = revalidate_value(pins)
    require(
        (inventory.plan_hash, inventory.scope_hash, inventory.reference_hash)
        == (pins.plan_hash, pins.scope_hash, pins.reference_hash),
        "EXPECTED_REFERENCE_PINS_MISMATCH",
    )
    expected = tuple(revalidate_value(item) for item in expected)
    require(
        tuple(item.lane for item in expected) == ("A1", "A2", "DOMAIN"),
        "COMPLETE_EXPECTED_PRODUCERS_REQUIRED",
    )
    relations = []
    for actual, anchor in zip(inventory.producers, expected, strict=True):
        require(
            (
                actual.lane,
                actual.run_id,
                actual.identity,
                actual.profile_sha256,
                actual.raw_output_sha256,
            )
            == (
                anchor.lane,
                anchor.run_id,
                anchor.identity,
                anchor.profile_sha256,
                anchor.raw_output_sha256,
            ),
            "PRODUCER_EXPECTATION_MISMATCH",
        )
        comparison = compare_identity_independence(
            inventory.reviewer.as_identity(), actual.identity.as_identity()
        )
        relations.append(
            ReviewIdentityRelation(
                lane=actual.lane,
                producer_run_id=actual.run_id,
                producer_record_hash=actual.record_hash,
                model_id_different=inventory.reviewer.model_id != actual.identity.model_id,
                family_label_different=comparison.model_family,
                provider_label_different=comparison.provider,
            )
        )
    return ReviewReferenceCheck(inventory.reference_hash, tuple(relations))


def assert_review_key_correspondence(
    invocation: ReviewInvocationKey, binding: ReviewBindingKey
) -> None:
    invocation, binding = revalidate_value(invocation), revalidate_value(binding)
    require(invocation.invocation_tuple() == binding.invocation_tuple(), "REVIEW_KEY_MISMATCH")


def assert_unique_review_bindings(entries: tuple[tuple[ReviewBindingKey, str], ...]) -> None:
    """Reject duplicates only within supplied data, not a database or other runs.

    Cannot prove absence of other rows/concurrent writers. SQL PK/UNIQUE/FK and
    complete-scope queries still need their own PostgreSQL implementation tests.
    Malformed values raise Pydantic ValidationError. Explicit duplicate conflicts
    raise ReviewReferenceError in key, invocation, then task precedence.
    """
    keys: set[tuple[str, int, str, str, str]] = set()
    invocations: set[str] = set()
    tasks: set[tuple[str, int, str, str]] = set()
    for candidate, invocation_hash in entries:
        key = revalidate_value(candidate)
        ref = _HASH_ADAPTER.validate_python(invocation_hash)
        require(key.binding_tuple() not in keys, "DUPLICATE_BINDING_KEY")
        require(ref not in invocations, "DUPLICATE_INVOCATION_RESULT")
        require(key.invocation_tuple() not in tasks, "DUPLICATE_TASK_RESULT")
        keys.add(key.binding_tuple())
        invocations.add(ref)
        tasks.add(key.invocation_tuple())


def conservative_s6_run_independence() -> RunIndependence:
    """Construct a new value, never import or modify the old S5 constant."""
    return RunIndependence(
        context=False,
        prompt=False,
        model_family=False,
        provider=False,
        evidence_path=False,
        expert=None,
    )


def assert_conservative_s6_run_independence(value: RunIndependence) -> None:
    flags = (value.context, value.prompt, value.model_family, value.provider, value.evidence_path)
    require(
        all(type(flag) is bool and flag is False for flag in flags) and value.expert is None,
        "NONCONSERVATIVE_S6_RUN_INDEPENDENCE",
    )
