"""S8-EVAL3 deterministic HC regression and parity sidecar.

This module reuses the discipline of S4 parity without importing S4 experiment
objects or historical-blind semantics. A clean regression result means only
that a preregistered regression was not detected; it never authorizes a
Human-COS superiority claim, Runtime progression, Final Synthesis, or reality
execution.
"""

from __future__ import annotations

import math
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


class HCRegressionError(ValueError):
    """S8 HC regression lineage or preregistration discipline was violated."""


class RegressionParityDimension(str, Enum):
    INPUT = "INPUT"
    TOOL = "TOOL"
    BUDGET = "BUDGET"
    OUTPUT_CONTRACT = "OUTPUT_CONTRACT"


class RegressionMetricDirection(str, Enum):
    HIGHER_IS_BETTER = "HIGHER_IS_BETTER"
    LOWER_IS_BETTER = "LOWER_IS_BETTER"


class RegressionValidity(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"


class RegressionDisposition(str, Enum):
    NO_REGRESSION_DETECTED = "NO_REGRESSION_DETECTED"
    REGRESSION_DETECTED = "REGRESSION_DETECTED"
    INVALID = "INVALID"


class _FrozenRegressionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("S8 HC regression timestamps require timezone-aware datetimes")
    return value


def _finite(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("S8 HC regression metric values must be finite")
    return value


def _assert_unique(values: tuple[str, ...], *, name: str) -> None:
    if len(values) != len(set(values)):
        raise HCRegressionError(f"{name} must not contain duplicates")


def _payload_without_hash(model: BaseModel, hash_field: str) -> dict[str, Any]:
    return model.model_dump(mode="json", exclude={hash_field}, exclude_none=True)


class HCRegressionParityDeclarationPayload(_FrozenRegressionModel):
    dimension: RegressionParityDimension
    hc_descriptor: str = Field(min_length=1)
    baseline_descriptor: str = Field(min_length=1)
    asymmetry_rationale: str | None = Field(default=None, min_length=1)


class HCRegressionParityDeclaration(HCRegressionParityDeclarationPayload):
    declaration_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        if self.hc_descriptor != self.baseline_descriptor and not self.asymmetry_rationale:
            raise HCRegressionError(
                "pre-registered asymmetric HC regression parity requires explicit rationale"
            )
        payload = _payload_without_hash(self, "declaration_hash")
        if self.declaration_hash != canonical_document_sha256(payload):
            raise HCRegressionError("HC regression parity declaration hash mismatch")


def freeze_hc_regression_parity_declaration(
    payload: HCRegressionParityDeclarationPayload,
) -> HCRegressionParityDeclaration:
    document = payload.to_document()
    frozen = HCRegressionParityDeclaration.model_validate(
        {**document, "declaration_hash": canonical_document_sha256(document)}
    )
    frozen.assert_integrity()
    return frozen


class HCRegressionMetricRulePayload(_FrozenRegressionModel):
    metric_id: str = Field(min_length=1)
    direction: RegressionMetricDirection
    noninferiority_margin: float = Field(ge=0.0)
    rationale: str = Field(min_length=1)

    _margin_must_be_finite = field_validator("noninferiority_margin")(_finite)


class HCRegressionMetricRule(HCRegressionMetricRulePayload):
    rule_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = _payload_without_hash(self, "rule_hash")
        if self.rule_hash != canonical_document_sha256(payload):
            raise HCRegressionError("HC regression metric rule hash mismatch")


def freeze_hc_regression_metric_rule(
    payload: HCRegressionMetricRulePayload,
) -> HCRegressionMetricRule:
    document = payload.to_document()
    frozen = HCRegressionMetricRule.model_validate(
        {**document, "rule_hash": canonical_document_sha256(document)}
    )
    frozen.assert_integrity()
    return frozen


class HCRegressionPreregistrationPayload(_FrozenRegressionModel):
    regression_id: str = Field(min_length=1)
    task_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    packet_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    hc_run_id: str = Field(min_length=1)
    baseline_run_id: str = Field(min_length=1)
    parity_declaration_hashes: tuple[str, ...] = Field(min_length=4, max_length=4)
    metric_rule_hashes: tuple[str, ...] = Field(min_length=1)
    stopping_rule: str = Field(min_length=1)
    failure_conditions: tuple[str, ...] = Field(min_length=1)
    process_authority: Literal[False] = False
    superiority_claim_authorized: Literal[False] = False
    reality_execution_authorized: Literal[False] = False
    final_claim_authorized: Literal[False] = False
    seal_authorized: Literal[False] = False
    protocol_version: str = Field(min_length=1)
    preregistered_at: datetime

    _preregistered_at_must_be_aware = field_validator("preregistered_at")(_aware)


class HCRegressionPreregistration(HCRegressionPreregistrationPayload):
    preregistration_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        if self.hc_run_id == self.baseline_run_id:
            raise HCRegressionError("HC and Baseline regression runs must be distinct")
        _assert_unique(
            self.parity_declaration_hashes,
            name="HC regression parity declaration hashes",
        )
        _assert_unique(self.metric_rule_hashes, name="HC regression metric rule hashes")
        _assert_unique(self.failure_conditions, name="HC regression failure conditions")
        payload = _payload_without_hash(self, "preregistration_hash")
        if self.preregistration_hash != canonical_document_sha256(payload):
            raise HCRegressionError("HC regression preregistration hash mismatch")


def _assert_regression_task(task: EvaluatorTask, packet: EvaluatorInputPacket) -> None:
    assert_evaluator_packet_binding(task, packet)
    if task.evaluation_type is not EvaluationTaskType.HC_REGRESSION:
        raise HCRegressionError("S8-EVAL3 requires an HC_REGRESSION EvaluatorTask")


def freeze_hc_regression_preregistration(
    payload: HCRegressionPreregistrationPayload,
    *,
    task: EvaluatorTask,
    packet: EvaluatorInputPacket,
    declarations: tuple[HCRegressionParityDeclaration, ...],
    metric_rules: tuple[HCRegressionMetricRule, ...],
) -> HCRegressionPreregistration:
    _assert_regression_task(task, packet)
    if payload.task_hash != task.task_hash or payload.packet_hash != packet.packet_hash:
        raise HCRegressionError("HC regression preregistration must bind exact task and packet")
    if payload.case_id != task.case_id or payload.case_revision != task.case_revision:
        raise HCRegressionError("HC regression preregistration Case binding differs from task")
    if payload.protocol_version != task.protocol_version:
        raise HCRegressionError("HC regression preregistration protocol differs from task")
    if payload.preregistered_at < packet.frozen_at:
        raise HCRegressionError("HC regression preregistration cannot predate its source packet")
    if len(task.evaluated_run_ids) != 2 or {
        payload.hc_run_id,
        payload.baseline_run_id,
    } != set(task.evaluated_run_ids):
        raise HCRegressionError(
            "HC regression task must evaluate exactly the preregistered HC and Baseline runs"
        )

    required_dimensions = set(RegressionParityDimension)
    declaration_dimensions = {item.dimension for item in declarations}
    if len(declarations) != 4 or declaration_dimensions != required_dimensions:
        raise HCRegressionError(
            "HC regression requires exactly one preregistered declaration per parity dimension"
        )
    for declaration in declarations:
        declaration.assert_integrity()
    if payload.parity_declaration_hashes != tuple(item.declaration_hash for item in declarations):
        raise HCRegressionError("HC regression preregistration declaration hashes differ")

    if not metric_rules:
        raise HCRegressionError("HC regression requires at least one preregistered metric rule")
    for rule in metric_rules:
        rule.assert_integrity()
    _assert_unique(
        tuple(item.metric_id for item in metric_rules),
        name="HC regression metric IDs",
    )
    if payload.metric_rule_hashes != tuple(item.rule_hash for item in metric_rules):
        raise HCRegressionError("HC regression preregistration metric rule hashes differ")

    document = payload.to_document()
    frozen = HCRegressionPreregistration.model_validate(
        {**document, "preregistration_hash": canonical_document_sha256(document)}
    )
    frozen.assert_integrity()
    return frozen


class HCRegressionMetricObservation(_FrozenRegressionModel):
    metric_id: str = Field(min_length=1)
    value: float

    _value_must_be_finite = field_validator("value")(_finite)


class HCRegressionTrackSnapshotPayload(_FrozenRegressionModel):
    snapshot_id: str = Field(min_length=1)
    preregistration_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    task_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    packet_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    track_kind: Literal["HC", "BASELINE"]
    run_id: str = Field(min_length=1)
    run_manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    metric_source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    input_descriptor: str = Field(min_length=1)
    tool_descriptor: str = Field(min_length=1)
    budget_descriptor: str = Field(min_length=1)
    output_contract_descriptor: str = Field(min_length=1)
    metric_values: tuple[HCRegressionMetricObservation, ...] = Field(min_length=1)
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class HCRegressionTrackSnapshot(HCRegressionTrackSnapshotPayload):
    snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        _assert_unique(
            tuple(item.metric_id for item in self.metric_values),
            name="HC regression track metric IDs",
        )
        payload = _payload_without_hash(self, "snapshot_hash")
        if self.snapshot_hash != canonical_document_sha256(payload):
            raise HCRegressionError("HC regression track snapshot hash mismatch")


def freeze_hc_regression_track_snapshot(
    payload: HCRegressionTrackSnapshotPayload,
    *,
    preregistration: HCRegressionPreregistration,
    task: EvaluatorTask,
    packet: EvaluatorInputPacket,
    metric_rules: tuple[HCRegressionMetricRule, ...],
    run_manifest: RunManifest,
) -> HCRegressionTrackSnapshot:
    _assert_regression_task(task, packet)
    preregistration.assert_integrity()
    if payload.preregistration_hash != preregistration.preregistration_hash:
        raise HCRegressionError("HC regression track does not bind exact preregistration")
    if payload.task_hash != task.task_hash or payload.packet_hash != packet.packet_hash:
        raise HCRegressionError("HC regression track does not bind exact task and packet")
    expected_run_id = (
        preregistration.hc_run_id if payload.track_kind == "HC" else preregistration.baseline_run_id
    )
    if payload.run_id != expected_run_id:
        raise HCRegressionError("HC regression track kind does not match preregistered run")
    if run_manifest.run_id != payload.run_id:
        raise HCRegressionError("HC regression track Run Manifest ID differs")
    if run_manifest.case_id != task.case_id:
        raise HCRegressionError("HC regression track Run belongs to a different Case")
    if run_manifest.protocol_version != task.protocol_version:
        raise HCRegressionError("HC regression track Run protocol differs from task")
    if run_manifest.status != "FROZEN":
        raise HCRegressionError("HC regression track requires a frozen Run Manifest")
    expected_run_hash = canonical_document_sha256(run_manifest.to_document())
    if payload.run_manifest_hash != expected_run_hash:
        raise HCRegressionError("HC regression track Run Manifest hash differs")
    if payload.run_manifest_hash not in packet.source_hashes:
        raise HCRegressionError("HC regression Run Manifest hash is outside source packet")
    if payload.metric_source_hash not in packet.source_hashes:
        raise HCRegressionError("HC regression metric source hash is outside source packet")
    if payload.protocol_version != task.protocol_version:
        raise HCRegressionError("HC regression track protocol differs from task")
    if payload.frozen_at < preregistration.preregistered_at:
        raise HCRegressionError("HC regression track cannot predate preregistration")

    for rule in metric_rules:
        rule.assert_integrity()
    expected_metric_ids = tuple(item.metric_id for item in metric_rules)
    actual_metric_ids = tuple(item.metric_id for item in payload.metric_values)
    if actual_metric_ids != expected_metric_ids:
        raise HCRegressionError(
            "HC regression track metrics must match preregistered metric order exactly"
        )
    if preregistration.metric_rule_hashes != tuple(item.rule_hash for item in metric_rules):
        raise HCRegressionError("HC regression track metric rules differ from preregistration")

    document = payload.to_document()
    frozen = HCRegressionTrackSnapshot.model_validate(
        {**document, "snapshot_hash": canonical_document_sha256(document)}
    )
    frozen.assert_integrity()
    return frozen


class HCRegressionParityDimensionResult(_FrozenRegressionModel):
    dimension: RegressionParityDimension
    declaration_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    hc_matches_preregistration: bool
    baseline_matches_preregistration: bool

    @property
    def passed(self) -> bool:
        return self.hc_matches_preregistration and self.baseline_matches_preregistration


class HCRegressionMetricResult(_FrozenRegressionModel):
    metric_id: str = Field(min_length=1)
    rule_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    direction: RegressionMetricDirection
    noninferiority_margin: float = Field(ge=0.0)
    hc_value: float
    baseline_value: float
    regression_detected: bool

    _margin_must_be_finite = field_validator("noninferiority_margin")(_finite)
    _hc_value_must_be_finite = field_validator("hc_value")(_finite)
    _baseline_value_must_be_finite = field_validator("baseline_value")(_finite)


class HCRegressionReportPayload(_FrozenRegressionModel):
    report_id: str = Field(min_length=1)
    preregistration_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    task_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    packet_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    hc_snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    baseline_snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    parity_results: tuple[HCRegressionParityDimensionResult, ...] = Field(
        min_length=4,
        max_length=4,
    )
    metric_results: tuple[HCRegressionMetricResult, ...] = Field(min_length=1)
    validity: RegressionValidity
    invalid_reasons: tuple[str, ...] = ()
    disposition: RegressionDisposition
    process_authority: Literal[False] = False
    superiority_claim_authorized: Literal[False] = False
    reality_execution_authorized: Literal[False] = False
    final_claim_authorized: Literal[False] = False
    seal_authorized: Literal[False] = False
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class HCRegressionReport(HCRegressionReportPayload):
    report_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @property
    def regression_not_detected(self) -> bool:
        return (
            self.validity is RegressionValidity.VALID
            and self.disposition is RegressionDisposition.NO_REGRESSION_DETECTED
        )

    def assert_integrity(self) -> None:
        _assert_unique(self.invalid_reasons, name="HC regression invalid reasons")
        dimensions = tuple(item.dimension for item in self.parity_results)
        if set(dimensions) != set(RegressionParityDimension) or len(dimensions) != 4:
            raise HCRegressionError("HC regression report parity dimensions are incomplete")
        _assert_unique(
            tuple(item.metric_id for item in self.metric_results),
            name="HC regression report metric IDs",
        )
        expected_validity = (
            RegressionValidity.INVALID if self.invalid_reasons else RegressionValidity.VALID
        )
        if self.validity is not expected_validity:
            raise HCRegressionError("HC regression report validity is not recomputable")
        if self.validity is RegressionValidity.INVALID:
            expected_disposition = RegressionDisposition.INVALID
        elif any(item.regression_detected for item in self.metric_results):
            expected_disposition = RegressionDisposition.REGRESSION_DETECTED
        else:
            expected_disposition = RegressionDisposition.NO_REGRESSION_DETECTED
        if self.disposition is not expected_disposition:
            raise HCRegressionError("HC regression report disposition is not recomputable")
        payload = _payload_without_hash(self, "report_hash")
        if self.report_hash != canonical_document_sha256(payload):
            raise HCRegressionError("HC regression report hash mismatch")


def _descriptor_map(snapshot: HCRegressionTrackSnapshot) -> dict[RegressionParityDimension, str]:
    return {
        RegressionParityDimension.INPUT: snapshot.input_descriptor,
        RegressionParityDimension.TOOL: snapshot.tool_descriptor,
        RegressionParityDimension.BUDGET: snapshot.budget_descriptor,
        RegressionParityDimension.OUTPUT_CONTRACT: snapshot.output_contract_descriptor,
    }


def _metric_result(
    rule: HCRegressionMetricRule,
    hc: HCRegressionMetricObservation,
    baseline: HCRegressionMetricObservation,
) -> HCRegressionMetricResult:
    if rule.direction is RegressionMetricDirection.HIGHER_IS_BETTER:
        regression_detected = hc.value < baseline.value - rule.noninferiority_margin
    else:
        regression_detected = hc.value > baseline.value + rule.noninferiority_margin
    return HCRegressionMetricResult(
        metric_id=rule.metric_id,
        rule_hash=rule.rule_hash,
        direction=rule.direction,
        noninferiority_margin=rule.noninferiority_margin,
        hc_value=hc.value,
        baseline_value=baseline.value,
        regression_detected=regression_detected,
    )


def evaluate_hc_regression(
    *,
    preregistration: HCRegressionPreregistration,
    task: EvaluatorTask,
    packet: EvaluatorInputPacket,
    declarations: tuple[HCRegressionParityDeclaration, ...],
    metric_rules: tuple[HCRegressionMetricRule, ...],
    hc_snapshot: HCRegressionTrackSnapshot,
    baseline_snapshot: HCRegressionTrackSnapshot,
    report_id: str,
    frozen_at: datetime,
) -> HCRegressionReport:
    _assert_regression_task(task, packet)
    preregistration.assert_integrity()
    hc_snapshot.assert_integrity()
    baseline_snapshot.assert_integrity()
    if (
        preregistration.task_hash != task.task_hash
        or preregistration.packet_hash != packet.packet_hash
    ):
        raise HCRegressionError("HC regression preregistration lineage differs from task/packet")
    if hc_snapshot.track_kind != "HC" or baseline_snapshot.track_kind != "BASELINE":
        raise HCRegressionError("HC regression requires one HC and one BASELINE snapshot")
    if hc_snapshot.preregistration_hash != preregistration.preregistration_hash:
        raise HCRegressionError("HC snapshot preregistration lineage differs")
    if baseline_snapshot.preregistration_hash != preregistration.preregistration_hash:
        raise HCRegressionError("Baseline snapshot preregistration lineage differs")
    _aware(frozen_at)
    if frozen_at < max(hc_snapshot.frozen_at, baseline_snapshot.frozen_at):
        raise HCRegressionError("HC regression report cannot predate compared snapshots")

    for declaration in declarations:
        declaration.assert_integrity()
    if preregistration.parity_declaration_hashes != tuple(
        item.declaration_hash for item in declarations
    ):
        raise HCRegressionError("HC regression report declarations differ from preregistration")
    declaration_map = {item.dimension: item for item in declarations}
    if len(declaration_map) != 4 or set(declaration_map) != set(RegressionParityDimension):
        raise HCRegressionError("HC regression report requires exact four parity declarations")

    hc_descriptors = _descriptor_map(hc_snapshot)
    baseline_descriptors = _descriptor_map(baseline_snapshot)
    parity_results = tuple(
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
    invalid_reasons = tuple(
        f"parity-fail:{item.dimension.value}" for item in parity_results if not item.passed
    )

    for rule in metric_rules:
        rule.assert_integrity()
    if preregistration.metric_rule_hashes != tuple(item.rule_hash for item in metric_rules):
        raise HCRegressionError("HC regression report metric rules differ from preregistration")
    hc_metrics = {item.metric_id: item for item in hc_snapshot.metric_values}
    baseline_metrics = {item.metric_id: item for item in baseline_snapshot.metric_values}
    expected_metric_ids = tuple(item.metric_id for item in metric_rules)
    if tuple(hc_metrics) != expected_metric_ids or tuple(baseline_metrics) != expected_metric_ids:
        raise HCRegressionError("HC regression snapshot metric order differs from preregistration")
    metric_results = tuple(
        _metric_result(rule, hc_metrics[rule.metric_id], baseline_metrics[rule.metric_id])
        for rule in metric_rules
    )

    validity = RegressionValidity.INVALID if invalid_reasons else RegressionValidity.VALID
    if validity is RegressionValidity.INVALID:
        disposition = RegressionDisposition.INVALID
    elif any(item.regression_detected for item in metric_results):
        disposition = RegressionDisposition.REGRESSION_DETECTED
    else:
        disposition = RegressionDisposition.NO_REGRESSION_DETECTED

    payload = HCRegressionReportPayload(
        report_id=report_id,
        preregistration_hash=preregistration.preregistration_hash,
        task_hash=task.task_hash,
        packet_hash=packet.packet_hash,
        hc_snapshot_hash=hc_snapshot.snapshot_hash,
        baseline_snapshot_hash=baseline_snapshot.snapshot_hash,
        parity_results=parity_results,
        metric_results=metric_results,
        validity=validity,
        invalid_reasons=invalid_reasons,
        disposition=disposition,
        protocol_version=task.protocol_version,
        frozen_at=frozen_at,
    )
    document = payload.to_document()
    report = HCRegressionReport.model_validate(
        {**document, "report_hash": canonical_document_sha256(document)}
    )
    report.assert_integrity()
    return report
