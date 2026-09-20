"""TRIAL-SBX3 detached audit-bundle export and independent verification.

The exporter/verifier is a local evidence surface only. It grants no publication,
execution, Final Synthesis, Final Claim, Human Review, or Seal authority.
"""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .bundle import (
    _BOOTSTRAP_REGISTRY_ENTRY,
    _AuthenticatedCanonicalAdmission,
    _canonical_is_authenticated,
    _canonical_matches_provenance,
    _receipt_inventory_sha256,
)
from .contracts import (
    TRIAL_HARD_CAPS,
    TrialAttemptReceipt,
    TrialCanonicalAdmission,
    TrialCanonicalAdmissionStatus,
    TrialEnvironmentAdmission,
    TrialInputBundleReceipt,
    TrialManifest,
    TrialResult,
    TrialRuntimeStep,
    TrialStop,
    assert_environment_admission_binding,
    assert_trial_result_binding,
)

_AUDIT_VERSION = "trial-audit-v1"
_ALLOWED_ROOT = frozenset({"payload", "bundle_manifest.json", "bundle_address.sha256"})
_PAYLOAD_FILES = (
    "attempt.json",
    "input_bundle_receipt.json",
    "trial_manifest.json",
    "canonical_admission.json",
    "environment_admission.json",
    "runtime_trajectory.json",
    "trial_stop.json",
    "trial_result.json",
)
_AT_FDCWD = -100
_RENAME_NOREPLACE = 1


class TrialAuditError(ValueError):
    """An audit bundle is incomplete, unsafe, or fails typed lineage verification."""


@dataclass(frozen=True)
class TrialAuditRecord:
    attempt: TrialAttemptReceipt
    input_bundle_receipt: TrialInputBundleReceipt
    manifest: TrialManifest
    canonical_admission: TrialCanonicalAdmission
    environment: TrialEnvironmentAdmission
    runtime_trajectory: tuple[TrialRuntimeStep, ...]
    stop: TrialStop
    result: TrialResult
    bundle_address: str


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_bytes(document: Any) -> bytes:
    return (
        json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _write_exact(path: Path, value: bytes, *, maximum: int) -> None:
    if len(value) > maximum:
        raise TrialAuditError(f"audit file {path.name} exceeds hard cap")
    with path.open("xb") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())


def _publish_no_replace(temporary: Path, target: Path) -> None:
    """Atomically publish a complete directory without replacing any destination."""

    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise TrialAuditError("atomic no-replace directory publication is unavailable")
    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int
    result = renameat2(
        _AT_FDCWD,
        os.fsencode(temporary),
        _AT_FDCWD,
        os.fsencode(target),
        _RENAME_NOREPLACE,
    )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in (errno.EEXIST, errno.ENOTEMPTY):
        raise TrialAuditError("audit output root already exists")
    if error_number in (errno.ENOSYS, errno.EINVAL, errno.ENOTSUP):
        raise TrialAuditError("atomic no-replace directory publication is unavailable")
    raise OSError(error_number, os.strerror(error_number), target)


def _assert_package_canonical_record(
    receipt: TrialInputBundleReceipt,
    manifest: TrialManifest,
    canonical: TrialCanonicalAdmission,
) -> None:
    """Reconcile serialized PASS facts with the package-owned pre-SBX4 registry."""

    entry = _BOOTSTRAP_REGISTRY_ENTRY
    if canonical.status is not TrialCanonicalAdmissionStatus.PASS:
        raise TrialAuditError("audit canonical admission is not PASS")
    if not canonical.pre_freeze_admitted:
        raise TrialAuditError("audit canonical admission is not pre-freeze admitted")
    actual = (
        canonical.registry_entry_id,
        canonical.purpose,
        canonical.detached_input_address,
        canonical.case_id,
        canonical.case_revision,
        canonical.case_mode.value,
        canonical.source_commit_sha,
        canonical.protocol_version,
        manifest.manifest_hash,
        receipt.checksum_index_sha256,
        _receipt_inventory_sha256(receipt),
    )
    expected = (
        entry.entry_id,
        entry.purpose,
        entry.detached_input_address,
        entry.case_id,
        entry.case_revision,
        entry.case_mode,
        entry.source_commit_sha,
        entry.protocol_version,
        entry.manifest_hash,
        entry.checksum_index_sha256,
        entry.receipt_inventory_sha256,
    )
    if actual != expected:
        raise TrialAuditError("audit canonical admission does not match package-owned registry")


def _payload_documents(
    *,
    attempt: TrialAttemptReceipt,
    input_bundle_receipt: TrialInputBundleReceipt,
    manifest: TrialManifest,
    canonical_admission: _AuthenticatedCanonicalAdmission,
    environment: TrialEnvironmentAdmission,
    stop: TrialStop,
    result: TrialResult,
) -> dict[str, Any]:
    attempt.assert_integrity()
    input_bundle_receipt.assert_integrity()
    manifest.assert_integrity()
    canonical_admission.assert_integrity()
    environment.assert_integrity()
    stop.assert_integrity()
    result.assert_integrity()
    if not _canonical_is_authenticated(canonical_admission):
        raise TrialAuditError("audit export requires package-authenticated canonical admission")
    if not _canonical_matches_provenance(
        canonical_admission,
        attempt_receipt_hash=attempt.attempt_receipt_hash,
        manifest_hash=manifest.manifest_hash,
        bundle_receipt_hash=input_bundle_receipt.bundle_receipt_hash,
    ):
        raise TrialAuditError("audit canonical provenance differs from supplied bundle")
    canonical = canonical_admission.record
    _assert_package_canonical_record(input_bundle_receipt, manifest, canonical)
    assert_environment_admission_binding(attempt, manifest, canonical, environment)
    assert_trial_result_binding(attempt, manifest, environment, stop, result)
    if input_bundle_receipt.attempt_receipt_hash != attempt.attempt_receipt_hash:
        raise TrialAuditError("input bundle receipt does not bind exact Attempt Receipt")
    if canonical.bundle_receipt_hash != input_bundle_receipt.bundle_receipt_hash:
        raise TrialAuditError("canonical admission does not bind exact input bundle receipt")
    if canonical.canonical_admission_hash != environment.canonical_admission_hash:
        raise TrialAuditError("Environment Admission does not bind exact canonical admission")
    if result.runtime_trajectory != stop.runtime_trajectory:
        raise TrialAuditError("TrialResult trajectory differs from TrialStop trajectory")
    return {
        "attempt.json": attempt.to_document(),
        "input_bundle_receipt.json": input_bundle_receipt.to_document(),
        "trial_manifest.json": manifest.to_document(),
        "canonical_admission.json": canonical.to_document(),
        "environment_admission.json": environment.to_document(),
        "runtime_trajectory.json": [item.to_document() for item in result.runtime_trajectory],
        "trial_stop.json": stop.to_document(),
        "trial_result.json": result.to_document(),
    }


def export_audit_bundle(
    output_root: str | os.PathLike[str],
    *,
    attempt: TrialAttemptReceipt,
    input_bundle_receipt: TrialInputBundleReceipt,
    manifest: TrialManifest,
    canonical_admission: _AuthenticatedCanonicalAdmission,
    environment: TrialEnvironmentAdmission,
    stop: TrialStop,
    result: TrialResult,
) -> str:
    """Export one detached local audit bundle without replacing any destination."""

    target = Path(output_root)
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    documents = _payload_documents(
        attempt=attempt,
        input_bundle_receipt=input_bundle_receipt,
        manifest=manifest,
        canonical_admission=canonical_admission,
        environment=environment,
        stop=stop,
        result=result,
    )
    temporary = Path(tempfile.mkdtemp(prefix=f".{target.name}.tmp-", dir=parent))
    try:
        payload_limit = min(
            TRIAL_HARD_CAPS.max_audit_payload_bytes,
            manifest.resource_limits.max_audit_payload_bytes,
        )
        payload = temporary / "payload"
        payload.mkdir()
        manifest_entries: list[dict[str, Any]] = []
        total = 0
        for name in _PAYLOAD_FILES:
            value = _json_bytes(documents[name])
            total += len(value)
            if total > payload_limit:
                raise TrialAuditError("audit payload exceeds Manifest audit payload ceiling")
            _write_exact(payload / name, value, maximum=payload_limit)
            manifest_entries.append(
                {"path": f"payload/{name}", "size_bytes": len(value), "sha256": _sha256(value)}
            )
        bundle_manifest = _json_bytes({"audit_version": _AUDIT_VERSION, "files": manifest_entries})
        _write_exact(
            temporary / "bundle_manifest.json",
            bundle_manifest,
            maximum=TRIAL_HARD_CAPS.max_audit_payload_bytes,
        )
        address = _sha256(bundle_manifest)
        _write_exact(
            temporary / "bundle_address.sha256",
            (address + "\n").encode("ascii"),
            maximum=128,
        )
        _publish_no_replace(temporary, target)
        return address
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _read_regular(path: Path, *, maximum: int) -> bytes:
    try:
        before = path.lstat()
    except OSError as exc:
        raise TrialAuditError(f"cannot stat audit file {path.name}: {exc}") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise TrialAuditError(f"audit file {path.name} must be one regular non-linked file")
    if before.st_size > maximum:
        raise TrialAuditError(f"audit file {path.name} exceeds hard cap")
    try:
        value = path.read_bytes()
    except OSError as exc:
        raise TrialAuditError(f"cannot read audit file {path.name}: {exc}") from exc
    after = path.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise TrialAuditError(f"audit file {path.name} changed while being read")
    return value


def _load_json_bytes(name: str, value: bytes) -> Any:
    try:
        return json.loads(value)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrialAuditError(f"audit file {name} is not valid JSON") from exc


def verify_audit_bundle(input_root: str | os.PathLike[str]) -> TrialAuditRecord:
    """Independently verify detached address, exact inventory, typed objects, and lineage."""

    root = Path(input_root)
    try:
        root_stat = root.lstat()
    except OSError as exc:
        raise TrialAuditError(f"cannot stat audit root: {exc}") from exc
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        raise TrialAuditError("audit root must be a non-link directory")
    try:
        root_entries = {item.name for item in root.iterdir()}
    except OSError as exc:
        raise TrialAuditError(f"cannot list audit root: {exc}") from exc
    if root_entries != _ALLOWED_ROOT:
        raise TrialAuditError("audit root inventory differs from frozen structure")
    payload = root / "payload"
    try:
        payload_stat = payload.lstat()
    except OSError as exc:
        raise TrialAuditError(f"cannot stat audit payload: {exc}") from exc
    if stat.S_ISLNK(payload_stat.st_mode) or not stat.S_ISDIR(payload_stat.st_mode):
        raise TrialAuditError("audit payload must be a non-link directory")
    try:
        payload_entries = {item.name for item in payload.iterdir()}
    except OSError as exc:
        raise TrialAuditError(f"cannot list audit payload: {exc}") from exc
    if payload_entries != set(_PAYLOAD_FILES):
        raise TrialAuditError("audit payload inventory differs from frozen structure")

    manifest_bytes = _read_regular(
        root / "bundle_manifest.json", maximum=TRIAL_HARD_CAPS.max_audit_payload_bytes
    )
    address_bytes = _read_regular(root / "bundle_address.sha256", maximum=128)
    expected_address = _sha256(manifest_bytes)
    try:
        address = address_bytes.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise TrialAuditError("bundle address must be ASCII") from exc
    if address != expected_address:
        raise TrialAuditError("detached audit-bundle address mismatch")
    try:
        bundle_manifest = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrialAuditError("bundle manifest is invalid JSON") from exc
    if (
        not isinstance(bundle_manifest, dict)
        or bundle_manifest.get("audit_version") != _AUDIT_VERSION
    ):
        raise TrialAuditError("unsupported audit bundle manifest")
    files = bundle_manifest.get("files")
    if not isinstance(files, list) or len(files) != len(_PAYLOAD_FILES):
        raise TrialAuditError("bundle manifest file inventory is invalid")
    seen: set[str] = set()
    payload_values: dict[str, bytes] = {}
    total_payload_bytes = 0
    for item in files:
        if not isinstance(item, dict):
            raise TrialAuditError("bundle manifest entry is invalid")
        path = item.get("path")
        size = item.get("size_bytes")
        digest = item.get("sha256")
        if not isinstance(path, str) or not path.startswith("payload/"):
            raise TrialAuditError("bundle manifest path escapes payload")
        name = path.removeprefix("payload/")
        if name not in _PAYLOAD_FILES or name in seen:
            raise TrialAuditError("bundle manifest contains unexpected or duplicate path")
        seen.add(name)
        value = _read_regular(payload / name, maximum=TRIAL_HARD_CAPS.max_audit_payload_bytes)
        total_payload_bytes += len(value)
        if total_payload_bytes > TRIAL_HARD_CAPS.max_audit_payload_bytes:
            raise TrialAuditError("audit payload exceeds code-owned hard cap")
        if size != len(value) or digest != _sha256(value):
            raise TrialAuditError(f"audit payload integrity mismatch for {name}")
        payload_values[name] = value
    if seen != set(_PAYLOAD_FILES):
        raise TrialAuditError("bundle manifest omits required payload files")

    manifest = TrialManifest.model_validate(
        _load_json_bytes("trial_manifest.json", payload_values["trial_manifest.json"])
    )
    if total_payload_bytes > manifest.resource_limits.max_audit_payload_bytes:
        raise TrialAuditError("audit payload exceeds Manifest audit payload ceiling")
    attempt = TrialAttemptReceipt.model_validate(
        _load_json_bytes("attempt.json", payload_values["attempt.json"])
    )
    receipt = TrialInputBundleReceipt.model_validate(
        _load_json_bytes("input_bundle_receipt.json", payload_values["input_bundle_receipt.json"])
    )
    canonical = TrialCanonicalAdmission.model_validate(
        _load_json_bytes("canonical_admission.json", payload_values["canonical_admission.json"])
    )
    environment = TrialEnvironmentAdmission.model_validate(
        _load_json_bytes("environment_admission.json", payload_values["environment_admission.json"])
    )
    trajectory_document = _load_json_bytes(
        "runtime_trajectory.json", payload_values["runtime_trajectory.json"]
    )
    if not isinstance(trajectory_document, list):
        raise TrialAuditError("runtime trajectory must be a JSON array")
    trajectory = tuple(TrialRuntimeStep.model_validate(item) for item in trajectory_document)
    stop = TrialStop.model_validate(
        _load_json_bytes("trial_stop.json", payload_values["trial_stop.json"])
    )
    result = TrialResult.model_validate(
        _load_json_bytes("trial_result.json", payload_values["trial_result.json"])
    )

    attempt.assert_integrity()
    receipt.assert_integrity()
    manifest.assert_integrity()
    canonical.assert_integrity()
    environment.assert_integrity()
    stop.assert_integrity()
    result.assert_integrity()
    _assert_package_canonical_record(receipt, manifest, canonical)
    assert_environment_admission_binding(attempt, manifest, canonical, environment)
    if (
        tuple(result.runtime_trajectory) != trajectory
        or tuple(stop.runtime_trajectory) != trajectory
    ):
        raise TrialAuditError("typed runtime trajectory differs from audit trajectory payload")
    assert_trial_result_binding(attempt, manifest, environment, stop, result)
    if receipt.attempt_receipt_hash != attempt.attempt_receipt_hash:
        raise TrialAuditError("verified input receipt does not bind Attempt Receipt")
    if canonical.bundle_receipt_hash != receipt.bundle_receipt_hash:
        raise TrialAuditError("verified canonical admission does not bind input receipt")
    if environment.canonical_admission_hash != canonical.canonical_admission_hash:
        raise TrialAuditError("verified Environment Admission does not bind canonical admission")
    return TrialAuditRecord(
        attempt=attempt,
        input_bundle_receipt=receipt,
        manifest=manifest,
        canonical_admission=canonical,
        environment=environment,
        runtime_trajectory=trajectory,
        stop=stop,
        result=result,
        bundle_address=address,
    )
