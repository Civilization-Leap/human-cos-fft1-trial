"""Frozen-contract verification — the outer immutability gate for V0.1.

Repository-root files remain the canonical signed contract. Installed wheels
carry byte-identical transport copies and can verify those copies without a
source checkout.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import yaml

from human_cos.resources import read_runtime_resource_bytes, read_runtime_resource_text

_MODULE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _MODULE_DIR.parents[2]
DEFAULT_MANIFEST_NAME = "BASELINE_CONTRACT_HASHES.yaml"


class ContractHashMismatchError(ValueError):
    """Raised when a signed frozen-contract file is missing or differs from its hash."""


@dataclass
class ContractCheck:
    path: str
    expected_sha256: str
    actual_sha256: str
    ok: bool
    note: str = ""


@dataclass
class ContractReport:
    items: list[ContractCheck] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(item.ok for item in self.items)

    @property
    def failures(self) -> list[ContractCheck]:
        return [item for item in self.items if not item.ok]

    def summary(self) -> str:
        return (
            "; ".join(f"{i.path}: {i.note}" for i in self.failures)
            or "all 10 frozen contracts intact"
        )


def repo_root() -> Path:
    return _REPO_ROOT


def default_manifest_path() -> Path:
    return _REPO_ROOT / DEFAULT_MANIFEST_NAME


def _validate_manifest(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ContractHashMismatchError("frozen contract manifest must be a mapping")
    files = document.get("files")
    if not isinstance(files, list) or not files:
        raise ContractHashMismatchError("frozen contract manifest has no 'files' list")
    if document.get("version") != "V0.1":
        raise ContractHashMismatchError(
            f"frozen contract manifest version {document.get('version')!r} != V0.1"
        )
    return cast("dict[str, Any]", document)


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ContractHashMismatchError(
            f"frozen contract manifest not found: {path} (file: {DEFAULT_MANIFEST_NAME})"
        )
    with path.open("r", encoding="utf-8") as fh:
        return _validate_manifest(yaml.safe_load(fh) or {})


def _load_bundled_manifest() -> dict[str, Any]:
    try:
        text = read_runtime_resource_text(DEFAULT_MANIFEST_NAME, prefer_source=False)
    except FileNotFoundError as exc:
        raise ContractHashMismatchError("packaged frozen contract manifest not found") from exc
    return _validate_manifest(yaml.safe_load(text) or {})


def compute_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_entry(rel: str, expected: str, payload: bytes | None) -> ContractCheck:
    if payload is None:
        return ContractCheck(rel, expected, "", ok=False, note="missing signed file")
    actual = hashlib.sha256(payload).hexdigest()
    ok = actual == expected
    return ContractCheck(
        rel,
        expected,
        actual,
        ok=ok,
        note="intact" if ok else f"hash mismatch (expected {expected[:12]}… got {actual[:12]}…)",
    )


def verify_frozen_contracts(
    root: Path | None = None,
    manifest_path: Path | None = None,
    *,
    bundled: bool = False,
) -> ContractReport:
    """Verify canonical source files or packaged transport copies.

    Explicit ``root``/``manifest_path`` retain the historical source-tree API.
    With no explicit path, source bytes are preferred when available; installed
    distributions transparently fall back to packaged resources. ``bundled=True``
    forces validation of packaged copies even from a source checkout.
    """
    path_mode = root is not None or manifest_path is not None
    source_root = Path(root or _REPO_ROOT)
    source_manifest = Path(manifest_path or source_root / DEFAULT_MANIFEST_NAME)
    use_source = path_mode or (not bundled and source_manifest.is_file())
    manifest = _load_manifest(source_manifest) if use_source else _load_bundled_manifest()

    report = ContractReport()
    for entry in manifest["files"]:
        rel = str(entry["path"])
        expected = str(entry["sha256"]).lower()
        payload: bytes | None
        if use_source:
            candidate = source_root / rel
            payload = candidate.read_bytes() if candidate.exists() else None
        else:
            try:
                payload = read_runtime_resource_bytes(rel, prefer_source=False)
            except FileNotFoundError:
                payload = None
        report.items.append(_check_entry(rel, expected, payload))
    return report


def verify_bundled_frozen_contracts() -> ContractReport:
    """Force verification of distribution transport copies."""
    return verify_frozen_contracts(bundled=True)


def assert_frozen_contracts_intact(
    root: Path | None = None,
    manifest_path: Path | None = None,
    *,
    bundled: bool = False,
) -> ContractReport:
    report = verify_frozen_contracts(root=root, manifest_path=manifest_path, bundled=bundled)
    if not report.ok:
        raise ContractHashMismatchError("FROZEN CONTRACT VIOLATION — " + report.summary())
    return report


def assert_bundled_frozen_contracts_intact() -> ContractReport:
    """Merge-/distribution-gate helper for packaged copies."""
    return assert_frozen_contracts_intact(bundled=True)
