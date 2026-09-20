"""S5-CDE4 immutable Human Expert minimal contracts and AT-09 gates."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from human_cos.core.models import Case
from human_cos.runtime.run import canonical_document_sha256


class ExpertContractError(ValueError):
    """An Expert Profile/Task/Submission violates the authorized S5-CDE4 boundary."""


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("S5-CDE4 timestamps require timezone-aware datetimes")
    return value


class _FrozenExpertModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class ExpertIdentityMode(str, Enum):
    PUBLIC = "public"
    PSEUDONYMOUS = "pseudonymous"


class ExpertMaterialKind(str, Enum):
    CASE = "CASE"
    EVIDENCE = "EVIDENCE"
    SOURCE_SNAPSHOT = "SOURCE_SNAPSHOT"
    POLICY = "POLICY"
    MODEL_RUN = "MODEL_RUN"
    MODEL_OUTPUT = "MODEL_OUTPUT"
    EXPERT_SUBMISSION = "EXPERT_SUBMISSION"


_INDEPENDENCE_FORBIDDEN_KINDS = frozenset(
    {
        ExpertMaterialKind.MODEL_RUN,
        ExpertMaterialKind.MODEL_OUTPUT,
        ExpertMaterialKind.EXPERT_SUBMISSION,
    }
)


class ExpertProfilePayload(_FrozenExpertModel):
    expert_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    domain: str = Field(min_length=1)
    subdomains: tuple[str, ...] = ()
    experience_types: tuple[str, ...] = ()
    identity_mode: ExpertIdentityMode
    task_eligibility: tuple[str, ...]
    conflict_of_interest: tuple[str, ...]
    access_level: str = Field(min_length=1)
    review_history_refs: tuple[str, ...] = ()
    module_contribution_refs: tuple[str, ...] = ()
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class ExpertProfile(ExpertProfilePayload):
    profile_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"profile_hash"}, exclude_none=True)
        if self.profile_hash != canonical_document_sha256(payload):
            raise ExpertContractError("ExpertProfile profile_hash does not match payload")


class ExpertMaterialRef(_FrozenExpertModel):
    kind: ExpertMaterialKind
    ref: str = Field(min_length=1)
    sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class ExpertTaskPayload(_FrozenExpertModel):
    task_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    expert_id: str = Field(min_length=1)
    profile_revision: int = Field(ge=1)
    profile_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    domain: str = Field(min_length=1)
    task_question: str = Field(min_length=1)
    task_type: str = Field(min_length=1)
    permitted_materials: tuple[ExpertMaterialRef, ...]
    visibility_scope: tuple[str, ...]
    access_level: str = Field(min_length=1)
    protocol_version: str = Field(min_length=1)
    independent_required: bool
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class ExpertTask(ExpertTaskPayload):
    task_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"task_hash"}, exclude_none=True)
        if self.task_hash != canonical_document_sha256(payload):
            raise ExpertContractError("ExpertTask task_hash does not match payload")
        assert_expert_task_independence(self)


class ExpertTaskPacket(_FrozenExpertModel):
    task_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    expert_id: str = Field(min_length=1)
    task_question: str = Field(min_length=1)
    task_type: str = Field(min_length=1)
    materials: tuple[ExpertMaterialRef, ...]
    visibility_scope: tuple[str, ...]
    access_level: str = Field(min_length=1)
    independent_required: bool


class ExpertSubmissionPayload(_FrozenExpertModel):
    submission_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    task_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    expert_id: str = Field(min_length=1)
    profile_revision: int = Field(ge=1)
    profile_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    actor_type: Literal["HUMAN"] = "HUMAN"
    content: str | None = None
    content_ref: str | None = None
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    protocol_version: str = Field(min_length=1)
    submitted_at: datetime
    frozen_at: datetime

    _submitted_at_must_be_aware = field_validator("submitted_at")(_aware)
    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class ExpertSubmission(ExpertSubmissionPayload):
    submission_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"submission_hash"}, exclude_none=True)
        if self.submission_hash != canonical_document_sha256(payload):
            raise ExpertContractError("ExpertSubmission submission_hash does not match payload")
        if (self.content is None) == (self.content_ref is None):
            raise ExpertContractError(
                "ExpertSubmission requires exactly one content or content_ref"
            )
        expected_content_hash = _submission_content_hash(self.content, self.content_ref)
        if self.content_hash != expected_content_hash:
            raise ExpertContractError(
                "ExpertSubmission content_hash does not match submitted content"
            )
        if self.frozen_at < self.submitted_at:
            raise ExpertContractError("ExpertSubmission cannot freeze before submission")


def freeze_expert_profile(payload: ExpertProfilePayload) -> ExpertProfile:
    if not payload.conflict_of_interest:
        raise ExpertContractError(
            "Expert Profile requires an explicit COI disclosure; use an explicit none disclosure"
        )
    document = payload.to_document()
    return ExpertProfile(**document, profile_hash=canonical_document_sha256(document))


def assert_expert_task_independence(task: ExpertTask) -> None:
    if not task.independent_required:
        return
    forbidden = tuple(
        item.kind.value
        for item in task.permitted_materials
        if item.kind in _INDEPENDENCE_FORBIDDEN_KINDS
    )
    if forbidden:
        raise ExpertContractError(
            "AT-09 independent Expert Task cannot include model runs/outputs or expert submissions"
        )


def build_expert_task(
    *,
    case: Case,
    profile: ExpertProfile,
    task_id: str,
    task_question: str,
    task_type: str,
    permitted_materials: tuple[ExpertMaterialRef, ...],
    visibility_scope: tuple[str, ...],
    independent_required: bool,
    frozen_at: datetime,
) -> ExpertTask:
    profile.assert_integrity()
    if profile.protocol_version != case.protocol_version:
        raise ExpertContractError("Expert Profile protocol version does not match Case")
    if task_type not in profile.task_eligibility:
        raise ExpertContractError("Expert Profile is not eligible for requested task_type")
    if case.domains is not None and profile.domain not in case.domains:
        raise ExpertContractError("Expert Profile domain is outside the Case domains")
    payload = ExpertTaskPayload(
        task_id=task_id,
        case_id=case.case_id,
        case_revision=case.revision,
        expert_id=profile.expert_id,
        profile_revision=profile.revision,
        profile_hash=profile.profile_hash,
        domain=profile.domain,
        task_question=task_question,
        task_type=task_type,
        permitted_materials=permitted_materials,
        visibility_scope=visibility_scope,
        access_level=profile.access_level,
        protocol_version=case.protocol_version,
        independent_required=independent_required,
        frozen_at=frozen_at,
    )
    document = payload.to_document()
    task = ExpertTask(**document, task_hash=canonical_document_sha256(document))
    task.assert_integrity()
    return task


def build_expert_task_packet(task: ExpertTask) -> ExpertTaskPacket:
    """Return exactly the preregistered minimal material packet for one Expert Task."""
    task.assert_integrity()
    return ExpertTaskPacket(
        task_hash=task.task_hash,
        expert_id=task.expert_id,
        task_question=task.task_question,
        task_type=task.task_type,
        materials=task.permitted_materials,
        visibility_scope=task.visibility_scope,
        access_level=task.access_level,
        independent_required=task.independent_required,
    )


def _submission_content_hash(content: str | None, content_ref: str | None) -> str:
    if (content is None) == (content_ref is None):
        raise ExpertContractError("ExpertSubmission requires exactly one content or content_ref")
    document = {"content": content} if content is not None else {"content_ref": content_ref}
    return str(canonical_document_sha256(document))


def freeze_expert_submission(
    *,
    task: ExpertTask,
    profile: ExpertProfile,
    submission_id: str,
    submitted_at: datetime,
    frozen_at: datetime,
    content: str | None = None,
    content_ref: str | None = None,
) -> ExpertSubmission:
    task.assert_integrity()
    profile.assert_integrity()
    if (
        task.expert_id,
        task.profile_revision,
        task.profile_hash,
        task.protocol_version,
    ) != (
        profile.expert_id,
        profile.revision,
        profile.profile_hash,
        profile.protocol_version,
    ):
        raise ExpertContractError("ExpertSubmission profile does not match frozen ExpertTask")
    content_hash = _submission_content_hash(content, content_ref)
    payload = ExpertSubmissionPayload(
        submission_id=submission_id,
        case_id=task.case_id,
        case_revision=task.case_revision,
        task_hash=task.task_hash,
        expert_id=task.expert_id,
        profile_revision=task.profile_revision,
        profile_hash=task.profile_hash,
        content=content,
        content_ref=content_ref,
        content_hash=content_hash,
        protocol_version=task.protocol_version,
        submitted_at=submitted_at,
        frozen_at=frozen_at,
    )
    document = payload.to_document()
    submission = ExpertSubmission(
        **document,
        submission_hash=canonical_document_sha256(document),
    )
    submission.assert_integrity()
    return submission
