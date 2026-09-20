"""Offline S5 payload-to-reference binding under effective V0.3.

This module derives producer expectations only from verifier-owned immutable
operator input bytes plus the current code-owned approval catalogue, then checks
caller-supplied complete S5 payloads against those host-side expectations.
Evidence revision lineage is supplied explicitly by the host and bound to the
approved input identity and Evidence snapshots; it is never inferred from the
payload under review.

It does NOT create a trusted S6 scope, touch Docker/database/files, invoke a
model, persist typed review records, or grant execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from json import JSONDecodeError
from typing import Literal

from pydantic import ValidationError

from human_cos.controllers.framing import (
    FramingIntegrityError,
    FramingRequirement,
    InitialFramingContent,
    InitialFramingRecord,
    bind_initial_framing,
)
from human_cos.controllers.review import FramingReview, assert_framing_review_binding
from human_cos.core.context import (
    AdmittedEvidence,
    ContextAdmissionRecord,
    ContextBuildError,
    ContextBuildRequest,
    build_context,
)
from human_cos.core.models import Case, ContextManifest, Evidence
from human_cos.core.visibility import visibility_basis
from human_cos.domains.contracts import (
    DomainContractError,
    DomainOutputContent,
    DomainOutputRecord,
    DomainTask,
    bind_domain_output,
)
from human_cos.domains.routing import (
    DomainRoute,
    DomainRoutingPlan,
    assert_domain_route_binding,
    assert_domain_routing_plan_binding,
)
from human_cos.integration.review_references import (
    ReviewDirectSource,
    ReviewMockIdentity,
    ReviewProducerExpectation,
    ReviewProducerReference,
    ReviewReferenceError,
)
from human_cos.models import (
    EligibilityError,
    ModelIdentity,
    ModelRegistry,
    QualificationGate,
    RegistryError,
)
from human_cos.runtime.run import (
    RawOutputRecord,
    RunIndependence,
    RunManifest,
    canonical_document_sha256,
    structured_output_sha256,
)

from . import operator_admission as admission
from .contracts import TrialContractError
from .operator_bundle import OperatorBundleError, VerifiedOperatorBundle, _json_object
from .operator_contracts import OperatorAdmissionError, OperatorApprovalStatus

_ERROR = "operator S5 source binding rejected"
_EXPECTED_FIXTURES = ("s5-framing-a1", "s5-framing-a2", "s5-domain")
_EXPECTED_LANES: tuple[Literal["A1", "A2", "DOMAIN"], ...] = ("A1", "A2", "DOMAIN")


class OperatorReviewSourceReason(str, Enum):
    """Bounded local rejection diagnostics, not admission or publication authority."""

    CONSTRAINT_MISMATCH = "CONSTRAINT_MISMATCH"
    NOT_APPROVED = "NOT_APPROVED"
    DECLARED_DEPENDENCY_REJECTION = "DECLARED_DEPENDENCY_REJECTION"
    A1_CONTENT_MISMATCH = "A1_CONTENT_MISMATCH"
    A2_CONTENT_MISMATCH = "A2_CONTENT_MISMATCH"
    DOMAIN_CONTENT_MISMATCH = "DOMAIN_CONTENT_MISMATCH"


class OperatorReviewSourceError(ValueError):
    """Expected rejection: fixed public text plus a code-owned reason."""

    def __init__(
        self,
        reason: OperatorReviewSourceReason = OperatorReviewSourceReason.CONSTRAINT_MISMATCH,
    ) -> None:
        if type(reason) is not OperatorReviewSourceReason:
            raise TypeError("invalid operator source rejection reason")
        super().__init__(_ERROR)
        self._reason = reason

    @property
    def reason(self) -> OperatorReviewSourceReason:
        """Stable code-owned diagnostic; callers may read but not rewrite it."""

        return self._reason


class OperatorReviewSourceFault(RuntimeError):
    """Unclassified failure, NEVER evidence of an expected payload rejection.

    The sanitized display suppresses upstream details, not Python's in-process
    exception context. Do not export that context or treat this as a receipt.
    """

    def __init__(self) -> None:
        super().__init__("operator S5 source binding failed unexpectedly")


# Only named rejection contracts are normalized as expected failures. Broad
# built-in ValueError/TypeError/KeyError are not on this list. A dependency may
# itself have normalized an internal fault; this layer cannot undo that loss.
_DECLARED_REJECTIONS = (
    ValidationError,
    ReviewReferenceError,
    OperatorBundleError,
    OperatorAdmissionError,
    TrialContractError,
    RegistryError,
    EligibilityError,
    FramingIntegrityError,
    DomainContractError,
    ContextBuildError,
    JSONDecodeError,
    UnicodeError,
)


def _require(
    condition: bool,
    reason: OperatorReviewSourceReason = OperatorReviewSourceReason.CONSTRAINT_MISMATCH,
) -> None:
    if not condition:
        raise OperatorReviewSourceError(reason)


@dataclass(frozen=True)
class ApprovedS5Expectations:
    """Host-side priors derived from verifier-owned approved input bytes."""

    detached_input_address: str
    case_id: str
    case_revision: int
    protocol_version: str
    approval_slot: Literal["A", "B"]
    owner_approval_reference: str
    producers: tuple[ReviewProducerExpectation, ...]


@dataclass(frozen=True)
class HostEvidenceRevisionPrior:
    """Host-supplied Evidence lineage bound to the exact approved input snapshot.

    This value carries no execution authority. The host remains responsible for
    obtaining revisions from an authoritative lineage source; the bridge only
    verifies that ids/snapshot hashes bind exactly to the approved immutable
    Evidence documents before using the revisions to reconstruct Context.
    """

    detached_input_address: str
    entries: tuple[tuple[str, int, str], ...]


def bind_host_evidence_revision_prior(
    bundle: VerifiedOperatorBundle, revisions: dict[str, int]
) -> HostEvidenceRevisionPrior:
    """Bind explicit host revision facts to approved Evidence ids and snapshots."""
    try:
        bundle.assert_integrity()
        evidence = tuple(bundle.execution_inputs.evidence)
        expected_ids = {item.evidence_id for item in evidence}
        _require(set(revisions) == expected_ids)
        entries: list[tuple[str, int, str]] = []
        for item in sorted(evidence, key=lambda value: value.evidence_id):
            revision = revisions[item.evidence_id]
            _require(type(revision) is int and revision >= 1)
            entries.append((item.evidence_id, revision, item.snapshot_hash))
        return HostEvidenceRevisionPrior(bundle.identity.detached_input_address, tuple(entries))
    except (OperatorReviewSourceError, OperatorReviewSourceFault):
        raise
    except _DECLARED_REJECTIONS:
        raise OperatorReviewSourceError(
            OperatorReviewSourceReason.DECLARED_DEPENDENCY_REJECTION
        ) from None
    except Exception:
        raise OperatorReviewSourceFault() from None


def _evidence_revision_map(
    bundle: VerifiedOperatorBundle, prior: HostEvidenceRevisionPrior
) -> dict[str, int]:
    _require(type(prior) is HostEvidenceRevisionPrior)
    _require(prior.detached_input_address == bundle.identity.detached_input_address)
    approved = {item.evidence_id: item for item in bundle.execution_inputs.evidence}
    _require(len(approved) == len(bundle.execution_inputs.evidence))
    observed: dict[str, int] = {}
    for entry in prior.entries:
        _require(type(entry) is tuple and len(entry) == 3)
        evidence_id, revision, snapshot_hash = entry
        _require(type(evidence_id) is str and evidence_id in approved)
        _require(type(revision) is int and revision >= 1)
        _require(
            type(snapshot_hash) is str and snapshot_hash == approved[evidence_id].snapshot_hash
        )
        _require(evidence_id not in observed)
        observed[evidence_id] = revision
    _require(set(observed) == set(approved))
    return observed


@dataclass(frozen=True)
class FrozenRunPayload:
    """One complete frozen Run payload plus its append-only revision number."""

    revision: int
    manifest: RunManifest


@dataclass(frozen=True)
class S5ProducerPayload:
    """Full payloads needed to validate one S5 producer edge offline."""

    run: FrozenRunPayload
    context: ContextManifest
    admission: ContextAdmissionRecord
    raw_output: RawOutputRecord


@dataclass(frozen=True)
class CompleteS5PayloadSet:
    """Complete supplied S5 material for the fixed engineering prefix."""

    requirement: FramingRequirement
    a1: InitialFramingRecord
    a2: InitialFramingRecord
    review: FramingReview
    domain_task: DomainTask
    domain_route: DomainRoute
    routing_plan: DomainRoutingPlan
    domain_output: DomainOutputRecord
    producers: tuple[S5ProducerPayload, S5ProducerPayload, S5ProducerPayload]


@dataclass(frozen=True)
class VerifiedS5ReferenceBinding:
    """Verified full supplied S5 payload linkage, still not trusted S6 scope."""

    expectations: ApprovedS5Expectations
    direct_sources: tuple[ReviewDirectSource, ReviewDirectSource]
    producers: tuple[ReviewProducerReference, ReviewProducerReference, ReviewProducerReference]
    status: Literal["FULL_S5_PAYLOAD_REFERENCE_BINDING_ONLY"] = field(
        default="FULL_S5_PAYLOAD_REFERENCE_BINDING_ONLY", init=False
    )
    input_approval_verified: Literal[True] = field(default=True, init=False)
    full_source_payloads_verified: Literal[True] = field(default=True, init=False)
    scope_origin_verified: Literal[False] = field(default=False, init=False)
    fresh_execution_verified: Literal[False] = field(default=False, init=False)
    execution_authorized: Literal[False] = field(default=False, init=False)


class _ApprovedEvidenceSource:
    def __init__(self, evidence: tuple[Evidence, ...], revisions: dict[str, int]) -> None:
        self._evidence = evidence
        self._revisions = revisions

    def list_context_evidence(
        self,
        case: Case,
        *,
        actor_id: str | None,
        role_id: str | None,
        as_of: datetime,
    ) -> tuple[AdmittedEvidence, ...]:
        result: list[AdmittedEvidence] = []
        for item in self._evidence:
            basis = visibility_basis(item.visibility, actor_id=actor_id, role_id=role_id)
            if basis is not None:
                result.append(
                    AdmittedEvidence(
                        evidence=item,
                        revision=self._revisions[item.evidence_id],
                        visibility_basis=basis,
                    )
                )
        return tuple(result)


def _identity(model_id: str, model_family: str) -> ReviewMockIdentity:
    return ReviewMockIdentity(model_id=model_id, model_family=model_family, provider="mock")


def derive_approved_s5_expectations(bundle: VerifiedOperatorBundle) -> ApprovedS5Expectations:
    """Derive A1/A2/Domain priors from approved immutable input, never runtime output."""
    try:
        bundle.assert_integrity()
        decision = admission.evaluate_operator_approval(bundle.identity)
        _require(
            decision.status is OperatorApprovalStatus.MATCHED_REQUIRES_VERIFICATION,
            OperatorReviewSourceReason.NOT_APPROVED,
        )
        _require(
            decision.approval_slot in ("A", "B") and decision.owner_approval_reference is not None
        )
        admission.assert_current_operator_decision(decision)

        inputs = bundle.execution_inputs
        case = inputs.case
        _require(case.revision == 1 and case.protocol_version == "0.1")
        _require(bool(case.domains) and len(case.domains or ()) == 1 and not inputs.expert_fixtures)

        by_fixture = {item.fixture_id: item for item in inputs.mock_outputs}
        _require(len(by_fixture) == len(inputs.mock_outputs))
        _require(set(_EXPECTED_FIXTURES) <= set(by_fixture))
        fixtures = tuple(by_fixture[key] for key in _EXPECTED_FIXTURES)
        _require(len({item.run_id for item in fixtures}) == 3)
        _require(len({item.model_id for item in fixtures}) == 3)

        profiles = {item.model_id: item for item in inputs.model_profiles}
        profile_hashes = dict(bundle.identity.profile_hashes)
        _require(set(profiles) == set(profile_hashes))
        registry = ModelRegistry(list(inputs.model_profiles))
        gate = QualificationGate(registry)

        expected: list[ReviewProducerExpectation] = []
        for lane, fixture in zip(_EXPECTED_LANES, fixtures, strict=True):
            fixture.assert_integrity()
            registry.assert_identity(ModelIdentity("mock", fixture.model_id, fixture.model_family))
            if lane == "DOMAIN":
                assert case.domains is not None
                gate.assert_domain_eligible(fixture.model_id, case.domains[0], "mechanism_analysis")
            else:
                gate.assert_controller_eligible(fixture.model_id)
            expected.append(
                ReviewProducerExpectation(
                    lane=lane,
                    run_id=fixture.run_id,
                    identity=_identity(fixture.model_id, fixture.model_family),
                    profile_sha256=profile_hashes[fixture.model_id],
                    raw_output_sha256=fixture.output_sha256,
                )
            )
        assert decision.approval_slot is not None
        assert decision.owner_approval_reference is not None
        return ApprovedS5Expectations(
            detached_input_address=bundle.identity.detached_input_address,
            case_id=case.case_id,
            case_revision=case.revision,
            protocol_version=case.protocol_version,
            approval_slot=decision.approval_slot,
            owner_approval_reference=decision.owner_approval_reference,
            producers=tuple(expected),
        )
    except (OperatorReviewSourceError, OperatorReviewSourceFault):
        raise
    except _DECLARED_REJECTIONS:
        raise OperatorReviewSourceError(
            OperatorReviewSourceReason.DECLARED_DEPENDENCY_REJECTION
        ) from None
    except Exception:
        raise OperatorReviewSourceFault() from None


def _expected_context(
    bundle: VerifiedOperatorBundle,
    expectation: ReviewProducerExpectation,
    evidence_revisions: dict[str, int],
) -> tuple[ContextManifest, ContextAdmissionRecord]:
    inputs = bundle.execution_inputs
    case = inputs.case
    lane = expectation.lane
    stage = "DOMAIN_INDEPENDENT_RUN" if lane == "DOMAIN" else "FRAMING_INDEPENDENT"
    role_id = "operator-domain" if lane == "DOMAIN" else f"operator-framing-{lane.lower()}"
    source = _ApprovedEvidenceSource(tuple(inputs.evidence), evidence_revisions)
    result = build_context(
        source,
        case,
        ContextBuildRequest(
            context_manifest_id=f"context:{expectation.run_id}",
            run_id=expectation.run_id,
            stage=stage,
            role_id=role_id,
            actor_id=None,
            model_id=expectation.identity.model_id,
            prompt_version="operator-s5-v1",
            reference_time=case.time_boundary.T0,
            tool_permissions=(),
            prior_run_ids=(),
            forbidden_scopes=(),
        ),
    )
    return result.manifest, result.admission


def _assert_run_payload(
    bundle: VerifiedOperatorBundle,
    expectation: ReviewProducerExpectation,
    payload: S5ProducerPayload,
    evidence_revisions: dict[str, int],
) -> None:
    run = payload.run.manifest
    context = payload.context
    admission_record = payload.admission
    raw = payload.raw_output
    lane = expectation.lane
    expected_context, expected_admission = _expected_context(
        bundle, expectation, evidence_revisions
    )
    expected_stage = "DOMAIN_INDEPENDENT_RUN" if lane == "DOMAIN" else "FRAMING_INDEPENDENT"
    expected_role = "domain_worker" if lane == "DOMAIN" else "meta_controller"
    _require(payload.run.revision == 3)
    _require(run.status == "FROZEN" and run.run_id == expectation.run_id)
    _require(run.case_id == bundle.execution_inputs.case.case_id)
    _require((run.stage, run.role_type) == (expected_stage, expected_role))
    _require(
        (run.model_id, run.model_family, run.provider)
        == (
            expectation.identity.model_id,
            expectation.identity.model_family,
            "mock",
        )
    )
    _require(run.protocol_version == bundle.execution_inputs.case.protocol_version)
    _require(run.prompt_version == "operator-s5-v1" and run.tool_permissions == ())
    _require(run.parent_run_id is None and run.fallback_from is None)
    _require(run.raw_output_ref == raw.output_ref and run.raw_output_hash == raw.sha256)
    _require(raw.run_id == expectation.run_id and raw.sha256 == expectation.raw_output_sha256)
    fixture = next(
        item for item in bundle.execution_inputs.mock_outputs if item.run_id == expectation.run_id
    )
    _require(raw.content == fixture.output_text.encode("utf-8"))
    _require(
        run.structured_output_hash
        == structured_output_sha256({"output_text": fixture.output_text, "finish_reason": "mock"})
    )
    _require(run.finished_at is not None and run.started_at is not None)
    _require(run.finished_at >= run.started_at)
    _require(
        run.independence
        == RunIndependence(
            context=True,
            prompt=True,
            model_family=False,
            provider=False,
            evidence_path=True,
            expert=None,
        )
    )
    _require(context == expected_context)
    _require(admission_record == expected_admission)
    _require(context.hash_sha256 == run.context_manifest_hash)
    _require(admission_record.manifest_hash == run.context_manifest_hash)


def _raise_missing_context_hash() -> str:
    raise OperatorReviewSourceError()


def verify_full_s5_payload_references(
    bundle: VerifiedOperatorBundle,
    payloads: CompleteS5PayloadSet,
    *,
    evidence_revision_prior: HostEvidenceRevisionPrior | None = None,
) -> VerifiedS5ReferenceBinding:
    """Verify supplied complete S5 payloads against approved host-side priors."""
    try:
        expected = derive_approved_s5_expectations(bundle)
        if evidence_revision_prior is None:
            # Compatibility only: pre-N-2 callers represented the clean, single-seed
            # operator rehearsal where every approved Evidence row is revision 1.
            # Revision-aware hosts must pass an explicit prior; real conformance does.
            evidence_revision_prior = bind_host_evidence_revision_prior(
                bundle, {item.evidence_id: 1 for item in bundle.execution_inputs.evidence}
            )
        evidence_revisions = _evidence_revision_map(bundle, evidence_revision_prior)
        case = bundle.execution_inputs.case
        requirement = payloads.requirement
        requirement.assert_integrity()
        _require(
            (
                requirement.case_id,
                requirement.case_revision,
                requirement.protocol_version,
                requirement.dual_framing_required,
                requirement.authority_ref,
            )
            == (
                case.case_id,
                case.revision,
                case.protocol_version,
                True,
                expected.owner_approval_reference,
            )
        )
        _require((payloads.a1.lane, payloads.a2.lane) == ("A1", "A2"))
        assert_framing_review_binding(
            review=payloads.review,
            requirement=requirement,
            records=(payloads.a1, payloads.a2),
        )

        for expectation, producer in zip(expected.producers, payloads.producers, strict=True):
            _assert_run_payload(bundle, expectation, producer, evidence_revisions)

        fixtures_by_run = {item.run_id: item for item in bundle.execution_inputs.mock_outputs}
        _require(
            payloads.a1.content
            == InitialFramingContent.model_validate(
                _json_object(fixtures_by_run[expected.producers[0].run_id].output_text.encode())
            ),
            OperatorReviewSourceReason.A1_CONTENT_MISMATCH,
        )
        _require(
            payloads.a2.content
            == InitialFramingContent.model_validate(
                _json_object(fixtures_by_run[expected.producers[1].run_id].output_text.encode())
            ),
            OperatorReviewSourceReason.A2_CONTENT_MISMATCH,
        )
        _require(
            payloads.domain_output.content
            == DomainOutputContent.model_validate(
                _json_object(fixtures_by_run[expected.producers[2].run_id].output_text.encode())
            ),
            OperatorReviewSourceReason.DOMAIN_CONTENT_MISMATCH,
        )
        a1_run, a2_run, domain_run = (item.run.manifest for item in payloads.producers)
        _require(
            payloads.a1
            == bind_initial_framing(
                case=case,
                lane="A1",
                content=payloads.a1.content,
                frozen_run=a1_run,
                context_manifest=payloads.producers[0].context,
            )
        )
        _require(
            payloads.a2
            == bind_initial_framing(
                case=case,
                lane="A2",
                content=payloads.a2.content,
                frozen_run=a2_run,
                context_manifest=payloads.producers[1].context,
            )
        )

        task = payloads.domain_task
        task.assert_integrity()
        _require(task.case_id == case.case_id and task.case_revision == case.revision)
        _require(task.protocol_version == case.protocol_version)
        _require(task.task_id == f"task:{expected.producers[2].run_id}")
        _require(task.domain_id == (case.domains or (None,))[0])
        _require(task.domain_task_type == "mechanism_analysis")
        _require(
            task.allowed_evidence_ids
            == tuple(item.evidence_id for item in bundle.execution_inputs.evidence)
        )
        _require(task.actor_scope == (case.actors or ()))
        _require(
            task.assumptions == () and task.requested_horizon == "synthetic-observation-window"
        )
        _require(task.framing_review_hash == payloads.review.review_hash)
        assert_domain_route_binding(task=task, route=payloads.domain_route)
        _require(payloads.domain_route.model_id == expected.producers[2].identity.model_id)
        assert_domain_routing_plan_binding(
            plan=payloads.routing_plan,
            tasks=(task,),
            routes=(payloads.domain_route,),
            framing_review_hash=payloads.review.review_hash,
        )
        payloads.domain_output.assert_integrity()
        rebound = bind_domain_output(
            task=task,
            route=payloads.domain_route,
            content=payloads.domain_output.content,
            frozen_run=domain_run,
            context_manifest=payloads.producers[2].context,
        )
        _require(rebound == payloads.domain_output)
        _require(
            set(payloads.domain_output.content.facts_used)
            <= set(payloads.producers[2].context.evidence_ids)
        )

        # Everything above this point validates supplied/derived material. The values
        # below are bridge-owned projections into the reference layer. A Pydantic
        # ValidationError here therefore signals an internal projection defect, not a
        # caller/dependency rejection, and must never become DECLARED_DEPENDENCY_REJECTION.
        try:
            references: list[ReviewProducerReference] = []
            records = (payloads.a1, payloads.a2, payloads.domain_output)
            for expectation, source, record in zip(
                expected.producers, payloads.producers, records, strict=True
            ):
                references.append(
                    ReviewProducerReference(
                        **expectation.to_document(),
                        record_hash=record.record_hash,
                        frozen_run_version=source.run.revision,
                        frozen_run_hash=canonical_document_sha256(
                            source.run.manifest.to_document()
                        ),
                        context_manifest_hash=(
                            source.context.hash_sha256
                            if source.context.hash_sha256 is not None
                            else _raise_missing_context_hash()
                        ),
                        context_admission_hash=source.admission.record_hash,
                        raw_output_ref=source.raw_output.output_ref,
                    )
                )
            direct_sources = (
                ReviewDirectSource(
                    kind="FRAMING", ref=f"review:{case.case_id}", sha256=payloads.review.review_hash
                ),
                ReviewDirectSource(
                    kind="DOMAIN_OUTPUT",
                    ref=f"domain:{case.case_id}",
                    sha256=payloads.domain_output.record_hash,
                ),
            )
        except ValidationError:
            raise OperatorReviewSourceFault() from None

        return VerifiedS5ReferenceBinding(
            expectations=expected,
            direct_sources=direct_sources,
            producers=(references[0], references[1], references[2]),
        )
    except (OperatorReviewSourceError, OperatorReviewSourceFault):
        raise
    except _DECLARED_REJECTIONS:
        raise OperatorReviewSourceError(
            OperatorReviewSourceReason.DECLARED_DEPENDENCY_REJECTION
        ) from None
    except Exception:
        raise OperatorReviewSourceFault() from None
