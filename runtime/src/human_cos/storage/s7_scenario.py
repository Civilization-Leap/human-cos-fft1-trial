"""Typed append-only PostgreSQL persistence for the authorized S7-SCS slice.

The storage layer never creates S7 business authority. Callers pass already
frozen/hash-validated contract objects; this module records their JSON payloads
and exact hash lineage in the generic 0006 S7 artifact ledger.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal, Protocol

from psycopg import Connection, errors
from psycopg.types.json import Jsonb

from human_cos.challengers import (
    ChallengerFinding,
    ChallengerResponse,
    ChallengerReviewGateResult,
    ChallengerSourcePacket,
    ChallengerTask,
    PendingChallengerSatisfaction,
)
from human_cos.controllers.scenario import (
    ControllerCInvocationPacket,
    ControllerCOutputRecord,
)
from human_cos.safety import (
    ResearchSafetyAdmission,
    ResearchSafetyResult,
    ResimulationSafetyAdmission,
    ResimulationSafetyResult,
)
from human_cos.scenario import (
    AT17WorldRevisionEvidence,
    InterventionRecord,
    ScenarioDomainRerunOutput,
    ScenarioDomainRerunRoute,
    ScenarioDomainRerunTask,
    ScenarioGenerationAdmissionPacket,
    ScenarioGenerationAdmissionResult,
    ScenarioPath,
    ScenarioResimulationPlan,
    ScenarioResimulationResult,
    ScenarioSet,
)
from human_cos.storage.repository import DuplicateRevisionError

ArtifactLayer = Literal["S6", "S7", "RUNTIME"]
ArtifactLink = tuple[str, str, ArtifactLayer]


class _IntegrityChecked(Protocol):
    protocol_version: str

    def assert_integrity(self) -> None: ...
    def to_document(self) -> dict[str, Any]: ...


def _insert_artifact(
    connection: Connection[Any],
    *,
    kind: str,
    artifact_id: str,
    artifact_hash: str,
    case_id: str,
    case_revision: int,
    protocol_version: str,
    record: _IntegrityChecked,
    links: Iterable[ArtifactLink] = (),
) -> None:
    record.assert_integrity()
    document = record.to_document()
    normalized_links = tuple(sorted(set(links)))
    try:
        with connection.transaction():
            connection.execute(
                """
                INSERT INTO human_cos_s7_artifact
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
                    INSERT INTO human_cos_s7_artifact_link
                        (artifact_hash, relation, source_hash, source_layer)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (artifact_hash, relation, source_hash, source_layer),
                )
    except errors.UniqueViolation as exc:
        raise DuplicateRevisionError(
            f"S7-SCS immutable artifact already exists: {kind}:{artifact_id}"
        ) from exc


def store_research_safety_admission(
    connection: Connection[Any], record: ResearchSafetyAdmission
) -> None:
    _insert_artifact(
        connection,
        kind="RESEARCH_SAFETY_ADMISSION",
        artifact_id=record.admission_id,
        artifact_hash=record.admission_hash,
        case_id=record.case_id,
        case_revision=record.case_revision,
        protocol_version=record.protocol_version,
        record=record,
        links=(
            ("parent_world_state", record.parent_world_state_hash, "S6"),
            ("parent_causal_graph", record.parent_causal_graph_hash, "S6"),
            ("critical_detection", record.critical_detection_hash, "S6"),
            ("critical_review_plan", record.critical_review_plan_hash, "S6"),
        ),
    )


def store_research_safety_result(connection: Connection[Any], record: ResearchSafetyResult) -> None:
    _insert_artifact(
        connection,
        kind="RESEARCH_SAFETY_RESULT",
        artifact_id=record.result_id,
        artifact_hash=record.result_hash,
        case_id=record.case_id,
        case_revision=record.case_revision,
        protocol_version=record.protocol_version,
        record=record,
        links=(
            ("admission", record.admission_hash, "S7"),
            ("parent_world_state", record.parent_world_state_hash, "S6"),
            ("parent_causal_graph", record.parent_causal_graph_hash, "S6"),
            ("critical_detection", record.critical_detection_hash, "S6"),
            ("critical_review_plan", record.critical_review_plan_hash, "S6"),
        ),
    )


def store_scenario_generation_packet(
    connection: Connection[Any], record: ScenarioGenerationAdmissionPacket
) -> None:
    _insert_artifact(
        connection,
        kind="SCENARIO_GENERATION_PACKET",
        artifact_id=record.packet_id,
        artifact_hash=record.packet_hash,
        case_id=record.case_id,
        case_revision=record.case_revision,
        protocol_version=record.protocol_version,
        record=record,
        links=(
            ("research_safety_admission", record.research_safety_admission_hash, "S7"),
            ("parent_world_state", record.parent_world_state_hash, "S6"),
            ("parent_causal_graph", record.parent_causal_graph_hash, "S6"),
            ("critical_detection", record.critical_detection_hash, "S6"),
            ("critical_review_plan", record.critical_review_plan_hash, "S6"),
        ),
    )


def store_scenario_generation_result(
    connection: Connection[Any],
    packet: ScenarioGenerationAdmissionPacket,
    record: ScenarioGenerationAdmissionResult,
) -> None:
    packet.assert_integrity()
    if record.packet_hash != packet.packet_hash:
        raise ValueError("Scenario admission result does not bind supplied packet")
    _insert_artifact(
        connection,
        kind="SCENARIO_GENERATION_RESULT",
        artifact_id=record.result_id,
        artifact_hash=record.result_hash,
        case_id=packet.case_id,
        case_revision=packet.case_revision,
        protocol_version=record.protocol_version,
        record=record,
        links=(
            ("scenario_generation_packet", record.packet_hash, "S7"),
            ("research_safety_result", record.research_safety_result_hash, "S7"),
        ),
    )


def store_controller_c_invocation(
    connection: Connection[Any], record: ControllerCInvocationPacket
) -> None:
    _insert_artifact(
        connection,
        kind="CONTROLLER_C_INVOCATION",
        artifact_id=record.invocation_packet_id,
        artifact_hash=record.packet_hash,
        case_id=record.case_id,
        case_revision=record.case_revision,
        protocol_version=record.protocol_version,
        record=record,
        links=(
            ("parent_world_state", record.parent_world_state_hash, "S6"),
            ("parent_causal_graph", record.parent_causal_graph_hash, "S6"),
            ("critical_detection", record.critical_detection_hash, "S6"),
            ("critical_review_plan", record.critical_review_plan_hash, "S6"),
            ("research_safety_result", record.research_safety_result_hash, "S7"),
            ("scenario_admission_packet", record.scenario_admission_packet_hash, "S7"),
            ("scenario_admission_result", record.scenario_admission_result_hash, "S7"),
        ),
    )


def store_scenario_path(connection: Connection[Any], record: ScenarioPath) -> None:
    _insert_artifact(
        connection,
        kind="SCENARIO_PATH",
        artifact_id=record.scenario_path_id,
        artifact_hash=record.path_hash,
        case_id=record.case_id,
        case_revision=record.case_revision,
        protocol_version=record.protocol_version,
        record=record,
        links=(
            ("parent_world_state", record.parent_world_state_hash, "S6"),
            ("parent_causal_graph", record.parent_causal_graph_hash, "S6"),
            ("critical_detection", record.critical_detection_hash, "S6"),
            ("critical_review_plan", record.critical_review_plan_hash, "S6"),
        ),
    )


def store_intervention(connection: Connection[Any], record: InterventionRecord) -> None:
    _insert_artifact(
        connection,
        kind="INTERVENTION",
        artifact_id=record.intervention_id,
        artifact_hash=record.intervention_hash,
        case_id=record.case_id,
        case_revision=record.case_revision,
        protocol_version=record.protocol_version,
        record=record,
    )


def store_scenario_set(connection: Connection[Any], record: ScenarioSet) -> None:
    child_links: list[ArtifactLink] = [
        ("parent_world_state", record.parent_world_state_hash, "S6"),
        ("parent_causal_graph", record.parent_causal_graph_hash, "S6"),
        ("critical_detection", record.critical_detection_hash, "S6"),
        ("critical_review_plan", record.critical_review_plan_hash, "S6"),
    ]
    child_links.extend(("scenario_path", item.path_hash, "S7") for item in record.paths)
    child_links.extend(
        ("intervention", item.intervention_hash, "S7") for item in record.interventions
    )
    _insert_artifact(
        connection,
        kind="SCENARIO_SET",
        artifact_id=record.scenario_set_id,
        artifact_hash=record.scenario_set_hash,
        case_id=record.case_id,
        case_revision=record.case_revision,
        protocol_version=record.protocol_version,
        record=record,
        links=child_links,
    )


def store_controller_c_output(connection: Connection[Any], record: ControllerCOutputRecord) -> None:
    links: list[ArtifactLink] = [
        ("controller_c_invocation", record.invocation_packet_hash, "S7"),
        ("scenario_set", record.scenario_set_hash, "S7"),
    ]
    links.extend(("scenario_path", value, "S7") for value in record.scenario_path_hashes)
    links.extend(("intervention", value, "S7") for value in record.intervention_hashes)
    _insert_artifact(
        connection,
        kind="CONTROLLER_C_OUTPUT",
        artifact_id=record.output_id,
        artifact_hash=record.output_hash,
        case_id=record.case_id,
        case_revision=record.case_revision,
        protocol_version=record.protocol_version,
        record=record,
        links=links,
    )


def store_resimulation_safety_admission(
    connection: Connection[Any], record: ResimulationSafetyAdmission
) -> None:
    links: list[ArtifactLink] = [
        ("scenario_set", record.scenario_set_hash, "S7"),
        ("scenario_path", record.scenario_path_hash, "S7"),
        ("parent_world_state", record.parent_world_state_hash, "S6"),
        ("parent_causal_graph", record.parent_causal_graph_hash, "S6"),
    ]
    if record.intervention_hash is not None:
        links.append(("intervention", record.intervention_hash, "S7"))
    _insert_artifact(
        connection,
        kind="RESIMULATION_SAFETY_ADMISSION",
        artifact_id=record.admission_id,
        artifact_hash=record.admission_hash,
        case_id=record.case_id,
        case_revision=record.case_revision,
        protocol_version=record.protocol_version,
        record=record,
        links=links,
    )


def store_resimulation_safety_result(
    connection: Connection[Any], record: ResimulationSafetyResult
) -> None:
    links: list[ArtifactLink] = [
        ("admission", record.admission_hash, "S7"),
        ("scenario_set", record.scenario_set_hash, "S7"),
        ("scenario_path", record.scenario_path_hash, "S7"),
        ("parent_world_state", record.parent_world_state_hash, "S6"),
        ("parent_causal_graph", record.parent_causal_graph_hash, "S6"),
    ]
    if record.intervention_hash is not None:
        links.append(("intervention", record.intervention_hash, "S7"))
    _insert_artifact(
        connection,
        kind="RESIMULATION_SAFETY_RESULT",
        artifact_id=record.result_id,
        artifact_hash=record.result_hash,
        case_id=record.case_id,
        case_revision=record.case_revision,
        protocol_version=record.protocol_version,
        record=record,
        links=links,
    )


def store_rerun_task(connection: Connection[Any], record: ScenarioDomainRerunTask) -> None:
    links: list[ArtifactLink] = [
        ("scenario_set", record.scenario_set_hash, "S7"),
        ("scenario_path", record.scenario_path_hash, "S7"),
        ("parent_world_state", record.parent_world_state_hash, "S6"),
        ("parent_causal_graph", record.parent_causal_graph_hash, "S6"),
    ]
    if record.intervention_hash is not None:
        links.append(("intervention", record.intervention_hash, "S7"))
    _insert_artifact(
        connection,
        kind="RERUN_TASK",
        artifact_id=record.rerun_task_id,
        artifact_hash=record.task_hash,
        case_id=record.case_id,
        case_revision=record.case_revision,
        protocol_version=record.protocol_version,
        record=record,
        links=links,
    )


def store_rerun_route(connection: Connection[Any], record: ScenarioDomainRerunRoute) -> None:
    _insert_artifact(
        connection,
        kind="RERUN_ROUTE",
        artifact_id=f"{record.task_hash}:{record.model_id}",
        artifact_hash=record.route_hash,
        case_id=record.case_id,
        case_revision=record.case_revision,
        protocol_version=record.protocol_version,
        record=record,
        links=(("rerun_task", record.task_hash, "S7"),),
    )


def store_rerun_output(connection: Connection[Any], record: ScenarioDomainRerunOutput) -> None:
    links: list[ArtifactLink] = [
        ("rerun_task", record.task_hash, "S7"),
        ("rerun_route", record.route_hash, "S7"),
        ("scenario_set", record.scenario_set_hash, "S7"),
        ("scenario_path", record.scenario_path_hash, "S7"),
        ("parent_world_state", record.parent_world_state_hash, "S6"),
        ("parent_causal_graph", record.parent_causal_graph_hash, "S6"),
        ("raw_output", record.raw_output_hash, "RUNTIME"),
    ]
    if record.intervention_hash is not None:
        links.append(("intervention", record.intervention_hash, "S7"))
    _insert_artifact(
        connection,
        kind="RERUN_OUTPUT",
        artifact_id=record.output_id,
        artifact_hash=record.output_hash,
        case_id=record.case_id,
        case_revision=record.case_revision,
        protocol_version=record.protocol_version,
        record=record,
        links=links,
    )


def store_resimulation_plan(connection: Connection[Any], record: ScenarioResimulationPlan) -> None:
    links: list[ArtifactLink] = [
        ("controller_c_output", record.controller_c_output_hash, "S7"),
        ("scenario_set", record.scenario_set_hash, "S7"),
        ("scenario_path", record.scenario_path_hash, "S7"),
        ("parent_world_state", record.parent_world_state_hash, "S6"),
        ("parent_causal_graph", record.parent_causal_graph_hash, "S6"),
        ("resimulation_safety_admission", record.resimulation_safety_admission_hash, "S7"),
        ("resimulation_safety_result", record.resimulation_safety_result_hash, "S7"),
    ]
    if record.intervention_hash is not None:
        links.append(("intervention", record.intervention_hash, "S7"))
    links.extend(("parent_actor_state", value, "S6") for value in record.parent_actor_state_hashes)
    links.extend(("rerun_task", item.task_hash, "S7") for item in record.rerun_tasks)
    links.extend(
        ("rerun_route", item.route_hash, "S7")
        for item in record.routing_entries
        if item.route_hash is not None
    )
    _insert_artifact(
        connection,
        kind="RESIMULATION_PLAN",
        artifact_id=record.plan_id,
        artifact_hash=record.plan_hash,
        case_id=record.case_id,
        case_revision=record.case_revision,
        protocol_version=record.protocol_version,
        record=record,
        links=links,
    )


def store_resimulation_result(
    connection: Connection[Any], record: ScenarioResimulationResult
) -> None:
    links: list[ArtifactLink] = [
        ("resimulation_plan", record.plan_hash, "S7"),
        ("scenario_set", record.scenario_set_hash, "S7"),
        ("scenario_path", record.scenario_path_hash, "S7"),
        ("parent_world_state", record.parent_world_state_hash, "S6"),
        ("parent_causal_graph", record.parent_causal_graph_hash, "S6"),
        ("resulting_world_state", record.resulting_world_state_hash, "S6"),
        ("resulting_causal_graph", record.resulting_causal_graph_hash, "S6"),
    ]
    if record.intervention_hash is not None:
        links.append(("intervention", record.intervention_hash, "S7"))
    links.extend(("parent_actor_state", value, "S6") for value in record.parent_actor_state_hashes)
    links.extend(("rerun_task", value, "S7") for value in record.rerun_task_hashes)
    links.extend(("rerun_route", value, "S7") for value in record.rerun_route_hashes)
    links.extend(("rerun_output", value, "S7") for value in record.rerun_output_hashes)
    links.extend(
        ("revised_actor_state", value, "S6") for value in record.revised_actor_state_hashes
    )
    _insert_artifact(
        connection,
        kind="RESIMULATION_RESULT",
        artifact_id=record.result_id,
        artifact_hash=record.result_hash,
        case_id=record.case_id,
        case_revision=record.case_revision,
        protocol_version=record.protocol_version,
        record=record,
        links=links,
    )


def store_at17_evidence(
    connection: Connection[Any],
    result: ScenarioResimulationResult,
    record: AT17WorldRevisionEvidence,
) -> None:
    result.assert_integrity()
    if record.resimulation_result_hash != result.result_hash:
        raise ValueError("AT-17 evidence does not bind supplied re-simulation result")
    links: list[ArtifactLink] = [
        ("resimulation_result", record.resimulation_result_hash, "S7"),
        ("parent_world_state", record.parent_world_state_hash, "S6"),
        ("resulting_world_state", record.resulting_world_state_hash, "S6"),
        ("parent_causal_graph", record.parent_causal_graph_hash, "S6"),
        ("resulting_causal_graph", record.resulting_causal_graph_hash, "S6"),
    ]
    links.extend(
        ("revised_actor_state", value, "S6") for value in record.revised_actor_state_hashes
    )
    _insert_artifact(
        connection,
        kind="AT17_EVIDENCE",
        artifact_id=record.evidence_id,
        artifact_hash=record.evidence_hash,
        case_id=result.case_id,
        case_revision=result.case_revision,
        protocol_version=record.protocol_version,
        record=record,
        links=links,
    )


def store_challenger_task(connection: Connection[Any], record: ChallengerTask) -> None:
    _insert_artifact(
        connection,
        kind="CHALLENGER_TASK",
        artifact_id=record.task_id,
        artifact_hash=record.task_hash,
        case_id=record.case_id,
        case_revision=record.case_revision,
        protocol_version=record.protocol_version,
        record=record,
        links=(
            ("critical_review_plan", record.critical_review_plan_hash, "S6"),
            ("controller_c_output", record.controller_c_output_hash, "S7"),
            ("scenario_set", record.scenario_set_hash, "S7"),
            ("resimulation_plan", record.resimulation_plan_hash, "S7"),
            ("resimulation_result", record.resimulation_result_hash, "S7"),
            ("at17_evidence", record.at17_evidence_hash, "S7"),
            ("resulting_world_state", record.resulting_world_state_hash, "S6"),
            ("resulting_causal_graph", record.resulting_causal_graph_hash, "S6"),
            ("resimulation_safety_result", record.resimulation_safety_result_hash, "S7"),
        ),
    )


def _challenger_source_layers(packet: ChallengerSourcePacket) -> dict[str, ArtifactLayer]:
    packet.assert_integrity()
    s6_kinds = {"CRITICAL_REVIEW_PLAN", "WORLD_STATE", "CAUSAL_GRAPH"}
    return {
        source.sha256: "S6" if source.kind.value in s6_kinds else "S7"
        for source in packet.source_refs
    }


def store_challenger_packet(connection: Connection[Any], record: ChallengerSourcePacket) -> None:
    source_layers = _challenger_source_layers(record)
    links: list[ArtifactLink] = [("challenger_task", record.task_hash, "S7")]
    links.extend(
        (f"source:{source.kind.value.lower()}", source.sha256, source_layers[source.sha256])
        for source in record.source_refs
    )
    _insert_artifact(
        connection,
        kind="CHALLENGER_PACKET",
        artifact_id=record.packet_id,
        artifact_hash=record.packet_hash,
        case_id=record.case_id,
        case_revision=record.case_revision,
        protocol_version=record.protocol_version,
        record=record,
        links=links,
    )


def store_challenger_finding(
    connection: Connection[Any],
    packet: ChallengerSourcePacket,
    response: ChallengerResponse,
    record: ChallengerFinding,
) -> None:
    packet.assert_integrity()
    response.assert_integrity()
    if response.packet_hash != packet.packet_hash:
        raise ValueError("Challenger response does not bind supplied source packet")
    if record.finding_hash not in {item.finding_hash for item in response.findings}:
        raise ValueError("Challenger finding is not part of supplied response")
    source_layers = _challenger_source_layers(packet)
    links: list[ArtifactLink] = [
        ("challenger_task", record.task_hash, "S7"),
        ("challenger_packet", record.packet_hash, "S7"),
    ]
    for source_hash in record.source_hash_refs:
        source_layer = source_layers.get(source_hash)
        if source_layer is None:
            raise ValueError("Challenger finding source hash is outside supplied packet")
        links.append(("finding_source", source_hash, source_layer))
    _insert_artifact(
        connection,
        kind="CHALLENGER_FINDING",
        artifact_id=record.finding_id,
        artifact_hash=record.finding_hash,
        case_id=response.case_id,
        case_revision=response.case_revision,
        protocol_version=record.protocol_version,
        record=record,
        links=links,
    )


def store_challenger_response(connection: Connection[Any], record: ChallengerResponse) -> None:
    links: list[ArtifactLink] = [
        ("challenger_task", record.task_hash, "S7"),
        ("challenger_packet", record.packet_hash, "S7"),
        ("raw_output", record.raw_output_hash, "RUNTIME"),
    ]
    links.extend(("challenger_finding", item.finding_hash, "S7") for item in record.findings)
    _insert_artifact(
        connection,
        kind="CHALLENGER_RESPONSE",
        artifact_id=record.response_id,
        artifact_hash=record.response_hash,
        case_id=record.case_id,
        case_revision=record.case_revision,
        protocol_version=record.protocol_version,
        record=record,
        links=links,
    )


def store_challenger_satisfaction(
    connection: Connection[Any], record: PendingChallengerSatisfaction
) -> None:
    links: list[ArtifactLink] = [
        ("critical_review_plan", record.critical_review_plan_hash, "S6"),
        ("challenger_task", record.challenger_task_hash, "S7"),
        ("challenger_packet", record.challenger_packet_hash, "S7"),
        ("challenger_response", record.challenger_response_hash, "S7"),
    ]
    links.extend(("challenger_finding", value, "S7") for value in record.challenger_finding_hashes)
    _insert_artifact(
        connection,
        kind="CHALLENGER_SATISFACTION",
        artifact_id=record.satisfaction_id,
        artifact_hash=record.satisfaction_hash,
        case_id=record.case_id,
        case_revision=record.case_revision,
        protocol_version=record.protocol_version,
        record=record,
        links=links,
    )


def store_challenger_gate(
    connection: Connection[Any],
    satisfaction: PendingChallengerSatisfaction,
    record: ChallengerReviewGateResult,
) -> None:
    satisfaction.assert_integrity()
    if record.satisfaction_hash != satisfaction.satisfaction_hash:
        raise ValueError("Challenger gate does not bind supplied satisfaction sidecar")
    links: list[ArtifactLink] = [
        ("challenger_response", record.challenger_response_hash, "S7"),
        ("challenger_satisfaction", record.satisfaction_hash, "S7"),
    ]
    links.extend(("blocking_finding", value, "S7") for value in record.blocking_finding_hashes)
    links.extend(("unresolved_finding", value, "S7") for value in record.unresolved_finding_hashes)
    _insert_artifact(
        connection,
        kind="CHALLENGER_GATE",
        artifact_id=record.gate_result_id,
        artifact_hash=record.gate_result_hash,
        case_id=satisfaction.case_id,
        case_revision=satisfaction.case_revision,
        protocol_version=record.protocol_version,
        record=record,
        links=links,
    )
