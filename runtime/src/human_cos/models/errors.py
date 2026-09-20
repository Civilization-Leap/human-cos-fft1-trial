"""Typed S2-L adapter and qualification failures."""

from __future__ import annotations

from human_cos.models.types import AdapterErrorCode, ModelIdentity


class ModelAdapterError(RuntimeError):
    def __init__(
        self,
        code: AdapterErrorCode,
        identity: ModelIdentity,
        message: str,
        *,
        retryable: bool,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.identity = identity
        self.retryable = retryable


class RegistryError(ValueError):
    """Base class for deterministic registry failures."""


class UnknownModelError(RegistryError):
    """Raised when a model identity is not registered."""


class IdentityMismatchError(RegistryError):
    """Raised when an adapter identity disagrees with its registered profile."""


class EligibilityError(PermissionError):
    """Raised when a model is not eligible for a requested restricted role."""


class CapabilityGapError(EligibilityError):
    """Raised when no registered qualified domain capability satisfies the request."""

    def __init__(self, message: str, gap: object) -> None:
        super().__init__(message)
        self.gap = gap
