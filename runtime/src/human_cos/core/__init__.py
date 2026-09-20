"""S1 deterministic data-boundary primitives."""

from .context import (
    AdmittedEvidence,
    ContextAdmissionRecord,
    ContextBuildRequest,
    ContextBuildResult,
    build_context,
)
from .models import (
    Case,
    ContextManifest,
    Evidence,
    parse_case,
    parse_context_manifest,
    parse_evidence,
)
from .visibility import context_allows, temporal_allows, visibility_allows, visibility_basis

__all__ = [
    "AdmittedEvidence",
    "Case",
    "ContextAdmissionRecord",
    "ContextBuildRequest",
    "ContextBuildResult",
    "ContextManifest",
    "Evidence",
    "build_context",
    "context_allows",
    "parse_case",
    "parse_context_manifest",
    "parse_evidence",
    "temporal_allows",
    "visibility_allows",
    "visibility_basis",
]
