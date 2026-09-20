"""Trusted operator resource preparation; no cognitive execution or destruction."""

from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import operator_environment as environment
from .operator_bundle import VerifiedOperatorBundle


class OperatorResourceError(ValueError):
    """Sanitized preparation failure; owned resources are retained for inspection."""


@dataclass(frozen=True)
class PreparedOperatorResources:
    workspace: Path
    plan: environment.OperatorEnvironmentPlan
    observation: environment.VerifiedOperatorEnvironment


def _command(*arguments: str) -> str:
    result = subprocess.run(
        ["/usr/bin/docker", *arguments],
        env={"PATH": os.defpath, "DOCKER_HOST": "unix:///var/run/docker.sock"},
        capture_output=True,
        timeout=180,
        check=False,
    )
    if result.returncode != 0:
        raise OperatorResourceError("operator resource preparation rejected")
    return result.stdout.decode().strip()


def _compose_document(
    root: Path, project: str, owner: str, attempt: str, runtime: str, database: str
) -> dict[str, Any]:
    # Compose itself supplies its reserved project label to every resource.
    labels = {environment._OWNER: owner}
    marker = json.dumps({"attempt_id": attempt, "owner_id": owner, "project": project})
    initialize = (
        "import os,pathlib; p=pathlib.Path('/operator/output'); "
        "assert not list(p.iterdir()); "
        f"(p/'operator-owner.json').write_text({marker!r}); "
        "os.chown(p/'operator-owner.json',1000,1000); "
        "os.chmod(p/'operator-owner.json',0o600); os.chown(p,1000,1000); os.chmod(p,0o700)"
    )
    return {
        "name": project,
        "services": {
            "initialize": {
                "image": "sha256:" + runtime,
                "pull_policy": "never",
                "user": "0:0",
                "entrypoint": [],
                "command": ["/usr/local/bin/python", "-I", "-c", initialize],
                "network_mode": "none",
                "read_only": True,
                "cap_drop": ["ALL"],
                "cap_add": ["CHOWN", "DAC_OVERRIDE", "FOWNER"],
                "security_opt": ["no-new-privileges:true"],
                "labels": labels,
                "volumes": ["output:/operator/output"],
            },
            "postgres": {
                "image": "sha256:" + database,
                "pull_policy": "never",
                "labels": labels,
                "environment": {
                    "POSTGRES_DB": "human_cos_operator",
                    "POSTGRES_USER": "postgres",
                    "POSTGRES_HOST_AUTH_METHOD": "trust",
                },
                "networks": {"internal": {"aliases": ["postgres"]}},
                "volumes": ["database:/var/lib/postgresql/data"],
                "healthcheck": {
                    "test": ["CMD", "pg_isready", "-U", "postgres", "-d", "human_cos_operator"],
                    "interval": "1s",
                    "timeout": "3s",
                    "retries": 60,
                },
            },
            "runtime": {
                "image": "sha256:" + runtime,
                "pull_policy": "never",
                "labels": labels,
                "entrypoint": [],
                "command": ["sleep", "infinity"],
                "user": "1000:1000",
                "read_only": True,
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                "environment": {"HOME": "/nonexistent"},
                "networks": ["internal"],
                "volumes": [
                    {
                        "type": "bind",
                        "source": str(root / "input"),
                        "target": "/operator/input",
                        "read_only": True,
                        "bind": {"create_host_path": False},
                    },
                    "output:/operator/output",
                ],
            },
        },
        "networks": {"internal": {"internal": True, "labels": labels}},
        "volumes": {"output": {"labels": labels}, "database": {"labels": labels}},
    }


def prepare_operator_resources(
    bundle: VerifiedOperatorBundle,
    workspace: Path,
    *,
    expected_build_sha: str,
    runtime_image_sha256: str,
    database_image_sha256: str,
) -> PreparedOperatorResources:
    """Prepare fresh resources only for current approved bytes on a trusted host.

    Images are already built/pulled by the trusted build layer. No network build,
    provider credential, arbitrary command, existing output adoption or cleanup.
    The new private workspace is the retained lifecycle journal, including failure.
    """
    created = False
    state: dict[str, Any] = {"version": "operator-resource-preparation-v1", "status": "REJECTED"}
    try:
        approval = environment._approved_binding(bundle)
        installed = environment._installed_identity()
        environment._require(installed["build_sha"] == expected_build_sha)
        for image in (runtime_image_sha256, database_image_sha256):
            environment._require(re.fullmatch(r"[a-f0-9]{64}", image) is not None)
        # The launch workspace is trusted, exclusive and never adopted from old runs.
        environment._require(
            workspace.is_absolute() and workspace.parent.resolve() == workspace.parent
        )
        workspace.mkdir(mode=0o700)
        created = True
        nonce = secrets.token_hex(16)
        project, owner = "human-cos-sbx7-" + nonce, secrets.token_hex(32)
        state.update(
            project=project,
            owner_id=owner,
            attempt_id=nonce,
            installed=installed,
            approval=approval,
            status="PREPARING",
        )
        (workspace / "preparation.json").write_bytes(environment._bytes(state))
        root = workspace / "input"
        root.mkdir(mode=0o755)
        for name, content in bundle.payload_files:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            path.write_bytes(content)
            path.chmod(0o444)
        (root / "checksums.sha256").write_bytes(bundle.checksum_index)
        (root / "input_address.sha256").write_text(bundle.identity.detached_input_address + "\n")
        document = _compose_document(
            workspace, project, owner, nonce, runtime_image_sha256, database_image_sha256
        )
        compose = workspace / "compose.json"
        compose.write_bytes(environment._bytes(document))
        prefix = ("compose", "--project-name", project, "--file", str(compose))
        # Do not adopt even a randomly colliding project resource.
        for kind in ("container", "network", "volume"):
            existing = _command(
                kind,
                "ls",
                *(("--all",) if kind == "container" else ()),
                "-q",
                "--filter",
                "label=" + environment._PROJECT + "=" + project,
            )
            environment._require(not existing)
        initializer = project + "-initialize"
        _command(*prefix, "run", "--name", initializer, "--no-deps", "initialize")
        initializer_id = _command("inspect", "--format", "{{.Id}}", initializer)
        environment._require(re.fullmatch(r"[a-f0-9]{64}", initializer_id) is not None)
        state["initializer"] = {"container_id": initializer_id, "exit_code": 0}
        (workspace / "preparation.json").write_bytes(environment._bytes(state))
        # Only a successful, recorded helper is removed to release its volume.
        # Failed helpers remain inspectable, with their logs, under this project.
        _command("rm", initializer_id)
        environment._require(approval == environment._approved_binding(bundle))
        _command(*prefix, "up", "--detach", "--wait", "--wait-timeout", "90", "postgres", "runtime")
        runtime_id = _command(*prefix, "ps", "--quiet", "runtime")
        database_id = _command(*prefix, "ps", "--quiet", "postgres")
        plan = environment.OperatorEnvironmentPlan(
            nonce,
            project,
            owner,
            expected_build_sha,
            runtime_id,
            database_id,
            runtime_image_sha256,
            database_image_sha256,
        )
        state["plan"] = plan.to_document()
        (workspace / "preparation.json").write_bytes(environment._bytes(state))
        _command(
            "exec",
            database_id,
            "psql",
            "-X",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "postgres",
            "-d",
            "human_cos_operator",
            "-c",
            "CREATE SCHEMA human_cos_operator; "
            "CREATE TABLE human_cos_operator.trial_ownership (target text, owner_token text); "
            "INSERT INTO human_cos_operator.trial_ownership VALUES "
            f"('human_cos_operator','{owner}');",
        )
        observation = environment.observe_operator_environment(bundle, plan)
        state.update(status="PREPARED", observation=observation.to_document())
        (workspace / "preparation.json").write_bytes(environment._bytes(state))
        return PreparedOperatorResources(workspace, plan, observation)
    except Exception:
        if created:
            state["status"] = "FAILED_RESOURCES_RETAINED"
            try:
                (workspace / "preparation.json").write_bytes(environment._bytes(state))
            except OSError:
                pass  # Storage failure cannot grant cleanup or expose raw paths.
        raise OperatorResourceError("operator resource preparation rejected") from None
