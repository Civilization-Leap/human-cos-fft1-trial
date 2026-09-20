"""Installed guarded runtime for the SBX7 input-driven S6 engineering slice."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import psycopg
from psycopg import Connection

from human_cos.runtime.run import canonical_document_sha256
from human_cos.storage.migrations import (
    apply_s1_migration,
    apply_s3_migration,
    apply_s4_migration,
    apply_s5_migration,
    apply_s6_migration,
)

from . import operator_environment as environment
from . import operator_s5 as s5
from .bundle import _open_root_directory
from .integrated_chain import _assert_clean_database, _capture_installed_evidence
from .operator_bundle import VerifiedOperatorBundle, _json_object, verify_operator_input_bundle
from .operator_s6_assembly import S6AssemblyInputs, assemble_s6_slice
from .operator_s6_preflight import Inputs, OperatorS6SliceError, preflight, require

_DSN = "host=postgres dbname=human_cos_operator user=postgres connect_timeout=3"
_ERROR = "operator S6 slice rejected"


def _finalize(
    progress: dict[str, Any], root_fd: int | None, claimed: bool, deadline: float | None
) -> dict[str, Any]:
    checkpoint = dict(progress)
    if deadline is None or time.monotonic() > deadline:
        checkpoint.update(status="FAILED", budget_exhausted=True)
    elif checkpoint["status"] == "S6_SLICE_COMPLETE":
        checkpoint["status"] = "S6_SLICE_AWAITING_FINALIZATION"
    checkpoint["record_hash"] = canonical_document_sha256(checkpoint)
    written = False
    write_error = False
    failure_written = False
    try:
        if root_fd is not None and claimed:
            s5._write_once(root_fd, "s6-slice-result.json", checkpoint)
            written = True
            if deadline is None or time.monotonic() > deadline:
                failure = {
                    "version": "operator-s6-slice-finalization-failure-v1",
                    "status": "FAILED",
                    "reason": "PERSISTENCE_DEADLINE_EXCEEDED",
                    "checkpoint_hash": checkpoint["record_hash"],
                }
                failure["record_hash"] = canonical_document_sha256(failure)
                s5._write_once(root_fd, "s6-slice-finalization-failure.json", failure)
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
        and checkpoint["status"] == "S6_SLICE_AWAITING_FINALIZATION"
        and deadline is not None
        and time.monotonic() <= deadline
    ):
        status = "S6_SLICE_COMPLETE"
    response: dict[str, Any] = {
        "version": "operator-s6-slice-attempt-v1",
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
            {k: v for k, v in response.items() if k != "result_hash"}
        )
    return response


def _runtime_s6_slice(plan_json: str) -> dict[str, Any]:
    started = time.monotonic()
    deadline: float | None = None
    root_fd: int | None = None
    connection: Connection[Any] | None = None
    claimed = False
    capture_owned = False
    progress: dict[str, Any] = {
        "version": "operator-s6-slice-assembly-v1",
        "status": "FAILED",
        "trial_capability_acceptance": "NOT_EVALUATED",
        "s6_cognitive_acceptance": "NOT_EVALUATED",
        "s5_terminal_hash": None,
        "s6_terminal_hash": None,
        "s7_terminal_hash": None,
        "s8_terminal_hash": None,
        "s6_slice_hash": None,
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
        prepared = preflight(bundle)
        deadline = started + bundle.manifest.resource_limits.max_wall_clock_seconds
        require(time.monotonic() <= deadline)
        observed = environment._runtime_observation(plan_json)
        require(time.monotonic() <= deadline)
        require(
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
        require(
            [info.st_dev, info.st_ino, info.st_uid, info.st_mode] == observed["output_identity"]
        )
        s5._write_once(root_fd, "s6-slice-start.json", progress)
        claimed = True
        connection = psycopg.connect(_DSN, options="-c statement_timeout=5000")
        require(
            connection.execute("SELECT pg_catalog.current_database()").fetchone()
            == (environment._DATABASE,)
        )
        require(
            connection.execute(
                "SELECT target, owner_token FROM human_cos_operator.trial_ownership LIMIT 2"
            ).fetchall()
            == [(environment._DATABASE, plan.owner_id)]
        )
        require(connection.execute("SELECT pg_try_advisory_lock(72570501)").fetchone() == (True,))
        _assert_clean_database(connection)
        capture_owned = True
        for migration in (
            apply_s1_migration,
            apply_s3_migration,
            apply_s4_migration,
            apply_s5_migration,
        ):
            require(time.monotonic() <= deadline)
            migration(connection)
            require(time.monotonic() <= deadline)
        s5._assemble(connection, prepared.s5_inputs, plan, progress, deadline)
        require(progress["s5_terminal_hash"] is not None)
        apply_s6_migration(connection)
        require(time.monotonic() <= deadline)
        approval_hash = canonical_document_sha256(environment._approved_binding(bundle))

        def check_binding() -> None:
            require(time.monotonic() <= deadline)
            require(
                canonical_document_sha256(environment._approved_binding(bundle)) == approval_hash
            )

        assembled = assemble_s6_slice(
            connection,
            case=bundle.execution_inputs.case,
            domain_output_document=progress["domain_output"],
            attempt_id=plan.attempt_id,
            inputs=S6AssemblyInputs(
                reviewer_model_id=prepared.reviewer.model_id,
                reviewer_frozen_at=prepared.reviewer.frozen_at,
                reviewer_fixture_hash=prepared.reviewer.fixture_hash,
                reviewer_content=prepared.reviewer_content,
                controller_model_id=prepared.controller.model_id,
                controller_frozen_at=prepared.controller.frozen_at,
                controller_fixture_hash=prepared.controller.fixture_hash,
                controller_content=prepared.controller_content,
                qualification=prepared.s5_inputs.qualification,
            ),
            deadline=deadline,
            check_binding=check_binding,
        )
        connection.commit()
        progress.update(assembled)
        progress["s6_slice_hash"] = assembled["critical_integration_hash"]
        require(progress["s6_terminal_hash"] is None)
        require(environment._runtime_observation(plan_json) == observed)
        require(time.monotonic() <= deadline)
        progress["status"] = "S6_SLICE_COMPLETE"
    except Exception:
        progress["error"] = _ERROR
    finally:
        if connection is not None:
            try:
                if capture_owned:
                    if deadline is None or time.monotonic() > deadline:
                        progress.update(status="FAILED", budget_exhausted=True)
                    snapshot, digest, tables = _capture_installed_evidence(connection)
                    audit = dict(
                        progress,
                        evidence_snapshot_json=snapshot,
                        evidence_snapshot_hash=digest,
                        tables=list(tables),
                    )
                    require(
                        len(environment._bytes(audit)) + 1024
                        <= min(bundle.manifest.resource_limits.max_audit_payload_bytes, 900_000)
                    )
                    progress.update(audit)
                    if deadline is None or time.monotonic() > deadline:
                        progress.update(status="FAILED", budget_exhausted=True)
            except Exception:
                progress.update(status="FAILED", evidence_export_error=_ERROR)
            finally:
                connection.close()
    return _finalize(progress, root_fd, claimed, deadline)


def execute_operator_s6_slice(
    bundle: VerifiedOperatorBundle,
    observed: environment.VerifiedOperatorEnvironment,
    plan: environment.OperatorEnvironmentPlan,
) -> dict[str, Any]:
    try:
        started = time.monotonic()
        prepared: Inputs = preflight(bundle)
        deadline = started + bundle.manifest.resource_limits.max_wall_clock_seconds
        environment.revalidate_operator_environment(observed, bundle, plan)
        require(time.monotonic() <= deadline)
        result: dict[str, Any] = environment._docker(
            "exec",
            plan.runtime_container_id,
            environment._RUNTIME_PYTHON,
            "-I",
            "-c",
            (
                "import json,sys; "
                "from human_cos.trial.operator_s6_runtime import _runtime_s6_slice; "
                "print(json.dumps(_runtime_s6_slice(sys.argv[1]),sort_keys=True))"
            ),
            environment._bytes(plan.to_document()).decode(),
        )
        require(type(result) is dict and result["version"] == "operator-s6-slice-attempt-v1")
        require(result["status"] == "S6_SLICE_COMPLETE")
        require(
            result["checkpoint_write_verified"] is True and result["persistence_error"] is False
        )
        require(result["finalization_failure_written"] is False)
        require(
            result["result_hash"]
            == canonical_document_sha256({k: v for k, v in result.items() if k != "result_hash"})
        )
        checkpoint = result["checkpoint"]
        require(checkpoint["status"] == "S6_SLICE_AWAITING_FINALIZATION")
        require(
            checkpoint["record_hash"]
            == canonical_document_sha256(
                {k: v for k, v in checkpoint.items() if k != "record_hash"}
            )
        )
        require(checkpoint["input_address"] == bundle.identity.detached_input_address)
        require(checkpoint["plan"] == plan.to_document() and checkpoint["model_calls"] == 3)
        require(
            checkpoint["s5_terminal_hash"] is not None and checkpoint["s6_terminal_hash"] is None
        )
        require(
            checkpoint["s6_slice_hash"] is not None
            and checkpoint["position"] == "WORLD_CAUSAL_INTEGRATION"
        )
        require(checkpoint["trial_capability_acceptance"] == "NOT_EVALUATED")
        require(checkpoint["s6_cognitive_acceptance"] == "NOT_EVALUATED")
        require(
            checkpoint["s6_fixture_hashes"]
            == [prepared.reviewer.fixture_hash, prepared.controller.fixture_hash]
        )
        require(
            checkpoint["evidence_snapshot_hash"]
            == canonical_document_sha256(json.loads(checkpoint["evidence_snapshot_json"]))
        )
        environment.revalidate_operator_environment(observed, bundle, plan)
        require(time.monotonic() <= deadline)
        return result
    except Exception:
        raise OperatorS6SliceError(_ERROR) from None
