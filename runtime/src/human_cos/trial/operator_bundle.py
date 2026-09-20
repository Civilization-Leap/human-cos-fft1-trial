"""Versioned operator input verification; no environment or execution authority.

The durable in-process input is exact immutable bytes. Parsed views are disposable
and are always rebuilt from that snapshot, never from the original input path.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from weakref import WeakKeyDictionary

from pydantic import BaseModel, ConfigDict, Field

from .bundle import (
    TrialExecutionInputs,
    _open_parent_directory,
    _open_root_directory,
    _parse_checksum_index,
    _parse_execution_documents,
    _read_regular_relative,
    _verify_payload_bytes,
)
from .contracts import TRIAL_HARD_CAPS, TrialResourceLimits
from .operator_admission import evaluate_operator_approval
from .operator_contracts import OperatorApprovalDecision, OperatorInputIdentity

_MANIFEST = "payload/operator_manifest.json"
_CASE = "payload/case.json"
_DATA_PATH = re.compile(
    r"payload/(evidence|model_profiles|expert_fixtures|mock_outputs)/"
    r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}\.json"
)
_SIDECARS = ("checksums.sha256", "input_address.sha256")
_ERROR = "operator input verification failed"


class OperatorBundleError(ValueError):
    """Sanitized rejection: input paths, parser errors and bodies are not echoed."""


class OperatorInputManifest(BaseModel):
    """Acyclic input declaration, separate from a future execution record."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    input_version: Literal["operator-synthetic-v1"]
    baseline_version: Literal["V0.2"]
    protocol_version: Literal["0.1"]
    case_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    case_revision: int = Field(ge=1)
    case_mode: Literal["MECHANISM_BENCHMARK"]
    data_class: Literal["SYNTHETIC"]
    adapter_lane: Literal["MOCK"]
    publication_policy: Literal["RESTRICTED"]
    authorized_terminal_state: Literal["ADVERSARIAL_REVIEW"]
    resource_limits: TrialResourceLimits


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise OperatorBundleError(_ERROR)
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise OperatorBundleError(_ERROR)


def _json_object(content: bytes) -> dict[str, Any]:
    value = json.loads(
        content.decode("utf-8"),
        object_pairs_hook=_unique_object,
        parse_constant=_reject_constant,
    )
    if not isinstance(value, dict):
        raise OperatorBundleError(_ERROR)
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > 32:
            raise OperatorBundleError(_ERROR)
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
            pending.extend((key, depth + 1) for key in item)
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
        elif isinstance(item, str):
            item.encode("utf-8")  # Reject unpaired Unicode surrogates before typed parsing.
        elif isinstance(item, float) and not math.isfinite(item):
            raise OperatorBundleError(_ERROR)
    return value


def _assert_paths(entries: dict[str, str]) -> None:
    if _MANIFEST not in entries or _CASE not in entries:
        raise OperatorBundleError(_ERROR)
    if any(path not in (_MANIFEST, _CASE) and not _DATA_PATH.fullmatch(path) for path in entries):
        raise OperatorBundleError(_ERROR)


def _change_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
        value.st_nlink,
    )


def _layout(root_fd: int, entries: dict[str, str]) -> dict[str, tuple[int, ...]]:
    """Bound traversal to the version's shallow, exact directory inventory."""
    files = {*entries, *_SIDECARS}
    directories = {"", "payload"} | {path.rsplit("/", 1)[0] for path in entries}
    observed: dict[str, tuple[int, ...]] = {}
    for directory in sorted(directories):
        parts = tuple(directory.split("/")) if directory else ()
        fd = _open_parent_directory(root_fd, parts)
        try:
            observed["directory:" + directory] = _change_identity(os.fstat(fd))
            prefix = directory + "/" if directory else ""
            expected = {
                path[len(prefix) :]
                for path in files | directories
                if path.startswith(prefix) and path != directory and "/" not in path[len(prefix) :]
            }
            actual: set[str] = set()
            with os.scandir(fd) as iterator:
                for entry in iterator:
                    if entry.name not in expected or entry.name in actual:
                        raise OperatorBundleError(_ERROR)
                    actual.add(entry.name)
                    relative = prefix + entry.name
                    info = entry.stat(follow_symlinks=False)
                    if relative in files:
                        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                            raise OperatorBundleError(_ERROR)
                        observed[relative] = _change_identity(info)
                    elif not stat.S_ISDIR(info.st_mode):
                        raise OperatorBundleError(_ERROR)
            if actual != expected:
                raise OperatorBundleError(_ERROR)
        finally:
            os.close(fd)
    return observed


def _read_snapshot(root: Path) -> tuple[bytes, tuple[tuple[str, bytes], ...]]:
    root_fd = _open_root_directory(root)
    try:
        root_before = _change_identity(os.fstat(root_fd))
        sidecar_stats = {
            name: os.stat(name, dir_fd=root_fd, follow_symlinks=False) for name in _SIDECARS
        }
        if any(
            not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 for info in sidecar_stats.values()
        ):
            raise OperatorBundleError(_ERROR)
        index = _read_regular_relative(
            root_fd,
            _SIDECARS[0],
            maximum=TRIAL_HARD_CAPS.max_file_bytes,
            expected_stat=sidecar_stats[_SIDECARS[0]],
        )
        address = _read_regular_relative(
            root_fd, _SIDECARS[1], maximum=256, expected_stat=sidecar_stats[_SIDECARS[1]]
        )
        # This version has exactly one address encoding; no whitespace aliases.
        if address != (_digest(index) + "\n").encode("ascii"):
            raise OperatorBundleError(_ERROR)
        entries = _parse_checksum_index(index)
        _assert_paths(entries)
        before = _layout(root_fd, entries)
        if any(before[name] != _change_identity(info) for name, info in sidecar_stats.items()):
            raise OperatorBundleError(_ERROR)
        payload = _verify_payload_bytes(root, entries)
        if before != _layout(root_fd, entries) or root_before != _change_identity(root.lstat()):
            raise OperatorBundleError(_ERROR)
        return index, tuple(sorted(payload.items()))
    finally:
        os.close(root_fd)


def _parse_snapshot(
    index: bytes, payload_files: tuple[tuple[str, bytes], ...]
) -> tuple[OperatorInputManifest, TrialExecutionInputs, OperatorInputIdentity]:
    payload = dict(payload_files)
    documents = {path: _json_object(content) for path, content in payload_files}
    # Mandatory explicit dispatch. There is no attempt to parse a canonical bundle.
    if documents[_MANIFEST].get("input_version") != "operator-synthetic-v1":
        raise OperatorBundleError(_ERROR)
    manifest = OperatorInputManifest.model_validate(documents[_MANIFEST], strict=True)
    limits = manifest.resource_limits
    if (
        len(payload) > limits.max_payload_files
        or sum(map(len, payload.values())) > limits.max_total_payload_bytes
        or any(len(content) > limits.max_file_bytes for content in payload.values())
    ):
        raise OperatorBundleError(_ERROR)
    execution = _parse_execution_documents(
        payload,
        case_path=_CASE,
        mock_count_limit=limits.max_mock_outputs,
        mock_byte_limit=limits.max_mock_output_bytes,
    )
    case = execution.case
    if (
        type(documents[_CASE].get("revision")) is not int
        or (case.case_id, case.revision, case.case_mode, case.protocol_version)
        != (
            manifest.case_id,
            manifest.case_revision,
            manifest.case_mode,
            manifest.protocol_version,
        )
        or case.publication_policy != "RESTRICTED"
        or case.state is not None
        or any(item.case_id != case.case_id for item in execution.evidence)
    ):
        raise OperatorBundleError(_ERROR)
    profiles = {profile.model_id: profile for profile in execution.model_profiles}
    for fixture in execution.mock_outputs:
        profile = profiles[fixture.model_id]
        if (
            fixture.model_family != profile.model_family
            or fixture.protocol_version != manifest.protocol_version
        ):
            raise OperatorBundleError(_ERROR)
    identity = OperatorInputIdentity(
        detached_input_address=_digest(index),
        case_id=case.case_id,
        case_revision=case.revision,
        profile_hashes=tuple(
            sorted(
                (documents[path]["model_id"], _digest(content))
                for path, content in payload_files
                if path.startswith("payload/model_profiles/")
            )
        ),
        input_version=manifest.input_version,
        baseline_version=manifest.baseline_version,
        case_mode=case.case_mode,
    )
    return manifest, execution, identity


@dataclass(frozen=True, eq=False)
class VerifiedOperatorBundle:
    """Verifier-owned bytes, not a serialized approval token or Environment PASS.

    Each parsed view is rebuilt. In particular an expert's arbitrary JSON mapping
    cannot mutate the stored bytes or another consumer's view. No root path is kept.
    """

    checksum_index: bytes
    payload_files: tuple[tuple[str, bytes], ...]

    def assert_integrity(self) -> None:
        binding = _VERIFIED.get(self)
        if type(self) is not VerifiedOperatorBundle or binding is None:
            raise OperatorBundleError(_ERROR)
        if self.checksum_index is not binding[0] or self.payload_files is not binding[1]:
            raise OperatorBundleError(_ERROR)

    def _parsed(self) -> tuple[OperatorInputManifest, TrialExecutionInputs, OperatorInputIdentity]:
        self.assert_integrity()
        try:
            return _parse_snapshot(self.checksum_index, self.payload_files)
        except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
            raise OperatorBundleError(_ERROR) from None

    @property
    def manifest(self) -> OperatorInputManifest:
        return self._parsed()[0]

    @property
    def execution_inputs(self) -> TrialExecutionInputs:
        return self._parsed()[1]

    @property
    def identity(self) -> OperatorInputIdentity:
        return self._parsed()[2]

    @property
    def approval(self) -> OperatorApprovalDecision:
        """Query the current trusted catalogue using identity derived from bytes."""
        return evaluate_operator_approval(self.identity)


_VERIFIED: WeakKeyDictionary[
    VerifiedOperatorBundle, tuple[bytes, tuple[tuple[str, bytes], ...]]
] = WeakKeyDictionary()


def verify_operator_input_bundle(input_root: str | os.PathLike[str]) -> VerifiedOperatorBundle:
    """Verify bytes and typed input, then query approval; never create or run data.

    A well-formed unapproved input has approval.status NOT_APPROVED. Even a matched
    input still needs qualification, environment admission and the future runner.
    """
    try:
        index, payload = _read_snapshot(Path(input_root))
        _, _, identity = _parse_snapshot(index, payload)
        evaluate_operator_approval(identity)  # Fail closed for a malformed trusted catalogue.
    except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError):
        raise OperatorBundleError(_ERROR) from None
    bundle = VerifiedOperatorBundle(index, payload)
    _VERIFIED[bundle] = (index, payload)
    bundle.assert_integrity()
    return bundle
