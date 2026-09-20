"""S6-WCI1 immutable Disagreement Nodes and AT-07 dissent-preservation gate."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from human_cos.runtime.run import canonical_document_sha256


class DisagreementContractError(ValueError):
    """A Disagreement Node violates the authorized WCI1 dissent boundary."""


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("S6-WCI1 timestamps require timezone-aware datetimes")
    return value


class ConflictType(str, Enum):
    EVIDENCE = "evidence"
    ASSUMPTION = "assumption"
    MECHANISM = "mechanism"
    VALUE = "value"
    SCOPE = "scope"
    UNKNOWN = "unknown"


class ResolutionRoute(str, Enum):
    SECOND_MODEL = "second_model"
    EXPERT = "expert"
    MORE_EVIDENCE = "more_evidence"
    PRESERVE_UNRESOLVED = "preserve_unresolved"


class DissentPosition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    position_id: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    statement: str = Field(min_length=1)
    impact: Literal["LOW", "MEDIUM", "HIGH"]
    minority: bool = False


class DisagreementNodePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    conflict_type: ConflictType
    positions: tuple[DissentPosition, ...]
    resolution_route: ResolutionRoute
    unresolved: bool
    high_impact: bool
    source_response_hashes: tuple[str, ...]
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class DisagreementNode(DisagreementNodePayload):
    node_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"node_hash"}, exclude_none=True)
        if self.node_hash != canonical_document_sha256(payload):
            raise DisagreementContractError("DisagreementNode node_hash does not match payload")
        if len(self.positions) < 2:
            raise DisagreementContractError("DisagreementNode requires at least two positions")
        position_ids = tuple(item.position_id for item in self.positions)
        if len(position_ids) != len(set(position_ids)):
            raise DisagreementContractError("DisagreementNode position IDs must be unique")
        if not self.source_response_hashes:
            raise DisagreementContractError("DisagreementNode requires source response lineage")
        if len(self.source_response_hashes) != len(set(self.source_response_hashes)):
            raise DisagreementContractError("source_response_hashes must be unique")
        has_high = any(item.impact == "HIGH" for item in self.positions)
        if has_high and not self.high_impact:
            raise DisagreementContractError("high-impact position requires high_impact node flag")
        if self.resolution_route is ResolutionRoute.PRESERVE_UNRESOLVED and not self.unresolved:
            raise DisagreementContractError(
                "preserve_unresolved resolution route requires unresolved=true"
            )


def freeze_disagreement_node(payload: DisagreementNodePayload) -> DisagreementNode:
    document = payload.to_document()
    node = DisagreementNode(**document, node_hash=canonical_document_sha256(document))
    node.assert_integrity()
    return node


def assert_dissent_preserved(
    *,
    nodes: tuple[DisagreementNode, ...],
    required_high_impact_position_ids: tuple[str, ...],
) -> None:
    """Fail closed if a required high-impact/minority position was dropped."""
    required = set(required_high_impact_position_ids)
    if len(required) != len(required_high_impact_position_ids):
        raise DisagreementContractError("required high-impact dissent IDs must be unique")
    if not required:
        return

    preserved: set[str] = set()
    for node in nodes:
        node.assert_integrity()
        for position in node.positions:
            if position.position_id not in required:
                continue
            if position.impact != "HIGH":
                raise DisagreementContractError(
                    "required high-impact dissent position is not marked HIGH"
                )
            if not node.high_impact:
                raise DisagreementContractError(
                    "required high-impact dissent is detached from high-impact node"
                )
            preserved.add(position.position_id)

    missing = sorted(required - preserved)
    if missing:
        raise DisagreementContractError(
            "AT-07 high-impact dissent was omitted: " + ", ".join(missing)
        )
