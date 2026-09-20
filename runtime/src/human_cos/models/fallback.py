"""Explicit S2-L fallback with re-qualification and visible provenance."""

from __future__ import annotations

from human_cos.models.adapters.base import ModelAdapter
from human_cos.models.errors import IdentityMismatchError, ModelAdapterError
from human_cos.models.qualification import (
    EligibilityRequirement,
    QualificationGate,
    assert_requirement,
)
from human_cos.models.registry import ModelRegistry
from human_cos.models.types import InvocationOutcome, ModelRequest, ModelResponse


def _assert_adapter(
    registry: ModelRegistry,
    gate: QualificationGate,
    adapter: ModelAdapter,
    requirement: EligibilityRequirement,
) -> None:
    registry.assert_identity(adapter.identity)
    assert_requirement(gate, adapter.identity.model_id, requirement)


def _invoke_checked(
    adapter: ModelAdapter,
    request: ModelRequest,
    registry: ModelRegistry,
) -> ModelResponse:
    response = adapter.invoke(request)
    if response.identity != adapter.identity:
        raise IdentityMismatchError(
            "adapter returned a response identity different from its declared identity"
        )
    registry.assert_identity(response.identity)
    return response


def invoke_with_explicit_fallback(
    *,
    primary: ModelAdapter,
    fallback: ModelAdapter,
    request: ModelRequest,
    registry: ModelRegistry,
    gate: QualificationGate,
    requirement: EligibilityRequirement,
) -> InvocationOutcome:
    """Invoke primary; on a retryable provider failure explicitly try fallback.

    The fallback is never silent: the outcome carries ``fallback_from`` and the
    primary error code. Primary and fallback identities are checked before and
    after invocation, and fallback qualification is independently rechecked.
    """
    _assert_adapter(registry, gate, primary, requirement)
    try:
        response = _invoke_checked(primary, request, registry)
        return InvocationOutcome(response=response)
    except ModelAdapterError as exc:
        if not exc.retryable:
            raise
        _assert_adapter(registry, gate, fallback, requirement)
        response = _invoke_checked(fallback, request, registry)
        return InvocationOutcome(
            response=response,
            fallback_from=primary.identity.model_id,
            primary_error_code=exc.code,
        )
