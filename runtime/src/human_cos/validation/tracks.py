"""S4-V immutable HC/Baseline experiment-side track bindings."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from psycopg import Connection, errors
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator

from human_cos.runtime.run import canonical_document_sha256
from human_cos.storage.repository import DuplicateRevisionError, MissingRecordError

TrackKind = Literal["HC", "BASELINE"]


class TrackIntegrityError(ValueError):
    """A stored track binding does not match its canonical content hash."""


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("S4-V timestamps require timezone-aware datetimes")
    return value


class TrackBindingDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    experiment_id: str = Field(min_length=1)
    experiment_revision: int = Field(ge=1)
    manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    track_kind: TrackKind
    input_descriptor: str = Field(min_length=1)
    tool_descriptor: str = Field(min_length=1)
    budget_descriptor: str = Field(min_length=1)
    output_contract_descriptor: str = Field(min_length=1)
    run_id: str | None = None
    output_ref: str = Field(min_length=1)
    output_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware_datetime)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class TrackBinding(TrackBindingDraft):
    binding_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


def freeze_track_binding(draft: TrackBindingDraft) -> TrackBinding:
    document = draft.to_document()
    binding_hash = canonical_document_sha256(document)
    return TrackBinding.model_validate({**document, "binding_hash": binding_hash})


def validate_track_binding(binding: TrackBinding) -> None:
    document = binding.to_document()
    actual = str(document.pop("binding_hash"))
    expected = canonical_document_sha256(document)
    if actual != expected:
        raise TrackIntegrityError(f"track binding hash mismatch: expected {expected}, got {actual}")


def store_track_binding(connection: Connection[Any], binding: TrackBinding) -> None:
    validate_track_binding(binding)
    experiment = connection.execute(
        """
        SELECT manifest_hash
        FROM human_cos_experiment_revision
        WHERE experiment_id = %s AND revision = %s
        """,
        (binding.experiment_id, binding.experiment_revision),
    ).fetchone()
    if experiment is None:
        raise MissingRecordError(
            f"experiment not found: {binding.experiment_id}@{binding.experiment_revision}"
        )
    if str(experiment[0]) != binding.manifest_hash:
        raise TrackIntegrityError("track manifest_hash does not bind the registered experiment")

    try:
        connection.execute(
            """
            INSERT INTO human_cos_validation_track
                (experiment_id, experiment_revision, track_kind, binding_hash, payload)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                binding.experiment_id,
                binding.experiment_revision,
                binding.track_kind,
                binding.binding_hash,
                Jsonb(binding.to_document()),
            ),
        )
        connection.commit()
    except errors.UniqueViolation as exc:
        connection.rollback()
        raise DuplicateRevisionError(
            f"track already frozen: {binding.experiment_id}@{binding.experiment_revision}:"
            f"{binding.track_kind}"
        ) from exc


def get_track_binding(
    connection: Connection[Any],
    experiment_id: str,
    experiment_revision: int,
    track_kind: TrackKind,
) -> TrackBinding:
    row = connection.execute(
        """
        SELECT payload
        FROM human_cos_validation_track
        WHERE experiment_id = %s AND experiment_revision = %s AND track_kind = %s
        """,
        (experiment_id, experiment_revision, track_kind),
    ).fetchone()
    if row is None:
        raise MissingRecordError(
            f"track not found: {experiment_id}@{experiment_revision}:{track_kind}"
        )
    binding = TrackBinding.model_validate(dict(row[0]))
    validate_track_binding(binding)
    return binding
