"""Evidence-bound admission for S8 HC Regression and Low-recognition results.

EVAL3 and EVAL4 objects are immutable analytical sidecars, but immutability alone
cannot prove that their metric or exposure facts came from the artifacts they cite.
This module freezes packet-addressable source artifacts and recomputes every
material downstream judgment before a result may be persisted or counted as
milestone evidence.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from human_cos.runtime.run import RunManifest, canonical_document_sha256

from .contracts import (
    EvaluationTaskType,
    EvaluatorInputPacket,
    EvaluatorTask,
    assert_evaluator_packet_binding,
)
from .hc_regression import (
    HCRegressionMetricObservation,
    HCRegressionMetricResult,
    HCRegressionMetricRule,
    HCRegressionParityDeclaration,
    HCRegressionParityDimensionResult,
    HCRegressionPreregistration,
    HCRegressionReport,
    HCRegressionTrackSnapshot,
    RegressionDisposition,
    RegressionMetricDirection,
    RegressionParityDimension,
    RegressionValidity,
)
from .low_recognition import (
    LowRecognitionExposureSnapshot,
    LowRecognitionGate,
    LowRecognitionGateStatus,
    LowRecognitionInvalidFact,
    LowRecognitionVisibilityPolicy,
)


class EvaluationEvidenceBindingError(ValueError):
    """An S8 evaluation object is not bound to code-verifiable source facts."""


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("S8 evidence-binding timestamps require timezone-aware datetimes")
    return value


def _finite(value: float) -> float:
    if value != value or value in {float("inf"), float("-inf")}:
        raise ValueError("S8 evidence-binding metric values must be finite")
    return value


def _assert_unique(values: tuple[str, ...], *, name: str) -> None:
    if len(values) != len(set(values)):
        raise EvaluationEvidenceBindingError(f"{name} must not contain duplicates")


def _payload_without_hash(model: BaseModel, hash_field: str) -> dict[str, Any]:
    return model.model_dump(mode="json", exclude={hash_field}, exclude_none=True)


class _FrozenBindingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class EvaluationBindingSubject(str, Enum):
    HC_REGRESSION = "HC_REGRESSION"
    LOW_RECOGNITION = "LOW_RECOGNITION"


class HCRegressionMetricSourcePayload(_FrozenBindingModel):
    """Exact, packet-addressable observations for one regression track."""

    source_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    track_kind: Literal["HC", "BASELINE"]
    run_id: str = Field(min_length=1)
    run_manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    metric_values: tuple[HCRegressionMetricObservation, ...] = Field(min_length=1)
    source_hash_refs: tuple[str, ...] = Field(min_length=1)
    protocol_version: str = Field(min_length=1)
    observed_at: datetime
    frozen_at: datetime

    _observed_at_must_be_aware = field_validator("observed_at")(_aware)
    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class HCRegressionMetricSource(HCRegressionMetricSourcePayload):
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        _assert_unique(
            tuple(item.metric_id for item in self.metric_values),
            name="HC metric source metric IDs",
        )
        _assert_unique(self.source_hash_refs, name="HC metric source refs")
        if self.frozen_at < self.observed_at:
            raise EvaluationEvidenceBindingError(
                "HC metric source cannot freeze before observation"
            )
        payload = _payload_without_hash(self, "source_hash")
        if self.source_hash != canonical_document_sha256(payload):
            raise EvaluationEvidenceBindingError("HC metric source hash mismatch")


def freeze_hc_regression_metric_source(
    payload: HCRegressionMetricSourcePayload,
    *,
    run_manifest: RunManifest,
) -> HCRegressionMetricSource:
    if run_manifest.run_id != payload.run_id:
        raise EvaluationEvidenceBindingError("HC metric source Run ID differs")
    if run_manifest.case_id != payload.case_id:
        raise EvaluationEvidenceBindingError("HC metric source Run belongs to another Case")
    if run_manifest.protocol_version != payload.protocol_version:
        raise EvaluationEvidenceBindingError("HC metric source Run protocol differs")
    if run_manifest.status != "FROZEN":
        raise EvaluationEvidenceBindingError("HC metric source requires a frozen Run")
    run_hash = canonical_document_sha256(run_manifest.to_document())
    if payload.run_manifest_hash != run_hash:
        raise EvaluationEvidenceBindingError("HC metric source Run hash differs")
    document = payload.to_document()
    source = HCRegressionMetricSource.model_validate(
        {**document, "source_hash": canonical_document_sha256(document)}
    )
    source.assert_integrity()
    return source


class LowRecognitionExposureSourcePayload(_FrozenBindingModel):
    """Exact, packet-addressable visibility and contamination observations."""

    source_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    entity_system_identity_exposed: bool
    provenance_label_exposed: bool
    solver_controller_identity_exposed: bool
    comparison_label_exposed: bool
    material_revealed_before_freeze: tuple[str, ...] = ()
    same_session_or_inherited_knowledge: bool
    cross_evaluator_contamination: bool
    cross_comparison_contamination: bool
    unresolved_protocol_invalid: bool
    source_hash_refs: tuple[str, ...] = Field(min_length=1)
    protocol_version: str = Field(min_length=1)
    observed_at: datetime
    frozen_at: datetime

    _observed_at_must_be_aware = field_validator("observed_at")(_aware)
    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class LowRecognitionExposureSource(LowRecognitionExposureSourcePayload):
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        _assert_unique(
            self.material_revealed_before_freeze,
            name="Low-recognition prematurely revealed material",
        )
        _assert_unique(self.source_hash_refs, name="Low-recognition source refs")
        if self.frozen_at < self.observed_at:
            raise EvaluationEvidenceBindingError(
                "Low-recognition source cannot freeze before observation"
            )
        payload = _payload_without_hash(self, "source_hash")
        if self.source_hash != canonical_document_sha256(payload):
            raise EvaluationEvidenceBindingError("Low-recognition source hash mismatch")


def freeze_low_recognition_exposure_source(
    payload: LowRecognitionExposureSourcePayload,
) -> LowRecognitionExposureSource:
    document = payload.to_document()
    source = LowRecognitionExposureSource.model_validate(
        {**document, "source_hash": canonical_document_sha256(document)}
    )
    source.assert_integrity()
    return source


class EvaluationEvidenceBindingPayload(_FrozenBindingModel):
    binding_id: str = Field(min_length=1)
    subject: EvaluationBindingSubject
    task_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    packet_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    subject_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_artifact_hashes: tuple[str, ...] = Field(min_length=1)
    recomputed_facts: tuple[str, ...] = Field(min_length=1)
    status: Literal["PASS"] = "PASS"
    process_authority: Literal[False] = False
    superiority_claim_authorized: Literal[False] = False
    reality_execution_authorized: Literal[False] = False
    final_claim_authorized: Literal[False] = False
    seal_authorized: Literal[False] = False
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class EvaluationEvidenceBinding(EvaluationEvidenceBindingPayload):
    binding_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        _assert_unique(self.source_artifact_hashes, name="binding source artifacts")
        _assert_unique(self.recomputed_facts, name="binding recomputed facts")
        if (
            self.process_authority
            or self.superiority_claim_authorized
            or self.reality_execution_authorized
            or self.final_claim_authorized
            or self.seal_authorized
        ):
            raise EvaluationEvidenceBindingError("evidence binding grants no authority")
        payload = _payload_without_hash(self, "binding_hash")
        if self.binding_hash != canonical_document_sha256(payload):
            raise EvaluationEvidenceBindingError("Evaluation evidence-binding hash mismatch")


def _freeze_binding(
    payload: EvaluationEvidenceBindingPayload,
) -> EvaluationEvidenceBinding:
    document = payload.to_document()
    binding = EvaluationEvidenceBinding.model_validate(
        {**document, "binding_hash": canonical_document_sha256(document)}
    )
    binding.assert_integrity()
    return binding


def _assert_packet_contains(
    packet: EvaluatorInputPacket,
    hashes: tuple[str, ...],
    *,
    name: str,
) -> None:
    missing = tuple(sorted(set(hashes).difference(packet.source_hashes)))
    if missing:
        raise EvaluationEvidenceBindingError(
            f"{name} contains hashes outside the code-owned packet: " + ", ".join(missing)
        )


def _assert_no_result_authority(result: object, *, name: str) -> None:
    for field in (
        "process_authority",
        "superiority_claim_authorized",
        "reality_execution_authorized",
        "final_claim_authorized",
        "seal_authorized",
    ):
        if bool(getattr(result, field, False)):
            raise EvaluationEvidenceBindingError(f"{name} cannot authorize {field}")


def _assert_regression_preregistration(
    *,
    task: EvaluatorTask,
    packet: EvaluatorInputPacket,
    preregistration: HCRegressionPreregistration,
    declarations: tuple[HCRegressionParityDeclaration, ...],
    metric_rules: tuple[HCRegressionMetricRule, ...],
) -> None:
    assert_evaluator_packet_binding(task, packet)
    if task.evaluation_type is not EvaluationTaskType.HC_REGRESSION:
        raise EvaluationEvidenceBindingError("HC binding requires an HC_REGRESSION task")
    preregistration.assert_integrity()
    for declaration in declarations:
        declaration.assert_integrity()
    for rule in metric_rules:
        rule.assert_integrity()
    if (
        preregistration.task_hash != task.task_hash
        or preregistration.packet_hash != packet.packet_hash
        or preregistration.case_id != task.case_id
        or preregistration.case_revision != task.case_revision
        or preregistration.protocol_version != task.protocol_version
    ):
        raise EvaluationEvidenceBindingError("HC preregistration lineage differs")
    if preregistration.parity_declaration_hashes != tuple(
        item.declaration_hash for item in declarations
    ):
        raise EvaluationEvidenceBindingError("HC parity declarations differ")
    if preregistration.metric_rule_hashes != tuple(item.rule_hash for item in metric_rules):
        raise EvaluationEvidenceBindingError("HC metric rules differ")
    dimensions = tuple(item.dimension for item in declarations)
    if len(dimensions) != 4 or set(dimensions) != set(RegressionParityDimension):
        raise EvaluationEvidenceBindingError("HC parity declarations are incomplete")
    metric_ids = tuple(item.metric_id for item in metric_rules)
    _assert_unique(metric_ids, name="HC preregistered metric IDs")
    if not metric_ids:
        raise EvaluationEvidenceBindingError("HC regression requires metric rules")


def _assert_metric_source(
    *,
    source: HCRegressionMetricSource,
    expected_track: Literal["HC", "BASELINE"],
    task: EvaluatorTask,
    packet: EvaluatorInputPacket,
    preregistration: HCRegressionPreregistration,
    metric_rules: tuple[HCRegressionMetricRule, ...],
    run_manifest: RunManifest,
) -> None:
    source.assert_integrity()
    if source.track_kind != expected_track:
        raise EvaluationEvidenceBindingError("HC metric source track kind differs")
    expected_run_id = (
        preregistration.hc_run_id if expected_track == "HC" else preregistration.baseline_run_id
    )
    if source.run_id != expected_run_id:
        raise EvaluationEvidenceBindingError("HC metric source Run differs")
    if (
        source.case_id != task.case_id
        or source.case_revision != task.case_revision
        or source.protocol_version != task.protocol_version
    ):
        raise EvaluationEvidenceBindingError("HC metric source Case/protocol differs")
    if source.frozen_at > packet.frozen_at:
        raise EvaluationEvidenceBindingError(
            "HC metric source must freeze before the packet that cites it"
        )
    if run_manifest.run_id != source.run_id or run_manifest.case_id != task.case_id:
        raise EvaluationEvidenceBindingError("HC source Run Manifest identity differs")
    if run_manifest.protocol_version != task.protocol_version or run_manifest.status != "FROZEN":
        raise EvaluationEvidenceBindingError("HC source Run Manifest is not eligible")
    run_hash = canonical_document_sha256(run_manifest.to_document())
    if source.run_manifest_hash != run_hash:
        raise EvaluationEvidenceBindingError("HC source Run Manifest hash differs")
    expected_metrics = tuple(item.metric_id for item in metric_rules)
    actual_metrics = tuple(item.metric_id for item in source.metric_values)
    if actual_metrics != expected_metrics:
        raise EvaluationEvidenceBindingError("HC metric source order differs from rules")
    _assert_packet_contains(
        packet,
        (source.source_hash, source.run_manifest_hash, *source.source_hash_refs),
        name=f"{expected_track} metric source",
    )


def _assert_track_snapshot(
    *,
    snapshot: HCRegressionTrackSnapshot,
    source: HCRegressionMetricSource,
    expected_track: Literal["HC", "BASELINE"],
    task: EvaluatorTask,
    packet: EvaluatorInputPacket,
    preregistration: HCRegressionPreregistration,
) -> None:
    snapshot.assert_integrity()
    if (
        snapshot.task_hash != task.task_hash
        or snapshot.packet_hash != packet.packet_hash
        or snapshot.preregistration_hash != preregistration.preregistration_hash
        or snapshot.protocol_version != task.protocol_version
    ):
        raise EvaluationEvidenceBindingError("HC snapshot lineage differs")
    if snapshot.track_kind != expected_track or snapshot.run_id != source.run_id:
        raise EvaluationEvidenceBindingError("HC snapshot track/Run differs from source")
    if snapshot.run_manifest_hash != source.run_manifest_hash:
        raise EvaluationEvidenceBindingError("HC snapshot Run hash differs from source")
    if snapshot.metric_source_hash != source.source_hash:
        raise EvaluationEvidenceBindingError("HC snapshot omits its exact metric source")
    if snapshot.metric_values != source.metric_values:
        raise EvaluationEvidenceBindingError(
            "HC snapshot metric values are not derived from the cited source artifact"
        )
    if snapshot.frozen_at < max(preregistration.preregistered_at, source.frozen_at):
        raise EvaluationEvidenceBindingError("HC snapshot predates its frozen inputs")


def _expected_parity_results(
    *,
    declarations: tuple[HCRegressionParityDeclaration, ...],
    hc_snapshot: HCRegressionTrackSnapshot,
    baseline_snapshot: HCRegressionTrackSnapshot,
) -> tuple[HCRegressionParityDimensionResult, ...]:
    declaration_map = {item.dimension: item for item in declarations}
    hc_descriptors = {
        RegressionParityDimension.INPUT: hc_snapshot.input_descriptor,
        RegressionParityDimension.TOOL: hc_snapshot.tool_descriptor,
        RegressionParityDimension.BUDGET: hc_snapshot.budget_descriptor,
        RegressionParityDimension.OUTPUT_CONTRACT: hc_snapshot.output_contract_descriptor,
    }
    baseline_descriptors = {
        RegressionParityDimension.INPUT: baseline_snapshot.input_descriptor,
        RegressionParityDimension.TOOL: baseline_snapshot.tool_descriptor,
        RegressionParityDimension.BUDGET: baseline_snapshot.budget_descriptor,
        RegressionParityDimension.OUTPUT_CONTRACT: baseline_snapshot.output_contract_descriptor,
    }
    return tuple(
        HCRegressionParityDimensionResult(
            dimension=dimension,
            declaration_hash=declaration_map[dimension].declaration_hash,
            hc_matches_preregistration=(
                hc_descriptors[dimension] == declaration_map[dimension].hc_descriptor
            ),
            baseline_matches_preregistration=(
                baseline_descriptors[dimension] == declaration_map[dimension].baseline_descriptor
            ),
        )
        for dimension in RegressionParityDimension
    )


def _regression_detected(
    rule: HCRegressionMetricRule,
    *,
    hc_value: float,
    baseline_value: float,
) -> bool:
    if rule.direction is RegressionMetricDirection.HIGHER_IS_BETTER:
        return hc_value < baseline_value - rule.noninferiority_margin
    return hc_value > baseline_value + rule.noninferiority_margin


def _expected_metric_results(
    *,
    metric_rules: tuple[HCRegressionMetricRule, ...],
    hc_source: HCRegressionMetricSource,
    baseline_source: HCRegressionMetricSource,
) -> tuple[HCRegressionMetricResult, ...]:
    hc_values = {item.metric_id: item.value for item in hc_source.metric_values}
    baseline_values = {item.metric_id: item.value for item in baseline_source.metric_values}
    return tuple(
        HCRegressionMetricResult(
            metric_id=rule.metric_id,
            rule_hash=rule.rule_hash,
            direction=rule.direction,
            noninferiority_margin=rule.noninferiority_margin,
            hc_value=hc_values[rule.metric_id],
            baseline_value=baseline_values[rule.metric_id],
            regression_detected=_regression_detected(
                rule,
                hc_value=hc_values[rule.metric_id],
                baseline_value=baseline_values[rule.metric_id],
            ),
        )
        for rule in metric_rules
    )


def assert_hc_regression_evidence_binding(
    *,
    task: EvaluatorTask,
    packet: EvaluatorInputPacket,
    preregistration: HCRegressionPreregistration,
    declarations: tuple[HCRegressionParityDeclaration, ...],
    metric_rules: tuple[HCRegressionMetricRule, ...],
    hc_run_manifest: RunManifest,
    baseline_run_manifest: RunManifest,
    hc_metric_source: HCRegressionMetricSource,
    baseline_metric_source: HCRegressionMetricSource,
    hc_snapshot: HCRegressionTrackSnapshot,
    baseline_snapshot: HCRegressionTrackSnapshot,
    report: HCRegressionReport,
    binding_id: str,
    frozen_at: datetime,
) -> EvaluationEvidenceBinding:
    """Recompute EVAL3 facts before the report can become authoritative evidence."""

    _aware(frozen_at)
    _assert_regression_preregistration(
        task=task,
        packet=packet,
        preregistration=preregistration,
        declarations=declarations,
        metric_rules=metric_rules,
    )
    _assert_metric_source(
        source=hc_metric_source,
        expected_track="HC",
        task=task,
        packet=packet,
        preregistration=preregistration,
        metric_rules=metric_rules,
        run_manifest=hc_run_manifest,
    )
    _assert_metric_source(
        source=baseline_metric_source,
        expected_track="BASELINE",
        task=task,
        packet=packet,
        preregistration=preregistration,
        metric_rules=metric_rules,
        run_manifest=baseline_run_manifest,
    )
    if hc_metric_source.source_hash == baseline_metric_source.source_hash:
        raise EvaluationEvidenceBindingError("HC and Baseline require distinct sources")
    _assert_track_snapshot(
        snapshot=hc_snapshot,
        source=hc_metric_source,
        expected_track="HC",
        task=task,
        packet=packet,
        preregistration=preregistration,
    )
    _assert_track_snapshot(
        snapshot=baseline_snapshot,
        source=baseline_metric_source,
        expected_track="BASELINE",
        task=task,
        packet=packet,
        preregistration=preregistration,
    )

    report.assert_integrity()
    if (
        report.task_hash != task.task_hash
        or report.packet_hash != packet.packet_hash
        or report.preregistration_hash != preregistration.preregistration_hash
        or report.hc_snapshot_hash != hc_snapshot.snapshot_hash
        or report.baseline_snapshot_hash != baseline_snapshot.snapshot_hash
        or report.protocol_version != task.protocol_version
    ):
        raise EvaluationEvidenceBindingError("HC report lineage differs")
    if report.frozen_at < max(hc_snapshot.frozen_at, baseline_snapshot.frozen_at):
        raise EvaluationEvidenceBindingError("HC report predates its compared snapshots")

    expected_parity = _expected_parity_results(
        declarations=declarations,
        hc_snapshot=hc_snapshot,
        baseline_snapshot=baseline_snapshot,
    )
    if report.parity_results != expected_parity:
        raise EvaluationEvidenceBindingError("HC report parity facts are not recomputable")
    expected_metrics = _expected_metric_results(
        metric_rules=metric_rules,
        hc_source=hc_metric_source,
        baseline_source=baseline_metric_source,
    )
    if report.metric_results != expected_metrics:
        raise EvaluationEvidenceBindingError("HC report metric judgments are not recomputable")

    expected_invalid = tuple(
        f"parity-fail:{item.dimension.value}" for item in expected_parity if not item.passed
    )
    if report.invalid_reasons != expected_invalid:
        raise EvaluationEvidenceBindingError("HC invalid reasons are not parity-derived")
    expected_validity = RegressionValidity.INVALID if expected_invalid else RegressionValidity.VALID
    if report.validity is not expected_validity:
        raise EvaluationEvidenceBindingError("HC report validity is not recomputable")
    if expected_validity is RegressionValidity.INVALID:
        expected_disposition = RegressionDisposition.INVALID
    elif any(item.regression_detected for item in expected_metrics):
        expected_disposition = RegressionDisposition.REGRESSION_DETECTED
    else:
        expected_disposition = RegressionDisposition.NO_REGRESSION_DETECTED
    if report.disposition is not expected_disposition:
        raise EvaluationEvidenceBindingError("HC report disposition is not recomputable")
    _assert_no_result_authority(report, name="HC report")
    if frozen_at < max(
        report.frozen_at,
        hc_metric_source.frozen_at,
        baseline_metric_source.frozen_at,
    ):
        raise EvaluationEvidenceBindingError("HC binding predates its authoritative inputs")

    facts = (
        f"parity_valid={str(not expected_invalid).lower()}",
        f"validity={expected_validity.value}",
        f"disposition={expected_disposition.value}",
        *(
            f"metric:{item.metric_id}:regression_detected={str(item.regression_detected).lower()}"
            for item in expected_metrics
        ),
        "superiority_claim_authorized=false",
    )
    return _freeze_binding(
        EvaluationEvidenceBindingPayload(
            binding_id=binding_id,
            subject=EvaluationBindingSubject.HC_REGRESSION,
            task_hash=task.task_hash,
            packet_hash=packet.packet_hash,
            subject_hash=report.report_hash,
            source_artifact_hashes=(
                hc_metric_source.source_hash,
                baseline_metric_source.source_hash,
            ),
            recomputed_facts=facts,
            protocol_version=task.protocol_version,
            frozen_at=frozen_at,
        )
    )


def _expected_low_recognition_facts(
    sources: tuple[LowRecognitionExposureSource, ...],
) -> dict[str, object]:
    material = tuple(
        sorted({item for source in sources for item in source.material_revealed_before_freeze})
    )
    return {
        "entity_system_identity_exposed": any(
            source.entity_system_identity_exposed for source in sources
        ),
        "provenance_label_exposed": any(source.provenance_label_exposed for source in sources),
        "solver_controller_identity_exposed": any(
            source.solver_controller_identity_exposed for source in sources
        ),
        "comparison_label_exposed": any(source.comparison_label_exposed for source in sources),
        "material_revealed_before_freeze": material,
        "same_session_or_inherited_knowledge": any(
            source.same_session_or_inherited_knowledge for source in sources
        ),
        "cross_evaluator_contamination": any(
            source.cross_evaluator_contamination for source in sources
        ),
        "cross_comparison_contamination": any(
            source.cross_comparison_contamination for source in sources
        ),
        "unresolved_protocol_invalid": any(
            source.unresolved_protocol_invalid for source in sources
        ),
    }


def _expected_low_recognition_invalid_facts(
    facts: dict[str, object],
) -> tuple[LowRecognitionInvalidFact, ...]:
    invalid: list[LowRecognitionInvalidFact] = []
    checks = (
        (
            "entity_system_identity_exposed",
            LowRecognitionInvalidFact.ENTITY_SYSTEM_IDENTITY_EXPOSED,
        ),
        (
            "provenance_label_exposed",
            LowRecognitionInvalidFact.PROVENANCE_LABEL_EXPOSED,
        ),
        (
            "solver_controller_identity_exposed",
            LowRecognitionInvalidFact.SOLVER_CONTROLLER_IDENTITY_EXPOSED,
        ),
        (
            "comparison_label_exposed",
            LowRecognitionInvalidFact.COMPARISON_LABEL_EXPOSED,
        ),
        (
            "same_session_or_inherited_knowledge",
            LowRecognitionInvalidFact.SAME_SESSION_OR_INHERITED_KNOWLEDGE,
        ),
        (
            "cross_evaluator_contamination",
            LowRecognitionInvalidFact.CROSS_EVALUATOR_CONTAMINATION,
        ),
        (
            "cross_comparison_contamination",
            LowRecognitionInvalidFact.CROSS_COMPARISON_CONTAMINATION,
        ),
        (
            "unresolved_protocol_invalid",
            LowRecognitionInvalidFact.UNRESOLVED_PROTOCOL_INVALID,
        ),
    )
    for field, invalid_fact in checks:
        if facts[field] is True:
            invalid.append(invalid_fact)
    if facts["material_revealed_before_freeze"]:
        invalid.insert(4, LowRecognitionInvalidFact.MATERIAL_REVEALED_BEFORE_FREEZE)
    return tuple(invalid)


def assert_low_recognition_evidence_binding(
    *,
    task: EvaluatorTask,
    packet: EvaluatorInputPacket,
    policy: LowRecognitionVisibilityPolicy,
    exposure_sources: tuple[LowRecognitionExposureSource, ...],
    exposure_snapshot: LowRecognitionExposureSnapshot,
    gate: LowRecognitionGate,
    binding_id: str,
    frozen_at: datetime,
) -> EvaluationEvidenceBinding:
    """Recompute EVAL4 visibility facts before the gate can become evidence."""

    _aware(frozen_at)
    assert_evaluator_packet_binding(task, packet)
    if task.evaluation_type is not EvaluationTaskType.LOW_RECOGNITION:
        raise EvaluationEvidenceBindingError(
            "Low-recognition binding requires a LOW_RECOGNITION task"
        )
    policy.assert_integrity()
    if (
        policy.task_hash != task.task_hash
        or policy.packet_hash != packet.packet_hash
        or policy.case_id != task.case_id
        or policy.case_revision != task.case_revision
        or policy.protocol_version != task.protocol_version
    ):
        raise EvaluationEvidenceBindingError("Low-recognition policy lineage differs")
    if not exposure_sources:
        raise EvaluationEvidenceBindingError("Low-recognition requires exposure sources")
    source_ids = tuple(source.source_id for source in exposure_sources)
    source_hashes = tuple(source.source_hash for source in exposure_sources)
    _assert_unique(source_ids, name="Low-recognition source IDs")
    _assert_unique(source_hashes, name="Low-recognition source hashes")
    for source in exposure_sources:
        source.assert_integrity()
        if (
            source.case_id != task.case_id
            or source.case_revision != task.case_revision
            or source.protocol_version != task.protocol_version
        ):
            raise EvaluationEvidenceBindingError("Low-recognition source Case/protocol differs")
        if source.frozen_at > packet.frozen_at:
            raise EvaluationEvidenceBindingError(
                "Low-recognition source must freeze before the packet that cites it"
            )
        _assert_packet_contains(
            packet,
            (source.source_hash, *source.source_hash_refs),
            name=f"Low-recognition source {source.source_id}",
        )

    exposure_snapshot.assert_integrity()
    if (
        exposure_snapshot.task_hash != task.task_hash
        or exposure_snapshot.packet_hash != packet.packet_hash
        or exposure_snapshot.policy_hash != policy.policy_hash
        or exposure_snapshot.protocol_version != task.protocol_version
    ):
        raise EvaluationEvidenceBindingError("Low-recognition snapshot lineage differs")
    expected_hashes = tuple(sorted(source_hashes))
    if exposure_snapshot.exposure_evidence_hashes != expected_hashes:
        raise EvaluationEvidenceBindingError(
            "Low-recognition snapshot does not cite the exact source set"
        )
    facts = _expected_low_recognition_facts(exposure_sources)
    for field, expected in facts.items():
        if getattr(exposure_snapshot, field) != expected:
            raise EvaluationEvidenceBindingError(
                f"Low-recognition snapshot {field} is not source-derived"
            )
    if exposure_snapshot.frozen_at < max(
        policy.frozen_at,
        *(source.frozen_at for source in exposure_sources),
    ):
        raise EvaluationEvidenceBindingError("Low-recognition snapshot predates its frozen inputs")

    gate.assert_integrity(snapshot=exposure_snapshot)
    if (
        gate.task_hash != task.task_hash
        or gate.packet_hash != packet.packet_hash
        or gate.policy_hash != policy.policy_hash
        or gate.exposure_snapshot_hash != exposure_snapshot.snapshot_hash
        or gate.protocol_version != task.protocol_version
    ):
        raise EvaluationEvidenceBindingError("Low-recognition gate lineage differs")
    expected_invalid = _expected_low_recognition_invalid_facts(facts)
    expected_status = (
        LowRecognitionGateStatus.PASS if not expected_invalid else LowRecognitionGateStatus.BLOCK
    )
    if gate.invalid_facts != expected_invalid or gate.status is not expected_status:
        raise EvaluationEvidenceBindingError(
            "Low-recognition gate is not recomputable from source artifacts"
        )
    if gate.frozen_at < exposure_snapshot.frozen_at:
        raise EvaluationEvidenceBindingError("Low-recognition gate predates snapshot")
    _assert_no_result_authority(gate, name="Low-recognition gate")
    if frozen_at < max(gate.frozen_at, *(source.frozen_at for source in exposure_sources)):
        raise EvaluationEvidenceBindingError(
            "Low-recognition binding predates authoritative inputs"
        )

    recomputed_facts = tuple(f"{field}={str(value).lower()}" for field, value in facts.items()) + (
        f"status={expected_status.value}",
        "superiority_claim_authorized=false",
    )
    return _freeze_binding(
        EvaluationEvidenceBindingPayload(
            binding_id=binding_id,
            subject=EvaluationBindingSubject.LOW_RECOGNITION,
            task_hash=task.task_hash,
            packet_hash=packet.packet_hash,
            subject_hash=gate.gate_hash,
            source_artifact_hashes=expected_hashes,
            recomputed_facts=recomputed_facts,
            protocol_version=task.protocol_version,
            frozen_at=frozen_at,
        )
    )


def assert_evaluation_subject_is_bound(
    binding: EvaluationEvidenceBinding,
    *,
    expected_subject: EvaluationBindingSubject,
    task: EvaluatorTask,
    packet: EvaluatorInputPacket,
    subject_hash: str,
) -> None:
    """Common EVAL5 admission check for a previously recomputed subject."""

    assert_evaluator_packet_binding(task, packet)
    binding.assert_integrity()
    if (
        binding.subject is not expected_subject
        or binding.task_hash != task.task_hash
        or binding.packet_hash != packet.packet_hash
        or binding.subject_hash != subject_hash
        or binding.protocol_version != task.protocol_version
        or binding.status != "PASS"
    ):
        raise EvaluationEvidenceBindingError(
            "evaluation subject lacks an exact PASS evidence binding"
        )
