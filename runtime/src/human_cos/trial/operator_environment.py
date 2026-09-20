"""Read-only operator environment observation from a trusted Linux Docker host.

No supplied PASS/facts object is accepted. This observes already-created resources;
it neither provisions them nor launches the cognitive chain or grants its authority.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from importlib.metadata import distribution
from pathlib import Path
from typing import Any
from weakref import WeakKeyDictionary

from human_cos.protocols.frozen_contract import assert_bundled_frozen_contracts_intact

from .bundle import _baseline_contract_hashes, _open_root_directory, _read_regular_relative
from .operator_bundle import VerifiedOperatorBundle, _json_object, verify_operator_input_bundle
from .operator_contracts import OperatorApprovalStatus
from .rehearsal import _installed_build_commit_sha, _probe_outbound_connections

_ERROR = "operator environment admission rejected"
_OWNER = "org.human-cos.operator.owner"
_PROJECT = "com.docker.compose.project"
_INPUT = "/operator/input"
_OUTPUT = "/operator/output"
_DATABASE = "human_cos_operator"
_MARKER = "operator-owner.json"
_RUNTIME_PYTHON = "/usr/local/bin/python"


class OperatorEnvironmentError(ValueError):
    """Fixed-text rejection; never expose Docker output, credentials or case data."""


def _require(condition: bool) -> None:
    if not condition:
        raise OperatorEnvironmentError(_ERROR)


def _bytes(document: Any) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


@dataclass(frozen=True)
class OperatorEnvironmentPlan:
    """Trusted launch expectations, outside the address-covered operator payload."""

    attempt_id: str
    project: str
    owner_id: str
    expected_build_sha: str
    runtime_container_id: str
    database_container_id: str
    runtime_image_sha256: str
    database_image_sha256: str

    def to_document(self) -> dict[str, str]:
        _require(type(self) is OperatorEnvironmentPlan)
        values = asdict(self)
        for name, value in values.items():
            _require(type(value) is str)
            if name == "attempt_id":
                pattern = r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}"
            elif name == "project":
                pattern = r"human-cos-sbx7-[a-z0-9][a-z0-9-]{0,47}"
            elif name == "expected_build_sha":
                pattern = r"[0-9a-f]{40}"
            else:
                pattern = r"[0-9a-f]{64}"
            _require(re.fullmatch(pattern, value) is not None and set(value) != {"0"})
        _require(self.runtime_container_id != self.database_container_id)
        return values


def _approved_binding(bundle: VerifiedOperatorBundle) -> dict[str, Any]:
    _require(type(bundle) is VerifiedOperatorBundle)
    bundle.assert_integrity()
    decision = bundle.approval
    _require(decision.status is OperatorApprovalStatus.MATCHED_REQUIRES_VERIFICATION)
    return {
        "identity": asdict(decision.identity),
        "slot": decision.approval_slot,
        "owner_approval_reference": decision.owner_approval_reference,
    }


def _installed_identity() -> dict[str, Any]:
    """Read observed identity independently of any plan/expected SHA."""
    package = distribution("human-cos-runtime")
    direct = package.read_text("direct_url.json")
    if direct is not None:
        _require(not json.loads(direct).get("dir_info", {}).get("editable", False))
    expected_module = Path(str(package.locate_file("human_cos/trial/operator_environment.py")))
    _require(expected_module.resolve() == Path(__file__).resolve())
    build = _installed_build_commit_sha()
    _require(build != "0" * 40)
    report = assert_bundled_frozen_contracts_intact()
    observed = {item.path: item.actual_sha256 for item in report.items}
    expected = {item["name"]: item["sha256"] for item in _baseline_contract_hashes()}
    _require(len(report.items) == 10 and observed == expected)
    return {"build_sha": build, "contract_hashes": observed}


def _docker(*arguments: str) -> Any:
    result = subprocess.run(
        ["/usr/bin/docker", *arguments],
        env={"PATH": os.defpath, "DOCKER_HOST": "unix:///var/run/docker.sock"},
        capture_output=True,
        timeout=20,
        check=False,
    )
    _require(result.returncode == 0 and len(result.stdout) <= 1_048_576)
    return json.loads(result.stdout)


def _inspect(kind: str, identifier: str) -> dict[str, Any]:
    result = _docker("inspect", "--type", kind, identifier)
    _require(type(result) is list and len(result) == 1 and type(result[0]) is dict)
    return dict(result[0])


def _owned(labels: Any, plan: OperatorEnvironmentPlan) -> None:
    _require(type(labels) is dict)
    _require(labels.get(_OWNER) == plan.owner_id and labels.get(_PROJECT) == plan.project)


def _container(
    item: dict[str, Any], plan: OperatorEnvironmentPlan, *, runtime: bool
) -> tuple[str, str]:
    expected_id = plan.runtime_container_id if runtime else plan.database_container_id
    _require(item["Id"] == expected_id and item["State"]["Running"] is True)
    image = plan.runtime_image_sha256 if runtime else plan.database_image_sha256
    _require(item["Image"] == "sha256:" + image)
    _owned(item["Config"]["Labels"], plan)
    host = item["HostConfig"]
    _require(host["Privileged"] is False)
    _require(host.get("NetworkMode") not in ("host", "none") and not host.get("PublishAllPorts"))
    _require(not host.get("PortBindings") and not host.get("ExtraHosts"))
    _require(not any(host.get(key) for key in ("Dns", "DnsSearch", "DnsOptions")))
    _require(not host.get("Links") and not host.get("VolumesFrom") and not host.get("Devices"))
    _require(not host.get("PidMode") and host.get("IpcMode") in ("private", ""))
    networks = item["NetworkSettings"]["Networks"]
    _require(type(networks) is dict and len(networks) == 1)
    network = next(iter(networks.values()))
    _require(all(value is None for value in item["NetworkSettings"].get("Ports", {}).values()))
    aliases = network.get("Aliases") or []
    _require(("postgres" in aliases) is (not runtime))
    mounts = item["Mounts"]
    _require(type(mounts) is list and len(mounts) == (2 if runtime else 1))
    by_destination = {mount["Destination"]: mount for mount in mounts}
    if runtime:
        _require(host["ReadonlyRootfs"] is True and host.get("CapDrop") == ["ALL"])
        security = host.get("SecurityOpt") or []
        _require(
            not host.get("CapAdd")
            and any(value in security for value in ("no-new-privileges", "no-new-privileges:true"))
        )
        _require(not any("unconfined" in value for value in security))
        _require(re.fullmatch(r"[1-9][0-9]*(?::[1-9][0-9]*)?", item["Config"]["User"]) is not None)
        _require(
            not item["Config"].get("Entrypoint") and item["Config"]["Cmd"] == ["sleep", "infinity"]
        )
        # Do not pass credentials, provider settings or arbitrary runtime overrides.
        allowed = {
            "PATH",
            "LANG",
            "LC_ALL",
            "HOME",
            "PYTHON_VERSION",
            "PYTHON_SHA256",
            "GPG_KEY",
            "PYTHONUNBUFFERED",
            "PYTHONDONTWRITEBYTECODE",
        }
        entries = item["Config"].get("Env", [])
        environment = dict(entry.split("=", 1) for entry in entries)
        _require(len(environment) == len(entries) and set(environment) <= allowed)
        for name, value in environment.items():
            if name == "PATH":
                _require(
                    bool(value)
                    and set(value.split(":"))
                    <= {
                        "/usr/local/bin",
                        "/usr/local/sbin",
                        "/usr/sbin",
                        "/usr/bin",
                        "/sbin",
                        "/bin",
                    }
                )
            elif name == "HOME":
                _require(value == "/nonexistent")
            elif name in ("LANG", "LC_ALL"):
                _require(value in ("C", "C.UTF-8"))
            elif name == "PYTHON_VERSION":
                _require(re.fullmatch(r"3\.[0-9]+\.[0-9]+", value) is not None)
            elif name == "PYTHON_SHA256":
                _require(re.fullmatch(r"[0-9a-f]{64}", value) is not None)
            elif name == "GPG_KEY":
                _require(re.fullmatch(r"[0-9A-F]{40}", value) is not None)
            else:
                _require(value == "1")
        _require(set(by_destination) == {_INPUT, _OUTPUT})
        input_mount = by_destination[_INPUT]
        _require(input_mount["Type"] == "bind" and input_mount["RW"] is False)
        output = by_destination[_OUTPUT]
    else:
        _require(set(by_destination) == {"/var/lib/postgresql/data"})
        output = by_destination["/var/lib/postgresql/data"]
    _require(output["Type"] == "volume" and output["RW"] is True)
    return str(network["NetworkID"]), str(output["Name"])


def _topology(plan: OperatorEnvironmentPlan) -> dict[str, Any]:
    runtime = _inspect("container", plan.runtime_container_id)
    database = _inspect("container", plan.database_container_id)
    network_id, output_volume = _container(runtime, plan, runtime=True)
    database_network, database_volume = _container(database, plan, runtime=False)
    _require(network_id == database_network and output_volume != database_volume)
    _require(re.fullmatch(r"[a-f0-9]{64}", network_id) is not None)
    network = _inspect("network", network_id)
    _require(network["Id"] == network_id and network["Internal"] is True)
    _require(network["Driver"] == "bridge")
    _owned(network["Labels"], plan)
    _require(set(network["Containers"]) == {plan.runtime_container_id, plan.database_container_id})
    for name, container_id in (
        (output_volume, plan.runtime_container_id),
        (database_volume, plan.database_container_id),
    ):
        _require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name) is not None)
        volume = _inspect("volume", name)
        _require(
            volume["Name"] == name and volume["Driver"] == "local" and not volume.get("Options")
        )
        _owned(volume["Labels"], plan)
        consumer = _docker(
            "ps", "--all", "--no-trunc", "--filter", "volume=" + name, "--format", "{{json .ID}}"
        )
        _require(consumer == container_id)
    # Exclude uptime/health counters. Bind the actual security-relevant configuration.
    containers = [
        {
            key: (
                sorted(item[key], key=lambda mount: mount["Destination"])
                if key == "Mounts"
                else item[key]
            )
            for key in ("Id", "Image", "Config", "HostConfig", "Mounts", "NetworkSettings")
        }
        for item in (runtime, database)
    ]
    return {
        "configuration_sha256": _hash(_bytes(containers)),
        "network_sha256": _hash(_bytes(network)),
        "network_id": network_id,
        "output_volume": output_volume,
        "database_volume": database_volume,
        "runtime_image": runtime["Image"],
        "database_image": database["Image"],
    }


def _runtime_observation(plan_document: str) -> dict[str, Any]:
    """Fixed read-only probe invoked inside the already-running runtime container."""
    import psycopg

    _require(sys.flags.isolated == 1)
    _require(Path(sys.executable).resolve() == Path(_RUNTIME_PYTHON).resolve())
    plan = OperatorEnvironmentPlan(**json.loads(plan_document))
    plan.to_document()
    installed = _installed_identity()
    _require(installed["build_sha"] == plan.expected_build_sha)
    bundle = verify_operator_input_bundle(_INPUT)
    approval = _approved_binding(bundle)
    _require(os.geteuid() != 0)
    root_fd = _open_root_directory(Path(_OUTPUT))
    try:
        info = os.fstat(root_fd)
        _require(info.st_uid == os.geteuid() and info.st_mode & 0o777 == 0o700)
        marker = _json_object(_read_regular_relative(root_fd, _MARKER, maximum=4096))
        _require(
            marker
            == {"attempt_id": plan.attempt_id, "owner_id": plan.owner_id, "project": plan.project}
        )
        output_identity = [info.st_dev, info.st_ino, info.st_uid, info.st_mode]
    finally:
        os.close(root_fd)
    with psycopg.connect(
        "host=postgres dbname=human_cos_operator user=postgres connect_timeout=3",
        options="-c statement_timeout=3000 -c default_transaction_read_only=on",
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_catalog.current_database()")
            _require(cursor.fetchone() == (_DATABASE,))
            cursor.execute(
                "SELECT target, owner_token FROM human_cos_operator.trial_ownership LIMIT 2"
            )
            _require(cursor.fetchall() == [(_DATABASE, plan.owner_id)])
    _require(_probe_outbound_connections())
    return {
        "installed": installed,
        "approval": approval,
        "output_identity": output_identity,
        "owner_marker_sha256": _hash(_bytes(marker)),
        "database_target": _DATABASE,
        "database_owner_id": plan.owner_id,
        "outbound_probes_denied": True,
    }


@dataclass(frozen=True, eq=False)
class VerifiedOperatorEnvironment:
    """Point-in-time observer provenance, never an execution or cleanup permit."""

    record_bytes: bytes

    def to_document(self) -> dict[str, Any]:
        binding = _OBSERVED.get(self)
        _require(binding is not None and self.record_bytes is binding)
        return _json_object(self.record_bytes)


_OBSERVED: WeakKeyDictionary[VerifiedOperatorEnvironment, bytes] = WeakKeyDictionary()


def observe_operator_environment(
    bundle: VerifiedOperatorBundle, plan: OperatorEnvironmentPlan
) -> VerifiedOperatorEnvironment:
    """Observe owned resources; reject unapproved input before any Docker operation."""
    try:
        expectations = plan.to_document()
        approval = _approved_binding(bundle)
        installed = _installed_identity()
        _require(installed["build_sha"] == plan.expected_build_sha)
        before = _topology(plan)
        observation = _docker(
            "exec",
            plan.runtime_container_id,
            _RUNTIME_PYTHON,
            "-I",
            "-c",
            "import json,sys; "
            "from human_cos.trial.operator_environment import _runtime_observation; "
            "print(json.dumps(_runtime_observation(sys.argv[1]),sort_keys=True))",
            _bytes(expectations).decode(),
        )
        _require(type(observation) is dict)
        _require(
            observation["installed"] == installed
            and observation["approval"] == json.loads(_bytes(approval))
        )
        _require(observation["outbound_probes_denied"] is True)
        _require(
            observation["database_target"] == _DATABASE
            and observation["database_owner_id"] == plan.owner_id
        )
        _require(before == _topology(plan))
        _require(approval == _approved_binding(bundle) and installed == _installed_identity())
        record = _bytes(
            {
                "version": "operator-environment-v1",
                "status": "PASS",
                "execution_authorized": False,
                "cleanup_authorized": False,
                "plan": expectations,
                "approval": approval,
                "topology": before,
                "observation": observation,
            }
        )
    except Exception:
        raise OperatorEnvironmentError(_ERROR) from None
    result = VerifiedOperatorEnvironment(record)
    _OBSERVED[result] = record
    return result


def revalidate_operator_environment(
    environment: VerifiedOperatorEnvironment,
    bundle: VerifiedOperatorBundle,
    plan: OperatorEnvironmentPlan,
) -> VerifiedOperatorEnvironment:
    """Reobserve before consumption; a historical PASS is not current isolation."""
    _require(type(environment) is VerifiedOperatorEnvironment)
    previous = environment.to_document()
    _require(previous["plan"] == plan.to_document())
    _require(previous["approval"] == json.loads(_bytes(_approved_binding(bundle))))
    current = observe_operator_environment(bundle, plan)
    _require(previous == current.to_document())
    return current
