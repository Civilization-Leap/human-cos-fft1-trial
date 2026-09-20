"""S2-L qualification enforcement and Capability Gap generation.

Qualification evidence/status is supplied by approved profile records. This
module deliberately contains no automatic qualification scoring or thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from human_cos.models.errors import CapabilityGapError, EligibilityError
from human_cos.models.profile import DomainCapability, DomainTaskType, ModelProfile
from human_cos.models.registry import ModelRegistry


@dataclass(frozen=True)
class EligibilityDecision:
    allowed: bool
    reason: str


@dataclass(frozen=True)
class CapabilityGap:
    capability_gap_id: str
    model_id: str
    domain: str
    task_type: DomainTaskType
    why_required: str
    impact_if_missing: str
    resolution: tuple[str, ...] = (
        "new_model",
        "expert",
        "tool",
        "more_evidence",
        "preserve_unknown",
    )
    status: str = "OPEN"


class QualificationGate:
    def __init__(self, registry: ModelRegistry) -> None:
        self._registry = registry

    def controller_decision(self, model_id: str) -> EligibilityDecision:
        profile = self._registry.get(model_id)
        if profile.status != "QUALIFIED":
            return EligibilityDecision(False, f"model status is {profile.status}, not QUALIFIED")
        if not profile.role_eligibility.meta_controller:
            return EligibilityDecision(False, "meta_controller role is not eligible")
        if profile.controller_qualification is None:
            return EligibilityDecision(False, "controller qualification record is absent")
        return EligibilityDecision(True, "qualified controller role explicitly recorded")

    def assert_controller_eligible(self, model_id: str) -> ModelProfile:
        decision = self.controller_decision(model_id)
        if not decision.allowed:
            raise EligibilityError(f"{model_id}: {decision.reason}")
        return self._registry.get(model_id)

    def challenger_decision(self, model_id: str) -> EligibilityDecision:
        profile = self._registry.get(model_id)
        if profile.status != "QUALIFIED":
            return EligibilityDecision(False, f"model status is {profile.status}, not QUALIFIED")
        if not profile.role_eligibility.challenger:
            return EligibilityDecision(False, "challenger role is not eligible")
        return EligibilityDecision(True, "qualified Challenger role explicitly recorded")

    def assert_challenger_eligible(self, model_id: str) -> ModelProfile:
        decision = self.challenger_decision(model_id)
        if not decision.allowed:
            raise EligibilityError(f"{model_id}: {decision.reason}")
        return self._registry.get(model_id)

    def evaluator_decision(self, model_id: str) -> EligibilityDecision:
        profile = self._registry.get(model_id)
        if profile.status != "QUALIFIED":
            return EligibilityDecision(False, f"model status is {profile.status}, not QUALIFIED")
        if not profile.role_eligibility.evaluator:
            return EligibilityDecision(False, "evaluator role is not eligible")
        return EligibilityDecision(True, "qualified Evaluator role explicitly recorded")

    def assert_evaluator_eligible(self, model_id: str) -> ModelProfile:
        decision = self.evaluator_decision(model_id)
        if not decision.allowed:
            raise EligibilityError(f"{model_id}: {decision.reason}")
        return self._registry.get(model_id)

    @staticmethod
    def _matching_domain_capabilities(
        profile: ModelProfile,
        domain: str,
        task_type: DomainTaskType,
    ) -> tuple[DomainCapability, ...]:
        return tuple(
            capability
            for capability in profile.domain_capabilities
            if capability.domain == domain and capability.task_type == task_type
        )

    def domain_decision(
        self,
        model_id: str,
        domain: str,
        task_type: DomainTaskType,
    ) -> EligibilityDecision:
        profile = self._registry.get(model_id)
        if profile.status != "QUALIFIED":
            return EligibilityDecision(False, f"model status is {profile.status}, not QUALIFIED")
        if domain not in profile.role_eligibility.domain_worker:
            return EligibilityDecision(False, f"domain {domain!r} is not in role eligibility")
        matches = self._matching_domain_capabilities(profile, domain, task_type)
        if not matches:
            return EligibilityDecision(False, "no matching domain/task capability record")
        if len(matches) > 1:
            return EligibilityDecision(
                False,
                "ambiguous duplicate domain/task capability records; qualification denied",
            )
        capability = matches[0]
        if capability.eligibility != "QUALIFIED":
            return EligibilityDecision(
                False,
                f"domain capability status is {capability.eligibility}, not QUALIFIED",
            )
        return EligibilityDecision(True, "qualified domain/task capability explicitly recorded")

    def capability_gap(
        self,
        model_id: str,
        domain: str,
        task_type: DomainTaskType,
        *,
        why_required: str = "restricted Human-COS domain task requires explicit qualification",
        impact_if_missing: str = (
            "result must pause or preserve unknown; role-play fallback forbidden"
        ),
    ) -> CapabilityGap:
        return CapabilityGap(
            capability_gap_id=f"gap:{model_id}:{domain}:{task_type}",
            model_id=model_id,
            domain=domain,
            task_type=task_type,
            why_required=why_required,
            impact_if_missing=impact_if_missing,
        )

    def assert_domain_eligible(
        self,
        model_id: str,
        domain: str,
        task_type: DomainTaskType,
    ) -> ModelProfile:
        decision = self.domain_decision(model_id, domain, task_type)
        if not decision.allowed:
            gap = self.capability_gap(model_id, domain, task_type)
            raise CapabilityGapError(f"{model_id}: {decision.reason}", gap)
        return self._registry.get(model_id)


RestrictedRole = Literal["meta_controller", "domain_worker", "challenger", "evaluator"]


@dataclass(frozen=True)
class EligibilityRequirement:
    role: RestrictedRole
    domain: str | None = None
    task_type: DomainTaskType | None = None


def assert_requirement(
    gate: QualificationGate,
    model_id: str,
    requirement: EligibilityRequirement,
) -> ModelProfile:
    if requirement.role == "meta_controller":
        return gate.assert_controller_eligible(model_id)
    if requirement.role == "challenger":
        return gate.assert_challenger_eligible(model_id)
    if requirement.role == "evaluator":
        return gate.assert_evaluator_eligible(model_id)
    if requirement.domain is None or requirement.task_type is None:
        raise ValueError("domain_worker requirement needs domain and task_type")
    return gate.assert_domain_eligible(model_id, requirement.domain, requirement.task_type)
