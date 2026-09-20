"""Context construction and immutable admission sidecar for S1.

The frozen Context Manifest schema is not extended. Exact Evidence revisions,
snapshots, actor scope, visibility basis, and reference time are recorded in a
separate immutable admission record bound to the manifest hash.

The Context Builder re-applies temporal and visibility gates itself. A data
source may narrow the candidate set for efficiency, but it is never trusted as
the authority that decides what the final Context may see.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import Case, ContextManifest, Evidence, parse_context_manifest
from .visibility import VisibilityBasis, temporal_allows, visibility_basis


class ContextBuildError(ValueError):
    """Context cannot be deterministically constructed."""


@dataclass(frozen=True)
class AdmittedEvidence:
    evidence: Evidence
    revision: int
    visibility_basis: VisibilityBasis


class ContextEvidenceSource(Protocol):
    def list_context_evidence(
        self,
        case: Case,
        *,
        actor_id: str | None,
        role_id: str | None,
        as_of: datetime,
    ) -> Sequence[AdmittedEvidence]: ...


@dataclass(frozen=True)
class ContextBuildRequest:
    context_manifest_id: str
    run_id: str
    stage: str
    role_id: str
    actor_id: str | None
    model_id: str
    prompt_version: str
    reference_time: datetime | None = None
    tool_permissions: tuple[str, ...] = ()
    prior_run_ids: tuple[str, ...] = ()
    forbidden_scopes: tuple[str, ...] = ()


def _stable_hash(document: dict[str, object]) -> str:
    encoded = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class _SidecarModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def to_document(self) -> dict[str, object]:
        # Audit records preserve explicit nulls such as actor_id=None so their
        # canonical hash and persisted representation have one stable shape.
        return self.model_dump(mode="json", exclude_none=False)


class EvidenceAdmissionRecord(_SidecarModel):
    evidence_id: str
    revision: int = Field(ge=1)
    snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    visibility_basis: VisibilityBasis


def _canonical_admission_payload(
    *,
    context_manifest_id: str,
    manifest_hash: str,
    actor_id: str | None,
    role_id: str,
    reference_time: datetime,
    evidence: Sequence[EvidenceAdmissionRecord],
) -> dict[str, object]:
    """Return the only byte-hashable representation of an admission record."""
    return {
        "context_manifest_id": context_manifest_id,
        "manifest_hash": manifest_hash,
        "actor_id": actor_id,
        "role_id": role_id,
        "reference_time": reference_time.isoformat(),
        "evidence": [item.to_document() for item in evidence],
    }


class ContextAdmissionRecord(_SidecarModel):
    context_manifest_id: str
    manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    actor_id: str | None
    role_id: str
    reference_time: datetime
    evidence: tuple[EvidenceAdmissionRecord, ...]
    record_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("reference_time")
    @classmethod
    def _reference_time_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Context admission reference_time must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _record_hash_must_match_payload(self) -> ContextAdmissionRecord:
        payload = _canonical_admission_payload(
            context_manifest_id=self.context_manifest_id,
            manifest_hash=self.manifest_hash,
            actor_id=self.actor_id,
            role_id=self.role_id,
            reference_time=self.reference_time,
            evidence=self.evidence,
        )
        if self.record_hash != _stable_hash(payload):
            raise ValueError("Context admission record_hash does not match payload")
        return self


@dataclass(frozen=True)
class ContextBuildResult:
    manifest: ContextManifest
    admission: ContextAdmissionRecord


def _effective_reference_time(case: Case, request: ContextBuildRequest) -> datetime:
    if case.case_mode == "HISTORICAL_BLIND_EVAL":
        return case.time_boundary.T0
    if request.reference_time is None:
        raise ContextBuildError(
            f"{case.case_mode} context requires an explicit timezone-aware reference_time"
        )
    if request.reference_time.tzinfo is None or request.reference_time.utcoffset() is None:
        raise ContextBuildError("reference_time must be timezone-aware")
    return request.reference_time


def _revalidate_candidates(
    candidates: Sequence[AdmittedEvidence],
    *,
    case: Case,
    actor_id: str | None,
    role_id: str | None,
    reference_time: datetime,
) -> tuple[AdmittedEvidence, ...]:
    """Re-apply the non-bypassable temporal + ACL gates at Context assembly."""
    admitted: list[AdmittedEvidence] = []
    for candidate in candidates:
        evidence = candidate.evidence
        if evidence.case_id != case.case_id:
            continue
        if candidate.revision < 1:
            raise ContextBuildError("evidence revision must be >= 1")
        if not temporal_allows(case, evidence, as_of=reference_time):
            continue
        basis = visibility_basis(evidence.visibility, actor_id=actor_id, role_id=role_id)
        if basis is None:
            continue
        # Do not trust source-supplied visibility metadata. Recompute it from
        # the frozen Evidence object and the actual Context subject.
        admitted.append(
            AdmittedEvidence(
                evidence=evidence,
                revision=candidate.revision,
                visibility_basis=basis,
            )
        )
    return tuple(admitted)


def build_context(
    source: ContextEvidenceSource,
    case: Case,
    request: ContextBuildRequest,
) -> ContextBuildResult:
    reference_time = _effective_reference_time(case, request)
    candidates = tuple(
        source.list_context_evidence(
            case,
            actor_id=request.actor_id,
            role_id=request.role_id,
            as_of=reference_time,
        )
    )
    admitted = _revalidate_candidates(
        candidates,
        case=case,
        actor_id=request.actor_id,
        role_id=request.role_id,
        reference_time=reference_time,
    )

    ids = [item.evidence.evidence_id for item in admitted]
    if len(ids) != len(set(ids)):
        raise ContextBuildError(
            "context source returned multiple admissible revisions for one evidence_id"
        )
    admitted = tuple(sorted(admitted, key=lambda item: item.evidence.evidence_id))

    document: dict[str, object] = {
        "context_manifest_id": request.context_manifest_id,
        "case_id": case.case_id,
        "run_id": request.run_id,
        "stage": request.stage,
        "role_id": request.role_id,
        "evidence_ids": [item.evidence.evidence_id for item in admitted],
        "prior_run_ids": list(request.prior_run_ids),
        "tool_permissions": list(request.tool_permissions),
        "protocol_version": case.protocol_version,
        "model_id": request.model_id,
        "prompt_version": request.prompt_version,
        "forbidden_scopes": list(request.forbidden_scopes),
        "time_boundary": reference_time.isoformat(),
    }
    document["hash_sha256"] = _stable_hash(document)
    manifest = parse_context_manifest(document)
    if manifest.hash_sha256 is None:
        raise ContextBuildError("manifest hash unexpectedly missing")

    evidence_records = tuple(
        EvidenceAdmissionRecord(
            evidence_id=item.evidence.evidence_id,
            revision=item.revision,
            snapshot_hash=item.evidence.snapshot_hash,
            visibility_basis=item.visibility_basis,
        )
        for item in admitted
    )
    admission_payload = _canonical_admission_payload(
        context_manifest_id=manifest.context_manifest_id,
        manifest_hash=manifest.hash_sha256,
        actor_id=request.actor_id,
        role_id=request.role_id,
        reference_time=reference_time,
        evidence=evidence_records,
    )
    admission = ContextAdmissionRecord(
        context_manifest_id=manifest.context_manifest_id,
        manifest_hash=manifest.hash_sha256,
        actor_id=request.actor_id,
        role_id=request.role_id,
        reference_time=reference_time,
        evidence=evidence_records,
        record_hash=_stable_hash(admission_payload),
    )
    return ContextBuildResult(manifest=manifest, admission=admission)
