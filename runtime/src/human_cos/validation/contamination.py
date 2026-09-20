"""S4-V3 fail-closed Recognition/Contamination and AT-05 Invalid Gate."""

from __future__ import annotations

from typing import Any, Literal

from psycopg import Connection, errors
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from human_cos.runtime.run import canonical_document_sha256
from human_cos.storage.repository import DuplicateRevisionError, MissingRecordError
from human_cos.validation.manifest import ExperimentManifest, validate_experiment_manifest
from human_cos.validation.tracks import TrackBinding, validate_track_binding

GateStatus = Literal["PASS", "FAIL"]
RecognitionInvalidFact = Literal[
    "event_identity_recognized",
    "same_session_or_knowledge_inheritance",
    "post_t0_leakage",
    "unresolved_protocol_invalid",
]
ContaminationInvalidFact = Literal[
    "event_identity_recognized",
    "same_session_or_knowledge_inheritance",
    "post_t0_leakage",
    "cross_track_contamination",
    "blind_judge_identity_leakage",
    "unresolved_protocol_invalid",
]


class InvalidGateIntegrityError(ValueError):
    """A frozen recognition/contamination report is internally inconsistent."""


class InvalidGateError(RuntimeError):
    """A fail-closed S4 AT-05 guard rejected progression."""


class RecognitionPrecheckFacts(BaseModel):
    """Explicit pre-track facts; every field is required so missing facts cannot default PASS."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_identity_recognized: bool
    same_session_or_knowledge_inheritance: bool
    post_t0_leakage: bool
    unresolved_protocol_invalid: bool

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class RecognitionPrecheckReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    experiment_id: str = Field(min_length=1)
    experiment_revision: int = Field(ge=1)
    manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    facts: RecognitionPrecheckFacts
    invalid_facts: tuple[RecognitionInvalidFact, ...]
    status: GateStatus
    report_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ContaminationFacts(BaseModel):
    """Exact authorized S4 Validation-Lab invalidity facts; no numeric recognition threshold."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_identity_recognized: bool
    same_session_or_knowledge_inheritance: bool
    post_t0_leakage: bool
    cross_track_contamination: bool
    blind_judge_identity_leakage: bool
    unresolved_protocol_invalid: bool

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ContaminationGateReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    experiment_id: str = Field(min_length=1)
    experiment_revision: int = Field(ge=1)
    manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    hc_binding_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    baseline_binding_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    facts: ContaminationFacts
    invalid_facts: tuple[ContaminationInvalidFact, ...]
    status: GateStatus
    report_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def _recognition_invalid_facts(
    facts: RecognitionPrecheckFacts,
) -> tuple[RecognitionInvalidFact, ...]:
    invalid: list[RecognitionInvalidFact] = []
    if facts.event_identity_recognized:
        invalid.append("event_identity_recognized")
    if facts.same_session_or_knowledge_inheritance:
        invalid.append("same_session_or_knowledge_inheritance")
    if facts.post_t0_leakage:
        invalid.append("post_t0_leakage")
    if facts.unresolved_protocol_invalid:
        invalid.append("unresolved_protocol_invalid")
    return tuple(invalid)


def _contamination_invalid_facts(facts: ContaminationFacts) -> tuple[ContaminationInvalidFact, ...]:
    invalid: list[ContaminationInvalidFact] = []
    if facts.event_identity_recognized:
        invalid.append("event_identity_recognized")
    if facts.same_session_or_knowledge_inheritance:
        invalid.append("same_session_or_knowledge_inheritance")
    if facts.post_t0_leakage:
        invalid.append("post_t0_leakage")
    if facts.cross_track_contamination:
        invalid.append("cross_track_contamination")
    if facts.blind_judge_identity_leakage:
        invalid.append("blind_judge_identity_leakage")
    if facts.unresolved_protocol_invalid:
        invalid.append("unresolved_protocol_invalid")
    return tuple(invalid)


def evaluate_recognition_precheck(
    manifest: ExperimentManifest,
    experiment_revision: int,
    facts: RecognitionPrecheckFacts,
) -> RecognitionPrecheckReport:
    """Fail closed when any explicitly recorded pre-track invalidity fact is present."""
    validate_experiment_manifest(manifest)
    invalid_facts = _recognition_invalid_facts(facts)
    status: GateStatus = "PASS" if not invalid_facts else "FAIL"
    payload = {
        "experiment_id": manifest.experiment_id,
        "experiment_revision": experiment_revision,
        "manifest_hash": manifest.manifest_hash,
        "facts": facts.to_document(),
        "invalid_facts": list(invalid_facts),
        "status": status,
    }
    return RecognitionPrecheckReport.model_validate(
        {**payload, "report_hash": str(canonical_document_sha256(payload))}
    )


def validate_recognition_precheck_report(report: RecognitionPrecheckReport) -> None:
    document = report.to_document()
    actual_hash = str(document.pop("report_hash"))
    expected_hash = str(canonical_document_sha256(document))
    if actual_hash != expected_hash:
        raise InvalidGateIntegrityError(
            f"recognition precheck hash mismatch: expected {expected_hash}, got {actual_hash}"
        )
    expected_invalid = _recognition_invalid_facts(report.facts)
    expected_status: GateStatus = "PASS" if not expected_invalid else "FAIL"
    if report.invalid_facts != expected_invalid or report.status != expected_status:
        raise InvalidGateIntegrityError("recognition precheck does not match its explicit facts")


def require_recognition_precheck_pass(report: RecognitionPrecheckReport) -> None:
    validate_recognition_precheck_report(report)
    if report.status != "PASS":
        raise InvalidGateError("S4 AT-05 blocks track execution: recognition precheck is invalid")


def evaluate_contamination_gate(
    manifest: ExperimentManifest,
    hc: TrackBinding,
    baseline: TrackBinding,
    facts: ContaminationFacts,
) -> ContaminationGateReport:
    """Evaluate only explicit authorized invalidity facts for the exact frozen track set."""
    validate_experiment_manifest(manifest)
    validate_track_binding(hc)
    validate_track_binding(baseline)
    if hc.track_kind != "HC" or baseline.track_kind != "BASELINE":
        raise ValueError("contamination gate requires one HC and one BASELINE track")
    if (
        hc.experiment_id != manifest.experiment_id
        or baseline.experiment_id != manifest.experiment_id
    ):
        raise ValueError("contamination tracks must belong to the manifest experiment")
    if hc.experiment_revision != baseline.experiment_revision:
        raise ValueError("contamination tracks must bind the same experiment revision")
    if (
        hc.manifest_hash != manifest.manifest_hash
        or baseline.manifest_hash != manifest.manifest_hash
    ):
        raise ValueError("contamination tracks must bind the exact Experiment Manifest hash")

    invalid_facts = _contamination_invalid_facts(facts)
    status: GateStatus = "PASS" if not invalid_facts else "FAIL"
    payload = {
        "experiment_id": manifest.experiment_id,
        "experiment_revision": hc.experiment_revision,
        "manifest_hash": manifest.manifest_hash,
        "hc_binding_hash": hc.binding_hash,
        "baseline_binding_hash": baseline.binding_hash,
        "facts": facts.to_document(),
        "invalid_facts": list(invalid_facts),
        "status": status,
    }
    return ContaminationGateReport.model_validate(
        {**payload, "report_hash": str(canonical_document_sha256(payload))}
    )


def validate_contamination_gate_report(report: ContaminationGateReport) -> None:
    document = report.to_document()
    actual_hash = str(document.pop("report_hash"))
    expected_hash = str(canonical_document_sha256(document))
    if actual_hash != expected_hash:
        raise InvalidGateIntegrityError(
            f"contamination gate hash mismatch: expected {expected_hash}, got {actual_hash}"
        )
    expected_invalid = _contamination_invalid_facts(report.facts)
    expected_status: GateStatus = "PASS" if not expected_invalid else "FAIL"
    if report.invalid_facts != expected_invalid or report.status != expected_status:
        raise InvalidGateIntegrityError("contamination gate does not match its explicit facts")


def require_contamination_pass(report: ContaminationGateReport) -> None:
    validate_contamination_gate_report(report)
    if report.status != "PASS":
        raise InvalidGateError("S4 AT-05 blocks Blind Judging: contamination gate is invalid")


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
        raise InvalidGateIntegrityError("gate report does not bind the registered manifest hash")


def store_recognition_precheck(
    connection: Connection[Any],
    report: RecognitionPrecheckReport,
) -> None:
    """Freeze the sole recognition precheck for an experiment revision."""
    validate_recognition_precheck_report(report)
    _assert_registered_manifest(
        connection,
        report.experiment_id,
        report.experiment_revision,
        report.manifest_hash,
    )
    try:
        connection.execute(
            """
            INSERT INTO human_cos_recognition_precheck
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
            "recognition precheck already frozen: "
            f"{report.experiment_id}@{report.experiment_revision}"
        ) from exc


def _assert_stored_track_hashes(
    connection: Connection[Any],
    report: ContaminationGateReport,
) -> None:
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
        raise InvalidGateIntegrityError("contamination gate does not bind the stored HC track")
    if stored.get("BASELINE") != report.baseline_binding_hash:
        raise InvalidGateIntegrityError(
            "contamination gate does not bind the stored BASELINE track"
        )


def store_contamination_gate(
    connection: Connection[Any],
    report: ContaminationGateReport,
) -> None:
    """Freeze the sole fail-closed contamination/invalid outcome for the exact track set."""
    validate_contamination_gate_report(report)
    _assert_registered_manifest(
        connection,
        report.experiment_id,
        report.experiment_revision,
        report.manifest_hash,
    )
    _assert_stored_track_hashes(connection, report)
    try:
        connection.execute(
            """
            INSERT INTO human_cos_contamination_gate
                (experiment_id, experiment_revision, hc_binding_hash,
                 baseline_binding_hash, status, report_hash, payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                report.experiment_id,
                report.experiment_revision,
                report.hc_binding_hash,
                report.baseline_binding_hash,
                report.status,
                report.report_hash,
                Jsonb(report.to_document()),
            ),
        )
        connection.commit()
    except errors.UniqueViolation as exc:
        connection.rollback()
        raise DuplicateRevisionError(
            "contamination gate already frozen: "
            f"{report.experiment_id}@{report.experiment_revision}"
        ) from exc
