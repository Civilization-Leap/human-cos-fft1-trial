"""Input-driven S5 prefix through existing wrappers; not full SBX7 acceptance.

The host revalidates the prepared environment. Only the installed, fixed runtime
entry opens the owned database; payloads cannot select code, tools or transitions.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import psycopg
from psycopg import Connection

from human_cos.controllers import (
    FramingRequirementPayload,
    InitialFramingContent,
    InitialFramingRecord,
    bind_initial_framing,
    build_framing_review,
    freeze_framing_requirement,
    transition_s5_cde3,
)
from human_cos.domains import (
    DomainOutputContent,
    bind_domain_output,
    build_domain_routing_plan,
    build_domain_task,
    get_domain_descriptor,
    route_domain_task,
    run_qualified_domain_task,
)
from human_cos.models import (
    EligibilityRequirement,
    MockAdapter,
    ModelIdentity,
    ModelRegistry,
    QualificationGate,
)
from human_cos.runtime.run import canonical_document_sha256
from human_cos.runtime.scheduler import TrustedScheduler, WorkerTask
from human_cos.runtime.state_machine import CaseMode, CaseRuntimePosition, RuntimeState
from human_cos.runtime.tool_policy import ToolPolicy
from human_cos.storage.migrations import (
    apply_s1_migration,
    apply_s3_migration,
    apply_s4_migration,
    apply_s5_migration,
)
from human_cos.storage.repository import PostgresRepository
from human_cos.storage.s5_cde import (
    store_domain_output,
    store_domain_route,
    store_domain_routing_plan,
    store_domain_task,
    store_framing_requirement,
    store_framing_review,
    store_initial_framing,
)

from . import operator_environment as environment
from .bundle import _open_root_directory
from .contracts import TrialMockOutputFixture
from .integrated_chain import _assert_clean_database, _capture_installed_evidence
from .operator_bundle import VerifiedOperatorBundle, _json_object, verify_operator_input_bundle

_ERROR = "operator S5 assembly rejected"
_FIXTURES = ("s5-framing-a1", "s5-framing-a2", "s5-domain")
_DSN = "host=postgres dbname=human_cos_operator user=postgres connect_timeout=3"


class OperatorS5Error(ValueError):
    """Fixed-text error; raw Case, model, path and database errors stay private."""


def _require(condition: bool) -> None:
    if not condition:
        raise OperatorS5Error(_ERROR)


@dataclass(frozen=True)
class _S5Inputs:
    bundle: VerifiedOperatorBundle
    fixtures: tuple[TrialMockOutputFixture, ...]
    registry: ModelRegistry
    qualification: QualificationGate
    tool_policy: ToolPolicy


def _identity(fixture: TrialMockOutputFixture) -> ModelIdentity:
    return ModelIdentity(
        provider="mock", model_id=fixture.model_id, model_family=fixture.model_family
    )


def _preflight(bundle: VerifiedOperatorBundle) -> _S5Inputs:
    """No files, Docker, business writes or adapter calls during preflight."""
    try:
        environment._approved_binding(bundle)
        inputs = bundle.execution_inputs
        case = inputs.case
        _require(case.revision == 1 and bool(case.domains) and len(case.domains or ()) == 1)
        _require(not inputs.expert_fixtures)
        assert case.domains is not None
        get_domain_descriptor(case.domains[0])
        by_id = {item.fixture_id: item for item in inputs.mock_outputs}
        _require(len(by_id) == len(inputs.mock_outputs) and set(by_id) == set(_FIXTURES))
        fixtures = tuple(by_id[key] for key in _FIXTURES)
        _require(len({item.run_id for item in fixtures}) == 3)
        _require(len({item.model_id for item in fixtures}) == 3)
        registry = ModelRegistry(list(inputs.model_profiles))
        qualification = QualificationGate(registry)
        evidence_ids = {item.evidence_id for item in inputs.evidence}
        for index, fixture in enumerate(fixtures):
            fixture.assert_integrity()
            registry.assert_identity(_identity(fixture))
            document = _json_object(fixture.output_text.encode())
            if index < 2:
                qualification.assert_controller_eligible(fixture.model_id)
                InitialFramingContent.model_validate(document)
            else:
                qualification.assert_domain_eligible(
                    fixture.model_id, case.domains[0], "mechanism_analysis"
                )
                content = DomainOutputContent.model_validate(document)
                _require(set(content.facts_used) <= evidence_ids)
        limits = bundle.manifest.resource_limits
        # Bound calls/records before starting this fixed prefix. UTF-8 bytes are
        # an explicit conservative token reservation, not a provider token count.
        output_bytes = sum(len(item.output_text.encode()) for item in fixtures)
        _require(limits.max_model_calls >= 3 and limits.max_stage_calls >= 8)
        _require(limits.max_frozen_artifacts >= 64 + len(inputs.evidence))
        _require(output_bytes <= min(limits.max_output_bytes, limits.max_output_tokens))
        return _S5Inputs(bundle, fixtures, registry, qualification, ToolPolicy(()))
    except Exception:
        raise OperatorS5Error(_ERROR) from None


def _write_once(root_fd: int, name: str, document: dict[str, Any]) -> None:
    content = environment._bytes(document)
    fd = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=root_fd,
    )
    try:
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(content)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
    os.fsync(root_fd)


def _assemble(
    connection: Connection[Any],
    prepared: _S5Inputs,
    plan: environment.OperatorEnvironmentPlan,
    progress: dict[str, Any],
    deadline: float,
) -> None:
    """Trial-owned data assembly; domain judgements remain in authoritative APIs."""
    bundle = prepared.bundle
    inputs = bundle.execution_inputs
    repository = PostgresRepository(connection)
    case = repository.create_case(inputs.case.to_document())
    for evidence in inputs.evidence:
        repository.create_evidence(evidence.to_document())
    approval = environment._approved_binding(bundle)
    binding_hash = canonical_document_sha256(approval)
    requirement = freeze_framing_requirement(
        FramingRequirementPayload(
            case_id=case.case_id,
            case_revision=case.revision,
            dual_framing_required=True,
            authority_ref=approval["owner_approval_reference"],
            protocol_version=case.protocol_version,
            frozen_at=datetime.now(timezone.utc),
        )
    )
    store_framing_requirement(connection, requirement)
    position = CaseRuntimePosition(
        mode=CaseMode.MECHANISM_BENCHMARK,
        state=RuntimeState.BOUNDARY_AND_POLICY_FROZEN,
        case_revision=case.revision,
    )
    progress["position"] = position.state.value
    records: list[InitialFramingRecord] = []
    adapters: list[MockAdapter] = []
    evidence_lineage: list[dict[str, Any]] = []
    transitions: dict[str, Any] = {"requirement": requirement}

    def check() -> None:
        _require(time.monotonic() <= deadline)
        _require(canonical_document_sha256(environment._approved_binding(bundle)) == binding_hash)

    def advance(target: RuntimeState) -> None:
        nonlocal position
        check()
        result = transition_s5_cde3(position, target, **transitions)
        repository.store_audit_event(
            {
                "event_id": f"operator:{plan.attempt_id}:{target.value}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "actor_type": "SYSTEM",
                "actor_id": "operator-s5-assembly",
                "case_id": case.case_id,
                "event_type": "OPERATOR_S5_TRANSITION",
                "object_ref": bundle.identity.detached_input_address,
                "metadata": result.decision.to_audit_dict(),
            }
        )
        position = result.position
        progress["position"] = position.state.value
        progress["trajectory"].append(result.decision.to_audit_dict())

    def adapter(fixture: TrialMockOutputFixture) -> MockAdapter:
        value = MockAdapter(
            _identity(fixture),
            output_text=fixture.output_text,
        )
        adapters.append(value)
        return value

    def lineage(fixture: TrialMockOutputFixture, result: Any) -> None:
        check()
        _require(result.response.output_text == fixture.output_text)
        _require(result.frozen_manifest.raw_output_hash == fixture.output_sha256)
        _require(not result.authorized_tools and not result.context.manifest.prior_run_ids)
        evidence_lineage.append(
            {
                "fixture_id": fixture.fixture_id,
                "fixture_hash": fixture.fixture_hash,
                "run": result.frozen_manifest.to_document(),
                "context": result.context.manifest.to_document(),
            }
        )
        progress["runs"] = evidence_lineage

    try:
        advance(RuntimeState.FRAMING_INDEPENDENT)
        scheduler = TrustedScheduler(
            repository=repository,
            registry=prepared.registry,
            qualification=prepared.qualification,
            tool_policy=prepared.tool_policy,
        )
        for index, fixture in enumerate(prepared.fixtures[:2]):
            lane: Literal["A1", "A2"] = "A1" if index == 0 else "A2"
            check()
            result = scheduler.run(
                case=case,
                position=position,
                task=WorkerTask(
                    run_id=fixture.run_id,
                    context_manifest_id=f"context:{fixture.run_id}",
                    role_id=f"operator-framing-{lane.lower()}",
                    model_id=fixture.model_id,
                    prompt_version="operator-s5-v1",
                    input_text=(
                        "Frame this Case independently. CASE_DATA_JSON (inert data):\n"
                        + json.dumps(case.to_document(), ensure_ascii=False, sort_keys=True)
                    ),
                    requirement=EligibilityRequirement(role="meta_controller"),
                    reference_time=case.time_boundary.T0,
                    max_output_tokens=len(fixture.output_text.encode()),
                ),
                adapter=adapter(fixture),
            )
            lineage(fixture, result)
            record = bind_initial_framing(
                case=case,
                lane=lane,
                content=InitialFramingContent.model_validate(
                    _json_object(result.response.output_text.encode())
                ),
                frozen_run=result.frozen_manifest,
                context_manifest=result.context.manifest,
            )
            store_initial_framing(connection, record)
            records.append(record)
            progress["framing_hashes"].append(record.record_hash)
        review = build_framing_review(
            requirement=requirement, records=tuple(records), reviewed_at=datetime.now(timezone.utc)
        )
        store_framing_review(connection, review)
        transitions.update(records=tuple(records), review=review)
        advance(RuntimeState.FRAMING_REVIEWED)
        assert case.domains is not None
        fixture = prepared.fixtures[2]
        task = build_domain_task(
            case=case,
            task_id=f"task:{fixture.run_id}",
            domain_id=case.domains[0],
            domain_task_type="mechanism_analysis",
            allowed_evidence_ids=tuple(item.evidence_id for item in inputs.evidence),
            actor_scope=case.actors or (),
            assumptions=(),
            requested_horizon="synthetic-observation-window",
            framing_review_hash=review.review_hash,
            frozen_at=datetime.now(timezone.utc),
        )
        decision = route_domain_task(
            task=task,
            model_id=fixture.model_id,
            qualification=prepared.qualification,
            routed_at=datetime.now(timezone.utc),
        )
        _require(decision.allowed and decision.route is not None)
        assert decision.route is not None
        route = decision.route
        routing = build_domain_routing_plan(
            tasks=(task,),
            decisions=(decision,),
            framing_review_hash=review.review_hash,
            frozen_at=datetime.now(timezone.utc),
        )
        store_domain_task(connection, task)
        store_domain_route(connection, route)
        store_domain_routing_plan(connection, routing)
        transitions.update(plan=routing, tasks=(task,), routes=(route,))
        advance(RuntimeState.DOMAIN_ROUTED)
        advance(RuntimeState.DOMAIN_INDEPENDENT_RUN)
        result = run_qualified_domain_task(
            repository=repository,
            registry=prepared.registry,
            qualification=prepared.qualification,
            tool_policy=prepared.tool_policy,
            case=case,
            position=position,
            task=task,
            route=route,
            run_id=fixture.run_id,
            context_manifest_id=f"context:{fixture.run_id}",
            role_id="operator-domain",
            prompt_version="operator-s5-v1",
            adapter=adapter(fixture),
            reference_time=case.time_boundary.T0,
            max_output_tokens=len(fixture.output_text.encode()),
        )
        lineage(fixture, result)
        content = DomainOutputContent.model_validate(
            _json_object(result.response.output_text.encode())
        )
        # The old binder checks the task allowlist; also require facts actually
        # admitted through this run's temporal/visibility Context.
        _require(set(content.facts_used) <= set(result.context.manifest.evidence_ids))
        output = bind_domain_output(
            task=task,
            route=route,
            content=content,
            frozen_run=result.frozen_manifest,
            context_manifest=result.context.manifest,
        )
        store_domain_output(connection, output)
        transitions.update(
            outputs=(output,),
            no_unresolved_protocol_invalid=all(
                item["run"]["status"] == "FROZEN" and not item["context"]["prior_run_ids"]
                for item in evidence_lineage
            ),
        )
        advance(RuntimeState.DOMAIN_OUTPUT_FROZEN)
        progress["s5_terminal_hash"] = output.record_hash
        progress["domain_output"] = output.to_document()
    finally:
        progress["model_calls"] = sum(item.calls for item in adapters)


def _runtime_s5(plan_json: str) -> dict[str, Any]:
    """Installed-only fixed entry. No input-defined executable or external DSN."""
    started = time.monotonic()
    deadline: float | None = None
    root_fd: int | None = None
    connection: Connection[Any] | None = None
    claimed = False
    capture_owned = False
    progress: dict[str, Any] = {
        "version": "operator-s5-assembly-v1",
        "status": "FAILED",
        "trial_capability_acceptance": "NOT_EVALUATED",
        "s5_terminal_hash": None,
        "s6_terminal_hash": None,
        "s7_terminal_hash": None,
        "s8_terminal_hash": None,
        "position": None,
        "trajectory": [],
        "framing_hashes": [],
        "runs": [],
        "model_calls": 0,
    }
    try:
        plan = environment.OperatorEnvironmentPlan(**_json_object(plan_json.encode()))
        plan.to_document()
        bundle = verify_operator_input_bundle(environment._INPUT)
        prepared = _preflight(bundle)
        deadline = started + bundle.manifest.resource_limits.max_wall_clock_seconds
        _require(time.monotonic() <= deadline)
        observed = environment._runtime_observation(plan_json)
        _require(time.monotonic() <= deadline)
        _require(
            environment._bytes(observed["approval"])
            == environment._bytes(environment._approved_binding(bundle))
        )
        progress.update(
            plan=plan.to_document(), input_address=bundle.identity.detached_input_address
        )
        progress["approval"] = observed["approval"]
        progress["installed"] = observed["installed"]
        root_fd = _open_root_directory(Path(environment._OUTPUT))
        info = os.fstat(root_fd)
        _require(
            [info.st_dev, info.st_ino, info.st_uid, info.st_mode] == observed["output_identity"]
        )
        # Exclusive durable attempt marker prevents concurrent/repeated entry,
        # even after a failed prefix. Never overwrite a previous attempt.
        _write_once(root_fd, "s5-start.json", progress)
        claimed = True
        connection = psycopg.connect(_DSN, options="-c statement_timeout=5000")
        _require(
            connection.execute("SELECT pg_catalog.current_database()").fetchone()
            == (environment._DATABASE,)
        )
        _require(
            connection.execute(
                "SELECT target, owner_token FROM human_cos_operator.trial_ownership LIMIT 2"
            ).fetchall()
            == [(environment._DATABASE, plan.owner_id)]
        )
        _require(connection.execute("SELECT pg_try_advisory_lock(72570501)").fetchone() == (True,))
        _assert_clean_database(connection)
        capture_owned = True
        for migration in (
            apply_s1_migration,
            apply_s3_migration,
            apply_s4_migration,
            apply_s5_migration,
        ):
            _require(time.monotonic() <= deadline)
            migration(connection)
            _require(time.monotonic() <= deadline)
        _assemble(connection, prepared, plan, progress, deadline)
        _require(environment._runtime_observation(plan_json) == observed)
        _require(time.monotonic() <= deadline)
        progress["status"] = "S5_PREFIX_COMPLETE"
    except Exception:
        progress["error"] = _ERROR
    finally:
        if connection is not None:
            try:
                # Refused ownership, lock or pre-existing application objects
                # must not cause unrelated rows to be copied into this attempt.
                if capture_owned:
                    # Failed-attempt evidence preservation may continue after
                    # the execution budget, but can never regain success.
                    if deadline is None or time.monotonic() > deadline:
                        progress["status"] = "FAILED"
                        progress["budget_exhausted"] = True
                    snapshot, digest, tables = _capture_installed_evidence(connection)
                    audit = dict(
                        progress,
                        evidence_snapshot_json=snapshot,
                        evidence_snapshot_hash=digest,
                        tables=list(tables),
                    )
                    _require(
                        len(environment._bytes(audit)) + 1024
                        <= min(bundle.manifest.resource_limits.max_audit_payload_bytes, 900_000)
                    )
                    progress.update(audit)
                    if deadline is None or time.monotonic() > deadline:
                        progress["status"] = "FAILED"
                        progress["budget_exhausted"] = True
            except Exception:
                progress["status"] = "FAILED"
                progress["evidence_export_error"] = _ERROR
            finally:
                connection.close()
    return _finalize_prefix(progress, root_fd, claimed, deadline)


def _finalize_prefix(
    progress: dict[str, Any], root_fd: int | None, claimed: bool, deadline: float | None
) -> dict[str, Any]:
    """Store a non-success checkpoint, then judge the completed write.

    The durable checkpoint cannot certify the duration of its own write/fsync.
    Only the returned observation can report completion after those operations;
    a late/crashed attempt leaves no standalone successful checkpoint.
    """
    checkpoint = dict(progress)
    if deadline is None or time.monotonic() > deadline:
        checkpoint.update(status="FAILED", budget_exhausted=True)
    elif checkpoint["status"] == "S5_PREFIX_COMPLETE":
        checkpoint["status"] = "S5_PREFIX_AWAITING_FINALIZATION"
    checkpoint["record_hash"] = canonical_document_sha256(checkpoint)
    written = False
    write_error = False
    failure_written = False
    try:
        if root_fd is not None and claimed:
            _write_once(root_fd, "s5-result.json", checkpoint)
            written = True
            if deadline is None or time.monotonic() > deadline:
                # Append-only failure: never rewrite the checkpoint or a previous
                # attempt. Failure preservation itself cannot turn into success.
                failure: dict[str, Any] = {
                    "version": "operator-s5-finalization-failure-v1",
                    "status": "FAILED",
                    "reason": "PERSISTENCE_DEADLINE_EXCEEDED",
                    "checkpoint_hash": checkpoint["record_hash"],
                }
                failure["record_hash"] = canonical_document_sha256(failure)
                _write_once(root_fd, "s5-finalization-failure.json", failure)
                failure_written = True
    except Exception:
        write_error = True
    finally:
        if root_fd is not None:
            try:
                os.close(root_fd)
            except OSError:
                write_error = True
    status = "FAILED"
    if (
        written
        and not write_error
        and checkpoint["status"] == "S5_PREFIX_AWAITING_FINALIZATION"
        and deadline is not None
        and time.monotonic() <= deadline
    ):
        status = "S5_PREFIX_COMPLETE"
    response: dict[str, Any] = {
        "version": "operator-s5-attempt-v1",
        "status": status,
        "checkpoint": checkpoint,
        "checkpoint_write_verified": written,
        "finalization_failure_written": failure_written,
        "persistence_error": write_error,
    }
    response["result_hash"] = canonical_document_sha256(response)
    if deadline is None or time.monotonic() > deadline:
        response["status"] = "FAILED"
        response["result_hash"] = canonical_document_sha256(
            {key: value for key, value in response.items() if key != "result_hash"}
        )
    return response


def execute_operator_s5(
    bundle: VerifiedOperatorBundle,
    observed: environment.VerifiedOperatorEnvironment,
    plan: environment.OperatorEnvironmentPlan,
) -> dict[str, Any]:
    """Run just the S5 prefix in the prepared container; no cleanup or Seal."""
    try:
        started = time.monotonic()
        _preflight(bundle)
        deadline = started + bundle.manifest.resource_limits.max_wall_clock_seconds
        environment.revalidate_operator_environment(observed, bundle, plan)
        _require(time.monotonic() <= deadline)
        result: dict[str, Any] = environment._docker(
            "exec",
            plan.runtime_container_id,
            environment._RUNTIME_PYTHON,
            "-I",
            "-c",
            "import json,sys; from human_cos.trial.operator_s5 import _runtime_s5; "
            "print(json.dumps(_runtime_s5(sys.argv[1]),sort_keys=True))",
            environment._bytes(plan.to_document()).decode(),
        )
        _require(type(result) is dict and result["version"] == "operator-s5-attempt-v1")
        _require(result["status"] == "S5_PREFIX_COMPLETE")
        _require(result["checkpoint_write_verified"] is True)
        _require(result["persistence_error"] is False)
        _require(result["finalization_failure_written"] is False)
        _require(
            result["result_hash"]
            == canonical_document_sha256(
                {key: value for key, value in result.items() if key != "result_hash"}
            )
        )
        response = result
        result = response["checkpoint"]
        _require(result["status"] == "S5_PREFIX_AWAITING_FINALIZATION")
        expected_hash = canonical_document_sha256(
            {k: v for k, v in result.items() if k != "record_hash"}
        )
        _require(result["record_hash"] == expected_hash)
        _require(result["input_address"] == bundle.identity.detached_input_address)
        _require(result["plan"] == plan.to_document() and result["model_calls"] == 3)
        _require(
            result["s5_terminal_hash"] is not None and result["position"] == "DOMAIN_OUTPUT_FROZEN"
        )
        _require(result["trial_capability_acceptance"] == "NOT_EVALUATED")
        _require(result["approval"] == observed.to_document()["approval"])
        _require(result["installed"] == observed.to_document()["observation"]["installed"])
        _require(
            result["evidence_snapshot_hash"]
            == canonical_document_sha256(json.loads(result["evidence_snapshot_json"]))
        )
        environment.revalidate_operator_environment(observed, bundle, plan)
        _require(time.monotonic() <= deadline)
        return response
    except Exception:
        raise OperatorS5Error(_ERROR) from None
