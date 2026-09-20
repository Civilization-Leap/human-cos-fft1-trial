"""S6-WCI2 revisioned Causal/Feedback Graph and world-integration entry gate."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from human_cos.integration import (
    CrossExamResponse,
    DisagreementContractError,
    DisagreementNode,
    assert_dissent_preserved,
)
from human_cos.runtime.run import canonical_document_sha256
from human_cos.runtime.state_machine import (
    CaseMode,
    CaseRuntimePosition,
    GuardCheck,
    GuardStatus,
    RuntimeState,
    TransitionDecision,
    TransitionKey,
    TransitionStatus,
    can_transition,
)

from .state import ProvenanceRef, WorldStateContractError


class CausalGraphContractError(ValueError):
    """A Causal/Feedback Graph violates the authorized WCI2 contract."""


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("S6-WCI2 timestamps require timezone-aware datetimes")
    return value


class CausalNodeType(str, Enum):
    ACTOR = "Actor"
    ACTION = "Action"
    INTEREST = "Interest"
    HUMAN_STATE = "HumanState"
    SYSTEM_STATE = "SystemState"
    CONSTRAINT = "Constraint"
    UNKNOWN = "Unknown"
    CRITICAL_NODE_REF = "CriticalNode"


class CausalEdgeType(str, Enum):
    CAUSES = "CAUSES"
    ENABLES = "ENABLES"
    INHIBITS = "INHIBITS"
    AMPLIFIES = "AMPLIFIES"
    DAMPENS = "DAMPENS"
    DEPENDS_ON = "DEPENDS_ON"
    SIGNALS = "SIGNALS"
    TRIGGERS = "TRIGGERS"
    REVERSES = "REVERSES"
    DELAYED_EFFECT = "DELAYED_EFFECT"


class CausalNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(min_length=1)
    node_type: CausalNodeType
    label: str = Field(min_length=1)
    source_refs: tuple[ProvenanceRef, ...]


class CausalEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    edge_id: str = Field(min_length=1)
    source_node_id: str = Field(min_length=1)
    target_node_id: str = Field(min_length=1)
    edge_type: CausalEdgeType
    source_refs: tuple[ProvenanceRef, ...]


class FeedbackLoop(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    loop_id: str = Field(min_length=1)
    node_ids: tuple[str, ...]
    description: str = Field(min_length=1)


class CausalGraphPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    graph_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    revision: int = Field(ge=1)
    parent_graph_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    nodes: tuple[CausalNode, ...]
    edges: tuple[CausalEdge, ...]
    feedback_loops: tuple[FeedbackLoop, ...] = ()
    dissent_node_hashes: tuple[str, ...] = ()
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class CausalGraph(CausalGraphPayload):
    graph_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"graph_hash"}, exclude_none=True)
        if self.graph_hash != canonical_document_sha256(payload):
            raise CausalGraphContractError("CausalGraph graph_hash does not match payload")
        if self.revision == 1 and self.parent_graph_hash is not None:
            raise CausalGraphContractError("first CausalGraph revision cannot have a parent")
        if self.revision > 1 and self.parent_graph_hash is None:
            raise CausalGraphContractError("later CausalGraph revision requires parent hash")
        node_ids = tuple(node.node_id for node in self.nodes)
        if not node_ids or len(node_ids) != len(set(node_ids)):
            raise CausalGraphContractError("CausalGraph node IDs must be non-empty and unique")
        edge_ids = tuple(edge.edge_id for edge in self.edges)
        if len(edge_ids) != len(set(edge_ids)):
            raise CausalGraphContractError("CausalGraph edge IDs must be unique")
        node_set = set(node_ids)
        for node in self.nodes:
            if not node.source_refs:
                raise CausalGraphContractError("every CausalGraph node needs source lineage")
        for edge in self.edges:
            if edge.source_node_id not in node_set or edge.target_node_id not in node_set:
                raise CausalGraphContractError("CausalGraph edge references unknown node")
            if not edge.source_refs:
                raise CausalGraphContractError("every CausalGraph edge needs source lineage")
        for loop in self.feedback_loops:
            if len(loop.node_ids) < 2 or any(node_id not in node_set for node_id in loop.node_ids):
                raise CausalGraphContractError("FeedbackLoop requires at least two known nodes")


def freeze_causal_graph(
    payload: CausalGraphPayload,
    *,
    parent: CausalGraph | None = None,
) -> CausalGraph:
    if parent is None:
        if payload.revision != 1 or payload.parent_graph_hash is not None:
            raise CausalGraphContractError("CausalGraph without parent must be revision 1")
    else:
        parent.assert_integrity()
        if (
            payload.graph_id,
            payload.case_id,
            payload.case_revision,
            payload.protocol_version,
        ) != (
            parent.graph_id,
            parent.case_id,
            parent.case_revision,
            parent.protocol_version,
        ):
            raise CausalGraphContractError("CausalGraph revision identity does not match parent")
        if payload.revision != parent.revision + 1:
            raise CausalGraphContractError("CausalGraph revision must increment parent by one")
        if payload.parent_graph_hash != parent.graph_hash:
            raise CausalGraphContractError("CausalGraph parent hash does not match parent")
    document = payload.to_document()
    graph = CausalGraph(**document, graph_hash=canonical_document_sha256(document))
    graph.assert_integrity()
    return graph


_S6_COMMON_MODES = (
    CaseMode.LIVE_FORESIGHT,
    CaseMode.MECHANISM_BENCHMARK,
    CaseMode.SCENARIO_STRESS_TEST,
)

S6_WCI2_TRANSITIONS: frozenset[TransitionKey] = frozenset(
    {
        *(
            TransitionKey(
                mode,
                RuntimeState.DOMAIN_OUTPUT_FROZEN,
                RuntimeState.CROSS_EXAMINATION,
            )
            for mode in _S6_COMMON_MODES
        ),
        *(
            TransitionKey(
                mode,
                RuntimeState.CROSS_EXAMINATION,
                RuntimeState.WORLD_CAUSAL_INTEGRATION,
            )
            for mode in _S6_COMMON_MODES
        ),
    }
)


def _guard(name: str, passed: bool | None, reason: str) -> GuardCheck:
    if passed is None:
        return GuardCheck(name, GuardStatus.UNAVAILABLE, reason)
    if passed:
        return GuardCheck(name, GuardStatus.PASS, reason)
    return GuardCheck(name, GuardStatus.FAIL, reason)


def _with_guard(base: TransitionDecision, guard: GuardCheck) -> TransitionDecision:
    if guard.status is GuardStatus.PASS:
        return base
    status = (
        TransitionStatus.GUARD_UNAVAILABLE
        if guard.status is GuardStatus.UNAVAILABLE
        else TransitionStatus.GUARD_FAILED
    )
    return TransitionDecision(
        allowed=False,
        status=status,
        mode=base.mode,
        source=base.source,
        target=base.target,
        protocol_version=base.protocol_version,
        guard_results=base.guard_results + (guard,),
        reason="S6-WCI2 Cross Examination/dissent prerequisite was not satisfied",
    )


def can_s6_wci2_transition(
    position: CaseRuntimePosition,
    target: RuntimeState,
    *,
    responses: tuple[CrossExamResponse, ...] = (),
    disagreement_nodes: tuple[DisagreementNode, ...] = (),
    required_high_impact_position_ids: tuple[str, ...] = (),
) -> TransitionDecision:
    """Activate the second S6 edge only after frozen review and AT-07 preservation."""
    base = can_transition(
        position,
        target,
        authorized_future_transitions=S6_WCI2_TRANSITIONS,
    )
    if not base.allowed:
        return base
    if target is not RuntimeState.WORLD_CAUSAL_INTEGRATION:
        return base
    try:
        if not responses:
            raise CausalGraphContractError("frozen Cross Examination responses are required")
        response_hashes: set[str] = set()
        for response in responses:
            response.assert_integrity()
            if response.case_revision != position.case_revision:
                raise CausalGraphContractError("Cross Examination response Case revision mismatch")
            if response.protocol_version != base.protocol_version:
                raise CausalGraphContractError("Cross Examination response protocol mismatch")
            response_hashes.add(response.response_hash)
        if not disagreement_nodes:
            raise CausalGraphContractError("at least one DisagreementNode is required")
        for node in disagreement_nodes:
            node.assert_integrity()
            if node.case_revision != position.case_revision:
                raise CausalGraphContractError("DisagreementNode Case revision mismatch")
            if not set(node.source_response_hashes).issubset(response_hashes):
                raise CausalGraphContractError(
                    "DisagreementNode references unknown review response"
                )
        assert_dissent_preserved(
            nodes=disagreement_nodes,
            required_high_impact_position_ids=required_high_impact_position_ids,
        )
    except (CausalGraphContractError, DisagreementContractError) as exc:
        return _with_guard(base, _guard("at07_dissent_preserved", False, str(exc)))
    return _with_guard(
        base,
        _guard(
            "at07_dissent_preserved",
            True,
            "Cross Examination lineage is frozen and required high-impact dissent is preserved",
        ),
    )


def assert_world_graph_binding(
    *,
    world_case_id: str,
    world_case_revision: int,
    graph: CausalGraph,
) -> None:
    graph.assert_integrity()
    if (graph.case_id, graph.case_revision) != (world_case_id, world_case_revision):
        raise WorldStateContractError("WorldState and CausalGraph Case binding does not match")
