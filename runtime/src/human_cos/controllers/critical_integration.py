"""S6-WCI3 qualified Controller B Critical Integration and third-edge gate."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from human_cos.domains import DomainOutputRecord
from human_cos.integration import CrossExamResponse, DisagreementNode, assert_dissent_preserved
from human_cos.models import QualificationGate
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
from human_cos.world import (
    ActorStateSnapshot,
    CausalGraph,
    WorldStateSnapshot,
    assert_world_graph_binding,
)

from .review import FramingReview


class CriticalIntegrationError(ValueError):
    """Controller B integration violates the authorized WCI3 source/dissent boundary."""


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("S6-WCI3 timestamps require timezone-aware datetimes")
    return value


class CriticalIntegrationContent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    integrated_mechanisms: tuple[str, ...] = ()
    cross_domain_links: tuple[str, ...] = ()
    preserved_dissent_node_hashes: tuple[str, ...]
    critical_node_candidate_refs: tuple[str, ...] = ()
    open_unknowns: tuple[str, ...] = ()


class CriticalIntegrationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    integration_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    controller_model_id: str = Field(min_length=1)
    controller_model_family: str = Field(min_length=1)
    controller_provider: str = Field(min_length=1)
    framing_review_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    domain_output_hashes: tuple[str, ...]
    cross_exam_response_hashes: tuple[str, ...]
    disagreement_node_hashes: tuple[str, ...]
    actor_state_hashes: tuple[str, ...]
    world_state_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    causal_graph_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    required_high_impact_position_ids: tuple[str, ...] = ()
    content: CriticalIntegrationContent
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class CriticalIntegrationRecord(CriticalIntegrationPayload):
    integration_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(
            mode="json",
            exclude={"integration_hash"},
            exclude_none=True,
        )
        if self.integration_hash != canonical_document_sha256(payload):
            raise CriticalIntegrationError(
                "CriticalIntegrationRecord integration_hash does not match payload"
            )
        collections = (
            self.domain_output_hashes,
            self.cross_exam_response_hashes,
            self.disagreement_node_hashes,
            self.actor_state_hashes,
            self.content.preserved_dissent_node_hashes,
        )
        if any(len(items) != len(set(items)) for items in collections):
            raise CriticalIntegrationError(
                "CriticalIntegrationRecord hash collections must be unique"
            )
        if not self.domain_output_hashes:
            raise CriticalIntegrationError("CriticalIntegrationRecord requires Domain outputs")
        if not self.cross_exam_response_hashes or not self.disagreement_node_hashes:
            raise CriticalIntegrationError(
                "CriticalIntegrationRecord requires Cross Examination and disagreement lineage"
            )
        if not self.actor_state_hashes:
            raise CriticalIntegrationError("CriticalIntegrationRecord requires ActorState lineage")


def _assert_case_protocol(
    *,
    case_id: str,
    case_revision: int,
    protocol_version: str,
    actual: tuple[str, int, str],
    label: str,
) -> None:
    if actual != (case_id, case_revision, protocol_version):
        raise CriticalIntegrationError(f"{label} Case/revision/protocol binding mismatch")


def _required_dissent_node_hashes(
    nodes: tuple[DisagreementNode, ...],
    required_position_ids: tuple[str, ...],
) -> set[str]:
    required = set(required_position_ids)
    return {
        node.node_hash
        for node in nodes
        if any(position.position_id in required for position in node.positions)
    }


def build_critical_integration(
    *,
    qualification: QualificationGate,
    controller_model_id: str,
    framing_review: FramingReview,
    domain_outputs: tuple[DomainOutputRecord, ...],
    cross_exam_responses: tuple[CrossExamResponse, ...],
    disagreement_nodes: tuple[DisagreementNode, ...],
    actor_states: tuple[ActorStateSnapshot, ...],
    world_state: WorldStateSnapshot,
    causal_graph: CausalGraph,
    required_high_impact_position_ids: tuple[str, ...],
    integration_id: str,
    content: CriticalIntegrationContent,
    frozen_at: datetime,
) -> CriticalIntegrationRecord:
    """Freeze Controller B integration without mutating or upgrading source evidence."""
    profile = qualification.assert_controller_eligible(controller_model_id)
    framing_review.assert_integrity()
    world_state.assert_integrity()
    causal_graph.assert_integrity()

    case_id = framing_review.case_id
    case_revision = framing_review.case_revision
    protocol_version = framing_review.protocol_version
    _assert_case_protocol(
        case_id=case_id,
        case_revision=case_revision,
        protocol_version=protocol_version,
        actual=(world_state.case_id, world_state.case_revision, world_state.protocol_version),
        label="WorldState",
    )
    _assert_case_protocol(
        case_id=case_id,
        case_revision=case_revision,
        protocol_version=protocol_version,
        actual=(causal_graph.case_id, causal_graph.case_revision, causal_graph.protocol_version),
        label="CausalGraph",
    )
    assert_world_graph_binding(
        world_case_id=world_state.case_id,
        world_case_revision=world_state.case_revision,
        graph=causal_graph,
    )
    if world_state.causal_graph_hash != causal_graph.graph_hash:
        raise CriticalIntegrationError("WorldState does not bind the exact CausalGraph hash")

    for output in domain_outputs:
        output.assert_integrity()
        _assert_case_protocol(
            case_id=case_id,
            case_revision=case_revision,
            protocol_version=protocol_version,
            actual=(output.case_id, output.case_revision, output.protocol_version),
            label="DomainOutput",
        )
    for response in cross_exam_responses:
        response.assert_integrity()
        _assert_case_protocol(
            case_id=case_id,
            case_revision=case_revision,
            protocol_version=protocol_version,
            actual=(response.case_id, response.case_revision, response.protocol_version),
            label="CrossExamResponse",
        )
    for node in disagreement_nodes:
        node.assert_integrity()
        _assert_case_protocol(
            case_id=case_id,
            case_revision=case_revision,
            protocol_version=protocol_version,
            actual=(node.case_id, node.case_revision, node.protocol_version),
            label="DisagreementNode",
        )
    for actor in actor_states:
        actor.assert_integrity()
        _assert_case_protocol(
            case_id=case_id,
            case_revision=case_revision,
            protocol_version=protocol_version,
            actual=(actor.case_id, actor.case_revision, actor.protocol_version),
            label="ActorState",
        )

    if not domain_outputs or not cross_exam_responses or not disagreement_nodes or not actor_states:
        raise CriticalIntegrationError("Controller B requires all authorized S5/S6 source families")

    assert_dissent_preserved(
        nodes=disagreement_nodes,
        required_high_impact_position_ids=required_high_impact_position_ids,
    )
    disagreement_hashes = {node.node_hash for node in disagreement_nodes}
    if not disagreement_hashes.issubset(set(world_state.dissent_node_hashes)):
        raise CriticalIntegrationError("WorldState omitted a frozen DisagreementNode")
    if not disagreement_hashes.issubset(set(causal_graph.dissent_node_hashes)):
        raise CriticalIntegrationError("CausalGraph omitted a frozen DisagreementNode")

    required_node_hashes = _required_dissent_node_hashes(
        disagreement_nodes,
        required_high_impact_position_ids,
    )
    if not required_node_hashes.issubset(set(content.preserved_dissent_node_hashes)):
        raise CriticalIntegrationError("Controller B omitted required high-impact dissent")

    payload = CriticalIntegrationPayload(
        integration_id=integration_id,
        case_id=case_id,
        case_revision=case_revision,
        controller_model_id=profile.model_id,
        controller_model_family=profile.model_family,
        controller_provider=profile.provider,
        framing_review_hash=framing_review.review_hash,
        domain_output_hashes=tuple(output.record_hash for output in domain_outputs),
        cross_exam_response_hashes=tuple(
            response.response_hash for response in cross_exam_responses
        ),
        disagreement_node_hashes=tuple(node.node_hash for node in disagreement_nodes),
        actor_state_hashes=tuple(actor.state_hash for actor in actor_states),
        world_state_hash=world_state.world_state_hash,
        causal_graph_hash=causal_graph.graph_hash,
        required_high_impact_position_ids=required_high_impact_position_ids,
        content=content,
        protocol_version=protocol_version,
        frozen_at=frozen_at,
    )
    document = payload.to_document()
    record = CriticalIntegrationRecord(
        **document,
        integration_hash=canonical_document_sha256(document),
    )
    record.assert_integrity()
    return record


_S6_COMMON_MODES = (
    CaseMode.LIVE_FORESIGHT,
    CaseMode.MECHANISM_BENCHMARK,
    CaseMode.SCENARIO_STRESS_TEST,
)

S6_WCI3_TRANSITIONS: frozenset[TransitionKey] = frozenset(
    TransitionKey(
        mode,
        RuntimeState.WORLD_CAUSAL_INTEGRATION,
        RuntimeState.CRITICAL_NODE_DETECTION,
    )
    for mode in _S6_COMMON_MODES
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
        reason="S6-WCI3 Controller B integration prerequisite was not satisfied",
    )


def can_s6_wci3_transition(
    position: CaseRuntimePosition,
    target: RuntimeState,
    *,
    integration: CriticalIntegrationRecord | None = None,
) -> TransitionDecision:
    """Activate only WORLD_CAUSAL_INTEGRATION -> CRITICAL_NODE_DETECTION."""
    base = can_transition(
        position,
        target,
        authorized_future_transitions=S6_WCI3_TRANSITIONS,
    )
    if not base.allowed:
        return base
    if integration is None:
        return _with_guard(
            base,
            _guard("controller_b_integration_frozen", None, "integration was not supplied"),
        )
    try:
        integration.assert_integrity()
        if integration.case_revision != position.case_revision:
            raise CriticalIntegrationError("integration Case revision does not match runtime")
        if integration.protocol_version != base.protocol_version:
            raise CriticalIntegrationError("integration protocol version does not match runtime")
    except CriticalIntegrationError as exc:
        return _with_guard(base, _guard("controller_b_integration_frozen", False, str(exc)))
    return _with_guard(
        base,
        _guard(
            "controller_b_integration_frozen",
            True,
            "qualified Controller B integration is frozen and source-bound",
        ),
    )
