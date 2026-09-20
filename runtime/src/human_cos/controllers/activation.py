"""S5-CDE exact common-graph activation through authorized CDE3 Domain output."""

from __future__ import annotations

from human_cos.domains import (
    DomainContractError,
    DomainOutputRecord,
    DomainRoute,
    DomainRoutingPlan,
    DomainTask,
    assert_domain_output_set,
    assert_domain_routing_plan_binding,
)
from human_cos.runtime.state_machine import (
    CaseMode,
    CaseRuntimePosition,
    GuardCheck,
    GuardFacts,
    GuardStatus,
    RuntimeState,
    TransitionDecision,
    TransitionKey,
    TransitionRejected,
    TransitionResult,
    TransitionStatus,
    can_transition,
)

from .framing import FramingIntegrityError, FramingRequirement, InitialFramingRecord
from .review import FramingReview, assert_framing_review_binding

_S5_COMMON_MODES = (
    CaseMode.LIVE_FORESIGHT,
    CaseMode.MECHANISM_BENCHMARK,
    CaseMode.SCENARIO_STRESS_TEST,
)

S5_CDE2_TRANSITIONS: frozenset[TransitionKey] = frozenset(
    {
        *(
            TransitionKey(
                mode,
                RuntimeState.BOUNDARY_AND_POLICY_FROZEN,
                RuntimeState.FRAMING_INDEPENDENT,
            )
            for mode in _S5_COMMON_MODES
        ),
        *(
            TransitionKey(
                mode,
                RuntimeState.FRAMING_INDEPENDENT,
                RuntimeState.FRAMING_REVIEWED,
            )
            for mode in _S5_COMMON_MODES
        ),
    }
)

S5_CDE3_TRANSITIONS: frozenset[TransitionKey] = frozenset(
    {
        *S5_CDE2_TRANSITIONS,
        *(
            TransitionKey(mode, RuntimeState.FRAMING_REVIEWED, RuntimeState.DOMAIN_ROUTED)
            for mode in _S5_COMMON_MODES
        ),
        *(
            TransitionKey(
                mode,
                RuntimeState.DOMAIN_ROUTED,
                RuntimeState.DOMAIN_INDEPENDENT_RUN,
            )
            for mode in _S5_COMMON_MODES
        ),
        *(
            TransitionKey(
                mode,
                RuntimeState.DOMAIN_INDEPENDENT_RUN,
                RuntimeState.DOMAIN_OUTPUT_FROZEN,
            )
            for mode in _S5_COMMON_MODES
        ),
    }
)


def _guard(name: str, passed: bool | None, reason: str) -> GuardCheck:
    if passed is None:
        return GuardCheck(name, GuardStatus.UNAVAILABLE, reason)
    if passed:
        return GuardCheck(name, GuardStatus.PASS, reason)
    return GuardCheck(name, GuardStatus.FAIL, reason)


def _decision_with_guard(base: TransitionDecision, guard: GuardCheck) -> TransitionDecision:
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
        reason="S5-CDE prerequisite was not satisfied",
    )


def _requirement_guard(
    position: CaseRuntimePosition,
    protocol_version: str,
    requirement: FramingRequirement | None,
) -> GuardCheck:
    if requirement is None:
        return _guard(
            "framing_requirement_frozen",
            None,
            "FramingRequirement was not supplied",
        )
    try:
        requirement.assert_integrity()
    except FramingIntegrityError as exc:
        return _guard("framing_requirement_frozen", False, str(exc))
    if requirement.case_revision != position.case_revision:
        return _guard(
            "framing_requirement_frozen",
            False,
            "FramingRequirement Case revision does not match runtime position",
        )
    if requirement.protocol_version != protocol_version:
        return _guard(
            "framing_requirement_frozen",
            False,
            "FramingRequirement protocol version does not match runtime protocol",
        )
    return _guard(
        "framing_requirement_frozen",
        True,
        "FramingRequirement is immutable and bound to this Case revision/protocol",
    )


def _review_guard(
    position: CaseRuntimePosition,
    requirement: FramingRequirement | None,
    records: tuple[InitialFramingRecord, ...],
    review: FramingReview | None,
) -> GuardCheck:
    if requirement is None or review is None:
        return _guard(
            "framing_review_frozen",
            None,
            "FramingRequirement and FramingReview are required before FRAMING_REVIEWED",
        )
    try:
        assert_framing_review_binding(
            review=review,
            requirement=requirement,
            records=records,
        )
    except (FramingIntegrityError, RuntimeError) as exc:
        return _guard("framing_review_frozen", False, str(exc))
    if review.case_revision != position.case_revision:
        return _guard(
            "framing_review_frozen",
            False,
            "FramingReview Case revision does not match runtime position",
        )
    return _guard(
        "framing_review_frozen",
        True,
        "FramingReview preserves exact independent A1/A2 sources and satisfies AT-12",
    )


def can_s5_cde2_transition(
    position: CaseRuntimePosition,
    target: RuntimeState,
    *,
    requirement: FramingRequirement | None = None,
    records: tuple[InitialFramingRecord, ...] = (),
    review: FramingReview | None = None,
) -> TransitionDecision:
    """Authorize only the two formally granted common-graph edges through review."""
    base = can_transition(
        position,
        target,
        authorized_future_transitions=S5_CDE2_TRANSITIONS,
    )
    if not base.allowed:
        return base

    requirement_guard = _requirement_guard(
        position,
        base.protocol_version,
        requirement,
    )
    checked = _decision_with_guard(base, requirement_guard)
    if not checked.allowed:
        return checked

    if target is RuntimeState.FRAMING_REVIEWED:
        return _decision_with_guard(
            checked,
            _review_guard(position, requirement, records, review),
        )
    return checked


def transition_s5_cde2(
    position: CaseRuntimePosition,
    target: RuntimeState,
    *,
    requirement: FramingRequirement | None = None,
    records: tuple[InitialFramingRecord, ...] = (),
    review: FramingReview | None = None,
) -> TransitionResult:
    decision = can_s5_cde2_transition(
        position,
        target,
        requirement=requirement,
        records=records,
        review=review,
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


def _domain_review_guard(
    position: CaseRuntimePosition,
    protocol_version: str,
    review: FramingReview | None,
) -> GuardCheck:
    if review is None:
        return _guard("domain_review_binding", None, "FramingReview was not supplied")
    try:
        review.assert_integrity()
    except FramingIntegrityError as exc:
        return _guard("domain_review_binding", False, str(exc))
    if (
        review.case_revision != position.case_revision
        or review.protocol_version != protocol_version
    ):
        return _guard(
            "domain_review_binding",
            False,
            "FramingReview Case revision/protocol does not match Domain runtime position",
        )
    return _guard(
        "domain_review_binding",
        True,
        "Domain routing remains hash-bound to the frozen FramingReview",
    )


def _routing_guard(
    *,
    review: FramingReview | None,
    plan: DomainRoutingPlan | None,
    tasks: tuple[DomainTask, ...],
    routes: tuple[DomainRoute, ...],
) -> GuardCheck:
    if review is None or plan is None:
        return _guard(
            "domain_routing_complete",
            None,
            "FramingReview and DomainRoutingPlan are required",
        )
    if (plan.case_id, plan.case_revision, plan.protocol_version) != (
        review.case_id,
        review.case_revision,
        review.protocol_version,
    ):
        return _guard(
            "domain_routing_complete",
            False,
            "DomainRoutingPlan Case/protocol does not match FramingReview",
        )
    try:
        assert_domain_routing_plan_binding(
            plan=plan,
            tasks=tasks,
            routes=routes,
            framing_review_hash=review.review_hash,
        )
    except DomainContractError as exc:
        return _guard("domain_routing_complete", False, str(exc))
    if not plan.routing_complete:
        return _guard(
            "domain_routing_complete",
            False,
            "unresolved Capability Gap prevents required Domain routing",
        )
    return _guard(
        "domain_routing_complete",
        True,
        "all required Domain tasks have explicit qualified routes",
    )


def _output_set_complete(
    *,
    plan: DomainRoutingPlan | None,
    tasks: tuple[DomainTask, ...],
    routes: tuple[DomainRoute, ...],
    outputs: tuple[DomainOutputRecord, ...],
) -> bool:
    if plan is None:
        return False
    try:
        assert_domain_output_set(plan=plan, tasks=tasks, routes=routes, outputs=outputs)
    except DomainContractError:
        return False
    return True


def _output_guard(
    *,
    plan: DomainRoutingPlan | None,
    tasks: tuple[DomainTask, ...],
    routes: tuple[DomainRoute, ...],
    outputs: tuple[DomainOutputRecord, ...],
) -> GuardCheck:
    if plan is None:
        return _guard("domain_output_set_frozen", None, "DomainRoutingPlan was not supplied")
    try:
        assert_domain_output_set(plan=plan, tasks=tasks, routes=routes, outputs=outputs)
    except DomainContractError as exc:
        return _guard("domain_output_set_frozen", False, str(exc))
    return _guard(
        "domain_output_set_frozen",
        True,
        "each required qualified Domain route has exactly one immutable frozen output",
    )


def can_s5_cde3_transition(
    position: CaseRuntimePosition,
    target: RuntimeState,
    *,
    requirement: FramingRequirement | None = None,
    records: tuple[InitialFramingRecord, ...] = (),
    review: FramingReview | None = None,
    plan: DomainRoutingPlan | None = None,
    tasks: tuple[DomainTask, ...] = (),
    routes: tuple[DomainRoute, ...] = (),
    outputs: tuple[DomainOutputRecord, ...] = (),
    no_unresolved_protocol_invalid: bool | None = None,
) -> TransitionDecision:
    """Authorize the exact five CDE edges and stop at DOMAIN_OUTPUT_FROZEN."""
    if target in {RuntimeState.FRAMING_INDEPENDENT, RuntimeState.FRAMING_REVIEWED}:
        return can_s5_cde2_transition(
            position,
            target,
            requirement=requirement,
            records=records,
            review=review,
        )

    output_complete = _output_set_complete(
        plan=plan,
        tasks=tasks,
        routes=routes,
        outputs=outputs,
    )
    base = can_transition(
        position,
        target,
        guard_facts=GuardFacts(
            all_required_runs_finished=output_complete,
            no_unresolved_protocol_invalid=no_unresolved_protocol_invalid,
        ),
        authorized_future_transitions=S5_CDE3_TRANSITIONS,
    )
    if not base.allowed:
        return base

    checked = _decision_with_guard(
        base,
        _domain_review_guard(position, base.protocol_version, review),
    )
    if not checked.allowed:
        return checked
    checked = _decision_with_guard(
        checked,
        _routing_guard(review=review, plan=plan, tasks=tasks, routes=routes),
    )
    if not checked.allowed:
        return checked
    if target is RuntimeState.DOMAIN_OUTPUT_FROZEN:
        return _decision_with_guard(
            checked,
            _output_guard(plan=plan, tasks=tasks, routes=routes, outputs=outputs),
        )
    return checked


def transition_s5_cde3(
    position: CaseRuntimePosition,
    target: RuntimeState,
    *,
    requirement: FramingRequirement | None = None,
    records: tuple[InitialFramingRecord, ...] = (),
    review: FramingReview | None = None,
    plan: DomainRoutingPlan | None = None,
    tasks: tuple[DomainTask, ...] = (),
    routes: tuple[DomainRoute, ...] = (),
    outputs: tuple[DomainOutputRecord, ...] = (),
    no_unresolved_protocol_invalid: bool | None = None,
) -> TransitionResult:
    decision = can_s5_cde3_transition(
        position,
        target,
        requirement=requirement,
        records=records,
        review=review,
        plan=plan,
        tasks=tasks,
        routes=routes,
        outputs=outputs,
        no_unresolved_protocol_invalid=no_unresolved_protocol_invalid,
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
