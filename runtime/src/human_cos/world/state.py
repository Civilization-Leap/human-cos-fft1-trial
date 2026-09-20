"""S6-WCI2 revisioned ActorState and WorldState application records."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from human_cos.runtime.run import canonical_document_sha256


class WorldStateContractError(ValueError):
    """An Actor/World State record violates the authorized WCI2 revision contract."""


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("S6-WCI2 timestamps require timezone-aware datetimes")
    return value


class SourceClass(str, Enum):
    EVIDENCE = "EVIDENCE"
    MODEL = "MODEL"
    EXPERT = "EXPERT"
    ASSUMPTION = "ASSUMPTION"
    SYSTEM = "SYSTEM"


class ProvenanceRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_class: SourceClass
    ref: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ActorStateSnapshotPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    actor_state_id: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    revision: int = Field(ge=1)
    parent_state_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    timestamp: datetime
    observable_actions: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    interests: tuple[str, ...] = ()
    beliefs_or_expectations: tuple[str, ...] = ()
    risk_tolerance_direction: str | None = None
    commitments: tuple[str, ...] = ()
    information_visible: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()
    source_refs: tuple[ProvenanceRef, ...]
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _timestamp_must_be_aware = field_validator("timestamp")(_aware)
    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class ActorStateSnapshot(ActorStateSnapshotPayload):
    state_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"state_hash"}, exclude_none=True)
        if self.state_hash != canonical_document_sha256(payload):
            raise WorldStateContractError("ActorStateSnapshot state_hash does not match payload")
        if not self.source_refs:
            raise WorldStateContractError("ActorStateSnapshot requires provenance source refs")
        if self.revision == 1 and self.parent_state_hash is not None:
            raise WorldStateContractError("first ActorState revision cannot have a parent")
        if self.revision > 1 and self.parent_state_hash is None:
            raise WorldStateContractError("later ActorState revision requires parent_state_hash")


class WorldStateSnapshotPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_state_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    revision: int = Field(ge=1)
    parent_world_state_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    timestamp: datetime
    system_states: tuple[str, ...]
    actor_state_hashes: tuple[str, ...]
    causal_graph_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    critical_node_refs: tuple[str, ...] = ()
    open_unknowns: tuple[str, ...] = ()
    dissent_node_hashes: tuple[str, ...] = ()
    claim_refs: tuple[str, ...] = ()
    source_refs: tuple[ProvenanceRef, ...]
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _timestamp_must_be_aware = field_validator("timestamp")(_aware)
    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class WorldStateSnapshot(WorldStateSnapshotPayload):
    world_state_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(
            mode="json",
            exclude={"world_state_hash"},
            exclude_none=True,
        )
        if self.world_state_hash != canonical_document_sha256(payload):
            raise WorldStateContractError("WorldStateSnapshot hash does not match payload")
        if not self.actor_state_hashes:
            raise WorldStateContractError("WorldStateSnapshot requires actor-state references")
        if len(self.actor_state_hashes) != len(set(self.actor_state_hashes)):
            raise WorldStateContractError("actor_state_hashes must be unique")
        if not self.source_refs:
            raise WorldStateContractError("WorldStateSnapshot requires provenance source refs")
        if self.revision == 1 and self.parent_world_state_hash is not None:
            raise WorldStateContractError("first WorldState revision cannot have a parent")
        if self.revision > 1 and self.parent_world_state_hash is None:
            raise WorldStateContractError("later WorldState revision requires parent hash")


def freeze_actor_state(
    payload: ActorStateSnapshotPayload,
    *,
    parent: ActorStateSnapshot | None = None,
) -> ActorStateSnapshot:
    if parent is None:
        if payload.revision != 1 or payload.parent_state_hash is not None:
            raise WorldStateContractError("ActorState without parent must be revision 1")
    else:
        parent.assert_integrity()
        if (
            payload.actor_state_id,
            payload.actor_id,
            payload.case_id,
            payload.case_revision,
            payload.protocol_version,
        ) != (
            parent.actor_state_id,
            parent.actor_id,
            parent.case_id,
            parent.case_revision,
            parent.protocol_version,
        ):
            raise WorldStateContractError("ActorState revision identity does not match parent")
        if payload.revision != parent.revision + 1:
            raise WorldStateContractError("ActorState revision must increment parent by one")
        if payload.parent_state_hash != parent.state_hash:
            raise WorldStateContractError("ActorState parent hash does not match parent record")
    document = payload.to_document()
    snapshot = ActorStateSnapshot(
        **document,
        state_hash=canonical_document_sha256(document),
    )
    snapshot.assert_integrity()
    return snapshot


def freeze_world_state(
    payload: WorldStateSnapshotPayload,
    *,
    parent: WorldStateSnapshot | None = None,
) -> WorldStateSnapshot:
    if parent is None:
        if payload.revision != 1 or payload.parent_world_state_hash is not None:
            raise WorldStateContractError("WorldState without parent must be revision 1")
    else:
        parent.assert_integrity()
        if (
            payload.world_state_id,
            payload.case_id,
            payload.case_revision,
            payload.protocol_version,
        ) != (
            parent.world_state_id,
            parent.case_id,
            parent.case_revision,
            parent.protocol_version,
        ):
            raise WorldStateContractError("WorldState revision identity does not match parent")
        if payload.revision != parent.revision + 1:
            raise WorldStateContractError("WorldState revision must increment parent by one")
        if payload.parent_world_state_hash != parent.world_state_hash:
            raise WorldStateContractError("WorldState parent hash does not match parent record")
    document = payload.to_document()
    snapshot = WorldStateSnapshot(
        **document,
        world_state_hash=canonical_document_sha256(document),
    )
    snapshot.assert_integrity()
    return snapshot
