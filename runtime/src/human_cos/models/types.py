"""S2-L model identity, adapter, fallback, and eligibility value objects."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum


class AdapterErrorCode(str, Enum):
    AUTHENTICATION = "AUTHENTICATION"
    RATE_LIMIT = "RATE_LIMIT"
    TIMEOUT = "TIMEOUT"
    CONTENT_FILTER = "CONTENT_FILTER"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    CONFIGURATION = "CONFIGURATION"


@dataclass(frozen=True)
class ModelIdentity:
    provider: str
    model_id: str
    model_family: str

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("provider must be non-empty")
        if not self.model_id.strip():
            raise ValueError("model_id must be non-empty")
        if not self.model_family.strip():
            raise ValueError("model_family must be non-empty")


@dataclass(frozen=True)
class ModelRequest:
    input_text: str
    max_output_tokens: int = 1024

    def __post_init__(self) -> None:
        if not self.input_text:
            raise ValueError("input_text must be non-empty")
        if self.max_output_tokens < 1:
            raise ValueError("max_output_tokens must be >= 1")


@dataclass(frozen=True)
class ModelResponse:
    identity: ModelIdentity
    output_text: str
    finish_reason: str | None = None
    provider_request_id: str | None = None
    usage: Mapping[str, object] | None = None


@dataclass(frozen=True)
class InvocationOutcome:
    response: ModelResponse
    fallback_from: str | None = None
    primary_error_code: AdapterErrorCode | None = None


@dataclass(frozen=True)
class IdentityIndependence:
    model_family: bool
    provider: bool
