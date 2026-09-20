"""Detached TRIAL-SBX input verification and private pre-freeze admission.

Generic verification proves bytes, structure, and typed semantics only. It grants no
execution authority. The private pre-freeze gate admits exactly one package-owned
synthetic bootstrap descriptor.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from weakref import ReferenceType, WeakKeyDictionary, ref

import yaml

from human_cos.core.models import Case, Evidence, parse_case, parse_evidence
from human_cos.models.profile import ModelProfile, parse_model_profile
from human_cos.runtime.run import canonical_document_sha256

from .contracts import (
    TRIAL_HARD_CAPS,
    TrialAcceptanceOracle,
    TrialAcceptanceOraclePayload,
    TrialAttemptReceipt,
    TrialAttemptReceiptPayload,
    TrialCanonicalAdmission,
    TrialCanonicalAdmissionPayload,
    TrialCanonicalAdmissionStatus,
    TrialCanonicalPurpose,
    TrialDataClass,
    TrialDocumentKind,
    TrialEnvironmentAdmission,
    TrialInputBundleReceipt,
    TrialInputBundleReceiptPayload,
    TrialInputFileReceipt,
    TrialManifest,
    TrialManifestPayload,
    TrialMockOutputFixture,
    TrialMockOutputFixturePayload,
    freeze_trial_acceptance_oracle,
    freeze_trial_attempt_receipt,
    freeze_trial_canonical_admission,
    freeze_trial_input_bundle_receipt,
    freeze_trial_manifest,
    freeze_trial_mock_output_fixture,
)


class TrialBundleError(ValueError):
    """The detached trial input package is unsafe, incomplete, or non-canonical."""


@dataclass(frozen=True)
class TrialExecutionInputs:
    case: Case
    evidence: tuple[Evidence, ...]
    model_profiles: tuple[ModelProfile, ...]
    expert_fixtures: tuple[dict[str, Any], ...]
    mock_outputs: tuple[TrialMockOutputFixture, ...]


_VERIFICATION_SENTINEL = object()


@dataclass(frozen=True)
class VerifiedTrialBundle:
    attempt: TrialAttemptReceipt
    receipt: TrialInputBundleReceipt
    manifest: TrialManifest
    execution_inputs: TrialExecutionInputs
    acceptance_oracle: TrialAcceptanceOracle
    payload_documents_sha256: str
    _verification_proof: object = field(repr=False, compare=False)

    def assert_integrity(self) -> None:
        self.attempt.assert_integrity()
        self.receipt.assert_integrity()
        self.manifest.assert_integrity()
        self.acceptance_oracle.assert_integrity()
        if self._verification_proof is not _VERIFICATION_SENTINEL:
            raise TrialBundleError("VerifiedTrialBundle lacks verifier-owned provenance")
        if self.receipt.attempt_receipt_hash != self.attempt.attempt_receipt_hash:
            raise TrialBundleError("bundle receipt does not bind exact Attempt Receipt")
        if self.attempt.detached_input_address is not None and (
            self.attempt.detached_input_address != self.receipt.detached_input_address
        ):
            raise TrialBundleError("Attempt Receipt detached address differs from bundle")
        expected_documents = canonical_document_sha256(
            {
                item.path: item.sha256
                for item in sorted(self.receipt.files, key=lambda item: item.path)
            }
        )
        if self.payload_documents_sha256 != expected_documents:
            raise TrialBundleError("payload document digest does not match verified receipt")
        case = self.execution_inputs.case
        if (case.case_id, case.revision, case.case_mode, case.protocol_version) != (
            self.manifest.case_id,
            self.manifest.case_revision,
            self.manifest.case_mode.value,
            self.manifest.protocol_version,
        ):
            raise TrialBundleError("Case identity differs from Trial Manifest")
        if any(item.case_id != case.case_id for item in self.execution_inputs.evidence):
            raise TrialBundleError("Evidence belongs to a different Case")
        if any(item.provider != "mock" for item in self.execution_inputs.model_profiles):
            raise TrialBundleError("TRIAL-SBX1 permits only model profiles with provider='mock'")


@dataclass(frozen=True)
class _CanonicalRegistryEntry:
    entry_id: str
    purpose: TrialCanonicalPurpose
    detached_input_address: str
    checksum_index_sha256: str
    receipt_inventory_sha256: str
    payload_documents_sha256: str
    case_id: str
    case_revision: int
    case_mode: str
    manifest_hash: str
    semantic_fingerprint: str
    source_commit_sha: str
    protocol_version: str


@dataclass(frozen=True)
class _CanonicalProvenance:
    proof: object
    canonical_admission_hash: str
    attempt_receipt_hash: str
    bundle_receipt_hash: str
    manifest_hash: str
    receipt_inventory_sha256: str
    payload_documents_sha256: str
    semantic_fingerprint: str


@dataclass(frozen=True, eq=False)
class _AuthenticatedCanonicalAdmission:
    record: TrialCanonicalAdmission
    attempt_receipt_hash: str
    bundle_receipt_hash: str
    manifest_hash: str
    receipt_inventory_sha256: str
    payload_documents_sha256: str
    semantic_fingerprint: str
    _proof: object | None = field(default=None, init=False, repr=False, compare=False)

    def assert_integrity(self) -> None:
        self.record.assert_integrity()
        provenance = _CANONICAL_PROVENANCE.get(self)
        if provenance is None or self._proof is None or provenance.proof is not self._proof:
            raise TrialBundleError("canonical admission lacks package-owned provenance")
        actual = (
            self.record.canonical_admission_hash,
            self.attempt_receipt_hash,
            self.bundle_receipt_hash,
            self.manifest_hash,
            self.receipt_inventory_sha256,
            self.payload_documents_sha256,
            self.semantic_fingerprint,
        )
        expected = (
            provenance.canonical_admission_hash,
            provenance.attempt_receipt_hash,
            provenance.bundle_receipt_hash,
            provenance.manifest_hash,
            provenance.receipt_inventory_sha256,
            provenance.payload_documents_sha256,
            provenance.semantic_fingerprint,
        )
        if actual != expected:
            raise TrialBundleError("canonical admission differs from registered provenance")
        if self.record.bundle_receipt_hash != self.bundle_receipt_hash:
            raise TrialBundleError("canonical provenance differs from bundle receipt")
        if self.record.status is TrialCanonicalAdmissionStatus.PASS:
            if not self.record.pre_freeze_admitted:
                raise TrialBundleError("canonical PASS is not pre-freeze admitted")
            if self.record.registry_entry_id != _BOOTSTRAP_REGISTRY_ENTRY.entry_id:
                raise TrialBundleError("canonical PASS registry entry is not package-owned")
            if self.semantic_fingerprint != _BOOTSTRAP_REGISTRY_ENTRY.semantic_fingerprint:
                raise TrialBundleError("canonical PASS semantic fingerprint is not package-owned")

    @property
    def status(self) -> TrialCanonicalAdmissionStatus:
        return self.record.status

    @property
    def pre_freeze_admitted(self) -> bool:
        return self.record.pre_freeze_admitted

    @property
    def data_class(self) -> TrialDataClass:
        return self.record.data_class


_CANONICAL_PROVENANCE: WeakKeyDictionary[_AuthenticatedCanonicalAdmission, _CanonicalProvenance] = (
    WeakKeyDictionary()
)


@dataclass(frozen=True)
class _EnvironmentProvenance:
    environment_ref: ReferenceType[TrialEnvironmentAdmission]
    environment_admission_hash: str
    canonical_admission_hash: str


_ENVIRONMENT_PROVENANCE: dict[int, _EnvironmentProvenance] = {}


def _register_environment_provenance(
    environment: TrialEnvironmentAdmission,
    canonical: _AuthenticatedCanonicalAdmission,
) -> None:
    """Bind the exact evaluator-produced Environment to package provenance."""

    canonical.assert_integrity()
    environment.assert_integrity()
    if environment.canonical_admission_hash != canonical.record.canonical_admission_hash:
        raise TrialBundleError("Environment provenance differs from canonical admission")
    environment_id = id(environment)

    def remove_dead_environment(
        dead_ref: ReferenceType[TrialEnvironmentAdmission],
    ) -> None:
        current = _ENVIRONMENT_PROVENANCE.get(environment_id)
        if current is not None and current.environment_ref is dead_ref:
            _ENVIRONMENT_PROVENANCE.pop(environment_id, None)

    _ENVIRONMENT_PROVENANCE[environment_id] = _EnvironmentProvenance(
        environment_ref=ref(environment, remove_dead_environment),
        environment_admission_hash=environment.environment_admission_hash,
        canonical_admission_hash=canonical.record.canonical_admission_hash,
    )


def _assert_environment_provenance(
    environment: TrialEnvironmentAdmission,
    canonical: _AuthenticatedCanonicalAdmission,
) -> None:
    canonical.assert_integrity()
    environment.assert_integrity()
    provenance = _ENVIRONMENT_PROVENANCE.get(id(environment))
    if provenance is None or provenance.environment_ref() is not environment:
        raise TrialBundleError("Environment lacks package-owned evaluator provenance")
    if (
        environment.environment_admission_hash,
        canonical.record.canonical_admission_hash,
    ) != (
        provenance.environment_admission_hash,
        provenance.canonical_admission_hash,
    ):
        raise TrialBundleError("Environment differs from registered package provenance")


def _register_canonical_provenance(value: _AuthenticatedCanonicalAdmission) -> None:
    proof = object()
    object.__setattr__(value, "_proof", proof)
    _CANONICAL_PROVENANCE[value] = _CanonicalProvenance(
        proof=proof,
        canonical_admission_hash=value.record.canonical_admission_hash,
        attempt_receipt_hash=value.attempt_receipt_hash,
        bundle_receipt_hash=value.bundle_receipt_hash,
        manifest_hash=value.manifest_hash,
        receipt_inventory_sha256=value.receipt_inventory_sha256,
        payload_documents_sha256=value.payload_documents_sha256,
        semantic_fingerprint=value.semantic_fingerprint,
    )


def _canonical_record(
    value: TrialCanonicalAdmission | _AuthenticatedCanonicalAdmission,
) -> TrialCanonicalAdmission:
    if isinstance(value, _AuthenticatedCanonicalAdmission):
        return value.record
    return value


def _canonical_is_authenticated(
    value: TrialCanonicalAdmission | _AuthenticatedCanonicalAdmission,
) -> bool:
    if not isinstance(value, _AuthenticatedCanonicalAdmission):
        return False
    try:
        value.assert_integrity()
    except (TrialBundleError, ValueError):
        return False
    return True


def _canonical_matches_provenance(
    value: TrialCanonicalAdmission | _AuthenticatedCanonicalAdmission,
    *,
    attempt_receipt_hash: str,
    manifest_hash: str,
    bundle_receipt_hash: str | None = None,
) -> bool:
    if not _canonical_is_authenticated(value):
        return False
    assert isinstance(value, _AuthenticatedCanonicalAdmission)
    return (
        value.attempt_receipt_hash == attempt_receipt_hash
        and value.manifest_hash == manifest_hash
        and (bundle_receipt_hash is None or value.bundle_receipt_hash == bundle_receipt_hash)
    )


_ALLOWED_ROOT_ENTRIES = frozenset({"payload", "checksums.sha256", "input_address.sha256"})
_MANIFEST_PATH = "payload/trial_manifest.yaml"
_CASE_PATH = "payload/case.yaml"
_EXPECTED_PATH = "payload/expected_outcome.yaml"
_INVENTORY_POLICY_VERSION = "trial-input-v1"
_BOOTSTRAP_SOURCE_COMMIT = "f4f596b6f00d3fbd71c45464f4f33fbb2b48876d"
_READ_CHUNK = 65_536


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _typed_canonical_sha256(document: Any) -> str:
    return str(canonical_document_sha256(document))


def _canonical_json_bytes(document: dict[str, Any]) -> bytes:
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


def _safe_fingerprint(path: Path) -> str:
    resolved = os.path.realpath(os.fspath(path))
    return "root:" + _sha256_bytes(resolved.encode("utf-8"))


def _directory_flags() -> int:
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise TrialBundleError("descriptor-relative no-follow traversal is unavailable")
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def _file_flags() -> int:
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_PATH"):
        raise TrialBundleError("non-activating no-follow file descriptors are unavailable")
    return os.O_PATH | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def _open_pinned_regular_file(parent_fd: int, name: str) -> int:
    """Inspect without activating a device; reopen only the pinned regular inode.

    Linux O_PATH and procfs are required. Do not fall back to opening an untrusted
    path for reading when these primitives are unavailable.
    """
    listed = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if not stat.S_ISREG(listed.st_mode) or listed.st_nlink != 1:
        raise TrialBundleError("input must be one non-hard-linked regular file")
    pinned_fd = os.open(name, _file_flags(), dir_fd=parent_fd)
    try:
        pinned = os.fstat(pinned_fd)
        if not stat.S_ISREG(pinned.st_mode) or _file_identity(pinned) != _file_identity(listed):
            raise TrialBundleError("input changed before non-activating type verification")
        # This is a kernel descriptor reference, never an operator-provided link.
        fd = os.open(
            f"/proc/self/fd/{pinned_fd}",
            os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0),
        )
        try:
            if _file_identity(os.fstat(fd)) != _file_identity(pinned):
                raise TrialBundleError("input changed while reopening its pinned descriptor")
        except Exception:
            os.close(fd)
            raise
        return fd
    finally:
        os.close(pinned_fd)


def _open_root_directory(root: Path, *, expected: os.stat_result | None = None) -> int:
    try:
        lst = root.lstat()
    except OSError as exc:
        raise TrialBundleError(f"cannot stat input root: {exc}") from exc
    if stat.S_ISLNK(lst.st_mode) or not stat.S_ISDIR(lst.st_mode):
        raise TrialBundleError("input root must be a non-link directory")
    try:
        fd = os.open(root, _directory_flags())
    except OSError as exc:
        raise TrialBundleError(f"cannot open input root safely: {exc}") from exc
    opened = os.fstat(fd)
    observed = (opened.st_dev, opened.st_ino, opened.st_mtime_ns)
    current = (lst.st_dev, lst.st_ino, lst.st_mtime_ns)
    if observed != current:
        os.close(fd)
        raise TrialBundleError("input root changed while being opened")
    if expected is not None and observed != (
        expected.st_dev,
        expected.st_ino,
        expected.st_mtime_ns,
    ):
        os.close(fd)
        raise TrialBundleError("input root changed after inventory scan")
    return fd


def _open_parent_directory(root_fd: int, parts: tuple[str, ...]) -> int:
    current = os.dup(root_fd)
    try:
        for component in parts:
            try:
                child = os.open(component, _directory_flags(), dir_fd=current)
            except OSError as exc:
                raise TrialBundleError(
                    f"payload parent component {component!r} cannot be opened safely: {exc}"
                ) from exc
            opened = os.fstat(child)
            if not stat.S_ISDIR(opened.st_mode):
                os.close(child)
                raise TrialBundleError("payload parent component is not a directory")
            os.close(current)
            current = child
        return current
    except Exception:
        os.close(current)
        raise


def _read_regular_relative(
    root_fd: int,
    relative: str,
    *,
    maximum: int,
    expected_stat: os.stat_result | None = None,
) -> bytes:
    parts = PurePosixPath(relative).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise TrialBundleError("unsafe relative file path")
    parent_fd = _open_parent_directory(root_fd, tuple(parts[:-1]))
    try:
        try:
            fd = _open_pinned_regular_file(parent_fd, parts[-1])
        except OSError as exc:
            raise TrialBundleError(f"cannot open {relative} safely: {exc}") from exc
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise TrialBundleError(f"{relative} must be one non-hard-linked regular file")
            if expected_stat is not None:
                identity = (
                    before.st_dev,
                    before.st_ino,
                    before.st_size,
                    before.st_mtime_ns,
                )
                expected_identity = (
                    expected_stat.st_dev,
                    expected_stat.st_ino,
                    expected_stat.st_size,
                    expected_stat.st_mtime_ns,
                )
                if identity != expected_identity:
                    raise TrialBundleError(f"{relative} changed after inventory scan")
            if before.st_size > maximum:
                raise TrialBundleError(f"{relative} exceeds byte hard cap")
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(fd, min(_READ_CHUNK, maximum + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > maximum:
                    raise TrialBundleError(f"{relative} exceeds byte hard cap")
            after = os.fstat(fd)
            if (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            ) != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ):
                raise TrialBundleError(f"{relative} changed while being read")
            return b"".join(chunks)
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def _read_small_regular_file(root: Path, relative: str, *, maximum: int) -> bytes:
    root_fd = _open_root_directory(root)
    try:
        return _read_regular_relative(root_fd, relative, maximum=maximum)
    finally:
        os.close(root_fd)


def _try_detached_address(root: Path) -> str | None:
    try:
        index = _read_small_regular_file(
            root, "checksums.sha256", maximum=TRIAL_HARD_CAPS.max_file_bytes
        )
        address_bytes = _read_small_regular_file(root, "input_address.sha256", maximum=256)
        text = address_bytes.decode("ascii").strip()
        if len(text) != 64 or any(c not in "0123456789abcdef" for c in text):
            return None
        return text if text == _sha256_bytes(index) else None
    except (OSError, UnicodeError, TrialBundleError):
        return None


def begin_trial_attempt(
    input_root: str | os.PathLike[str],
    *,
    attempt_id: str,
    started_at: datetime,
) -> TrialAttemptReceipt:
    root = Path(input_root)
    return freeze_trial_attempt_receipt(
        TrialAttemptReceiptPayload(
            attempt_id=attempt_id,
            sanitized_input_root_fingerprint=_safe_fingerprint(root),
            detached_input_address=_try_detached_address(root),
            started_at=started_at,
        )
    )


def _normalize_index_path(raw: str) -> str:
    if not raw or "\\" in raw or raw.startswith("/"):
        raise TrialBundleError("checksum path must be a non-empty relative POSIX path")
    pure = PurePosixPath(raw)
    if any(part in {"", ".", ".."} for part in pure.parts):
        raise TrialBundleError("checksum path contains traversal or non-normal components")
    normalized = pure.as_posix()
    if normalized != raw or not normalized.startswith("payload/"):
        raise TrialBundleError("checksum path must be normalized and remain under payload/")
    return normalized


def _parse_checksum_index(index_bytes: bytes) -> dict[str, str]:
    try:
        text = index_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TrialBundleError("checksum index must be UTF-8") from exc
    entries: dict[str, str] = {}
    folded_paths: set[str] = set()
    for number, line in enumerate(text.splitlines(), start=1):
        if not line:
            raise TrialBundleError(f"checksum index line {number} is empty")
        if len(line) < 67 or line[64:66] != "  ":
            raise TrialBundleError(f"checksum index line {number} has invalid format")
        digest = line[:64]
        if any(c not in "0123456789abcdef" for c in digest):
            raise TrialBundleError(f"checksum index line {number} has invalid digest")
        path = _normalize_index_path(line[66:])
        folded = path.casefold()
        if path in entries or folded in folded_paths:
            raise TrialBundleError("checksum index contains duplicate/normalized collision")
        entries[path] = digest
        folded_paths.add(folded)
        if len(entries) > TRIAL_HARD_CAPS.max_payload_files:
            raise TrialBundleError("checksum index exceeds payload file hard cap")
    if not entries:
        raise TrialBundleError("checksum index is empty")
    return entries


def _walk_error(error: OSError) -> None:
    raise TrialBundleError(f"cannot read payload directory: {error}") from error


def _scan_payload(payload: Path) -> dict[str, os.stat_result]:
    try:
        root_stat = payload.lstat()
    except OSError as exc:
        raise TrialBundleError(f"cannot stat payload directory: {exc}") from exc
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        raise TrialBundleError("payload must be a non-link directory")
    found: dict[str, os.stat_result] = {}
    folded: set[str] = set()
    for directory, dirnames, filenames in os.walk(
        payload, topdown=True, followlinks=False, onerror=_walk_error
    ):
        current = Path(directory)
        dirnames.sort()
        filenames.sort()
        for dirname in tuple(dirnames):
            candidate = current / dirname
            try:
                entry_stat = candidate.lstat()
            except OSError as exc:
                raise TrialBundleError(f"cannot stat payload directory entry: {exc}") from exc
            if stat.S_ISLNK(entry_stat.st_mode) or not stat.S_ISDIR(entry_stat.st_mode):
                raise TrialBundleError("payload directories must be non-link directories")
        for filename in filenames:
            if len(found) >= TRIAL_HARD_CAPS.max_payload_files:
                raise TrialBundleError("payload file hard cap exceeded during traversal")
            candidate = current / filename
            try:
                entry_stat = candidate.lstat()
            except OSError as exc:
                raise TrialBundleError(f"cannot stat payload file: {exc}") from exc
            if stat.S_ISLNK(entry_stat.st_mode) or not stat.S_ISREG(entry_stat.st_mode):
                raise TrialBundleError("payload entries must be non-link regular files")
            if entry_stat.st_nlink != 1:
                raise TrialBundleError("payload files must not be hard-linked")
            relative = candidate.relative_to(payload.parent).as_posix()
            normalized = _normalize_index_path(relative)
            if normalized.casefold() in folded:
                raise TrialBundleError("payload contains normalized-path collision")
            found[normalized] = entry_stat
            folded.add(normalized.casefold())
    return found


def _file_identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_nlink,
    )


def _verify_payload_bytes(root: Path, entries: dict[str, str]) -> dict[str, bytes]:
    try:
        root_before = root.lstat()
    except OSError as exc:
        raise TrialBundleError(f"cannot stat input root: {exc}") from exc
    scanned = _scan_payload(root / "payload")
    if set(scanned) != set(entries):
        missing = sorted(set(entries).difference(scanned))
        extra = sorted(set(scanned).difference(entries))
        raise TrialBundleError(f"payload inventory mismatch; missing={missing}, extra={extra}")
    root_fd = _open_root_directory(root, expected=root_before)
    try:
        total = 0
        payload_bytes: dict[str, bytes] = {}
        for relative in sorted(entries):
            content = _read_regular_relative(
                root_fd,
                relative,
                maximum=TRIAL_HARD_CAPS.max_file_bytes,
                expected_stat=scanned[relative],
            )
            total += len(content)
            if total > TRIAL_HARD_CAPS.max_total_payload_bytes:
                raise TrialBundleError("payload exceeds total byte hard cap")
            if _sha256_bytes(content) != entries[relative]:
                raise TrialBundleError(f"payload digest mismatch for {relative}")
            payload_bytes[relative] = content
        rescanned = _scan_payload(root / "payload")
        if set(rescanned) != set(scanned):
            raise TrialBundleError("payload inventory changed after verified reads")
        for relative in sorted(scanned):
            if _file_identity(rescanned[relative]) != _file_identity(scanned[relative]):
                raise TrialBundleError(f"{relative} changed after verified reads")
        return payload_bytes
    finally:
        os.close(root_fd)


def _load_document(content: bytes, *, path: str) -> dict[str, Any]:
    try:
        if path.endswith(".json"):
            value = json.loads(content.decode("utf-8"))
        elif path.endswith((".yaml", ".yml")):
            value = yaml.safe_load(content.decode("utf-8"))
        else:
            raise TrialBundleError(f"unsupported trial document extension: {path}")
    except (UnicodeDecodeError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise TrialBundleError(f"cannot parse verified document {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise TrialBundleError(f"trial document {path} must contain one mapping/object")
    return value


def _kind_for(path: str) -> TrialDocumentKind:
    if path == _MANIFEST_PATH:
        return TrialDocumentKind.TRIAL_MANIFEST
    if path == _CASE_PATH:
        return TrialDocumentKind.CASE
    if path == _EXPECTED_PATH:
        return TrialDocumentKind.EXPECTED_OUTCOME
    if path.startswith("payload/evidence/"):
        return TrialDocumentKind.EVIDENCE
    if path.startswith("payload/model_profiles/"):
        return TrialDocumentKind.MODEL_PROFILE
    if path.startswith("payload/expert_fixtures/"):
        return TrialDocumentKind.EXPERT_FIXTURE
    if path.startswith("payload/mock_outputs/"):
        return TrialDocumentKind.MOCK_OUTPUT
    return TrialDocumentKind.OTHER


def _require_paths(payload_bytes: dict[str, bytes]) -> None:
    for required in (_MANIFEST_PATH, _CASE_PATH, _EXPECTED_PATH):
        if required not in payload_bytes:
            raise TrialBundleError(f"required payload document is missing: {required}")
    unknown = [path for path in payload_bytes if _kind_for(path) is TrialDocumentKind.OTHER]
    if unknown:
        raise TrialBundleError(f"unsupported payload paths: {sorted(unknown)}")


def _semantic_fingerprint(
    *,
    manifest: TrialManifest,
    execution_inputs: TrialExecutionInputs,
    oracle: TrialAcceptanceOracle,
) -> str:
    return _typed_canonical_sha256(
        {
            "manifest": manifest.to_document(),
            "case": execution_inputs.case.to_document(),
            "evidence": [item.to_document() for item in execution_inputs.evidence],
            "model_profiles": [item.to_document() for item in execution_inputs.model_profiles],
            "expert_fixtures": list(execution_inputs.expert_fixtures),
            "mock_outputs": [item.to_document() for item in execution_inputs.mock_outputs],
            "acceptance_oracle": oracle.to_document(),
        }
    )


def _assert_manifest_payload_limits(
    manifest: TrialManifest,
    payload_bytes: dict[str, bytes],
) -> None:
    if len(payload_bytes) > manifest.resource_limits.max_payload_files:
        raise TrialBundleError("payload file count exceeds Trial Manifest limit")
    total = sum(len(content) for content in payload_bytes.values())
    if total > manifest.resource_limits.max_total_payload_bytes:
        raise TrialBundleError("payload bytes exceed Trial Manifest total-byte limit")
    oversized = [
        path
        for path, content in payload_bytes.items()
        if len(content) > manifest.resource_limits.max_file_bytes
    ]
    if oversized:
        raise TrialBundleError(
            f"payload file exceeds Trial Manifest per-file limit: {sorted(oversized)}"
        )


def _parse_execution_documents(
    payload_bytes: dict[str, bytes],
    *,
    case_path: str,
    mock_count_limit: int,
    mock_byte_limit: int,
) -> TrialExecutionInputs:
    """Shared typed data parsing; callers own their version and manifest rules."""
    if sum(_kind_for(path) is TrialDocumentKind.MOCK_OUTPUT for path in payload_bytes) > (
        mock_count_limit
    ):
        raise TrialBundleError("mock output fixture count exceeds admitted limit")
    case = parse_case(_load_document(payload_bytes[case_path], path=case_path))
    evidence: list[Evidence] = []
    model_profiles: list[ModelProfile] = []
    experts: list[dict[str, Any]] = []
    mock_outputs: list[TrialMockOutputFixture] = []
    for path in sorted(payload_bytes):
        kind = _kind_for(path)
        if kind is TrialDocumentKind.EVIDENCE:
            evidence.append(parse_evidence(_load_document(payload_bytes[path], path=path)))
        elif kind is TrialDocumentKind.MODEL_PROFILE:
            profile = parse_model_profile(_load_document(payload_bytes[path], path=path))
            if profile.provider != "mock":
                raise TrialBundleError("all admitted model profiles must use provider='mock'")
            model_profiles.append(profile)
        elif kind is TrialDocumentKind.EXPERT_FIXTURE:
            expert = _load_document(payload_bytes[path], path=path)
            if not isinstance(expert.get("expert_id"), str) or not expert["expert_id"]:
                raise TrialBundleError("expert fixture requires a non-empty expert_id")
            if expert.get("real_human") is not False:
                raise TrialBundleError("SBX1 expert fixtures must explicitly be synthetic")
            experts.append(expert)
        elif kind is TrialDocumentKind.MOCK_OUTPUT:
            fixture = freeze_trial_mock_output_fixture(
                TrialMockOutputFixturePayload.model_validate(
                    _load_document(payload_bytes[path], path=path)
                )
            )
            if len(fixture.output_text.encode("utf-8")) > mock_byte_limit:
                raise TrialBundleError("mock output fixture exceeds admitted byte limit")
            mock_outputs.append(fixture)

    if not model_profiles:
        raise TrialBundleError("trial bundle requires at least one Mock model profile")
    if not mock_outputs:
        raise TrialBundleError("trial bundle requires at least one mock output fixture")
    model_ids = {item.model_id for item in model_profiles}
    if any(item.model_id not in model_ids for item in mock_outputs):
        raise TrialBundleError("mock output fixture references an unregistered Mock model")

    identities = (
        ("evidence", tuple(item.evidence_id for item in evidence)),
        ("model profile", tuple(item.model_id for item in model_profiles)),
        ("expert fixture", tuple(str(item["expert_id"]) for item in experts)),
        ("mock fixture", tuple(item.fixture_id for item in mock_outputs)),
        ("mock run", tuple(item.run_id for item in mock_outputs)),
    )
    for name, values in identities:
        if len(values) != len(set(values)):
            raise TrialBundleError(f"duplicate {name} logical identity")

    return TrialExecutionInputs(
        case=case,
        evidence=tuple(evidence),
        model_profiles=tuple(model_profiles),
        expert_fixtures=tuple(experts),
        mock_outputs=tuple(mock_outputs),
    )


def _parse_verified_documents(
    payload_bytes: dict[str, bytes],
) -> tuple[TrialManifest, TrialExecutionInputs, TrialAcceptanceOracle]:
    _require_paths(payload_bytes)
    manifest = freeze_trial_manifest(
        TrialManifestPayload.model_validate(
            _load_document(payload_bytes[_MANIFEST_PATH], path=_MANIFEST_PATH)
        )
    )
    _assert_manifest_payload_limits(manifest, payload_bytes)
    execution_inputs = _parse_execution_documents(
        payload_bytes,
        case_path=_CASE_PATH,
        mock_count_limit=min(
            TRIAL_HARD_CAPS.max_mock_outputs, manifest.resource_limits.max_mock_outputs
        ),
        mock_byte_limit=min(
            TRIAL_HARD_CAPS.max_mock_output_bytes, manifest.resource_limits.max_mock_output_bytes
        ),
    )
    oracle = freeze_trial_acceptance_oracle(
        TrialAcceptanceOraclePayload.model_validate(
            _load_document(payload_bytes[_EXPECTED_PATH], path=_EXPECTED_PATH)
        )
    )
    case = execution_inputs.case
    if (case.case_id, case.revision, case.case_mode, case.protocol_version) != (
        manifest.case_id,
        manifest.case_revision,
        manifest.case_mode.value,
        manifest.protocol_version,
    ):
        raise TrialBundleError("Case identity does not match Trial Manifest")
    if any(item.case_id != case.case_id for item in execution_inputs.evidence):
        raise TrialBundleError("Evidence case_id does not match Case")
    return manifest, execution_inputs, oracle


def verify_input_bundle(
    input_root: str | os.PathLike[str],
    *,
    attempt: TrialAttemptReceipt | None = None,
    attempt_id: str = "trial-attempt",
    started_at: datetime | None = None,
    verified_at: datetime | None = None,
) -> VerifiedTrialBundle:
    root = Path(input_root)
    if attempt is None:
        attempt = begin_trial_attempt(
            root,
            attempt_id=attempt_id,
            started_at=started_at or datetime.now(timezone.utc),
        )
    attempt.assert_integrity()
    try:
        root_stat = root.lstat()
    except OSError as exc:
        raise TrialBundleError(f"input root cannot be inspected: {exc}") from exc
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        raise TrialBundleError("input root must be an existing non-link directory")
    try:
        root_names = {item.name for item in root.iterdir()}
    except OSError as exc:
        raise TrialBundleError(f"input root cannot be enumerated: {exc}") from exc
    if root_names != _ALLOWED_ROOT_ENTRIES:
        raise TrialBundleError(
            f"input root entries must be exactly {sorted(_ALLOWED_ROOT_ENTRIES)}"
        )
    index_bytes = _read_small_regular_file(
        root, "checksums.sha256", maximum=TRIAL_HARD_CAPS.max_file_bytes
    )
    address_bytes = _read_small_regular_file(root, "input_address.sha256", maximum=256)
    try:
        detached_address = address_bytes.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise TrialBundleError("detached input address must be ASCII") from exc
    if len(detached_address) != 64 or any(c not in "0123456789abcdef" for c in detached_address):
        raise TrialBundleError("detached input address is not a lowercase SHA-256 digest")
    if detached_address != _sha256_bytes(index_bytes):
        raise TrialBundleError("detached input address does not hash exact checksum index bytes")
    if attempt.detached_input_address is not None and (
        attempt.detached_input_address != detached_address
    ):
        raise TrialBundleError("Attempt Receipt detached address differs from verified address")
    entries = _parse_checksum_index(index_bytes)
    payload_bytes = _verify_payload_bytes(root, entries)
    manifest, execution_inputs, oracle = _parse_verified_documents(payload_bytes)
    file_receipts = tuple(
        TrialInputFileReceipt(
            path=path,
            document_kind=_kind_for(path),
            size_bytes=len(payload_bytes[path]),
            sha256=entries[path],
        )
        for path in sorted(payload_bytes)
    )
    receipt = freeze_trial_input_bundle_receipt(
        TrialInputBundleReceiptPayload(
            receipt_id=f"bundle:{attempt.attempt_id}",
            attempt_receipt_hash=attempt.attempt_receipt_hash,
            detached_input_address=detached_address,
            checksum_index_sha256=_sha256_bytes(index_bytes),
            files=file_receipts,
            total_payload_bytes=sum(len(value) for value in payload_bytes.values()),
            inventory_policy_version=_INVENTORY_POLICY_VERSION,
            verified_at=verified_at or datetime.now(timezone.utc),
        )
    )
    payload_documents_sha256 = canonical_document_sha256(
        {path: _sha256_bytes(payload_bytes[path]) for path in sorted(payload_bytes)}
    )
    bundle = VerifiedTrialBundle(
        attempt=attempt,
        receipt=receipt,
        manifest=manifest,
        execution_inputs=execution_inputs,
        acceptance_oracle=oracle,
        payload_documents_sha256=payload_documents_sha256,
        _verification_proof=_VERIFICATION_SENTINEL,
    )
    bundle.assert_integrity()
    return bundle


def _baseline_contract_hashes() -> list[dict[str, str]]:
    return [
        {
            "name": "protocols/protocol_registry_v0.1.yaml",
            "sha256": "c1473518a19c48c06043c938de86c019408326d76e6f9cc03f648709fd437c89",
        },
        {
            "name": "schemas/audit-event.schema.json",
            "sha256": "5ab0b3096a0b86faa5e187ce569a7e61c712247020c5bc801d69bb716670f362",
        },
        {
            "name": "schemas/case.schema.json",
            "sha256": "1a443c5ace4c0def254b5029fa868a233e81f4a33dccc75a5db32a64f84a5c02",
        },
        {
            "name": "schemas/context-manifest.schema.json",
            "sha256": "84e8dc79709478b62338dc13123247d4c1a467789ca42112924159ed75301d2b",
        },
        {
            "name": "schemas/evidence.schema.json",
            "sha256": "6a63295229825d466df5628e3e34dea2dff63dcbfee103382ee8c65f73a1fd46",
        },
        {
            "name": "schemas/model-profile.schema.json",
            "sha256": "fd16d5c7a003d99469a2543646fb5df2efff5c90c9f225bae4fa869944153ead",
        },
        {
            "name": "schemas/phase-profile.schema.json",
            "sha256": "1b61a3d2e1e09241e2e207fa1b8ff935b8abef11e4183e82dfd906c0b5681f63",
        },
        {
            "name": "schemas/protocol-registry.schema.json",
            "sha256": "d7568772915468171d6646e9d0db0abe685c818eaba03cacbe6c932a25bf852c",
        },
        {
            "name": "schemas/run-manifest.schema.json",
            "sha256": "8b6001b9ffc19ab732664fb99c8c5dcd74547e7cbb866f38e090e46b2b7b6b73",
        },
        {
            "name": "schemas/visibility.schema.json",
            "sha256": "ebcf750575ebf9c24e80441835360928a88d301df5f0317f0e229be22b86cc38",
        },
    ]


def _bootstrap_payload_files() -> dict[str, bytes]:
    frozen_at = "2026-08-29T00:00:00+00:00"
    limits = {
        "max_payload_files": 16,
        "max_file_bytes": 131072,
        "max_total_payload_bytes": 1048576,
        "max_mock_outputs": 4,
        "max_mock_output_bytes": 65536,
        "max_stage_calls": 16,
        "max_model_calls": 16,
        "max_output_bytes": 262144,
        "max_output_tokens": 65536,
        "max_frozen_artifacts": 256,
        "max_audit_payload_bytes": 2097152,
        "max_wall_clock_seconds": 300,
        "max_retries": 0,
    }
    manifest = {
        "trial_id": "bootstrap-sbx1",
        "trial_protocol_version": "TRIAL-SBX1-v1",
        "source_commit_sha": _BOOTSTRAP_SOURCE_COMMIT,
        "protocol_version": "0.1",
        "frozen_contract_hashes": _baseline_contract_hashes(),
        "migration_ceiling": "0007",
        "case_id": "trial-bootstrap-case",
        "case_revision": 1,
        "case_mode": "MECHANISM_BENCHMARK",
        "adapter_lane": "MOCK",
        "data_class": "SYNTHETIC",
        "publication_policy": "RESTRICTED",
        "database_target": "trial_bootstrap",
        "output_root": "trial-output/bootstrap",
        "resource_limits": limits,
        "allowed_terminal_outcomes": [
            "COMPLETED_AT_AUTHORIZED_BOUNDARY",
            "CAPABILITY_GAP",
            "RESEARCH_SAFETY_BLOCK",
            "CHALLENGER_BLOCK",
            "HC_REGRESSION_DETECTED",
            "LOW_RECOGNITION_COMPROMISED",
        ],
        "inventory_policy_version": _INVENTORY_POLICY_VERSION,
        "authorized_terminal_state": "ADVERSARIAL_REVIEW",
        "final_synthesis_authorized": False,
        "final_claim_authorized": False,
        "seal_authorized": False,
        "publication_authorized": False,
        "reality_execution_authorized": False,
        "frozen_at": frozen_at,
    }
    case = {
        "case_id": "trial-bootstrap-case",
        "revision": 1,
        "case_mode": "MECHANISM_BENCHMARK",
        "question": ("Can the authorized Mock-only closed-sandbox path reach its frozen boundary?"),
        "protocol_version": "0.1",
        "phase_profile": {
            "civilization_stage": "STARTUP",
            "case_phase": "DISCOVERY",
        },
        "time_boundary": {
            "T0": "2026-08-29T00:00:00+00:00",
            "timezone": "UTC",
        },
        "domains": ["systems_risk"],
        "publication_policy": "RESTRICTED",
    }
    profile = {
        "model_id": "mock-bootstrap-model",
        "model_family": "mock-bootstrap-family",
        "provider": "mock",
        "status": "QUALIFIED",
        "role_eligibility": {
            "meta_controller": True,
            "challenger": True,
            "evaluator": True,
            "domain_worker": ["systems_risk"],
        },
        "controller_qualification": {"benchmark_version": "bootstrap-v1"},
        "domain_capabilities": [
            {
                "domain": "systems_risk",
                "task_type": "scenario_analysis",
                "eligibility": "QUALIFIED",
            }
        ],
    }
    mock_output = {
        "fixture_id": "mock-bootstrap-output",
        "run_id": "run:bootstrap",
        "model_id": "mock-bootstrap-model",
        "model_family": "mock-bootstrap-family",
        "provider": "mock",
        "output_text": '{"status":"bootstrap"}',
        "protocol_version": "0.1",
        "frozen_at": frozen_at,
    }
    oracle = {
        "oracle_id": "oracle:bootstrap",
        "expected_outcome": "COMPLETED_AT_AUTHORIZED_BOUNDARY",
        "expected_stop_condition": "AUTHORIZED_BOUNDARY_REACHED",
        "expected_terminal_state": "ADVERSARIAL_REVIEW",
        "expected_capability_acceptance": "PASS",
        "notes": ["Internal automated bootstrap only."],
        "disclosed_to_cognitive_wrappers": False,
        "grants_canonical_status": False,
        "grants_execution_authority": False,
        "frozen_at": frozen_at,
    }
    return {
        _MANIFEST_PATH: _canonical_json_bytes(manifest),
        _CASE_PATH: _canonical_json_bytes(case),
        "payload/model_profiles/mock-bootstrap.json": _canonical_json_bytes(profile),
        "payload/mock_outputs/bootstrap.json": _canonical_json_bytes(mock_output),
        _EXPECTED_PATH: _canonical_json_bytes(oracle),
    }


def _bootstrap_package_files() -> dict[str, bytes]:
    payload = _bootstrap_payload_files()
    index = "".join(f"{_sha256_bytes(payload[path])}  {path}\n" for path in sorted(payload)).encode(
        "utf-8"
    )
    return {
        **payload,
        "checksums.sha256": index,
        "input_address.sha256": (_sha256_bytes(index) + "\n").encode("ascii"),
    }


def _receipt_inventory_sha256(receipt: TrialInputBundleReceipt) -> str:
    return _typed_canonical_sha256(
        [
            item.model_dump(mode="json", exclude_none=True)
            for item in sorted(receipt.files, key=lambda item: item.path)
        ]
    )


def _bootstrap_registry_entry() -> _CanonicalRegistryEntry:
    files = _bootstrap_package_files()
    payload = {path: data for path, data in files.items() if path.startswith("payload/")}
    manifest, execution_inputs, oracle = _parse_verified_documents(payload)
    file_receipts = tuple(
        TrialInputFileReceipt(
            path=path,
            document_kind=_kind_for(path),
            size_bytes=len(payload[path]),
            sha256=_sha256_bytes(payload[path]),
        )
        for path in sorted(payload)
    )
    synthetic_receipt = freeze_trial_input_bundle_receipt(
        TrialInputBundleReceiptPayload(
            receipt_id="bundle:registry-template",
            attempt_receipt_hash="0" * 64,
            detached_input_address=_sha256_bytes(files["checksums.sha256"]),
            checksum_index_sha256=_sha256_bytes(files["checksums.sha256"]),
            files=file_receipts,
            total_payload_bytes=sum(len(value) for value in payload.values()),
            inventory_policy_version=_INVENTORY_POLICY_VERSION,
            verified_at=datetime(2026, 8, 29, tzinfo=timezone.utc),
        )
    )
    return _CanonicalRegistryEntry(
        entry_id="trial-bootstrap-sbx1-v1",
        purpose=TrialCanonicalPurpose.BOOTSTRAP_AUTOMATED_TEST,
        detached_input_address=_sha256_bytes(files["checksums.sha256"]),
        checksum_index_sha256=_sha256_bytes(files["checksums.sha256"]),
        receipt_inventory_sha256=_receipt_inventory_sha256(synthetic_receipt),
        payload_documents_sha256=canonical_document_sha256(
            {path: _sha256_bytes(payload[path]) for path in sorted(payload)}
        ),
        case_id=manifest.case_id,
        case_revision=manifest.case_revision,
        case_mode=manifest.case_mode.value,
        manifest_hash=manifest.manifest_hash,
        semantic_fingerprint=_semantic_fingerprint(
            manifest=manifest,
            execution_inputs=execution_inputs,
            oracle=oracle,
        ),
        source_commit_sha=manifest.source_commit_sha,
        protocol_version=manifest.protocol_version,
    )


_BOOTSTRAP_REGISTRY_ENTRY = _bootstrap_registry_entry()


def _materialize_bootstrap_bundle_for_test(root: Path) -> None:
    """Private deterministic materializer used only by internal automated tests."""
    for relative, content in _bootstrap_package_files().items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def _admit_pre_freeze_bundle(
    bundle: VerifiedTrialBundle,
    *,
    admission_id: str,
    frozen_at: datetime,
) -> _AuthenticatedCanonicalAdmission:
    bundle.assert_integrity()
    entry = _BOOTSTRAP_REGISTRY_ENTRY
    semantic = _semantic_fingerprint(
        manifest=bundle.manifest,
        execution_inputs=bundle.execution_inputs,
        oracle=bundle.acceptance_oracle,
    )
    actual = (
        bundle.receipt.detached_input_address,
        bundle.receipt.checksum_index_sha256,
        _receipt_inventory_sha256(bundle.receipt),
        bundle.payload_documents_sha256,
        bundle.manifest.case_id,
        bundle.manifest.case_revision,
        bundle.manifest.case_mode.value,
        bundle.manifest.manifest_hash,
        semantic,
        bundle.manifest.source_commit_sha,
        bundle.manifest.protocol_version,
    )
    expected = (
        entry.detached_input_address,
        entry.checksum_index_sha256,
        entry.receipt_inventory_sha256,
        entry.payload_documents_sha256,
        entry.case_id,
        entry.case_revision,
        entry.case_mode,
        entry.manifest_hash,
        entry.semantic_fingerprint,
        entry.source_commit_sha,
        entry.protocol_version,
    )
    reasons = (
        ()
        if actual == expected
        else ("bundle is not the exact package-owned SBX1 bootstrap identity",)
    )
    admitted = not reasons
    record = freeze_trial_canonical_admission(
        TrialCanonicalAdmissionPayload(
            admission_id=admission_id,
            bundle_receipt_hash=bundle.receipt.bundle_receipt_hash,
            detached_input_address=bundle.receipt.detached_input_address,
            registry_entry_id=entry.entry_id,
            purpose=entry.purpose,
            case_id=bundle.manifest.case_id,
            case_revision=bundle.manifest.case_revision,
            case_mode=bundle.manifest.case_mode,
            source_commit_sha=bundle.manifest.source_commit_sha,
            protocol_version=bundle.manifest.protocol_version,
            pre_freeze_admitted=admitted,
            status=(
                TrialCanonicalAdmissionStatus.PASS
                if admitted
                else TrialCanonicalAdmissionStatus.REJECTED
            ),
            reasons=reasons,
            frozen_at=frozen_at,
        )
    )
    authenticated = _AuthenticatedCanonicalAdmission(
        record=record,
        attempt_receipt_hash=bundle.attempt.attempt_receipt_hash,
        bundle_receipt_hash=bundle.receipt.bundle_receipt_hash,
        manifest_hash=bundle.manifest.manifest_hash,
        receipt_inventory_sha256=_receipt_inventory_sha256(bundle.receipt),
        payload_documents_sha256=bundle.payload_documents_sha256,
        semantic_fingerprint=semantic,
    )
    _register_canonical_provenance(authenticated)
    authenticated.assert_integrity()
    return authenticated
