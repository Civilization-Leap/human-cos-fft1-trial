"""S7-SCS3 public integration gate for deterministic AT-17 revision closure."""

from __future__ import annotations

from datetime import datetime

from human_cos.models import QualificationGate
from human_cos.safety.resimulation import ResimulationSafetyAdmission, ResimulationSafetyResult
from human_cos.world import ActorStateSnapshot, CausalGraph, WorldStateSnapshot

from .contracts import ScenarioSet
from .resimulation import (
    ControllerCOutputLike,
    ScenarioDomainRerunOutput,
    ScenarioDomainRerunRoute,
    ScenarioResimulationArtifacts,
    ScenarioResimulationError,
    ScenarioResimulationPlan,
    assert_scenario_domain_rerun_route_binding,
    assert_scenario_rerun_output_set,
)
from .resimulation import (
    integrate_scenario_resimulation as _assemble_scenario_resimulation,
)


def _canonical_routes(
    *,
    plan: ScenarioResimulationPlan,
    routes: tuple[ScenarioDomainRerunRoute, ...],
) -> tuple[ScenarioDomainRerunRoute, ...]:
    """Require the complete plan route set and return it in frozen task order."""
    plan.assert_integrity()
    if not plan.routing_complete:
        raise ScenarioResimulationError(
            "Capability Gap prevents SCS3 integration from admitting a route set"
        )

    expected_by_task = {
        entry.task_hash: entry.route_hash
        for entry in plan.routing_entries
        if entry.route_hash is not None
    }
    if len(expected_by_task) != len(plan.rerun_tasks):
        raise ScenarioResimulationError("SCS3 plan does not contain one qualified route per task")

    route_by_hash: dict[str, ScenarioDomainRerunRoute] = {}
    for route in routes:
        route.assert_integrity()
        if route.route_hash in route_by_hash:
            raise ScenarioResimulationError("SCS3 integration routes must be unique")
        route_by_hash[route.route_hash] = route

    expected_hashes = set(expected_by_task.values())
    if set(route_by_hash) != expected_hashes:
        raise ScenarioResimulationError(
            "SCS3 integration route set must exactly equal the frozen plan route set"
        )

    canonical: list[ScenarioDomainRerunRoute] = []
    for task in plan.rerun_tasks:
        route_hash = expected_by_task.get(task.task_hash)
        if route_hash is None:
            raise ScenarioResimulationError("SCS3 plan task is missing its qualified route")
        route = route_by_hash[route_hash]
        assert_scenario_domain_rerun_route_binding(task=task, route=route)
        canonical.append(route)
    return tuple(canonical)


def _canonical_outputs(
    *,
    plan: ScenarioResimulationPlan,
    routes: tuple[ScenarioDomainRerunRoute, ...],
    outputs: tuple[ScenarioDomainRerunOutput, ...],
) -> tuple[ScenarioDomainRerunOutput, ...]:
    """Require one output per frozen task/route and return outputs in task order."""
    expected_route_by_task = {route.task_hash: route.route_hash for route in routes}
    output_by_task: dict[str, ScenarioDomainRerunOutput] = {}
    output_hashes: set[str] = set()
    for output in outputs:
        output.assert_integrity()
        if output.task_hash in output_by_task or output.output_hash in output_hashes:
            raise ScenarioResimulationError("SCS3 integration outputs must be unique per task")
        expected_route_hash = expected_route_by_task.get(output.task_hash)
        if expected_route_hash is None or output.route_hash != expected_route_hash:
            raise ScenarioResimulationError(
                "SCS3 integration output does not bind the frozen task/route pair"
            )
        output_by_task[output.task_hash] = output
        output_hashes.add(output.output_hash)

    expected_tasks = tuple(task.task_hash for task in plan.rerun_tasks)
    if set(output_by_task) != set(expected_tasks):
        raise ScenarioResimulationError(
            "SCS3 integration outputs must exactly cover every frozen rerun task"
        )
    canonical = tuple(output_by_task[task_hash] for task_hash in expected_tasks)
    assert_scenario_rerun_output_set(plan=plan, routes=routes, outputs=canonical)
    return canonical


def _revalidate_executed_models(
    *,
    qualification: QualificationGate,
    routes: tuple[ScenarioDomainRerunRoute, ...],
    outputs: tuple[ScenarioDomainRerunOutput, ...],
) -> None:
    """Re-check both routed and actual/fallback identities before AT-17 integration."""
    for route, output in zip(routes, outputs, strict=True):
        routed_profile = qualification.assert_domain_eligible(
            route.model_id,
            route.domain_id,
            route.domain_task_type,
        )
        if routed_profile.model_id != output.routed_model_id:
            raise ScenarioResimulationError("SCS3 output routed identity differs from route")

        actual_profile = qualification.assert_domain_eligible(
            output.actual_model_id,
            output.domain_id,
            output.domain_task_type,
        )
        if (actual_profile.model_family, actual_profile.provider) != (
            output.model_family,
            output.provider,
        ):
            raise ScenarioResimulationError(
                "SCS3 output actual model family/provider differs from qualified registry identity"
            )


def _canonical_parent_actor_states(
    *,
    parent_world_state: WorldStateSnapshot,
    parent_actor_states: tuple[ActorStateSnapshot, ...],
) -> tuple[ActorStateSnapshot, ...]:
    """Make parent ActorState ordering follow the immutable WorldState hash order."""
    by_hash = {actor.state_hash: actor for actor in parent_actor_states}
    if len(by_hash) != len(parent_actor_states):
        raise ScenarioResimulationError("SCS3 parent ActorState inputs must be unique")
    if set(by_hash) != set(parent_world_state.actor_state_hashes):
        raise ScenarioResimulationError(
            "SCS3 parent ActorState set must exactly cover the parent WorldState"
        )
    return tuple(by_hash[state_hash] for state_hash in parent_world_state.actor_state_hashes)


def integrate_scenario_resimulation(
    *,
    plan: ScenarioResimulationPlan,
    controller_output: ControllerCOutputLike,
    scenario_set: ScenarioSet,
    parent_world_state: WorldStateSnapshot,
    parent_causal_graph: CausalGraph,
    parent_actor_states: tuple[ActorStateSnapshot, ...],
    qualification: QualificationGate,
    routes: tuple[ScenarioDomainRerunRoute, ...],
    outputs: tuple[ScenarioDomainRerunOutput, ...],
    safety_admission: ResimulationSafetyAdmission,
    safety_result: ResimulationSafetyResult,
    result_id: str,
    at17_evidence_id: str,
    frozen_at: datetime,
) -> ScenarioResimulationArtifacts:
    """Canonical public SCS3 gate before append-only revision assembly and AT-17."""
    canonical_routes = _canonical_routes(plan=plan, routes=routes)
    canonical_outputs = _canonical_outputs(
        plan=plan,
        routes=canonical_routes,
        outputs=outputs,
    )
    _revalidate_executed_models(
        qualification=qualification,
        routes=canonical_routes,
        outputs=canonical_outputs,
    )
    canonical_parent_actor_states = _canonical_parent_actor_states(
        parent_world_state=parent_world_state,
        parent_actor_states=parent_actor_states,
    )
    return _assemble_scenario_resimulation(
        plan=plan,
        controller_output=controller_output,
        scenario_set=scenario_set,
        parent_world_state=parent_world_state,
        parent_causal_graph=parent_causal_graph,
        parent_actor_states=canonical_parent_actor_states,
        qualification=qualification,
        routes=canonical_routes,
        outputs=canonical_outputs,
        safety_admission=safety_admission,
        safety_result=safety_result,
        result_id=result_id,
        at17_evidence_id=at17_evidence_id,
        frozen_at=frozen_at,
    )
