"""S4-V4 Blind Judge isolation and immutable submission contracts."""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any, Literal

from psycopg import Connection, errors
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator

from human_cos.runtime.run import canonical_document_sha256
from human_cos.storage.repository import DuplicateRevisionError, MissingRecordError
from human_cos.validation.contamination import (
    ContaminationGateReport,
    validate_contamination_gate_report,
)
from human_cos.validation.manifest import ExperimentManifest, validate_experiment_manifest
from human_cos.validation.parity import ParityReport, validate_parity_report
from human_cos.validation.tracks import TrackBinding, TrackKind, validate_track_binding

BlindAlias = Literal["A", "B"]
JudgeScalar = str | int | float | bool | None


class BlindJudgeIntegrityError(ValueError):
    """Blind Judge material does not preserve its frozen bindings."""


class BlindJudgeProtocolError(RuntimeError):
    """A prerequisite for Blind Judging has not been satisfied."""


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("S4-V timestamps require timezone-aware datetimes")
    return value


class JudgeVisibleArtifact(BaseModel):
    """Judge-visible artifact metadata with no HC/Baseline identity field."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    alias: BlindAlias
    artifact_ref: str = Field(min_length=1)
    output_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class BlindJudgeBundle(BaseModel):
    """Judge-visible A/B contract bound to frozen gates and preregistered judging references."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    experiment_id: str = Field(min_length=1)
    experiment_revision: int = Field(ge=1)
    manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    assignment_ref: str = Field(min_length=1)
    metric_refs: tuple[str, ...] = Field(min_length=1)
    parity_report_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    contamination_report_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    artifacts: tuple[JudgeVisibleArtifact, JudgeVisibleArtifact]
    bundle_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class BlindIdentityMapping(BaseModel):
    """Secret sidecar mapping kept separate from judge-visible material."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    experiment_id: str = Field(min_length=1)
    experiment_revision: int = Field(ge=1)
    manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    bundle_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    a_track_kind: TrackKind
    b_track_kind: TrackKind
    a_binding_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    b_binding_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    a_output_ref: str = Field(min_length=1)
    b_output_ref: str = Field(min_length=1)
    mapping_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class JudgeMetricResult(BaseModel):
    """Opaque per-metric A/B values; S4-V does not define scoring semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metric_ref: str = Field(min_length=1)
    a_value: JudgeScalar
    b_value: JudgeScalar


class JudgeSubmissionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    experiment_id: str = Field(min_length=1)
    experiment_revision: int = Field(ge=1)
    bundle_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    assignment_ref: str = Field(min_length=1)
    results: tuple[JudgeMetricResult, ...] = Field(min_length=1)
    submitted_at: datetime

    _submitted_at_must_be_aware = field_validator("submitted_at")(_aware_datetime)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class JudgeSubmission(JudgeSubmissionDraft):
    submission_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


def _assert_track_pair(
    manifest: ExperimentManifest,
    hc: TrackBinding,
    baseline: TrackBinding,
) -> None:
    validate_experiment_manifest(manifest)
    validate_track_binding(hc)
    validate_track_binding(baseline)
    if hc.track_kind != "HC" or baseline.track_kind != "BASELINE":
        raise BlindJudgeIntegrityError("Blind Judge bundle requires one HC and one BASELINE track")
    if (
        hc.experiment_id != manifest.experiment_id
        or baseline.experiment_id != manifest.experiment_id
    ):
        raise BlindJudgeIntegrityError("Blind Judge tracks must belong to the manifest experiment")
    if hc.experiment_revision != baseline.experiment_revision:
        raise BlindJudgeIntegrityError("Blind Judge tracks must bind the same experiment revision")
    if (
        hc.manifest_hash != manifest.manifest_hash
        or baseline.manifest_hash != manifest.manifest_hash
    ):
        raise BlindJudgeIntegrityError("Blind Judge tracks must bind the exact manifest hash")


def _assert_passed_report_bindings(
    manifest: ExperimentManifest,
    hc: TrackBinding,
    baseline: TrackBinding,
    parity: ParityReport,
    contamination: ContaminationGateReport,
) -> None:
    validate_parity_report(parity)
    validate_contamination_gate_report(contamination)
    if parity.status != "PASS" or contamination.status != "PASS":
        raise BlindJudgeProtocolError(
            "Blind Judging requires parity and contamination gates to PASS"
        )
    expected = (
        manifest.experiment_id,
        hc.experiment_revision,
        manifest.manifest_hash,
        hc.binding_hash,
        baseline.binding_hash,
    )
    parity_binding = (
        parity.experiment_id,
        parity.experiment_revision,
        parity.manifest_hash,
        parity.hc_binding_hash,
        parity.baseline_binding_hash,
    )
    contamination_binding = (
        contamination.experiment_id,
        contamination.experiment_revision,
        contamination.manifest_hash,
        contamination.hc_binding_hash,
        contamination.baseline_binding_hash,
    )
    if parity_binding != expected or contamination_binding != expected:
        raise BlindJudgeIntegrityError("Blind Judge gates do not bind the exact frozen track set")


def build_blind_judge_bundle(
    manifest: ExperimentManifest,
    hc: TrackBinding,
    baseline: TrackBinding,
    parity: ParityReport,
    contamination: ContaminationGateReport,
) -> tuple[BlindJudgeBundle, BlindIdentityMapping]:
    """Randomize A/B identity only after both frozen-track gates have passed."""
    _assert_track_pair(manifest, hc, baseline)
    _assert_passed_report_bindings(manifest, hc, baseline, parity, contamination)

    ordered = (hc, baseline) if secrets.randbelow(2) == 0 else (baseline, hc)
    artifacts = (
        JudgeVisibleArtifact(
            alias="A",
            artifact_ref=f"blind-artifact:{manifest.experiment_id}:{hc.experiment_revision}:A",
            output_hash=ordered[0].output_hash,
        ),
        JudgeVisibleArtifact(
            alias="B",
            artifact_ref=f"blind-artifact:{manifest.experiment_id}:{hc.experiment_revision}:B",
            output_hash=ordered[1].output_hash,
        ),
    )
    metric_refs = manifest.primary_metrics + manifest.secondary_metrics
    bundle_payload = {
        "experiment_id": manifest.experiment_id,
        "experiment_revision": hc.experiment_revision,
        "manifest_hash": manifest.manifest_hash,
        "assignment_ref": manifest.blind_judge_assignment,
        "metric_refs": list(metric_refs),
        "parity_report_hash": parity.report_hash,
        "contamination_report_hash": contamination.report_hash,
        "artifacts": [item.model_dump(mode="json") for item in artifacts],
    }
    bundle = BlindJudgeBundle.model_validate(
        {**bundle_payload, "bundle_hash": str(canonical_document_sha256(bundle_payload))}
    )
    mapping_payload = {
        "experiment_id": manifest.experiment_id,
        "experiment_revision": hc.experiment_revision,
        "manifest_hash": manifest.manifest_hash,
        "bundle_hash": bundle.bundle_hash,
        "a_track_kind": ordered[0].track_kind,
        "b_track_kind": ordered[1].track_kind,
        "a_binding_hash": ordered[0].binding_hash,
        "b_binding_hash": ordered[1].binding_hash,
        "a_output_ref": ordered[0].output_ref,
        "b_output_ref": ordered[1].output_ref,
    }
    mapping = BlindIdentityMapping.model_validate(
        {**mapping_payload, "mapping_hash": str(canonical_document_sha256(mapping_payload))}
    )
    return bundle, mapping


def validate_blind_judge_bundle(bundle: BlindJudgeBundle) -> None:
    document = bundle.to_document()
    actual_hash = str(document.pop("bundle_hash"))
    expected_hash = str(canonical_document_sha256(document))
    if actual_hash != expected_hash:
        raise BlindJudgeIntegrityError(
            f"Blind Judge bundle hash mismatch: expected {expected_hash}, got {actual_hash}"
        )
    if tuple(item.alias for item in bundle.artifacts) != ("A", "B"):
        raise BlindJudgeIntegrityError("Blind Judge bundle must expose exactly A then B")
    visible = bundle.model_dump(mode="json")
    if "track_kind" in str(visible) or "output_ref" in str(visible):
        raise BlindJudgeIntegrityError("judge-visible bundle contains forbidden identity metadata")


def validate_blind_identity_mapping(mapping: BlindIdentityMapping) -> None:
    document = mapping.to_document()
    actual_hash = str(document.pop("mapping_hash"))
    expected_hash = str(canonical_document_sha256(document))
    if actual_hash != expected_hash:
        raise BlindJudgeIntegrityError(
            f"Blind identity mapping hash mismatch: expected {expected_hash}, got {actual_hash}"
        )
    if {mapping.a_track_kind, mapping.b_track_kind} != {"HC", "BASELINE"}:
        raise BlindJudgeIntegrityError(
            "Blind identity mapping must contain HC and BASELINE exactly once"
        )


def freeze_judge_submission(
    bundle: BlindJudgeBundle,
    draft: JudgeSubmissionDraft,
) -> JudgeSubmission:
    validate_blind_judge_bundle(bundle)
    if (
        draft.experiment_id != bundle.experiment_id
        or draft.experiment_revision != bundle.experiment_revision
        or draft.bundle_hash != bundle.bundle_hash
        or draft.assignment_ref != bundle.assignment_ref
    ):
        raise BlindJudgeIntegrityError("judge submission does not bind the exact frozen bundle")
    metric_refs = tuple(item.metric_ref for item in draft.results)
    if len(set(metric_refs)) != len(metric_refs):
        raise BlindJudgeIntegrityError("judge submission contains duplicate metric references")
    if not set(metric_refs).issubset(set(bundle.metric_refs)):
        raise BlindJudgeIntegrityError("judge submission references a non-preregistered metric")
    payload = draft.to_document()
    return JudgeSubmission.model_validate(
        {**payload, "submission_hash": str(canonical_document_sha256(payload))}
    )


def validate_judge_submission(submission: JudgeSubmission) -> None:
    document = submission.to_document()
    actual_hash = str(document.pop("submission_hash"))
    expected_hash = str(canonical_document_sha256(document))
    if actual_hash != expected_hash:
        raise BlindJudgeIntegrityError(
            f"judge submission hash mismatch: expected {expected_hash}, got {actual_hash}"
        )


def _assert_registered_manifest(
    connection: Connection[Any],
    experiment_id: str,
    experiment_revision: int,
    manifest_hash: str,
) -> None:
    row = connection.execute(
        """
        SELECT manifest_hash
        FROM human_cos_experiment_revision
        WHERE experiment_id = %s AND revision = %s
        """,
        (experiment_id, experiment_revision),
    ).fetchone()
    if row is None:
        raise MissingRecordError(f"experiment not found: {experiment_id}@{experiment_revision}")
    if str(row[0]) != manifest_hash:
        raise BlindJudgeIntegrityError("Blind Judge material does not bind the registered manifest")


def _assert_stored_passed_gates(connection: Connection[Any], bundle: BlindJudgeBundle) -> None:
    parity = connection.execute(
        """
        SELECT status, report_hash
        FROM human_cos_parity_report
        WHERE experiment_id = %s AND experiment_revision = %s
        """,
        (bundle.experiment_id, bundle.experiment_revision),
    ).fetchone()
    contamination = connection.execute(
        """
        SELECT status, report_hash
        FROM human_cos_contamination_gate
        WHERE experiment_id = %s AND experiment_revision = %s
        """,
        (bundle.experiment_id, bundle.experiment_revision),
    ).fetchone()
    if parity is None or contamination is None:
        raise MissingRecordError("Blind Judge gates are not frozen")
    if str(parity[0]) != "PASS" or str(parity[1]) != bundle.parity_report_hash:
        raise BlindJudgeProtocolError("stored parity gate is not the exact PASS report")
    if str(contamination[0]) != "PASS" or str(contamination[1]) != bundle.contamination_report_hash:
        raise BlindJudgeProtocolError("stored contamination gate is not the exact PASS report")


def store_blind_judge_material(
    connection: Connection[Any],
    bundle: BlindJudgeBundle,
    mapping: BlindIdentityMapping,
) -> None:
    """Persist judge-visible bundle and secret mapping in separate immutable tables."""
    validate_blind_judge_bundle(bundle)
    validate_blind_identity_mapping(mapping)
    if (
        mapping.experiment_id != bundle.experiment_id
        or mapping.experiment_revision != bundle.experiment_revision
        or mapping.manifest_hash != bundle.manifest_hash
        or mapping.bundle_hash != bundle.bundle_hash
    ):
        raise BlindJudgeIntegrityError("secret mapping does not bind the exact judge bundle")
    _assert_registered_manifest(
        connection, bundle.experiment_id, bundle.experiment_revision, bundle.manifest_hash
    )
    _assert_stored_passed_gates(connection, bundle)
    try:
        connection.execute(
            """
            INSERT INTO human_cos_blind_judge_bundle
                (experiment_id, experiment_revision, bundle_hash, payload)
            VALUES (%s, %s, %s, %s)
            """,
            (
                bundle.experiment_id,
                bundle.experiment_revision,
                bundle.bundle_hash,
                Jsonb(bundle.to_document()),
            ),
        )
        connection.execute(
            """
            INSERT INTO human_cos_blind_identity_mapping
                (experiment_id, experiment_revision, bundle_hash, mapping_hash, payload)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                mapping.experiment_id,
                mapping.experiment_revision,
                mapping.bundle_hash,
                mapping.mapping_hash,
                Jsonb(mapping.to_document()),
            ),
        )
        connection.commit()
    except errors.UniqueViolation as exc:
        connection.rollback()
        raise DuplicateRevisionError(
            "Blind Judge material already frozen: "
            f"{bundle.experiment_id}@{bundle.experiment_revision}"
        ) from exc


def store_judge_submission(connection: Connection[Any], submission: JudgeSubmission) -> None:
    """Freeze the sole judge submission for an experiment revision."""
    validate_judge_submission(submission)
    row = connection.execute(
        """
        SELECT bundle_hash, payload
        FROM human_cos_blind_judge_bundle
        WHERE experiment_id = %s AND experiment_revision = %s
        """,
        (submission.experiment_id, submission.experiment_revision),
    ).fetchone()
    if row is None:
        raise MissingRecordError("Blind Judge bundle is not frozen")
    bundle = BlindJudgeBundle.model_validate(dict(row[1]))
    validate_blind_judge_bundle(bundle)
    if str(row[0]) != submission.bundle_hash or bundle.assignment_ref != submission.assignment_ref:
        raise BlindJudgeIntegrityError("judge submission does not bind the stored bundle")
    allowed_metrics = set(bundle.metric_refs)
    if not {item.metric_ref for item in submission.results}.issubset(allowed_metrics):
        raise BlindJudgeIntegrityError("judge submission references a non-preregistered metric")
    try:
        connection.execute(
            """
            INSERT INTO human_cos_judge_submission
                (experiment_id, experiment_revision, bundle_hash, submission_hash, payload)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                submission.experiment_id,
                submission.experiment_revision,
                submission.bundle_hash,
                submission.submission_hash,
                Jsonb(submission.to_document()),
            ),
        )
        connection.commit()
    except errors.UniqueViolation as exc:
        connection.rollback()
        raise DuplicateRevisionError(
            f"judge submission already frozen: "
            f"{submission.experiment_id}@{submission.experiment_revision}"
        ) from exc
