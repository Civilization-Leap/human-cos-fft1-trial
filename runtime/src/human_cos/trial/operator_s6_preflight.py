"""Content-only preflight for the five-fixture SBX7 S6 engineering slice."""

from __future__ import annotations

from dataclasses import dataclass

from human_cos.controllers import InitialFramingContent
from human_cos.domains import DomainOutputContent, get_domain_descriptor
from human_cos.models import ModelIdentity, ModelRegistry, QualificationGate
from human_cos.runtime.tool_policy import ToolPolicy

from . import operator_environment as environment
from . import operator_s5 as s5
from .contracts import TrialMockOutputFixture
from .operator_bundle import VerifiedOperatorBundle, _json_object
from .operator_s6_assembly import ControllerBFixtureContent, CrossExamFixtureContent

_ERROR = "operator S6 slice rejected"
S5_FIXTURES = ("s5-framing-a1", "s5-framing-a2", "s5-domain")
S6_FIXTURES = ("s6-cross-exam", "s6-controller-b")
ALL_FIXTURES = S5_FIXTURES + S6_FIXTURES


class OperatorS6SliceError(ValueError):
    pass


def require(condition: bool) -> None:
    if not condition:
        raise OperatorS6SliceError(_ERROR)


@dataclass(frozen=True)
class Inputs:
    bundle: VerifiedOperatorBundle
    s5_inputs: s5._S5Inputs
    reviewer: TrialMockOutputFixture
    controller: TrialMockOutputFixture
    reviewer_content: CrossExamFixtureContent
    controller_content: ControllerBFixtureContent


def _identity(fixture: TrialMockOutputFixture) -> ModelIdentity:
    return ModelIdentity(
        provider="mock", model_id=fixture.model_id, model_family=fixture.model_family
    )


def preflight(bundle: VerifiedOperatorBundle) -> Inputs:
    """No model invocation, files, Docker or database access."""
    try:
        environment._approved_binding(bundle)
        execution = bundle.execution_inputs
        case = execution.case
        require(case.revision == 1 and bool(case.domains) and len(case.domains or ()) == 1)
        require(bool(case.actors) and not execution.expert_fixtures)
        assert case.domains is not None
        get_domain_descriptor(case.domains[0])
        by_id = {item.fixture_id: item for item in execution.mock_outputs}
        require(len(by_id) == len(execution.mock_outputs) and set(by_id) == set(ALL_FIXTURES))
        fixtures = tuple(by_id[key] for key in ALL_FIXTURES)
        require(len({item.run_id for item in fixtures}) == 5)
        require(len({item.model_id for item in fixtures}) == 5)
        registry = ModelRegistry(list(execution.model_profiles))
        qualification = QualificationGate(registry)
        evidence_ids = {item.evidence_id for item in execution.evidence}
        reviewer_content = None
        controller_content = None
        for index, fixture in enumerate(fixtures):
            fixture.assert_integrity()
            registry.assert_identity(_identity(fixture))
            document = _json_object(fixture.output_text.encode())
            if index < 2:
                qualification.assert_controller_eligible(fixture.model_id)
                InitialFramingContent.model_validate(document)
            elif index == 2:
                qualification.assert_domain_eligible(
                    fixture.model_id, case.domains[0], "mechanism_analysis"
                )
                domain = DomainOutputContent.model_validate(document)
                require(bool(domain.mechanisms) and set(domain.facts_used) <= evidence_ids)
            elif index == 3:
                qualification.assert_challenger_eligible(fixture.model_id)
                reviewer_content = CrossExamFixtureContent.model_validate(document)
            else:
                qualification.assert_controller_eligible(fixture.model_id)
                controller_content = ControllerBFixtureContent.model_validate(document)
                require(bool(controller_content.integrated_mechanisms))
                require(controller_content.preserve_all_dissent)
        require(reviewer_content is not None and controller_content is not None)
        assert reviewer_content is not None
        assert controller_content is not None
        limits = bundle.manifest.resource_limits
        output_bytes = sum(len(item.output_text.encode()) for item in fixtures)
        require(limits.max_model_calls >= 3 and limits.max_stage_calls >= 12)
        # Fixed prefix reservation plus variable Evidence and ActorState records.
        # The assembler freezes one ActorState for every Case actor.
        actor_count = len(case.actors or ())
        require(limits.max_frozen_artifacts >= 96 + len(execution.evidence) + actor_count)
        require(output_bytes <= min(limits.max_output_bytes, limits.max_output_tokens))
        return Inputs(
            bundle=bundle,
            s5_inputs=s5._S5Inputs(
                bundle=bundle,
                fixtures=fixtures[:3],
                registry=registry,
                qualification=qualification,
                tool_policy=ToolPolicy(()),
            ),
            reviewer=fixtures[3],
            controller=fixtures[4],
            reviewer_content=reviewer_content,
            controller_content=controller_content,
        )
    except Exception:
        raise OperatorS6SliceError(_ERROR) from None
