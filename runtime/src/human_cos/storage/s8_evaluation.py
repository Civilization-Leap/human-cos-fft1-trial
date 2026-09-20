"""Typed append-only PostgreSQL persistence for the authorized S8-EVAL slice.

The database is transport and lineage only. Public stores revalidate frozen
application objects before insertion. HC Regression reports and Low-recognition
gates are accepted only through full source-aware recomputation; a standalone,
hash-consistent PASS binding is never sufficient provenance proof.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

from psycopg import Connection, errors
from psycopg.types.json import Jsonb

from human_cos.evaluation import (
    EvaluationBindingSubject,
    EvaluationEvidenceBinding,
    EvaluatorFinding,
    EvaluatorInputPacket,
    EvaluatorResult,
    EvaluatorTask,
    HCRegressionMetricRule,
    HCRegressionMetricSource,
    HCRegressionParityDeclaration,
    HCRegressionPreregistration,
    HCRegressionReport,
    HCRegressionTrackSnapshot,
    LowRecognitionExposureSnapshot,
    LowRecognitionExposureSource,
    LowRecognitionGate,
    LowRecognitionReveal,
    LowRecognitionVisibilityPolicy,
    assert_evaluator_finding_binding,
    assert_evaluator_packet_binding,
    assert_evaluator_result_binding,
    assert_hc_regression_evidence_binding,
    assert_low_recognition_evidence_binding,
)
from human_cos.runtime.run import RunManifest
from human_cos.storage.repository import DuplicateRevisionError

ArtifactLayer = Literal["S5", "S6", "S7", "S8", "RUNTIME"]
ArtifactLink = tuple[str, str, ArtifactLayer]


def _insert_artifact(
    connection: Connection[Any],
    *,
    kind: str,
    artifact_id: str,
    artifact_hash: str,
    case_id: str,
    case_revision: int,
    protocol_version: str,
    document: dict[str, Any],
    links: Iterable[ArtifactLink] = (),
) -> None:
    normalized_links = tuple(sorted(set(links)))
    try:
        connection.execute(
            """
            INSERT INTO human_cos_s8_artifact
                (artifact_hash, artifact_kind, artifact_id, case_id,
                 case_revision, protocol_version, payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                artifact_hash,
                kind,
                artifact_id,
                case_id,
                case_revision,
                protocol_version,
                Jsonb(document),
            ),
        )
        for relation, source_hash, source_layer in normalized_links:
            connection.execute(
                """
                INSERT INTO human_cos_s8_artifact_link
                    (artifact_hash, relation, source_hash, source_layer)
                VALUES (%s, %s, %s, %s)
                """,
                (artifact_hash, relation, source_hash, source_layer),
            )
    except errors.UniqueViolation as exc:
        raise DuplicateRevisionError(
            f"S8-EVAL immutable artifact already exists: {kind}:{artifact_id}"
        ) from exc


def _require_stored_artifact(
    connection: Connection[Any],
    *,
    kind: str,
    artifact_id: str,
    artifact_hash: str,
    document: dict[str, Any],
) -> None:
    row = connection.execute(
        """
        SELECT artifact_id, payload
        FROM human_cos_s8_artifact
        WHERE artifact_hash = %s AND artifact_kind = %s
        """,
        (artifact_hash, kind),
    ).fetchone()
    if row is None:
        raise ValueError(f"required S8 artifact is not stored: {kind}:{artifact_id}")
    stored_id, stored_payload = row
    if stored_id != artifact_id or stored_payload != document:
        raise ValueError(f"stored S8 artifact differs from supplied object: {kind}:{artifact_id}")


def read_s8_artifact(
    connection: Connection[Any],
    artifact_hash: str,
    *,
    expected_kind: str | None = None,
) -> dict[str, Any]:
    if expected_kind is None:
        row = connection.execute(
            """
            SELECT artifact_kind, payload
            FROM human_cos_s8_artifact
            WHERE artifact_hash = %s
            """,
            (artifact_hash,),
        ).fetchone()
    else:
        row = connection.execute(
            """
            SELECT artifact_kind, payload
            FROM human_cos_s8_artifact
            WHERE artifact_hash = %s AND artifact_kind = %s
            """,
            (artifact_hash, expected_kind),
        ).fetchone()
    if row is None:
        raise KeyError(artifact_hash)
    kind, payload = row
    if expected_kind is not None and kind != expected_kind:
        raise ValueError("stored S8 artifact kind differs from requested kind")
    if not isinstance(payload, dict):
        raise ValueError("stored S8 artifact payload is not a JSON object")
    return dict(payload)


def _packet_source_layers(packet: EvaluatorInputPacket) -> dict[str, ArtifactLayer]:
    packet.assert_integrity()
    layers: dict[str, ArtifactLayer] = {}
    for source in packet.source_refs:
        layer: ArtifactLayer = source.layer.value
        prior = layers.get(source.sha256)
        if prior is not None and prior != layer:
            raise ValueError("Evaluator packet assigns one source hash to multiple layers")
        layers[source.sha256] = layer
    return layers


def _require_packet_source_layer(
    packet: EvaluatorInputPacket,
    source_hash: str,
) -> ArtifactLayer:
    layer = _packet_source_layers(packet).get(source_hash)
    if layer is None:
        raise ValueError("S8 artifact source hash is outside supplied Evaluator packet")
    return layer


def _require_task_and_packet_stored(
    connection: Connection[Any],
    task: EvaluatorTask,
    packet: EvaluatorInputPacket,
) -> None:
    assert_evaluator_packet_binding(task, packet)
    _require_stored_artifact(
        connection,
        kind="EVALUATOR_TASK",
        artifact_id=task.task_id,
        artifact_hash=task.task_hash,
        document=task.to_document(),
    )
    _require_stored_artifact(
        connection,
        kind="EVALUATOR_INPUT_PACKET",
        artifact_id=packet.packet_id,
        artifact_hash=packet.packet_hash,
        document=packet.to_document(),
    )


def store_evaluator_task(connection: Connection[Any], record: EvaluatorTask) -> None:
    record.assert_integrity()
    with connection.transaction():
        _insert_artifact(
            connection,
            kind="EVALUATOR_TASK",
            artifact_id=record.task_id,
            artifact_hash=record.task_hash,
            case_id=record.case_id,
            case_revision=record.case_revision,
            protocol_version=record.protocol_version,
            document=record.to_document(),
        )


def store_evaluator_input_packet(
    connection: Connection[Any],
    task: EvaluatorTask,
    record: EvaluatorInputPacket,
) -> None:
    assert_evaluator_packet_binding(task, record)
    with connection.transaction():
        _require_stored_artifact(
            connection,
            kind="EVALUATOR_TASK",
            artifact_id=task.task_id,
            artifact_hash=task.task_hash,
            document=task.to_document(),
        )
        links: list[ArtifactLink] = [("evaluator_task", task.task_hash, "S8")]
        links.extend(
            (
                f"source:{source.layer.value.lower()}:{source.object_kind}",
                source.sha256,
                source.layer.value,
            )
            for source in record.source_refs
        )
        _insert_artifact(
            connection,
            kind="EVALUATOR_INPUT_PACKET",
            artifact_id=record.packet_id,
            artifact_hash=record.packet_hash,
            case_id=task.case_id,
            case_revision=task.case_revision,
            protocol_version=record.protocol_version,
            document=record.to_document(),
            links=links,
        )


def store_evaluator_finding(
    connection: Connection[Any],
    task: EvaluatorTask,
    packet: EvaluatorInputPacket,
    record: EvaluatorFinding,
) -> None:
    assert_evaluator_finding_binding(task, packet, record)
    with connection.transaction():
        _require_task_and_packet_stored(connection, task, packet)
        links: list[ArtifactLink] = [
            ("evaluator_task", task.task_hash, "S8"),
            ("evaluator_packet", packet.packet_hash, "S8"),
        ]
        links.extend(
            ("finding_source", source_hash, _require_packet_source_layer(packet, source_hash))
            for source_hash in record.source_hash_refs
        )
        _insert_artifact(
            connection,
            kind="EVALUATOR_FINDING",
            artifact_id=record.finding_id,
            artifact_hash=record.finding_hash,
            case_id=task.case_id,
            case_revision=task.case_revision,
            protocol_version=record.protocol_version,
            document=record.to_document(),
            links=links,
        )


def store_evaluator_result(
    connection: Connection[Any],
    task: EvaluatorTask,
    packet: EvaluatorInputPacket,
    findings: tuple[EvaluatorFinding, ...],
    record: EvaluatorResult,
) -> None:
    assert_evaluator_result_binding(task, packet, findings, record)
    with connection.transaction():
        _require_task_and_packet_stored(connection, task, packet)
        for finding in findings:
            _require_stored_artifact(
                connection,
                kind="EVALUATOR_FINDING",
                artifact_id=finding.finding_id,
                artifact_hash=finding.finding_hash,
                document=finding.to_document(),
            )
        links: list[ArtifactLink] = [
            ("evaluator_task", task.task_hash, "S8"),
            ("evaluator_packet", packet.packet_hash, "S8"),
        ]
        links.extend(("evaluator_finding", item.finding_hash, "S8") for item in findings)
        _insert_artifact(
            connection,
            kind="EVALUATOR_RESULT",
            artifact_id=record.result_id,
            artifact_hash=record.result_hash,
            case_id=task.case_id,
            case_revision=task.case_revision,
            protocol_version=record.protocol_version,
            document=record.to_document(),
            links=links,
        )


def _insert_hc_metric_source(
    connection: Connection[Any],
    *,
    task: EvaluatorTask,
    packet: EvaluatorInputPacket,
    source: HCRegressionMetricSource,
) -> None:
    links: list[ArtifactLink] = [
        ("evaluator_task", task.task_hash, "S8"),
        ("evaluator_packet", packet.packet_hash, "S8"),
        ("run_manifest", source.run_manifest_hash, "RUNTIME"),
    ]
    links.extend(
        ("metric_origin", item, _require_packet_source_layer(packet, item))
        for item in source.source_hash_refs
    )
    _insert_artifact(
        connection,
        kind="HC_REGRESSION_METRIC_SOURCE",
        artifact_id=source.source_id,
        artifact_hash=source.source_hash,
        case_id=source.case_id,
        case_revision=source.case_revision,
        protocol_version=source.protocol_version,
        document=source.to_document(),
        links=links,
    )


def store_bound_hc_regression(
    connection: Connection[Any],
    *,
    task: EvaluatorTask,
    packet: EvaluatorInputPacket,
    declarations: tuple[HCRegressionParityDeclaration, ...],
    metric_rules: tuple[HCRegressionMetricRule, ...],
    preregistration: HCRegressionPreregistration,
    hc_run_manifest: RunManifest,
    baseline_run_manifest: RunManifest,
    hc_metric_source: HCRegressionMetricSource,
    baseline_metric_source: HCRegressionMetricSource,
    hc_snapshot: HCRegressionTrackSnapshot,
    baseline_snapshot: HCRegressionTrackSnapshot,
    report: HCRegressionReport,
    binding: EvaluationEvidenceBinding,
) -> None:
    """Persist EVAL3 only after full source-aware fact recomputation succeeds."""

    recomputed = assert_hc_regression_evidence_binding(
        task=task,
        packet=packet,
        preregistration=preregistration,
        declarations=declarations,
        metric_rules=metric_rules,
        hc_run_manifest=hc_run_manifest,
        baseline_run_manifest=baseline_run_manifest,
        hc_metric_source=hc_metric_source,
        baseline_metric_source=baseline_metric_source,
        hc_snapshot=hc_snapshot,
        baseline_snapshot=baseline_snapshot,
        report=report,
        binding_id=binding.binding_id,
        frozen_at=binding.frozen_at,
    )
    if binding != recomputed:
        raise ValueError("supplied HC evidence binding differs from full code recomputation")

    with connection.transaction():
        _require_task_and_packet_stored(connection, task, packet)
        for declaration in declarations:
            _insert_artifact(
                connection,
                kind="HC_REGRESSION_PARITY_DECLARATION",
                artifact_id=f"{task.task_id}:{declaration.dimension.value}",
                artifact_hash=declaration.declaration_hash,
                case_id=task.case_id,
                case_revision=task.case_revision,
                protocol_version=task.protocol_version,
                document=declaration.to_document(),
                links=(("evaluator_task", task.task_hash, "S8"),),
            )
        for rule in metric_rules:
            _insert_artifact(
                connection,
                kind="HC_REGRESSION_METRIC_RULE",
                artifact_id=f"{task.task_id}:{rule.metric_id}",
                artifact_hash=rule.rule_hash,
                case_id=task.case_id,
                case_revision=task.case_revision,
                protocol_version=task.protocol_version,
                document=rule.to_document(),
                links=(("evaluator_task", task.task_hash, "S8"),),
            )
        _insert_hc_metric_source(
            connection,
            task=task,
            packet=packet,
            source=hc_metric_source,
        )
        _insert_hc_metric_source(
            connection,
            task=task,
            packet=packet,
            source=baseline_metric_source,
        )
        preregistration_links: list[ArtifactLink] = [
            ("evaluator_task", task.task_hash, "S8"),
            ("evaluator_packet", packet.packet_hash, "S8"),
        ]
        preregistration_links.extend(
            ("parity_declaration", item.declaration_hash, "S8") for item in declarations
        )
        preregistration_links.extend(("metric_rule", item.rule_hash, "S8") for item in metric_rules)
        _insert_artifact(
            connection,
            kind="HC_REGRESSION_PREREGISTRATION",
            artifact_id=preregistration.regression_id,
            artifact_hash=preregistration.preregistration_hash,
            case_id=task.case_id,
            case_revision=task.case_revision,
            protocol_version=task.protocol_version,
            document=preregistration.to_document(),
            links=preregistration_links,
        )
        for snapshot, source in (
            (hc_snapshot, hc_metric_source),
            (baseline_snapshot, baseline_metric_source),
        ):
            _insert_artifact(
                connection,
                kind="HC_REGRESSION_TRACK_SNAPSHOT",
                artifact_id=snapshot.snapshot_id,
                artifact_hash=snapshot.snapshot_hash,
                case_id=task.case_id,
                case_revision=task.case_revision,
                protocol_version=task.protocol_version,
                document=snapshot.to_document(),
                links=(
                    ("evaluator_task", task.task_hash, "S8"),
                    ("evaluator_packet", packet.packet_hash, "S8"),
                    ("hc_regression_preregistration", preregistration.preregistration_hash, "S8"),
                    ("run_manifest", snapshot.run_manifest_hash, "RUNTIME"),
                    ("metric_source", source.source_hash, "S8"),
                ),
            )
        _insert_artifact(
            connection,
            kind="HC_REGRESSION_REPORT",
            artifact_id=report.report_id,
            artifact_hash=report.report_hash,
            case_id=task.case_id,
            case_revision=task.case_revision,
            protocol_version=task.protocol_version,
            document=report.to_document(),
            links=(
                ("evaluator_task", task.task_hash, "S8"),
                ("evaluator_packet", packet.packet_hash, "S8"),
                ("hc_regression_preregistration", preregistration.preregistration_hash, "S8"),
                ("hc_snapshot", hc_snapshot.snapshot_hash, "S8"),
                ("baseline_snapshot", baseline_snapshot.snapshot_hash, "S8"),
            ),
        )
        _insert_artifact(
            connection,
            kind="EVALUATION_EVIDENCE_BINDING",
            artifact_id=binding.binding_id,
            artifact_hash=binding.binding_hash,
            case_id=task.case_id,
            case_revision=task.case_revision,
            protocol_version=task.protocol_version,
            document=binding.to_document(),
            links=(
                ("evaluator_task", task.task_hash, "S8"),
                ("evaluator_packet", packet.packet_hash, "S8"),
                ("subject", report.report_hash, "S8"),
                ("hc_metric_source", hc_metric_source.source_hash, "S8"),
                ("baseline_metric_source", baseline_metric_source.source_hash, "S8"),
            ),
        )


def _insert_low_recognition_source(
    connection: Connection[Any],
    *,
    task: EvaluatorTask,
    packet: EvaluatorInputPacket,
    source: LowRecognitionExposureSource,
) -> None:
    links: list[ArtifactLink] = [
        ("evaluator_task", task.task_hash, "S8"),
        ("evaluator_packet", packet.packet_hash, "S8"),
    ]
    links.extend(
        ("exposure_origin", item, _require_packet_source_layer(packet, item))
        for item in source.source_hash_refs
    )
    _insert_artifact(
        connection,
        kind="LOW_RECOGNITION_EXPOSURE_SOURCE",
        artifact_id=source.source_id,
        artifact_hash=source.source_hash,
        case_id=source.case_id,
        case_revision=source.case_revision,
        protocol_version=source.protocol_version,
        document=source.to_document(),
        links=links,
    )


def _assert_reveal_binding(
    *,
    task: EvaluatorTask,
    packet: EvaluatorInputPacket,
    policy: LowRecognitionVisibilityPolicy,
    gate: LowRecognitionGate,
    reveal: LowRecognitionReveal,
) -> None:
    reveal.assert_integrity()
    if (
        reveal.task_hash != task.task_hash
        or reveal.packet_hash != packet.packet_hash
        or reveal.policy_hash != policy.policy_hash
        or reveal.gate_hash != gate.gate_hash
        or reveal.protocol_version != task.protocol_version
    ):
        raise ValueError("Low-recognition reveal lineage differs from supplied closure")
    if reveal.revealed_at <= gate.frozen_at:
        raise ValueError("Low-recognition reveal must occur after gate freeze")
    if not set(reveal.revealed_material).issubset(policy.post_freeze_reveal_plan):
        raise ValueError("Low-recognition reveal exceeds frozen reveal plan")


def store_bound_low_recognition(
    connection: Connection[Any],
    *,
    task: EvaluatorTask,
    packet: EvaluatorInputPacket,
    policy: LowRecognitionVisibilityPolicy,
    exposure_sources: tuple[LowRecognitionExposureSource, ...],
    exposure_snapshot: LowRecognitionExposureSnapshot,
    gate: LowRecognitionGate,
    binding: EvaluationEvidenceBinding,
    reveal: LowRecognitionReveal | None = None,
) -> None:
    """Persist EVAL4 only after full source-aware visibility recomputation."""

    recomputed = assert_low_recognition_evidence_binding(
        task=task,
        packet=packet,
        policy=policy,
        exposure_sources=exposure_sources,
        exposure_snapshot=exposure_snapshot,
        gate=gate,
        binding_id=binding.binding_id,
        frozen_at=binding.frozen_at,
    )
    if binding != recomputed:
        raise ValueError("supplied Low-recognition binding differs from full code recomputation")
    if reveal is not None:
        _assert_reveal_binding(
            task=task,
            packet=packet,
            policy=policy,
            gate=gate,
            reveal=reveal,
        )

    with connection.transaction():
        _require_task_and_packet_stored(connection, task, packet)
        _insert_artifact(
            connection,
            kind="LOW_RECOGNITION_VISIBILITY_POLICY",
            artifact_id=policy.policy_id,
            artifact_hash=policy.policy_hash,
            case_id=task.case_id,
            case_revision=task.case_revision,
            protocol_version=task.protocol_version,
            document=policy.to_document(),
            links=(
                ("evaluator_task", task.task_hash, "S8"),
                ("evaluator_packet", packet.packet_hash, "S8"),
            ),
        )
        for source in exposure_sources:
            _insert_low_recognition_source(
                connection,
                task=task,
                packet=packet,
                source=source,
            )
        snapshot_links: list[ArtifactLink] = [
            ("evaluator_task", task.task_hash, "S8"),
            ("evaluator_packet", packet.packet_hash, "S8"),
            ("low_recognition_policy", policy.policy_hash, "S8"),
        ]
        snapshot_links.extend(
            ("exposure_source", source.source_hash, "S8") for source in exposure_sources
        )
        _insert_artifact(
            connection,
            kind="LOW_RECOGNITION_EXPOSURE_SNAPSHOT",
            artifact_id=exposure_snapshot.snapshot_id,
            artifact_hash=exposure_snapshot.snapshot_hash,
            case_id=task.case_id,
            case_revision=task.case_revision,
            protocol_version=task.protocol_version,
            document=exposure_snapshot.to_document(),
            links=snapshot_links,
        )
        _insert_artifact(
            connection,
            kind="LOW_RECOGNITION_GATE",
            artifact_id=gate.gate_id,
            artifact_hash=gate.gate_hash,
            case_id=task.case_id,
            case_revision=task.case_revision,
            protocol_version=task.protocol_version,
            document=gate.to_document(),
            links=(
                ("evaluator_task", task.task_hash, "S8"),
                ("evaluator_packet", packet.packet_hash, "S8"),
                ("low_recognition_policy", policy.policy_hash, "S8"),
                ("low_recognition_exposure", exposure_snapshot.snapshot_hash, "S8"),
            ),
        )
        _insert_artifact(
            connection,
            kind="EVALUATION_EVIDENCE_BINDING",
            artifact_id=binding.binding_id,
            artifact_hash=binding.binding_hash,
            case_id=task.case_id,
            case_revision=task.case_revision,
            protocol_version=task.protocol_version,
            document=binding.to_document(),
            links=(
                ("evaluator_task", task.task_hash, "S8"),
                ("evaluator_packet", packet.packet_hash, "S8"),
                ("subject", gate.gate_hash, "S8"),
                *(("exposure_source", source.source_hash, "S8") for source in exposure_sources),
            ),
        )
        if reveal is not None:
            _insert_artifact(
                connection,
                kind="LOW_RECOGNITION_REVEAL",
                artifact_id=reveal.reveal_id,
                artifact_hash=reveal.reveal_hash,
                case_id=task.case_id,
                case_revision=task.case_revision,
                protocol_version=task.protocol_version,
                document=reveal.to_document(),
                links=(
                    ("evaluator_task", task.task_hash, "S8"),
                    ("evaluator_packet", packet.packet_hash, "S8"),
                    ("low_recognition_policy", policy.policy_hash, "S8"),
                    ("low_recognition_gate", gate.gate_hash, "S8"),
                ),
            )


def assert_bound_subject_persisted(
    connection: Connection[Any],
    *,
    binding: EvaluationEvidenceBinding,
    expected_subject: EvaluationBindingSubject,
    subject_hash: str,
) -> None:
    binding.assert_integrity()
    if binding.subject is not expected_subject or binding.subject_hash != subject_hash:
        raise ValueError("evidence binding does not identify the expected subject")
    _require_stored_artifact(
        connection,
        kind="EVALUATION_EVIDENCE_BINDING",
        artifact_id=binding.binding_id,
        artifact_hash=binding.binding_hash,
        document=binding.to_document(),
    )
    subject_kind = (
        "HC_REGRESSION_REPORT"
        if expected_subject is EvaluationBindingSubject.HC_REGRESSION
        else "LOW_RECOGNITION_GATE"
    )
    row = connection.execute(
        """
        SELECT 1
        FROM human_cos_s8_artifact
        WHERE artifact_hash = %s AND artifact_kind = %s
        """,
        (subject_hash, subject_kind),
    ).fetchone()
    if row is None:
        raise ValueError("bound evaluation subject is not persisted")
