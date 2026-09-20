"""S4-V Experiment Manifest preregistration and immutable PostgreSQL storage."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg import Connection, errors
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator

from human_cos.runtime.run import canonical_document_sha256
from human_cos.storage.repository import (
    DuplicateRevisionError,
    InvalidRevisionError,
    MissingRecordError,
)


class ManifestIntegrityError(ValueError):
    """Experiment Manifest hash or preregistration lineage is inconsistent."""


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("S4-V timestamps require timezone-aware datetimes")
    return value


class ExperimentManifestDraft(BaseModel):
    """Frozen V0.1 Experiment Manifest fields before manifest_hash is bound."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    experiment_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    primary_hypotheses: tuple[str, ...] = Field(min_length=1)
    primary_metrics: tuple[str, ...] = Field(min_length=1)
    secondary_metrics: tuple[str, ...] = ()
    T0: datetime
    reveal_plan: tuple[str, ...] = Field(min_length=1)
    contamination_policy: str = Field(min_length=1)
    baseline_definition: str = Field(min_length=1)
    model_families: tuple[str, ...] = Field(min_length=1)
    input_parity: str = Field(min_length=1)
    tool_parity: str = Field(min_length=1)
    budget_parity: str = Field(min_length=1)
    output_contract_parity: str = Field(min_length=1)
    blind_judge_assignment: str = Field(min_length=1)
    stopping_rule: str = Field(min_length=1)
    failure_conditions: tuple[str, ...] = Field(min_length=1)
    preregistered_at: datetime

    _t0_must_be_aware = field_validator("T0")(_aware_datetime)
    _preregistered_at_must_be_aware = field_validator("preregistered_at")(_aware_datetime)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class ExperimentManifest(ExperimentManifestDraft):
    manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class ExperimentRegistration(BaseModel):
    """DB-side preregistration lineage without extending frozen manifest meaning."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest: ExperimentManifest
    case_revision: int = Field(ge=1)
    protocol_version: str = Field(min_length=1)
    revision: int = Field(ge=1)
    parent_manifest_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


def preregister_manifest(draft: ExperimentManifestDraft) -> ExperimentManifest:
    document = draft.to_document()
    manifest_hash = canonical_document_sha256(document)
    return ExperimentManifest.model_validate({**document, "manifest_hash": manifest_hash})


def validate_experiment_manifest(manifest: ExperimentManifest) -> None:
    document = manifest.to_document()
    actual = str(document.pop("manifest_hash"))
    expected = canonical_document_sha256(document)
    if actual != expected:
        raise ManifestIntegrityError(
            f"Experiment Manifest hash mismatch: expected {expected}, got {actual}"
        )


def store_experiment_registration(
    connection: Connection[Any],
    registration: ExperimentRegistration,
) -> None:
    """Append one immutable preregistration revision with exact Case binding."""
    validate_experiment_manifest(registration.manifest)
    manifest = registration.manifest

    with connection.transaction():
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))",
            (manifest.experiment_id,),
        )
        case_row = connection.execute(
            """
            SELECT 1
            FROM human_cos_case_revision
            WHERE case_id = %s AND revision = %s
            """,
            (manifest.case_id, registration.case_revision),
        ).fetchone()
        if case_row is None:
            raise MissingRecordError(
                f"case revision not found: {manifest.case_id}@{registration.case_revision}"
            )

        previous = connection.execute(
            """
            SELECT revision, case_id, manifest_hash
            FROM human_cos_experiment_revision
            WHERE experiment_id = %s
            ORDER BY revision DESC
            LIMIT 1
            """,
            (manifest.experiment_id,),
        ).fetchone()

        if previous is None:
            if registration.revision != 1 or registration.parent_manifest_hash is not None:
                raise InvalidRevisionError(
                    "initial Experiment registration must be revision 1 with no parent hash"
                )
        else:
            previous_revision = int(previous[0])
            previous_case_id = str(previous[1])
            previous_hash = str(previous[2])
            if manifest.case_id != previous_case_id:
                raise InvalidRevisionError("Experiment revision cannot change case_id")
            if registration.revision != previous_revision + 1:
                raise InvalidRevisionError(
                    "Experiment revision must append exactly one revision to the lineage"
                )
            if registration.parent_manifest_hash != previous_hash:
                raise InvalidRevisionError(
                    "Experiment parent_manifest_hash must bind the immediately prior revision"
                )

        try:
            connection.execute(
                """
                INSERT INTO human_cos_experiment_revision
                    (experiment_id, revision, case_id, case_revision, protocol_version,
                     parent_manifest_hash, manifest_hash, payload)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    manifest.experiment_id,
                    registration.revision,
                    manifest.case_id,
                    registration.case_revision,
                    registration.protocol_version,
                    registration.parent_manifest_hash,
                    manifest.manifest_hash,
                    Jsonb(registration.to_document()),
                ),
            )
        except errors.UniqueViolation as exc:
            raise DuplicateRevisionError(
                f"experiment revision exists: {manifest.experiment_id}@{registration.revision}"
            ) from exc


def get_experiment_registration(
    connection: Connection[Any],
    experiment_id: str,
    revision: int | None = None,
) -> ExperimentRegistration:
    if revision is None:
        row = connection.execute(
            """
            SELECT payload
            FROM human_cos_experiment_revision
            WHERE experiment_id = %s
            ORDER BY revision DESC
            LIMIT 1
            """,
            (experiment_id,),
        ).fetchone()
    else:
        row = connection.execute(
            """
            SELECT payload
            FROM human_cos_experiment_revision
            WHERE experiment_id = %s AND revision = %s
            """,
            (experiment_id, revision),
        ).fetchone()
    if row is None:
        raise MissingRecordError(f"experiment not found: {experiment_id}@{revision or 'latest'}")
    registration = ExperimentRegistration.model_validate(dict(row[0]))
    validate_experiment_manifest(registration.manifest)
    return registration
