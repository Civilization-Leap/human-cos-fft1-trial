"""S4-V deterministic AT-11 Baseline Parity evaluation."""

from __future__ import annotations

from typing import Any, Literal

from psycopg import Connection, errors
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, model_validator

from human_cos.runtime.run import canonical_document_sha256
from human_cos.storage.repository import DuplicateRevisionError, MissingRecordError
from human_cos.validation.manifest import ExperimentManifest
from human_cos.validation.tracks import TrackBinding, validate_track_binding

ParityDimension = Literal["input", "tool", "budget", "output_contract"]
ParityStatus = Literal["PASS", "FAIL"]


class ParityDeclaration(BaseModel):
    """Pre-result expected HC/Baseline descriptors for one frozen parity dimension."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension: ParityDimension
    hc_descriptor: str = Field(min_length=1)
    baseline_descriptor: str = Field(min_length=1)
    asymmetry_rationale: str | None = None

    @model_validator(mode="after")
    def _asymmetry_requires_rationale(self) -> ParityDeclaration:
        if self.hc_descriptor != self.baseline_descriptor and not self.asymmetry_rationale:
            raise ValueError("pre-registered asymmetric parity requires an explicit rationale")
        return self

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)

    @property
    def declaration_hash(self) -> str:
        return str(canonical_document_sha256(self.to_document()))


class ParityDimensionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension: ParityDimension
    declaration_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    manifest_binding_ok: bool
    hc_matches_preregistration: bool
    baseline_matches_preregistration: bool

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)

    @property
    def passed(self) -> bool:
        return (
            self.manifest_binding_ok
            and self.hc_matches_preregistration
            and self.baseline_matches_preregistration
        )


class ParityReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    experiment_id: str = Field(min_length=1)
    experiment_revision: int = Field(ge=1)
    manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    hc_binding_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    baseline_binding_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    dimensions: tuple[ParityDimensionResult, ...] = Field(min_length=4, max_length=4)
    status: ParityStatus
    report_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


def _manifest_parity_hashes(manifest: ExperimentManifest) -> dict[ParityDimension, str]:
    return {
        "input": manifest.input_parity,
        "tool": manifest.tool_parity,
        "budget": manifest.budget_parity,
        "output_contract": manifest.output_contract_parity,
    }


def _track_descriptors(binding: TrackBinding) -> dict[ParityDimension, str]:
    return {
        "input": binding.input_descriptor,
        "tool": binding.tool_descriptor,
        "budget": binding.budget_descriptor,
        "output_contract": binding.output_contract_descriptor,
    }


def evaluate_parity(
    manifest: ExperimentManifest,
    hc: TrackBinding,
    baseline: TrackBinding,
    declarations: tuple[ParityDeclaration, ...],
) -> ParityReport:
    """Compare frozen tracks only against declarations already hash-bound in the manifest."""
    validate_track_binding(hc)
    validate_track_binding(baseline)
    if hc.track_kind != "HC" or baseline.track_kind != "BASELINE":
        raise ValueError("AT-11 requires one HC track and one BASELINE track")
    if (
        hc.experiment_id != manifest.experiment_id
        or baseline.experiment_id != manifest.experiment_id
    ):
        raise ValueError("parity tracks must belong to the manifest experiment")
    if (
        hc.manifest_hash != manifest.manifest_hash
        or baseline.manifest_hash != manifest.manifest_hash
    ):
        raise ValueError("parity tracks must bind the exact Experiment Manifest hash")
    if hc.experiment_revision != baseline.experiment_revision:
        raise ValueError("parity tracks must bind the same experiment revision")

    by_dimension = {item.dimension: item for item in declarations}
    required: tuple[ParityDimension, ...] = ("input", "tool", "budget", "output_contract")
    if set(by_dimension) != set(required) or len(declarations) != 4:
        raise ValueError(
            "AT-11 requires exactly one preregistered declaration per parity dimension"
        )

    manifest_hashes = _manifest_parity_hashes(manifest)
    hc_descriptors = _track_descriptors(hc)
    baseline_descriptors = _track_descriptors(baseline)
    results = tuple(
        ParityDimensionResult(
            dimension=dimension,
            declaration_hash=by_dimension[dimension].declaration_hash,
            manifest_binding_ok=(
                manifest_hashes[dimension] == by_dimension[dimension].declaration_hash
            ),
            hc_matches_preregistration=(
                hc_descriptors[dimension] == by_dimension[dimension].hc_descriptor
            ),
            baseline_matches_preregistration=(
                baseline_descriptors[dimension] == by_dimension[dimension].baseline_descriptor
            ),
        )
        for dimension in required
    )
    status: ParityStatus = "PASS" if all(item.passed for item in results) else "FAIL"
    payload = {
        "experiment_id": manifest.experiment_id,
        "experiment_revision": hc.experiment_revision,
        "manifest_hash": manifest.manifest_hash,
        "hc_binding_hash": hc.binding_hash,
        "baseline_binding_hash": baseline.binding_hash,
        "dimensions": [item.to_document() for item in results],
        "status": status,
    }
    return ParityReport.model_validate(
        {**payload, "report_hash": canonical_document_sha256(payload)}
    )


def validate_parity_report(report: ParityReport) -> None:
    document = report.to_document()
    actual = str(document.pop("report_hash"))
    expected = canonical_document_sha256(document)
    if actual != expected:
        raise ValueError(f"parity report hash mismatch: expected {expected}, got {actual}")
    expected_status = "PASS" if all(item.passed for item in report.dimensions) else "FAIL"
    if report.status != expected_status:
        raise ValueError("parity report status does not match dimension results")


def _assert_stored_track_hashes(connection: Connection[Any], report: ParityReport) -> None:
    rows = connection.execute(
        """
        SELECT track_kind, binding_hash
        FROM human_cos_validation_track
        WHERE experiment_id = %s AND experiment_revision = %s
        """,
        (report.experiment_id, report.experiment_revision),
    ).fetchall()
    stored = {str(kind): str(binding_hash) for kind, binding_hash in rows}
    if stored.get("HC") != report.hc_binding_hash:
        raise ValueError("parity report HC hash does not bind the stored frozen HC track")
    if stored.get("BASELINE") != report.baseline_binding_hash:
        raise ValueError(
            "parity report BASELINE hash does not bind the stored frozen BASELINE track"
        )


def store_parity_report(connection: Connection[Any], report: ParityReport) -> None:
    """Freeze the sole AT-11 report for an experiment revision; no post-result waiver path."""
    validate_parity_report(report)
    experiment = connection.execute(
        """
        SELECT manifest_hash
        FROM human_cos_experiment_revision
        WHERE experiment_id = %s AND revision = %s
        """,
        (report.experiment_id, report.experiment_revision),
    ).fetchone()
    if experiment is None:
        raise MissingRecordError(
            f"experiment not found: {report.experiment_id}@{report.experiment_revision}"
        )
    if str(experiment[0]) != report.manifest_hash:
        raise ValueError("parity report does not bind the registered manifest hash")
    _assert_stored_track_hashes(connection, report)
    try:
        connection.execute(
            """
            INSERT INTO human_cos_parity_report
                (experiment_id, experiment_revision, status, report_hash, payload)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                report.experiment_id,
                report.experiment_revision,
                report.status,
                report.report_hash,
                Jsonb(report.to_document()),
            ),
        )
        connection.commit()
    except errors.UniqueViolation as exc:
        connection.rollback()
        raise DuplicateRevisionError(
            f"parity report already frozen: {report.experiment_id}@{report.experiment_revision}"
        ) from exc
