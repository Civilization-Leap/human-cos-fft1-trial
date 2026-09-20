"""Pure application assembler for the SBX7 input-driven S6 engineering slice."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from psycopg import Connection
from pydantic import BaseModel, ConfigDict, Field

from human_cos.controllers import FramingReview
from human_cos.controllers.critical_integration import (
    CriticalIntegrationContent,
    build_critical_integration,
)
from human_cos.domains import DomainOutputRecord
from human_cos.integration import (
    ConflictType,
    CrossExamFinding,
    DisagreementNodePayload,
    DisclosureGrantPayload,
    DissentPosition,
    ResolutionRoute,
    ReviewPromptType,
    SourceKind,
    SourceRef,
    build_cross_exam_task,
    freeze_cross_exam_response,
    freeze_disagreement_node,
    freeze_disclosure_grant,
)
from human_cos.integration.cross_exam import can_s6_wci1_transition
from human_cos.models import QualificationGate
from human_cos.runtime.state_machine import CaseMode, CaseRuntimePosition, RuntimeState
from human_cos.storage.s6_world import (
    store_actor_state,
    store_causal_graph,
    store_critical_integration,
    store_cross_exam_response,
    store_cross_exam_task,
    store_disagreement_node,
    store_disclosure_grant,
    store_world_state,
)
from human_cos.world import (
    ActorStateSnapshotPayload,
    CausalEdge,
    CausalEdgeType,
    CausalGraphPayload,
    CausalNode,
    CausalNodeType,
    ProvenanceRef,
    SourceClass,
    WorldStateSnapshotPayload,
    freeze_actor_state,
    freeze_causal_graph,
    freeze_world_state,
)
from human_cos.world.causal import can_s6_wci2_transition


class CrossExamFixtureContent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    statement: str = Field(min_length=1)
    open_unknowns: tuple[str, ...] = ()


class ControllerBFixtureContent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    integrated_mechanisms: tuple[str, ...]
    critical_node_candidate_refs: tuple[str, ...] = ()
    open_unknowns: tuple[str, ...] = ()
    preserve_all_dissent: bool = Field(strict=True)


@dataclass(frozen=True)
class S6AssemblyInputs:
    reviewer_model_id: str
    reviewer_frozen_at: Any
    reviewer_fixture_hash: str
    reviewer_content: CrossExamFixtureContent
    controller_model_id: str
    controller_frozen_at: Any
    controller_fixture_hash: str
    controller_content: ControllerBFixtureContent
    qualification: QualificationGate


def _load_review(connection: Connection[Any]) -> FramingReview:
    rows = connection.execute("SELECT payload FROM human_cos_framing_review LIMIT 2").fetchall()
    if len(rows) != 1:
        raise ValueError("expected exactly one framing review")
    review = FramingReview.model_validate(rows[0][0])
    review.assert_integrity()
    return review


def assemble_s6_slice(
    connection: Connection[Any],
    *,
    case: Any,
    domain_output_document: dict[str, Any],
    attempt_id: str,
    inputs: S6AssemblyInputs,
    deadline: float,
    check_binding: Callable[[], None],
) -> dict[str, Any]:
    """Freeze CrossExam -> World/Causal -> Controller-B integration without S6 terminal."""
    review = _load_review(connection)
    output = DomainOutputRecord.model_validate(domain_output_document)
    output.assert_integrity()
    if (review.case_id, review.case_revision) != (case.case_id, case.revision):
        raise ValueError("framing review case mismatch")
    if (output.case_id, output.case_revision) != (case.case_id, case.revision):
        raise ValueError("domain output case mismatch")
    if time.monotonic() > deadline:
        raise TimeoutError("S6 assembly deadline exceeded")

    framing_source = SourceRef(
        kind=SourceKind.FRAMING,
        ref=f"framing-review:{case.case_id}",
        sha256=review.review_hash,
    )
    domain_source = SourceRef(
        kind=SourceKind.DOMAIN_OUTPUT,
        ref=f"domain-output:{output.run_id}",
        sha256=output.record_hash,
    )
    grant = freeze_disclosure_grant(
        DisclosureGrantPayload(
            grant_id=f"grant:{attempt_id}",
            case_id=case.case_id,
            case_revision=case.revision,
            reviewer_id=inputs.reviewer_model_id,
            allowed_sources=(framing_source, domain_source),
            independent_review_required=True,
            protocol_version=case.protocol_version,
            frozen_at=inputs.reviewer_frozen_at,
        )
    )
    task = build_cross_exam_task(
        grant=grant,
        task_id=f"cross-exam:{attempt_id}",
        source_refs=(framing_source, domain_source),
        prompt_types=(ReviewPromptType.FALSIFICATION, ReviewPromptType.CONFLICT),
        frozen_at=inputs.reviewer_frozen_at,
    )
    store_disclosure_grant(connection, grant)
    store_cross_exam_task(connection, task)
    position = CaseRuntimePosition(
        mode=CaseMode.MECHANISM_BENCHMARK,
        state=RuntimeState.DOMAIN_OUTPUT_FROZEN,
        case_revision=case.revision,
    )
    first = can_s6_wci1_transition(
        position, RuntimeState.CROSS_EXAMINATION, grant=grant, tasks=(task,)
    )
    if not first.allowed:
        raise ValueError("WCI1 transition denied")
    position = CaseRuntimePosition(
        mode=position.mode, state=RuntimeState.CROSS_EXAMINATION, case_revision=case.revision
    )
    check_binding()

    finding = CrossExamFinding(
        finding_id=f"finding:{attempt_id}",
        prompt_type=ReviewPromptType.CONFLICT,
        statement=inputs.reviewer_content.statement,
        source_refs=(framing_source, domain_source),
        high_impact=True,
    )
    response = freeze_cross_exam_response(
        grant=grant,
        task=task,
        response_id=f"response:{attempt_id}",
        findings=(finding,),
        submitted_at=inputs.reviewer_frozen_at,
        frozen_at=inputs.reviewer_frozen_at,
    )
    store_cross_exam_response(connection, response)
    reviewer_position_id = f"position:reviewer:{attempt_id}"
    disagreement = freeze_disagreement_node(
        DisagreementNodePayload(
            node_id=f"dissent:{attempt_id}",
            case_id=case.case_id,
            case_revision=case.revision,
            conflict_type=ConflictType.MECHANISM,
            positions=(
                DissentPosition(
                    position_id=f"position:domain:{attempt_id}",
                    source_ref=domain_source.ref,
                    source_hash=output.record_hash,
                    statement=output.content.mechanisms[0],
                    impact="MEDIUM",
                ),
                DissentPosition(
                    position_id=reviewer_position_id,
                    source_ref=response.response_id,
                    source_hash=response.response_hash,
                    statement=inputs.reviewer_content.statement,
                    impact="HIGH",
                    minority=True,
                ),
            ),
            resolution_route=ResolutionRoute.PRESERVE_UNRESOLVED,
            unresolved=True,
            high_impact=True,
            source_response_hashes=(response.response_hash,),
            protocol_version=case.protocol_version,
            frozen_at=inputs.reviewer_frozen_at,
        )
    )
    store_disagreement_node(connection, disagreement)
    second = can_s6_wci2_transition(
        position,
        RuntimeState.WORLD_CAUSAL_INTEGRATION,
        responses=(response,),
        disagreement_nodes=(disagreement,),
        required_high_impact_position_ids=(reviewer_position_id,),
    )
    if not second.allowed:
        raise ValueError("WCI2 transition denied")
    check_binding()

    domain_provenance = ProvenanceRef(
        source_class=SourceClass.MODEL, ref=domain_source.ref, sha256=output.record_hash
    )
    review_provenance = ProvenanceRef(
        source_class=SourceClass.MODEL, ref=response.response_id, sha256=response.response_hash
    )
    if not case.actors:
        raise ValueError("actor state requires Case actors")
    actor_states = tuple(
        freeze_actor_state(
            ActorStateSnapshotPayload(
                actor_state_id=f"actor-state:{case.case_id}:{index}",
                actor_id=actor_id,
                case_id=case.case_id,
                case_revision=case.revision,
                revision=1,
                timestamp=case.time_boundary.T0,
                beliefs_or_expectations=tuple(output.content.mechanisms),
                information_visible=tuple(output.content.facts_used),
                uncertainties=tuple(inputs.reviewer_content.open_unknowns),
                source_refs=(domain_provenance, review_provenance),
                protocol_version=case.protocol_version,
                frozen_at=inputs.controller_frozen_at,
            )
        )
        for index, actor_id in enumerate(case.actors)
    )
    for actor in actor_states:
        store_actor_state(connection, actor)

    nodes = (
        CausalNode(
            node_id="actor:0",
            node_type=CausalNodeType.ACTOR,
            label=case.actors[0],
            source_refs=(domain_provenance,),
        ),
        CausalNode(
            node_id="mechanism:0",
            node_type=CausalNodeType.SYSTEM_STATE,
            label=output.content.mechanisms[0],
            source_refs=(domain_provenance,),
        ),
        CausalNode(
            node_id="dissent:0",
            node_type=CausalNodeType.UNKNOWN,
            label=inputs.reviewer_content.statement,
            source_refs=(review_provenance,),
        ),
    )
    graph = freeze_causal_graph(
        CausalGraphPayload(
            graph_id=f"causal:{case.case_id}",
            case_id=case.case_id,
            case_revision=case.revision,
            revision=1,
            nodes=nodes,
            edges=(
                CausalEdge(
                    edge_id="edge:actor-mechanism",
                    source_node_id="actor:0",
                    target_node_id="mechanism:0",
                    edge_type=CausalEdgeType.CAUSES,
                    source_refs=(domain_provenance,),
                ),
                CausalEdge(
                    edge_id="edge:mechanism-dissent",
                    source_node_id="mechanism:0",
                    target_node_id="dissent:0",
                    edge_type=CausalEdgeType.SIGNALS,
                    source_refs=(review_provenance,),
                ),
            ),
            dissent_node_hashes=(disagreement.node_hash,),
            protocol_version=case.protocol_version,
            frozen_at=inputs.controller_frozen_at,
        )
    )
    store_causal_graph(connection, graph)
    world = freeze_world_state(
        WorldStateSnapshotPayload(
            world_state_id=f"world:{case.case_id}",
            case_id=case.case_id,
            case_revision=case.revision,
            revision=1,
            timestamp=case.time_boundary.T0,
            system_states=tuple(output.content.mechanisms),
            actor_state_hashes=tuple(actor.state_hash for actor in actor_states),
            causal_graph_hash=graph.graph_hash,
            critical_node_refs=tuple(output.content.critical_node_candidates),
            open_unknowns=tuple(inputs.reviewer_content.open_unknowns),
            dissent_node_hashes=(disagreement.node_hash,),
            claim_refs=tuple(output.content.facts_used),
            source_refs=(domain_provenance, review_provenance),
            protocol_version=case.protocol_version,
            frozen_at=inputs.controller_frozen_at,
        )
    )
    store_world_state(connection, world)
    content = CriticalIntegrationContent(
        integrated_mechanisms=inputs.controller_content.integrated_mechanisms,
        preserved_dissent_node_hashes=(disagreement.node_hash,),
        critical_node_candidate_refs=inputs.controller_content.critical_node_candidate_refs,
        open_unknowns=inputs.controller_content.open_unknowns,
    )
    integration = build_critical_integration(
        qualification=inputs.qualification,
        controller_model_id=inputs.controller_model_id,
        framing_review=review,
        domain_outputs=(output,),
        cross_exam_responses=(response,),
        disagreement_nodes=(disagreement,),
        actor_states=actor_states,
        world_state=world,
        causal_graph=graph,
        required_high_impact_position_ids=(reviewer_position_id,),
        integration_id=f"critical-integration:{attempt_id}",
        content=content,
        frozen_at=inputs.controller_frozen_at,
    )
    store_critical_integration(connection, integration)
    check_binding()
    return {
        "position": RuntimeState.WORLD_CAUSAL_INTEGRATION.value,
        "cross_exam_response_hash": response.response_hash,
        "disagreement_node_hash": disagreement.node_hash,
        "actor_state_hashes": [actor.state_hash for actor in actor_states],
        "causal_graph_hash": graph.graph_hash,
        "world_state_hash": world.world_state_hash,
        "critical_integration_hash": integration.integration_hash,
        "s6_fixture_hashes": [inputs.reviewer_fixture_hash, inputs.controller_fixture_hash],
        "s6_cognitive_acceptance": "NOT_EVALUATED",
    }
