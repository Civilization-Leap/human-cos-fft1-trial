"""S7-SCS staged activation through Scenario re-simulation."""

from __future__ import annotations

from human_cos.core.models import Case
from human_cos.models import QualificationGate
from human_cos.runtime.state_machine import (
    CaseMode,
    CaseRuntimePosition,
    GuardCheck,
    GuardStatus,
    RuntimeState,
    TransitionDecision,
    TransitionKey,
    TransitionRejected,
    TransitionResult,
    TransitionStatus,
    can_transition,
)
from human_cos.safety.research import (
    ResearchSafetyAdmission,
    ResearchSafetyContractError,
    ResearchSafetyResult,
    assert_research_safety_result_binding,
)
from human_cos.safety.resimulation import (
    ResimulationSafetyAdmission,
    ResimulationSafetyOutcome,
    ResimulationSafetyResult,
)
from human_cos.world import (
    ActorStateSnapshot,
    CausalGraph,
    CausalGraphContractError,
    CriticalNodeContractError,
    CriticalNodeDetection,
    CriticalReviewPlan,
    WorldStateContractError,
    WorldStateSnapshot,
)

from .contracts import (
    ScenarioContractError,
    ScenarioGenerationAdmissionOutcome,
    ScenarioGenerationAdmissionPacket,
    ScenarioGenerationAdmissionResult,
    ScenarioSet,
    assert_scenario_generation_packet_binding,
    assert_scenario_generation_result_binding,
)
from .resimulation import (
    ControllerCOutputLike,
    ScenarioDomainRerunRoute,
    ScenarioResimulationError,
    ScenarioResimulationPlan,
    assert_scenario_resimulation_plan_binding,
)

_S7_COMMON_MODES = (
    CaseMode.LIVE_FORESIGHT,
    CaseMode.MECHANISM_BENCHMARK,
    CaseMode.SCENARIO_STRESS_TEST,
)

S7_SCS1_TRANSITIONS: frozenset[TransitionKey] = frozenset(
    TransitionKey(
        mode,
        RuntimeState.CRITICAL_NODE_REVIEW,
        RuntimeState.SCENARIO_GENERATION,
    )
    for mode in _S7_COMMON_MODES
)

S7_SCS3_TRANSITIONS: frozenset[TransitionKey] = frozenset(
    TransitionKey(
        mode,
        RuntimeState.SCENARIO_GENERATION,
        RuntimeState.SCENARIO_RESIMULATION,
    )
    for mode in _S7_COMMON_MODES
)


def _guard(name: str, passed: bool | None, reason: str) -> GuardCheck:
    if passed is None:
        return GuardCheck(name, GuardStatus.UNAVAILABLE, reason)
    if passed:
        return GuardCheck(name, GuardStatus.PASS, reason)
    return GuardCheck(name, GuardStatus.FAIL, reason)


def _with_guard(
    base: TransitionDecision,
    guard: GuardCheck,
    *,
    reason: str,
) -> TransitionDecision:
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
        reason=reason,
    )


def can_s7_scs1_transition(
    position: CaseRuntimePosition,
    target: RuntimeState,
    *,
    world_state: WorldStateSnapshot | None = None,
    causal_graph: CausalGraph | None = None,
    detection: CriticalNodeDetection | None = None,
    review_plan: CriticalReviewPlan | None = None,
    research_safety_admission: ResearchSafetyAdmission | None = None,
    research_safety_result: ResearchSafetyResult | None = None,
    admission_packet: ScenarioGenerationAdmissionPacket | None = None,
    admission_result: ScenarioGenerationAdmissionResult | None = None,
) -> TransitionDecision:
    """Authorize only CRITICAL_NODE_REVIEW -> SCENARIO_GENERATION."""

    base = can_transition(
        position,
        target,
        authorized_future_transitions=S7_SCS1_TRANSITIONS,
    )
    if not base.allowed:
        return base

    supplied = (
        world_state,
        causal_graph,
        detection,
        review_plan,
        research_safety_admission,
        research_safety_result,
        admission_packet,
        admission_result,
    )
    if any(item is None for item in supplied):
        return _with_guard(
            base,
            _guard(
                "scenario_generation_admission_frozen",
                None,
                "exact S6 lineage, Research Safety records, and admission records are required",
            ),
            reason="S7-SCS1 Scenario-generation admission prerequisite was not satisfied",
        )

    assert world_state is not None
    assert causal_graph is not None
    assert detection is not None
    assert review_plan is not None
    assert research_safety_admission is not None
    assert research_safety_result is not None
    assert admission_packet is not None
    assert admission_result is not None

    try:
        assert_research_safety_result_binding(
            research_safety_admission,
            research_safety_result,
        )
        assert_scenario_generation_packet_binding(
            packet=admission_packet,
            world_state=world_state,
            causal_graph=causal_graph,
            detection=detection,
            review_plan=review_plan,
            research_safety_admission=research_safety_admission,
        )
        assert_scenario_generation_result_binding(
            packet=admission_packet,
            research_safety_admission=research_safety_admission,
            research_safety_result=research_safety_result,
            result=admission_result,
        )
        if (
            admission_packet.case_revision != position.case_revision
            or admission_packet.protocol_version != base.protocol_version
        ):
            raise ScenarioContractError(
                "Scenario admission Case revision/protocol does not match runtime position"
            )
        if admission_result.outcome is not ScenarioGenerationAdmissionOutcome.ADMIT:
            raise ScenarioContractError("Scenario-generation admission is BLOCK")
    except (
        ScenarioContractError,
        ResearchSafetyContractError,
        CausalGraphContractError,
        WorldStateContractError,
        CriticalNodeContractError,
    ) as exc:
        return _with_guard(
            base,
            _guard("scenario_generation_admission_frozen", False, str(exc)),
            reason="S7-SCS1 Scenario-generation admission prerequisite was not satisfied",
        )

    return _with_guard(
        base,
        _guard(
            "scenario_generation_admission_frozen",
            True,
            (
                "exact S6 lineage and unresolved constraints are preserved; "
                "Research Safety admits read-only Scenario generation"
            ),
        ),
        reason="S7-SCS1 Scenario-generation admission prerequisite was not satisfied",
    )


def transition_s7_scs1(
    position: CaseRuntimePosition,
    target: RuntimeState,
    *,
    world_state: WorldStateSnapshot | None = None,
    causal_graph: CausalGraph | None = None,
    detection: CriticalNodeDetection | None = None,
    review_plan: CriticalReviewPlan | None = None,
    research_safety_admission: ResearchSafetyAdmission | None = None,
    research_safety_result: ResearchSafetyResult | None = None,
    admission_packet: ScenarioGenerationAdmissionPacket | None = None,
    admission_result: ScenarioGenerationAdmissionResult | None = None,
) -> TransitionResult:
    decision = can_s7_scs1_transition(
        position,
        target,
        world_state=world_state,
        causal_graph=causal_graph,
        detection=detection,
        review_plan=review_plan,
        research_safety_admission=research_safety_admission,
        research_safety_result=research_safety_result,
        admission_packet=admission_packet,
        admission_result=admission_result,
    )
    if not decision.allowed:
        raise TransitionRejected(decision)
    return TransitionResult(
        position=CaseRuntimePosition(
            mode=position.mode,
            state=target,
            case_revision=position.case_revision,
        ),
        decision=decision,
    )


def can_s7_scs3_transition(
    position: CaseRuntimePosition,
    target: RuntimeState,
    *,
    case: Case | None = None,
    controller_output: ControllerCOutputLike | None = None,
    scenario_set: ScenarioSet | None = None,
    parent_world_state: WorldStateSnapshot | None = None,
    parent_causal_graph: CausalGraph | None = None,
    parent_actor_states: tuple[ActorStateSnapshot, ...] = (),
    qualification: QualificationGate | None = None,
    routes: tuple[ScenarioDomainRerunRoute, ...] = (),
    safety_admission: ResimulationSafetyAdmission | None = None,
    safety_result: ResimulationSafetyResult | None = None,
    plan: ScenarioResimulationPlan | None = None,
) -> TransitionDecision:
    """Authorize only SCENARIO_GENERATION -> SCENARIO_RESIMULATION."""
    base = can_transition(
        position,
        target,
        authorized_future_transitions=S7_SCS3_TRANSITIONS,
    )
    if not base.allowed:
        return base

    required = (
        case,
        controller_output,
        scenario_set,
        parent_world_state,
        parent_causal_graph,
        qualification,
        safety_admission,
        safety_result,
        plan,
    )
    if any(item is None for item in required) or not parent_actor_states:
        return _with_guard(
            base,
            _guard(
                "scenario_resimulation_plan_frozen",
                None,
                (
                    "exact Controller C, Scenario, parent state, Safety, routing, "
                    "and plan are required"
                ),
            ),
            reason="S7-SCS3 re-simulation prerequisite was not satisfied",
        )

    assert case is not None
    assert controller_output is not None
    assert scenario_set is not None
    assert parent_world_state is not None
    assert parent_causal_graph is not None
    assert qualification is not None
    assert safety_admission is not None
    assert safety_result is not None
    assert plan is not None

    try:
        assert_scenario_resimulation_plan_binding(
            plan=plan,
            case=case,
            position=position,
            controller_output=controller_output,
            scenario_set=scenario_set,
            parent_world_state=parent_world_state,
            parent_causal_graph=parent_causal_graph,
            parent_actor_states=parent_actor_states,
            qualification=qualification,
            routes=routes,
            safety_admission=safety_admission,
            safety_result=safety_result,
        )
        if not plan.routing_complete:
            raise ScenarioResimulationError(
                "affected-domain Capability Gap keeps re-simulation fail closed"
            )
        if safety_result.outcome is not ResimulationSafetyOutcome.PASS:
            raise ScenarioResimulationError("Scenario re-simulation Safety outcome is BLOCK")
        if plan.case_revision != position.case_revision:
            raise ScenarioResimulationError("re-simulation plan Case revision mismatch")
        if plan.protocol_version != base.protocol_version:
            raise ScenarioResimulationError("re-simulation plan protocol mismatch")
    except (ValueError, PermissionError, KeyError) as exc:
        return _with_guard(
            base,
            _guard("scenario_resimulation_plan_frozen", False, str(exc)),
            reason="S7-SCS3 re-simulation prerequisite was not satisfied",
        )

    return _with_guard(
        base,
        _guard(
            "scenario_resimulation_plan_frozen",
            True,
            (
                "qualified affected-domain rerun plan is frozen, exact Scenario lineage is bound, "
                "and Research Safety admits read-only re-simulation"
            ),
        ),
        reason="S7-SCS3 re-simulation prerequisite was not satisfied",
    )


def transition_s7_scs3(
    position: CaseRuntimePosition,
    target: RuntimeState,
    *,
    case: Case | None = None,
    controller_output: ControllerCOutputLike | None = None,
    scenario_set: ScenarioSet | None = None,
    parent_world_state: WorldStateSnapshot | None = None,
    parent_causal_graph: CausalGraph | None = None,
    parent_actor_states: tuple[ActorStateSnapshot, ...] = (),
    qualification: QualificationGate | None = None,
    routes: tuple[ScenarioDomainRerunRoute, ...] = (),
    safety_admission: ResimulationSafetyAdmission | None = None,
    safety_result: ResimulationSafetyResult | None = None,
    plan: ScenarioResimulationPlan | None = None,
) -> TransitionResult:
    decision = can_s7_scs3_transition(
        position,
        target,
        case=case,
        controller_output=controller_output,
        scenario_set=scenario_set,
        parent_world_state=parent_world_state,
        parent_causal_graph=parent_causal_graph,
        parent_actor_states=parent_actor_states,
        qualification=qualification,
        routes=routes,
        safety_admission=safety_admission,
        safety_result=safety_result,
        plan=plan,
    )
    if not decision.allowed:
        raise TransitionRejected(decision)
    return TransitionResult(
        position=CaseRuntimePosition(
            mode=position.mode,
            state=target,
            case_revision=position.case_revision,
        ),
        decision=decision,
    )
