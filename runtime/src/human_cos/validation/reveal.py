"""S4-V4 Reveal and append-only Result Registry references."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg import Connection, errors
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator

from human_cos.runtime.run import canonical_document_sha256
from human_cos.storage.repository import DuplicateRevisionError, MissingRecordError
from human_cos.validation.blind_judge import (
    BlindIdentityMapping,
    BlindJudgeBundle,
    BlindJudgeIntegrityError,
    BlindJudgeProtocolError,
    JudgeSubmission,
    validate_blind_identity_mapping,
    validate_blind_judge_bundle,
    validate_judge_submission,
)
from human_cos.validation.contamination import (
    ContaminationGateReport,
    validate_contamination_gate_report,
)
from human_cos.validation.manifest import ExperimentManifest, validate_experiment_manifest
from human_cos.validation.parity import ParityReport, validate_parity_report
from human_cos.validation.tracks import TrackBinding, TrackKind, validate_track_binding


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("S4-V timestamps require timezone-aware datetimes")
    return value


class RevealDraft(BaseModel):
    """Canonical pre-hash form of the post-submission A/B disclosure."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    experiment_id: str = Field(min_length=1)
    experiment_revision: int = Field(ge=1)
    manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    bundle_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    mapping_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    submission_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    reveal_plan: tuple[str, ...] = Field(min_length=1)
    a_track_kind: TrackKind
    b_track_kind: TrackKind
    a_binding_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    b_binding_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    revealed_at: datetime

    _revealed_at_must_be_aware = field_validator("revealed_at")(_aware_datetime)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class RevealRecord(RevealDraft):
    """Immutable post-submission disclosure of the previously secret A/B mapping."""

    reveal_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class ResultRegistryRecord(BaseModel):
    """Immutable references only; no S8 effectiveness or evidence-grade decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    experiment_id: str = Field(min_length=1)
    experiment_revision: int = Field(ge=1)
    manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    metric_refs: tuple[str, ...] = Field(min_length=1)
    parity_status: str = Field(pattern=r"^(PASS|FAIL)$")
    parity_report_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    contamination_status: str = Field(pattern=r"^(PASS|FAIL)$")
    contamination_report_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    hc_binding_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    hc_output_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    hc_output_ref: str = Field(min_length=1)
    baseline_binding_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    baseline_output_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    baseline_output_ref: str = Field(min_length=1)
    judge_submission_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    mapping_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    reveal_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    registry_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def reveal_blind_mapping(
    manifest: ExperimentManifest,
    bundle: BlindJudgeBundle,
    mapping: BlindIdentityMapping,
    submission: JudgeSubmission,
    *,
    revealed_at: datetime,
) -> RevealRecord:
    """Reveal only after an immutable judge submission object is frozen."""
    validate_experiment_manifest(manifest)
    validate_blind_judge_bundle(bundle)
    validate_blind_identity_mapping(mapping)
    validate_judge_submission(submission)
    _aware_datetime(revealed_at)
    expected = (manifest.experiment_id, bundle.experiment_revision, manifest.manifest_hash)
    if (bundle.experiment_id, bundle.experiment_revision, bundle.manifest_hash) != expected or (
        mapping.experiment_id,
        mapping.experiment_revision,
        mapping.manifest_hash,
    ) != expected:
        raise BlindJudgeIntegrityError("Reveal inputs do not bind the same manifest revision")
    if mapping.bundle_hash != bundle.bundle_hash or submission.bundle_hash != bundle.bundle_hash:
        raise BlindJudgeIntegrityError("Reveal inputs do not bind the exact Blind Judge bundle")
    if (
        submission.experiment_id != bundle.experiment_id
        or submission.experiment_revision != bundle.experiment_revision
    ):
        raise BlindJudgeIntegrityError("judge submission does not bind the reveal experiment")
    if {mapping.a_track_kind, mapping.b_track_kind} != {"HC", "BASELINE"}:
        raise BlindJudgeIntegrityError("Reveal mapping must disclose HC and BASELINE exactly once")

    draft = RevealDraft(
        experiment_id=manifest.experiment_id,
        experiment_revision=bundle.experiment_revision,
        manifest_hash=manifest.manifest_hash,
        bundle_hash=bundle.bundle_hash,
        mapping_hash=mapping.mapping_hash,
        submission_hash=submission.submission_hash,
        reveal_plan=manifest.reveal_plan,
        a_track_kind=mapping.a_track_kind,
        b_track_kind=mapping.b_track_kind,
        a_binding_hash=mapping.a_binding_hash,
        b_binding_hash=mapping.b_binding_hash,
        revealed_at=revealed_at,
    )
    payload = draft.to_document()
    return RevealRecord.model_validate(
        {**payload, "reveal_hash": str(canonical_document_sha256(payload))}
    )


def validate_reveal_record(record: RevealRecord) -> None:
    document = record.to_document()
    actual_hash = str(document.pop("reveal_hash"))
    expected_hash = str(canonical_document_sha256(document))
    if actual_hash != expected_hash:
        raise BlindJudgeIntegrityError(
            f"Reveal record hash mismatch: expected {expected_hash}, got {actual_hash}"
        )
    if {record.a_track_kind, record.b_track_kind} != {"HC", "BASELINE"}:
        raise BlindJudgeIntegrityError("Reveal record must disclose HC and BASELINE exactly once")


def build_result_registry(
    manifest: ExperimentManifest,
    hc: TrackBinding,
    baseline: TrackBinding,
    parity: ParityReport,
    contamination: ContaminationGateReport,
    submission: JudgeSubmission,
    reveal: RevealRecord,
) -> ResultRegistryRecord:
    """Bind preregistered metrics and immutable S4-V artifacts without judging effectiveness."""
    validate_experiment_manifest(manifest)
    validate_track_binding(hc)
    validate_track_binding(baseline)
    validate_parity_report(parity)
    validate_contamination_gate_report(contamination)
    validate_judge_submission(submission)
    validate_reveal_record(reveal)
    if hc.track_kind != "HC" or baseline.track_kind != "BASELINE":
        raise BlindJudgeIntegrityError("Result Registry requires one HC and one BASELINE track")
    expected = (
        manifest.experiment_id,
        hc.experiment_revision,
        manifest.manifest_hash,
        hc.binding_hash,
        baseline.binding_hash,
    )
    if (
        parity.experiment_id,
        parity.experiment_revision,
        parity.manifest_hash,
        parity.hc_binding_hash,
        parity.baseline_binding_hash,
    ) != expected:
        raise BlindJudgeIntegrityError("Result Registry parity report binds a different track set")
    if (
        contamination.experiment_id,
        contamination.experiment_revision,
        contamination.manifest_hash,
        contamination.hc_binding_hash,
        contamination.baseline_binding_hash,
    ) != expected:
        raise BlindJudgeIntegrityError(
            "Result Registry contamination report binds a different track set"
        )
    if (
        reveal.experiment_id != manifest.experiment_id
        or reveal.experiment_revision != hc.experiment_revision
        or reveal.manifest_hash != manifest.manifest_hash
        or reveal.submission_hash != submission.submission_hash
    ):
        raise BlindJudgeIntegrityError("Result Registry reveal/submission lineage is inconsistent")

    metric_refs = manifest.primary_metrics + manifest.secondary_metrics
    payload = {
        "experiment_id": manifest.experiment_id,
        "experiment_revision": hc.experiment_revision,
        "manifest_hash": manifest.manifest_hash,
        "metric_refs": list(metric_refs),
        "parity_status": parity.status,
        "parity_report_hash": parity.report_hash,
        "contamination_status": contamination.status,
        "contamination_report_hash": contamination.report_hash,
        "hc_binding_hash": hc.binding_hash,
        "hc_output_hash": hc.output_hash,
        "hc_output_ref": hc.output_ref,
        "baseline_binding_hash": baseline.binding_hash,
        "baseline_output_hash": baseline.output_hash,
        "baseline_output_ref": baseline.output_ref,
        "judge_submission_hash": submission.submission_hash,
        "mapping_hash": reveal.mapping_hash,
        "reveal_hash": reveal.reveal_hash,
    }
    return ResultRegistryRecord.model_validate(
        {**payload, "registry_hash": str(canonical_document_sha256(payload))}
    )


def validate_result_registry(record: ResultRegistryRecord) -> None:
    document = record.to_document()
    actual_hash = str(document.pop("registry_hash"))
    expected_hash = str(canonical_document_sha256(document))
    if actual_hash != expected_hash:
        raise BlindJudgeIntegrityError(
            f"Result Registry hash mismatch: expected {expected_hash}, got {actual_hash}"
        )


def store_reveal_record(connection: Connection[Any], record: RevealRecord) -> None:
    """Persist Reveal only when the exact judge submission and secret mapping are frozen."""
    validate_reveal_record(record)
    submission = connection.execute(
        """
        SELECT submission_hash
        FROM human_cos_judge_submission
        WHERE experiment_id = %s AND experiment_revision = %s
        """,
        (record.experiment_id, record.experiment_revision),
    ).fetchone()
    mapping = connection.execute(
        """
        SELECT mapping_hash
        FROM human_cos_blind_identity_mapping
        WHERE experiment_id = %s AND experiment_revision = %s
        """,
        (record.experiment_id, record.experiment_revision),
    ).fetchone()
    if submission is None:
        raise BlindJudgeProtocolError("Reveal is forbidden before judge submission is frozen")
    if mapping is None:
        raise MissingRecordError("Blind identity mapping is not frozen")
    if str(submission[0]) != record.submission_hash or str(mapping[0]) != record.mapping_hash:
        raise BlindJudgeIntegrityError("Reveal does not bind the stored submission/mapping")
    try:
        connection.execute(
            """
            INSERT INTO human_cos_reveal_record
                (experiment_id, experiment_revision, submission_hash, mapping_hash,
                 reveal_hash, payload)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                record.experiment_id,
                record.experiment_revision,
                record.submission_hash,
                record.mapping_hash,
                record.reveal_hash,
                Jsonb(record.to_document()),
            ),
        )
        connection.commit()
    except errors.UniqueViolation as exc:
        connection.rollback()
        raise DuplicateRevisionError(
            f"Reveal already frozen: {record.experiment_id}@{record.experiment_revision}"
        ) from exc


def store_result_registry(connection: Connection[Any], record: ResultRegistryRecord) -> None:
    """Freeze one append-only Result Registry reference record per experiment revision."""
    validate_result_registry(record)
    reveal = connection.execute(
        """
        SELECT reveal_hash
        FROM human_cos_reveal_record
        WHERE experiment_id = %s AND experiment_revision = %s
        """,
        (record.experiment_id, record.experiment_revision),
    ).fetchone()
    if reveal is None:
        raise BlindJudgeProtocolError("Result Registry cannot precede Reveal")
    if str(reveal[0]) != record.reveal_hash:
        raise BlindJudgeIntegrityError("Result Registry does not bind the stored Reveal")
    try:
        connection.execute(
            """
            INSERT INTO human_cos_result_registry
                (experiment_id, experiment_revision, registry_hash, payload)
            VALUES (%s, %s, %s, %s)
            """,
            (
                record.experiment_id,
                record.experiment_revision,
                record.registry_hash,
                Jsonb(record.to_document()),
            ),
        )
        connection.commit()
    except errors.UniqueViolation as exc:
        connection.rollback()
        raise DuplicateRevisionError(
            f"Result Registry already frozen: {record.experiment_id}@{record.experiment_revision}"
        ) from exc
