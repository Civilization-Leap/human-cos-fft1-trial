"""Human-COS S2-L model registry, qualification, and adapter layer."""

from .adapters import AnthropicMessagesAdapter, MockAdapter, ModelAdapter, OpenAIResponsesAdapter
from .errors import (
    CapabilityGapError,
    EligibilityError,
    IdentityMismatchError,
    ModelAdapterError,
    RegistryError,
    UnknownModelError,
)
from .fallback import invoke_with_explicit_fallback
from .independence import compare_identity_independence
from .profile import (
    ControllerQualification,
    DomainCapability,
    DomainTaskType,
    ModelProfile,
    RoleEligibility,
    parse_model_profile,
)
from .qualification import (
    CapabilityGap,
    EligibilityDecision,
    EligibilityRequirement,
    QualificationGate,
)
from .registry import ModelRegistry
from .types import (
    AdapterErrorCode,
    IdentityIndependence,
    InvocationOutcome,
    ModelIdentity,
    ModelRequest,
    ModelResponse,
)

__all__ = [
    "AdapterErrorCode",
    "AnthropicMessagesAdapter",
    "CapabilityGap",
    "CapabilityGapError",
    "ControllerQualification",
    "DomainCapability",
    "DomainTaskType",
    "EligibilityDecision",
    "EligibilityError",
    "EligibilityRequirement",
    "IdentityIndependence",
    "IdentityMismatchError",
    "InvocationOutcome",
    "MockAdapter",
    "ModelAdapter",
    "ModelAdapterError",
    "ModelIdentity",
    "ModelProfile",
    "ModelRegistry",
    "ModelRequest",
    "ModelResponse",
    "OpenAIResponsesAdapter",
    "QualificationGate",
    "RegistryError",
    "RoleEligibility",
    "UnknownModelError",
    "compare_identity_independence",
    "invoke_with_explicit_fallback",
    "parse_model_profile",
]
