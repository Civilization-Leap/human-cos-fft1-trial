"""S6-WCI1 disclosure-controlled Cross Examination contracts and first-edge activation."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from human_cos.runtime.run import canonical_document_sha256
from human_cos.runtime.state_machine import (
    CaseMode,
    CaseRuntimePosition,
    GuardCheck,
    GuardStatus,
    RuntimeState,
    TransitionDecision,
    TransitionKey,
    TransitionStatus,
    can_transition,
)


class CrossExamContractError(ValueError):
    """A WCI1 disclosure or Cross Examination record violates its authorization."""


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("S6-WCI1 timestamps require timezone-aware datetimes")
    return value


class SourceKind(str, Enum):
    FRAMING = "FRAMING"
    DOMAIN_OUTPUT = "DOMAIN_OUTPUT"
    EXPERT_SUBMISSION = "EXPERT_SUBMISSION"


class ReviewPromptType(str, Enum):
    OMISSION = "OMISSION"
    FALSIFICATION = "FALSIFICATION"
    CONFLICT = "CONFLICT"
    CROSS_DOMAIN = "CROSS_DOMAIN"
    UNKNOWN = "UNKNOWN"


class SourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: SourceKind
    ref: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class DisclosureGrantPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    grant_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    reviewer_id: str = Field(min_length=1)
    allowed_sources: tuple[SourceRef, ...]
    independent_review_required: bool = True
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class DisclosureGrant(DisclosureGrantPayload):
    grant_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"grant_hash"}, exclude_none=True)
        if self.grant_hash != canonical_document_sha256(payload):
            raise CrossExamContractError("DisclosureGrant grant_hash does not match payload")
        keys = tuple((item.kind.value, item.ref, item.sha256) for item in self.allowed_sources)
        if len(keys) != len(set(keys)):
            raise CrossExamContractError("DisclosureGrant allowed_sources must be unique")
        if not self.allowed_sources:
            raise CrossExamContractError("DisclosureGrant requires at least one frozen source")


class CrossExamTaskPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    reviewer_id: str = Field(min_length=1)
    grant_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_refs: tuple[SourceRef, ...]
    prompt_types: tuple[ReviewPromptType, ...]
    prior_review_response_hashes: tuple[str, ...] = ()
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class CrossExamTask(CrossExamTaskPayload):
    task_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"task_hash"}, exclude_none=True)
        if self.task_hash != canonical_document_sha256(payload):
            raise CrossExamContractError("CrossExamTask task_hash does not match payload")
        if not self.source_refs:
            raise CrossExamContractError("CrossExamTask requires at least one disclosed source")
        if not self.prompt_types:
            raise CrossExamContractError("CrossExamTask requires at least one review prompt type")


class CrossExamFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    finding_id: str = Field(min_length=1)
    prompt_type: ReviewPromptType
    statement: str = Field(min_length=1)
    source_refs: tuple[SourceRef, ...]
    high_impact: bool = False


class CrossExamResponsePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    response_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    task_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewer_id: str = Field(min_length=1)
    grant_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    findings: tuple[CrossExamFinding, ...]
    protocol_version: str = Field(min_length=1)
    submitted_at: datetime
    frozen_at: datetime

    _submitted_at_must_be_aware = field_validator("submitted_at")(_aware)
    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class CrossExamResponse(CrossExamResponsePayload):
    response_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"response_hash"}, exclude_none=True)
        if self.response_hash != canonical_document_sha256(payload):
            raise CrossExamContractError("CrossExamResponse response_hash does not match payload")
        if self.frozen_at < self.submitted_at:
            raise CrossExamContractError("CrossExamResponse cannot freeze before submission")


def _source_key(source: SourceRef) -> tuple[str, str, str]:
    return source.kind.value, source.ref, source.sha256


def freeze_disclosure_grant(payload: DisclosureGrantPayload) -> DisclosureGrant:
    document = payload.to_document()
    record = DisclosureGrant(**document, grant_hash=canonical_document_sha256(document))
    record.assert_integrity()
    return record


def assert_disclosure_authorized(
    *,
    grant: DisclosureGrant,
    requested_sources: tuple[SourceRef, ...],
) -> None:
    grant.assert_integrity()
    allowed = {_source_key(item) for item in grant.allowed_sources}
    requested = {_source_key(item) for item in requested_sources}
    if not requested:
        raise CrossExamContractError("Cross Examination cannot request an empty source packet")
    if not requested.issubset(allowed):
        raise CrossExamContractError("Cross Examination requested a source not in disclosure grant")


def build_cross_exam_task(
    *,
    grant: DisclosureGrant,
    task_id: str,
    source_refs: tuple[SourceRef, ...],
    prompt_types: tuple[ReviewPromptType, ...],
    frozen_at: datetime,
    prior_review_response_hashes: tuple[str, ...] = (),
) -> CrossExamTask:
    assert_disclosure_authorized(grant=grant, requested_sources=source_refs)
    if grant.independent_review_required and prior_review_response_hashes:
        raise CrossExamContractError(
            "independent Cross Examination reviewer cannot see other review responses before freeze"
        )
    payload = CrossExamTaskPayload(
        task_id=task_id,
        case_id=grant.case_id,
        case_revision=grant.case_revision,
        reviewer_id=grant.reviewer_id,
        grant_hash=grant.grant_hash,
        source_refs=source_refs,
        prompt_types=prompt_types,
        prior_review_response_hashes=prior_review_response_hashes,
        protocol_version=grant.protocol_version,
        frozen_at=frozen_at,
    )
    document = payload.to_document()
    task = CrossExamTask(**document, task_hash=canonical_document_sha256(document))
    task.assert_integrity()
    return task


def freeze_cross_exam_response(
    *,
    grant: DisclosureGrant,
    task: CrossExamTask,
    response_id: str,
    findings: tuple[CrossExamFinding, ...],
    submitted_at: datetime,
    frozen_at: datetime,
) -> CrossExamResponse:
    grant.assert_integrity()
    task.assert_integrity()
    if (
        task.case_id,
        task.case_revision,
        task.reviewer_id,
        task.grant_hash,
        task.protocol_version,
    ) != (
        grant.case_id,
        grant.case_revision,
        grant.reviewer_id,
        grant.grant_hash,
        grant.protocol_version,
    ):
        raise CrossExamContractError("CrossExamTask does not bind the supplied DisclosureGrant")
    allowed = {_source_key(item) for item in task.source_refs}
    for finding in findings:
        if not finding.source_refs:
            raise CrossExamContractError("Cross Examination finding requires source references")
        if not {_source_key(item) for item in finding.source_refs}.issubset(allowed):
            raise CrossExamContractError("Cross Examination finding cites an undisclosed source")
    payload = CrossExamResponsePayload(
        response_id=response_id,
        case_id=task.case_id,
        case_revision=task.case_revision,
        task_hash=task.task_hash,
        reviewer_id=task.reviewer_id,
        grant_hash=task.grant_hash,
        findings=findings,
        protocol_version=task.protocol_version,
        submitted_at=submitted_at,
        frozen_at=frozen_at,
    )
    document = payload.to_document()
    response = CrossExamResponse(
        **document,
        response_hash=canonical_document_sha256(document),
    )
    response.assert_integrity()
    return response


_S6_COMMON_MODES = (
    CaseMode.LIVE_FORESIGHT,
    CaseMode.MECHANISM_BENCHMARK,
    CaseMode.SCENARIO_STRESS_TEST,
)

S6_WCI1_TRANSITIONS: frozenset[TransitionKey] = frozenset(
    TransitionKey(
        mode,
        RuntimeState.DOMAIN_OUTPUT_FROZEN,
        RuntimeState.CROSS_EXAMINATION,
    )
    for mode in _S6_COMMON_MODES
)


def _guard(name: str, passed: bool | None, reason: str) -> GuardCheck:
    if passed is None:
        return GuardCheck(name, GuardStatus.UNAVAILABLE, reason)
    if passed:
        return GuardCheck(name, GuardStatus.PASS, reason)
    return GuardCheck(name, GuardStatus.FAIL, reason)


def _with_guard(base: TransitionDecision, guard: GuardCheck) -> TransitionDecision:
    if guard.status is GuardStatus.PASS:
        return base
    status = (
        TransitionStatus.GUARD_UNAVAILABLE
        if guard.status is GuardStatus.UNAVAILABLE
        else TransitionStatus.GUARD_FAILED
    )
    return TransitionDecision(
        allowed=False,
        status=status,
        mode=base.mode,
        source=base.source,
        target=base.target,
        protocol_version=base.protocol_version,
        guard_results=base.guard_results + (guard,),
        reason="S6-WCI1 disclosure/Cross Examination prerequisite was not satisfied",
    )


def can_s6_wci1_transition(
    position: CaseRuntimePosition,
    target: RuntimeState,
    *,
    grant: DisclosureGrant | None = None,
    tasks: tuple[CrossExamTask, ...] = (),
) -> TransitionDecision:
    """Activate only DOMAIN_OUTPUT_FROZEN -> CROSS_EXAMINATION with a frozen grant."""
    base = can_transition(
        position,
        target,
        authorized_future_transitions=S6_WCI1_TRANSITIONS,
    )
    if not base.allowed:
        return base
    if grant is None:
        return _with_guard(
            base,
            _guard("cross_exam_disclosure_frozen", None, "DisclosureGrant was not supplied"),
        )
    try:
        grant.assert_integrity()
        if grant.case_revision != position.case_revision:
            raise CrossExamContractError("DisclosureGrant Case revision does not match runtime")
        if grant.protocol_version != base.protocol_version:
            raise CrossExamContractError("DisclosureGrant protocol version does not match runtime")
        if not tasks:
            raise CrossExamContractError("at least one frozen CrossExamTask is required")
        for task in tasks:
            task.assert_integrity()
            if (
                task.case_revision,
                task.grant_hash,
                task.protocol_version,
            ) != (
                grant.case_revision,
                grant.grant_hash,
                grant.protocol_version,
            ):
                raise CrossExamContractError("CrossExamTask does not bind the runtime grant")
    except CrossExamContractError as exc:
        return _with_guard(base, _guard("cross_exam_disclosure_frozen", False, str(exc)))
    return _with_guard(
        base,
        _guard(
            "cross_exam_disclosure_frozen",
            True,
            "immutable disclosure grant and Cross Examination tasks are bound",
        ),
    )
