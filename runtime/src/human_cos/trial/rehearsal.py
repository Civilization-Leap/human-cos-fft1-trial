"""Installed, Mock-only TRIAL-SBX5 integrated rehearsal.

This module composes the frozen SBX1--SBX4 surfaces. It admits only the package-owned
bootstrap input, probes a disposable PostgreSQL/internal-network environment, runs
deterministic structural replay, independently verifies every detached audit, and
removes only identity-bound transient resources. It grants no provider, publication,
synthesis, claim, seal, or reality authority.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import socket
import stat
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from human_cos.runtime.run import canonical_document_sha256
from human_cos.runtime.state_machine import RuntimeState

from .audit import _publish_no_replace, _read_regular, export_audit_bundle, verify_audit_bundle
from .bundle import (
    VerifiedTrialBundle,
    _admit_pre_freeze_bundle,
    _AuthenticatedCanonicalAdmission,
    _bootstrap_package_files,
    _register_environment_provenance,
    verify_input_bundle,
)
from .case_pack import (
    CANONICAL_TRIAL_CASE_PACK,
    TrialCanonicalCaseAdmission,
    TrialCaseAcceptance,
    TrialCaseReplayRecord,
    run_canonical_case_pack,
)
from .contracts import (
    TRIAL_HARD_CAPS,
    TrialAdmissionStatus,
    TrialArtifactRef,
    TrialAttemptReceipt,
    TrialAuditExportStatus,
    TrialCanonicalAdmission,
    TrialCapabilityAcceptance,
    TrialCleanupDisposition,
    TrialEnvironmentAdmission,
    TrialInputBundleReceipt,
    TrialManifest,
    TrialResult,
    TrialResultPayload,
    TrialRuntimePosition,
    TrialStop,
    TrialStopCondition,
    TrialStopPhase,
    assert_environment_admission_binding,
    freeze_trial_result,
)
from .environment import TrialEnvironmentFacts, evaluate_environment_admission
from .integrated_chain import (
    InstalledApplicationChainError,
    InstalledApplicationChainReceipt,
    InstalledApplicationCleanupError,
    assert_installed_application_resources_clean,
    exercise_installed_application_chain,
)
from .orchestrator import _BOOTSTRAP_CONTROL_STATES, run_bootstrap_control_rehearsal
from .stop_engine import TrialStopLedger, TrialStopSignal

_RECORDED_AT = datetime(2026, 8, 29, tzinfo=timezone.utc)
_OWNER_MARKER = ".human-cos-sbx5-owner"
_OWNER_VALUE = b"human-cos-runtime:TRIAL-SBX5:v1\n"
_RECEIPT_NAME = "rehearsal_receipt.json"
_APPLICATION_CHAIN_RECEIPT_NAME = "application_chain_receipt.json"
_APPLICATION_CHAIN_CHECKPOINT_NAME = "application_chain_checkpoint.json"
_BUILD_COMMIT_RESOURCE = Path(__file__).parents[1] / "_build_commit.txt"
_EXPECTED_BUILD_ENV = "HUMAN_COS_TRIAL_EXPECTED_BUILD_SHA"
_DATABASE_URL_ENV = "HUMAN_COS_TRIAL_DATABASE_URL"
_ISOLATION_ENV = "HUMAN_COS_TRIAL_NETWORK_ISOLATION"
_ISOLATION_VALUE = "docker-compose-internal-v1"
_DATABASE_SCHEMA = "human_cos_sbx5"


class TrialRehearsalError(ValueError):
    """The integrated rehearsal is unsafe, incomplete, or non-deterministic."""


@dataclass(frozen=True)
class TrialInstalledRehearsalReceipt:
    status: str
    expected_build_commit_sha: str
    installed_build_commit_sha: str
    case_pack_hash: str
    first_run_hash: str
    replay_run_hash: str
    installed_application_chain_receipt_hash: str
    control_audit_bundle_address: str
    verified_control_audit_bundle_address: str
    lifecycle_audit_bundle_address: str
    verified_lifecycle_audit_bundle_address: str
    lifecycle_result_hash: str
    case_audit_addresses: tuple[tuple[str, str], ...]
    verified_case_result_hashes: tuple[tuple[str, str], ...]
    sbx5_fixture_result_hashes: tuple[tuple[str, str], ...]
    sbx5_fixture_audit_addresses: tuple[tuple[str, str], ...]
    transient_resources_cleaned: bool
    audit_preserved: bool
    final_synthesis_authorized: bool
    publication_authorized: bool
    reality_execution_authorized: bool
    receipt_hash: str

    def to_document(self, *, include_hash: bool = True) -> dict[str, object]:
        document: dict[str, object] = {
            "status": self.status,
            "expected_build_commit_sha": self.expected_build_commit_sha,
            "installed_build_commit_sha": self.installed_build_commit_sha,
            "case_pack_hash": self.case_pack_hash,
            "first_run_hash": self.first_run_hash,
            "replay_run_hash": self.replay_run_hash,
            "installed_application_chain_receipt_hash": (
                self.installed_application_chain_receipt_hash
            ),
            "control_audit_bundle_address": self.control_audit_bundle_address,
            "verified_control_audit_bundle_address": self.verified_control_audit_bundle_address,
            "lifecycle_audit_bundle_address": self.lifecycle_audit_bundle_address,
            "verified_lifecycle_audit_bundle_address": (
                self.verified_lifecycle_audit_bundle_address
            ),
            "lifecycle_result_hash": self.lifecycle_result_hash,
            "case_audit_addresses": [list(item) for item in self.case_audit_addresses],
            "verified_case_result_hashes": [
                list(item) for item in self.verified_case_result_hashes
            ],
            "sbx5_fixture_result_hashes": [list(item) for item in self.sbx5_fixture_result_hashes],
            "sbx5_fixture_audit_addresses": [
                list(item) for item in self.sbx5_fixture_audit_addresses
            ],
            "transient_resources_cleaned": self.transient_resources_cleaned,
            "audit_preserved": self.audit_preserved,
            "final_synthesis_authorized": self.final_synthesis_authorized,
            "publication_authorized": self.publication_authorized,
            "reality_execution_authorized": self.reality_execution_authorized,
        }
        if include_hash:
            document["receipt_hash"] = self.receipt_hash
        return document

    def assert_integrity(self) -> None:
        if self.status != "PASS":
            raise TrialRehearsalError("installed rehearsal receipt is not PASS")
        if (
            len(self.installed_build_commit_sha) != 40
            or self.installed_build_commit_sha == "0" * 40
        ):
            raise TrialRehearsalError("installed rehearsal lacks an exact build identity")
        if self.expected_build_commit_sha != self.installed_build_commit_sha:
            raise TrialRehearsalError("expected and installed build identities differ")
        if self.first_run_hash != self.replay_run_hash:
            raise TrialRehearsalError("structural replay is not deterministic")
        if self.control_audit_bundle_address != self.verified_control_audit_bundle_address:
            raise TrialRehearsalError("exported audit address differs from verification")
        if self.lifecycle_audit_bundle_address != self.verified_lifecycle_audit_bundle_address:
            raise TrialRehearsalError("lifecycle audit address differs from verification")
        if len(self.installed_application_chain_receipt_hash) != 64:
            raise TrialRehearsalError("installed application chain evidence is absent")
        if len(self.lifecycle_result_hash) != 64:
            raise TrialRehearsalError("audited lifecycle result is absent")
        if len(self.case_audit_addresses) != len(CANONICAL_TRIAL_CASE_PACK.cases):
            raise TrialRehearsalError("rehearsal did not preserve every canonical case audit")
        if tuple(key for key, _ in self.case_audit_addresses) != tuple(
            case.case_key for case in CANONICAL_TRIAL_CASE_PACK.cases
        ):
            raise TrialRehearsalError("case audit inventory differs from canonical order")
        if len(self.verified_case_result_hashes) != len(self.case_audit_addresses):
            raise TrialRehearsalError("case audit verification inventory is incomplete")
        expected_fixtures = tuple(
            fixture.fixture_key
            for fixture in CANONICAL_TRIAL_CASE_PACK.additional_fixtures
            if fixture.exercise_owner == "TRIAL-SBX5"
        )
        if tuple(key for key, _ in self.sbx5_fixture_result_hashes) != expected_fixtures:
            raise TrialRehearsalError("SBX5-owned failure fixture inventory is incomplete")
        if tuple(key for key, _ in self.sbx5_fixture_audit_addresses) != expected_fixtures:
            raise TrialRehearsalError("SBX5-owned failure audit inventory is incomplete")
        if not self.transient_resources_cleaned or not self.audit_preserved:
            raise TrialRehearsalError("rehearsal cleanup or audit preservation is incomplete")
        if any(
            (
                self.final_synthesis_authorized,
                self.publication_authorized,
                self.reality_execution_authorized,
            )
        ):
            raise TrialRehearsalError("rehearsal receipt claims forbidden authority")
        if self.receipt_hash != canonical_document_sha256(self.to_document(include_hash=False)):
            raise TrialRehearsalError("rehearsal receipt hash does not match its payload")


def _write_new(path: Path, content: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written == 0:
                raise OSError("short write while materializing rehearsal file")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _initialize_owned_root(root: Path) -> tuple[int, int]:
    created_identity: tuple[int, int] | None = None
    directory_created = False
    descriptor: int | None = None
    try:
        root.mkdir(mode=0o700)
        directory_created = True
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(root, flags)
        root_stat = os.fstat(descriptor)
        if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
            raise TrialRehearsalError("new rehearsal root is not a non-link directory")
        created_identity = (root_stat.st_dev, root_stat.st_ino)
        _write_new(root / _OWNER_MARKER, _OWNER_VALUE)
        os.close(descriptor)
        descriptor = None
        return created_identity
    except BaseException as original:
        cleanup_error: BaseException | None = None
        exactly_created = False
        if descriptor is not None:
            try:
                root_stat = os.fstat(descriptor)
                exactly_created = (
                    created_identity is not None
                    and stat.S_ISDIR(root_stat.st_mode)
                    and (root_stat.st_dev, root_stat.st_ino) == created_identity
                )
            except OSError as exc:
                cleanup_error = exc
            finally:
                os.close(descriptor)
        if created_identity is not None:
            try:
                root_stat = root.lstat()
                exactly_created = exactly_created and (
                    stat.S_ISDIR(root_stat.st_mode)
                    and not stat.S_ISLNK(root_stat.st_mode)
                    and (root_stat.st_dev, root_stat.st_ino) == created_identity
                )
            except OSError as exc:
                cleanup_error = exc
                exactly_created = False
        if created_identity is None and directory_created:
            try:
                root.rmdir()
            except OSError as exc:
                cleanup_error = exc
        elif exactly_created:
            try:
                shutil.rmtree(root)
            except OSError as exc:
                cleanup_error = exc
        elif directory_created and cleanup_error is None:
            cleanup_error = TrialRehearsalError(
                "rehearsal root identity changed during initialization"
            )
        if cleanup_error is not None:
            raise TrialRehearsalError(
                "owned resource cleanup failed during root initialization"
            ) from cleanup_error
        if isinstance(original, OSError):
            raise TrialRehearsalError("rehearsal root initialization failed") from original
        raise


def _materialize_owned_input(root: Path) -> None:
    transient = root / "transient"
    transient.mkdir(mode=0o700)
    _write_new(transient / _OWNER_MARKER, _OWNER_VALUE)
    input_root = transient / "input"
    input_root.mkdir(mode=0o700)
    for relative, content in _bootstrap_package_files().items():
        path = input_root / relative
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        _write_new(path, content)


def _materialize_and_probe_resources(
    root: Path, *, manifest: TrialManifest, database_owner_token: str
) -> TrialEnvironmentFacts:
    transient = root / "transient"
    database_url = os.environ.get(_DATABASE_URL_ENV)
    if not database_url:
        raise TrialRehearsalError(f"{_DATABASE_URL_ENV} is required")
    database_name = conninfo_to_dict(database_url).get("dbname")
    if database_name != manifest.database_target:
        raise TrialRehearsalError("PostgreSQL database target differs from Trial Manifest")
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(_DATABASE_SCHEMA)))
            cursor.execute(
                sql.SQL(
                    "CREATE TABLE {}.trial_ownership "
                    "(target text PRIMARY KEY, owner_token text NOT NULL UNIQUE)"
                ).format(sql.Identifier(_DATABASE_SCHEMA))
            )
            cursor.execute(
                sql.SQL(
                    "INSERT INTO {}.trial_ownership(target, owner_token) VALUES (%s, %s)"
                ).format(sql.Identifier(_DATABASE_SCHEMA)),
                (manifest.database_target, database_owner_token),
            )
            cursor.execute(
                sql.SQL("SELECT target, owner_token FROM {}.trial_ownership").format(
                    sql.Identifier(_DATABASE_SCHEMA)
                )
            )
            row = cursor.fetchone()
            cursor.execute("SELECT current_database()")
            current_database = cursor.fetchone()
    database_owned = row == (manifest.database_target, database_owner_token) and (
        current_database == (manifest.database_target,)
    )

    output_path = transient / "output" / Path(manifest.output_root)
    output_path.mkdir(mode=0o700, parents=True)
    output_marker = output_path / _OWNER_MARKER
    _write_new(output_marker, _OWNER_VALUE)
    output_owned = output_path.is_dir() and output_marker.read_bytes() == _OWNER_VALUE

    outbound_disabled = _probe_outbound_isolation()
    live_provider_enabled = os.environ.get("HUMAN_COS_LIVE_PROVIDER_SMOKE") == "1"
    provider_secrets_present = any(
        os.environ.get(name)
        for name in (
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "HUMAN_COS_OPENAI_API_KEY",
            "HUMAN_COS_ANTHROPIC_API_KEY",
        )
    )
    return TrialEnvironmentFacts(
        observed_source_commit_sha=manifest.source_commit_sha,
        observed_database_target=manifest.database_target if database_owned else None,
        observed_output_root=manifest.output_root if output_owned else None,
        sandbox_mode=True,
        live_provider_enabled=live_provider_enabled,
        outbound_network_enabled=not outbound_disabled,
        external_tools_enabled=False,
        reality_execution_enabled=False,
        sensitive_data_present=False,
        real_experts_enabled=False,
        provider_secrets_present=provider_secrets_present,
        trial_database_disposable=database_owned,
        database_ownership_marker_present=database_owned,
        output_root_disposable=output_owned,
        output_root_ownership_marker_present=output_owned,
    )


def _installed_build_commit_sha() -> str:
    try:
        value = _BUILD_COMMIT_RESOURCE.read_text(encoding="ascii").strip()
    except OSError as exc:
        raise TrialRehearsalError("installed wheel lacks build identity") from exc
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise TrialRehearsalError("installed wheel build identity is malformed")
    return value


def _verify_installed_build_identity() -> tuple[str, str]:
    expected = os.environ.get(_EXPECTED_BUILD_ENV, "")
    observed = _installed_build_commit_sha()
    if expected == "" or expected == "0" * 40:
        raise TrialRehearsalError(f"{_EXPECTED_BUILD_ENV} must name the exact reviewed commit")
    if observed == "0" * 40 or observed != expected:
        raise TrialRehearsalError("installed wheel build identity differs from expected commit")
    return expected, observed


def _probe_outbound_isolation() -> bool:
    if os.environ.get(_ISOLATION_ENV) != _ISOLATION_VALUE:
        raise TrialRehearsalError("Docker internal-network isolation provenance is absent")
    return _probe_outbound_connections()


def _probe_outbound_connections() -> bool:
    """Shared connection probes; callers separately verify isolation provenance."""
    for address in (("1.1.1.1", 443), ("8.8.8.8", 53)):
        try:
            connection = socket.create_connection(address, timeout=0.25)
        except OSError:
            continue
        connection.close()
        raise TrialRehearsalError("outbound network probe unexpectedly succeeded")
    return True


def _cleanup_postgres_resources(manifest: TrialManifest, database_owner_token: str) -> None:
    database_url = os.environ.get(_DATABASE_URL_ENV)
    if not database_url:
        raise TrialRehearsalError("PostgreSQL cleanup target is unavailable")
    if conninfo_to_dict(database_url).get("dbname") != manifest.database_target:
        raise TrialRehearsalError("refusing cleanup outside the manifest PostgreSQL target")
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regnamespace(%s)", (_DATABASE_SCHEMA,))
            if cursor.fetchone() == (None,):
                return
            try:
                cursor.execute(
                    sql.SQL("SELECT target, owner_token FROM {}.trial_ownership").format(
                        sql.Identifier(_DATABASE_SCHEMA)
                    )
                )
                ownership = cursor.fetchall()
            except psycopg.Error as exc:
                raise TrialRehearsalError(
                    "refusing PostgreSQL cleanup without the exact ownership record"
                ) from exc
            if ownership != [(manifest.database_target, database_owner_token)]:
                raise TrialRehearsalError("refusing PostgreSQL cleanup for an unowned trial schema")
            cursor.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(_DATABASE_SCHEMA))
            )
            cursor.execute("SELECT to_regnamespace(%s)", (_DATABASE_SCHEMA,))
            if cursor.fetchone() != (None,):
                raise TrialRehearsalError("PostgreSQL trial schema cleanup was not proven")


def _exercise_installed_application_chain(
    manifest: TrialManifest,
) -> InstalledApplicationChainReceipt:
    database_url = os.environ.get(_DATABASE_URL_ENV)
    if not database_url or conninfo_to_dict(database_url).get("dbname") != manifest.database_target:
        raise TrialRehearsalError("installed application chain lacks the exact trial database")
    with psycopg.connect(database_url) as connection:
        return exercise_installed_application_chain(connection)


def _assert_application_resources_clean(manifest: TrialManifest) -> None:
    database_url = os.environ.get(_DATABASE_URL_ENV)
    if not database_url or conninfo_to_dict(database_url).get("dbname") != manifest.database_target:
        raise TrialRehearsalError("application cleanup lacks the exact trial database")
    with psycopg.connect(database_url) as connection:
        try:
            assert_installed_application_resources_clean(connection)
        except InstalledApplicationCleanupError as exc:
            raise TrialRehearsalError("installed application cleanup was not proven") from exc


def _assert_owned_root(root: Path, expected_identity: tuple[int, int]) -> None:
    root_stat = root.lstat()
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        raise TrialRehearsalError("rehearsal work root must be a non-link directory")
    if (root_stat.st_dev, root_stat.st_ino) != expected_identity:
        raise TrialRehearsalError("rehearsal work root identity changed")
    marker = root / _OWNER_MARKER
    marker_stat = marker.lstat()
    if (
        stat.S_ISLNK(marker_stat.st_mode)
        or not stat.S_ISREG(marker_stat.st_mode)
        or marker_stat.st_nlink != 1
        or marker.read_bytes() != _OWNER_VALUE
    ):
        raise TrialRehearsalError("rehearsal work root lacks the exact ownership marker")


def _case_record_document(
    record: TrialCaseReplayRecord,
    *,
    bundle_receipt: TrialInputBundleReceipt,
    attempt: TrialAttemptReceipt,
    root_manifest: TrialManifest,
    root_canonical: TrialCanonicalAdmission,
    root_environment: TrialEnvironmentAdmission,
) -> dict[str, object]:
    admission = record.case_admission
    return {
        "attempt": attempt.to_document(),
        "input_bundle_receipt": bundle_receipt.to_document(),
        "root_manifest": root_manifest.to_document(),
        "root_canonical_admission": root_canonical.to_document(),
        "root_environment": root_environment.to_document(),
        "case_admission": {
            "case_key": admission.case_key,
            "case_hash": admission.case_hash,
            "pack_hash": admission.pack_hash,
            "root_canonical_admission_hash": admission.root_canonical_admission_hash,
            "attempt_receipt_hash": admission.attempt_receipt_hash,
            "root_bundle_receipt_hash": admission.root_bundle_receipt_hash,
            "root_detached_input_address": admission.root_detached_input_address,
            "root_payload_documents_sha256": admission.root_payload_documents_sha256,
            "root_semantic_fingerprint": admission.root_semantic_fingerprint,
            "derived_case_sha256": admission.derived_case_sha256,
            "case_derivation_hash": admission.case_derivation_hash,
            "manifest": admission.manifest.to_document(),
            "canonical_admission": admission.canonical_admission.to_document(),
            "environment": admission.environment.to_document(),
            "admission_hash": admission.admission_hash,
        },
        "stop": record.stop.to_document(),
        "result": record.result.to_document(),
        "acceptance": {
            "accepted": record.acceptance.accepted,
            "mismatches": list(record.acceptance.mismatches),
            "expectation_hash": record.acceptance.expectation_hash,
            "observed_result_hash": record.acceptance.observed_result_hash,
            "acceptance_hash": record.acceptance.acceptance_hash,
        },
        "record_hash": record.record_hash,
    }


def _export_case_audit(
    target: Path,
    *,
    record: TrialCaseReplayRecord,
    bundle_receipt: TrialInputBundleReceipt,
    attempt: TrialAttemptReceipt,
    root_manifest: TrialManifest,
    root_canonical: TrialCanonicalAdmission,
    root_environment: TrialEnvironmentAdmission,
) -> str:
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{target.name}.tmp-", dir=target.parent))
    try:
        input_root = temporary / "input"
        input_root.mkdir(mode=0o700)
        for relative, content in _bootstrap_package_files().items():
            path = input_root / relative
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            _write_new(path, content)
        document = _case_record_document(
            record,
            bundle_receipt=bundle_receipt,
            attempt=attempt,
            root_manifest=root_manifest,
            root_canonical=root_canonical,
            root_environment=root_environment,
        )
        record_bytes = (
            json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
        ).encode("utf-8")
        if len(record_bytes) > TRIAL_HARD_CAPS.max_audit_payload_bytes:
            raise TrialRehearsalError("canonical case audit exceeds hard cap")
        _write_new(temporary / "record.json", record_bytes)
        address = cast(str, canonical_document_sha256(document))
        _write_new(temporary / "record_address.sha256", (address + "\n").encode("ascii"))
        _publish_no_replace(temporary, target)
        return address
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _verified_environment(
    stored: TrialEnvironmentAdmission,
    *,
    attempt: TrialAttemptReceipt,
    manifest: TrialManifest,
    canonical: _AuthenticatedCanonicalAdmission,
) -> TrialEnvironmentAdmission:
    recreated = evaluate_environment_admission(
        attempt=attempt,
        manifest=manifest,
        canonical_admission=canonical,
        facts=TrialEnvironmentFacts(
            observed_source_commit_sha=stored.observed_source_commit_sha,
            observed_database_target=stored.observed_database_target,
            observed_output_root=stored.observed_output_root,
            sandbox_mode=stored.sandbox_mode,
            live_provider_enabled=not stored.live_provider_disabled,
            outbound_network_enabled=not stored.outbound_network_disabled,
            external_tools_enabled=not stored.external_tools_disabled,
            reality_execution_enabled=not stored.reality_execution_disabled,
            sensitive_data_present=not stored.sensitive_data_absent,
            real_experts_enabled=not stored.real_experts_disabled,
            provider_secrets_present=not stored.provider_secrets_disabled,
            trial_database_disposable=stored.trial_database_disposable,
            database_ownership_marker_present=stored.database_ownership_marker_present,
            output_root_disposable=stored.output_root_disposable,
            output_root_ownership_marker_present=stored.output_root_ownership_marker_present,
            public_historical_approval_proven=True,
        ),
        admission_id=stored.admission_id,
        frozen_at=stored.frozen_at,
    )
    if recreated != stored:
        raise TrialRehearsalError("case audit Environment is not evaluator-reproducible")
    return recreated


def _verify_case_audit(path: Path) -> tuple[str, TrialCaseReplayRecord]:
    if path.is_symlink() or not path.is_dir():
        raise TrialRehearsalError("case audit root must be a non-link directory")
    if {item.name for item in path.iterdir()} != {
        "input",
        "record.json",
        "record_address.sha256",
    }:
        raise TrialRehearsalError("case audit inventory differs from frozen structure")
    record_bytes = _read_regular(
        path / "record.json", maximum=TRIAL_HARD_CAPS.max_audit_payload_bytes
    )
    address_bytes = _read_regular(path / "record_address.sha256", maximum=128)
    try:
        document = json.loads(record_bytes)
        address = address_bytes.decode("ascii").strip()
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrialRehearsalError("case audit metadata is invalid") from exc
    if not isinstance(document, dict) or address != canonical_document_sha256(document):
        raise TrialRehearsalError("case audit detached address mismatch")

    attempt = TrialAttemptReceipt.model_validate(document["attempt"])
    receipt = TrialInputBundleReceipt.model_validate(document["input_bundle_receipt"])
    root_manifest = TrialManifest.model_validate(document["root_manifest"])
    stored_canonical = TrialCanonicalAdmission.model_validate(document["root_canonical_admission"])
    stored_environment = TrialEnvironmentAdmission.model_validate(document["root_environment"])
    bundle = verify_input_bundle(
        path / "input",
        attempt=attempt,
        verified_at=receipt.verified_at,
    )
    if bundle.receipt != receipt or bundle.manifest != root_manifest:
        raise TrialRehearsalError("case audit input differs from its serialized root receipt")
    canonical = _admit_pre_freeze_bundle(
        bundle,
        admission_id=stored_canonical.admission_id,
        frozen_at=stored_canonical.frozen_at,
    )
    if canonical.record != stored_canonical:
        raise TrialRehearsalError("case audit canonical admission is not package-reproducible")
    environment = _verified_environment(
        stored_environment,
        attempt=attempt,
        manifest=root_manifest,
        canonical=canonical,
    )
    _register_environment_provenance(environment, canonical)
    assert_environment_admission_binding(attempt, root_manifest, canonical.record, environment)

    raw_admission = document["case_admission"]
    if not isinstance(raw_admission, dict):
        raise TrialRehearsalError("case audit admission is invalid")
    case_admission = TrialCanonicalCaseAdmission(
        case_key=str(raw_admission["case_key"]),
        case_hash=str(raw_admission["case_hash"]),
        pack_hash=str(raw_admission["pack_hash"]),
        root_canonical_admission_hash=str(raw_admission["root_canonical_admission_hash"]),
        attempt_receipt_hash=str(raw_admission["attempt_receipt_hash"]),
        root_bundle_receipt_hash=str(raw_admission["root_bundle_receipt_hash"]),
        root_detached_input_address=str(raw_admission["root_detached_input_address"]),
        root_payload_documents_sha256=str(raw_admission["root_payload_documents_sha256"]),
        root_semantic_fingerprint=str(raw_admission["root_semantic_fingerprint"]),
        derived_case_sha256=str(raw_admission["derived_case_sha256"]),
        case_derivation_hash=str(raw_admission["case_derivation_hash"]),
        manifest=TrialManifest.model_validate(raw_admission["manifest"]),
        canonical_admission=TrialCanonicalAdmission.model_validate(
            raw_admission["canonical_admission"]
        ),
        environment=TrialEnvironmentAdmission.model_validate(raw_admission["environment"]),
        admission_hash=str(raw_admission["admission_hash"]),
    )
    raw_acceptance = document["acceptance"]
    if not isinstance(raw_acceptance, dict):
        raise TrialRehearsalError("case audit acceptance is invalid")
    replay = TrialCaseReplayRecord(
        case_key=case_admission.case_key,
        case_hash=case_admission.case_hash,
        case_admission=case_admission,
        stop=TrialStop.model_validate(document["stop"]),
        result=TrialResult.model_validate(document["result"]),
        acceptance=TrialCaseAcceptance(
            accepted=bool(raw_acceptance["accepted"]),
            mismatches=tuple(str(item) for item in raw_acceptance["mismatches"]),
            expectation_hash=str(raw_acceptance["expectation_hash"]),
            observed_result_hash=str(raw_acceptance["observed_result_hash"]),
            acceptance_hash=str(raw_acceptance["acceptance_hash"]),
        ),
        record_hash=str(document["record_hash"]),
    )
    replay.assert_integrity(
        root_admission=canonical,
        root_bundle=bundle,
        root_environment=environment,
    )
    return address, replay


class _RequestedOperatorAbort(Exception):
    pass


class _CleanupRefused(Exception):
    pass


def _exercise_sbx5_failure_probe(fixture_key: str, probe_root: Path) -> None:
    if fixture_key == "additional:model-output-invalid":
        json.loads("{")
    elif fixture_key == "additional:infrastructure-failure":
        database_url = os.environ[_DATABASE_URL_ENV]
        connection = psycopg.connect(database_url)
        connection.close()
        connection.execute("SELECT 1")
    elif fixture_key == "additional:persistence-duplicate":
        database_url = os.environ[_DATABASE_URL_ENV]
        with psycopg.connect(database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL(
                        "INSERT INTO {}.trial_ownership(target, owner_token) VALUES (%s, %s)"
                    ).format(sql.Identifier(_DATABASE_SCHEMA)),
                    (CANONICAL_TRIAL_CASE_PACK.pack_id, "duplicate-failure-probe"),
                )
                cursor.execute(
                    sql.SQL(
                        "INSERT INTO {}.trial_ownership(target, owner_token) VALUES (%s, %s)"
                    ).format(sql.Identifier(_DATABASE_SCHEMA)),
                    (CANONICAL_TRIAL_CASE_PACK.pack_id, "duplicate-failure-probe"),
                )
    elif fixture_key == "additional:operator-abort":
        raise _RequestedOperatorAbort("package-owned operator-abort probe")
    elif fixture_key == "additional:cleanup-refusal-non-trial-target":
        target = probe_root / "non-trial-target"
        target.mkdir()
        target_stat = target.lstat()
        try:
            _assert_owned_root(target, (target_stat.st_dev, target_stat.st_ino))
        except (OSError, TrialRehearsalError) as exc:
            raise _CleanupRefused("cleanup target lacks SBX5 ownership") from exc
    else:  # pragma: no cover - caller filters the frozen SBX5 fixture vocabulary.
        raise TrialRehearsalError(f"unsupported SBX5 fixture: {fixture_key}")
    raise TrialRehearsalError(f"SBX5 fixture did not produce its expected failure: {fixture_key}")


def _map_failure_to_stop(exc: BaseException) -> TrialStopSignal:
    """Map an observed operation failure to the code-owned terminal vocabulary."""

    if isinstance(exc, json.JSONDecodeError):
        return TrialStopSignal(
            condition=TrialStopCondition.MODEL_OUTPUT_INVALID,
            phase=TrialStopPhase.EXECUTION,
            reason="model output failed strict JSON validation",
        )
    if isinstance(exc, psycopg.errors.UniqueViolation):
        return TrialStopSignal(
            condition=TrialStopCondition.ARTIFACT_INTEGRITY_FAILURE,
            phase=TrialStopPhase.PERSISTENCE,
            reason="PostgreSQL rejected a duplicate immutable artifact",
        )
    if isinstance(exc, _RequestedOperatorAbort) or isinstance(exc, KeyboardInterrupt):
        return TrialStopSignal(
            condition=TrialStopCondition.OPERATOR_ABORTED,
            phase=TrialStopPhase.EXECUTION,
            reason="operator interrupted the trial",
        )
    if isinstance(exc, _CleanupRefused):
        return TrialStopSignal(
            condition=TrialStopCondition.INFRASTRUCTURE_FAILURE,
            phase=TrialStopPhase.CLEANUP,
            reason="cleanup refused a non-trial target",
        )
    if isinstance(exc, (OSError, psycopg.Error)):
        return TrialStopSignal(
            condition=TrialStopCondition.INFRASTRUCTURE_FAILURE,
            phase=TrialStopPhase.EXECUTION,
            reason="trial infrastructure operation failed",
        )
    raise TrialRehearsalError("failure has no authorized stop mapping") from exc


def _exercise_sbx5_fixtures(
    root: Path,
    *,
    bundle: VerifiedTrialBundle,
    canonical: _AuthenticatedCanonicalAdmission,
    environment: TrialEnvironmentAdmission,
    preserved_artifacts: list[TrialArtifactRef],
) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
    manifest = bundle.manifest
    attempt = bundle.attempt
    probe_root = root / "transient" / "failure-probes"
    probe_root.mkdir(mode=0o700)
    records: list[tuple[str, str]] = []
    audit_addresses: list[tuple[str, str]] = []
    for fixture in CANONICAL_TRIAL_CASE_PACK.additional_fixtures:
        if fixture.exercise_owner != "TRIAL-SBX5":
            continue
        try:
            _exercise_sbx5_failure_probe(fixture.fixture_key, probe_root)
        except BaseException as exc:
            signal = _map_failure_to_stop(exc)
        else:  # pragma: no cover - every package-owned negative probe must fail.
            raise TrialRehearsalError(f"SBX5 fixture did not fail: {fixture.fixture_key}")
        if (signal.condition, signal.phase) != (
            fixture.expected_stop_condition,
            fixture.expected_stop_phase,
        ):
            raise TrialRehearsalError(
                f"real stop mapping differs from frozen fixture: {fixture.fixture_key}"
            )
        ledger = TrialStopLedger(
            attempt_receipt_hash=attempt.attempt_receipt_hash,
            manifest=manifest,
            environment=environment,
        )
        ledger.record_position(
            TrialRuntimePosition(
                mode=manifest.case_mode,
                state=_BOOTSTRAP_CONTROL_STATES[0],
                case_revision=manifest.case_revision,
            ),
            controlling_ref=f"sbx5:failure-probe:{fixture.fixture_key}",
            recorded_at=_RECORDED_AT,
        )
        ledger.record_artifacts(fixture.required_artifacts)
        ledger.signal(
            TrialStopSignal(
                condition=signal.condition,
                phase=signal.phase,
                reason=signal.reason,
                controlling_artifact_refs=fixture.required_controlling_artifact_refs,
            )
        )
        stop, result = ledger.freeze_terminal(
            stop_id=f"stop:{fixture.fixture_key}",
            result_id=f"result:{fixture.fixture_key}",
            trial_capability_acceptance=TrialCapabilityAcceptance.PASS,
            substantive_case_outcome=None,
            limitations=("SBX5 package-owned failure-path rehearsal only.",),
            stopped_at=_RECORDED_AT,
        )
        if (
            stop.stop_condition,
            stop.stop_phase,
            result.stop_condition,
            result.stop_phase,
            result.controlling_artifact_refs,
            result.produced_artifacts,
            result.cleanup_disposition,
        ) != (
            fixture.expected_stop_condition,
            fixture.expected_stop_phase,
            fixture.expected_stop_condition,
            fixture.expected_stop_phase,
            fixture.required_controlling_artifact_refs,
            fixture.required_artifacts,
            TrialCleanupDisposition.NOT_ATTEMPTED,
        ):
            raise TrialRehearsalError(
                f"SBX5 fixture result differs from frozen expectation: {fixture.fixture_key}"
            )
        records.append((fixture.fixture_key, result.result_hash))
        audit_path = root / "failure-audits" / f"{len(records):02d}"
        audit_address = export_audit_bundle(
            audit_path,
            attempt=attempt,
            input_bundle_receipt=bundle.receipt,
            manifest=manifest,
            canonical_admission=canonical,
            environment=environment,
            stop=stop,
            result=result,
        )
        verified = verify_audit_bundle(audit_path)
        if verified.bundle_address != audit_address or verified.result != result:
            raise TrialRehearsalError(
                f"SBX5 failure audit verification failed: {fixture.fixture_key}"
            )
        audit_addresses.append((fixture.fixture_key, audit_address))
        preserved_artifacts.append(
            TrialArtifactRef(
                kind="SBX5_FAILURE_AUDIT_BUNDLE",
                ref=f"failure-audits/{len(records):02d}",
                sha256=audit_address,
            )
        )
    return tuple(records), tuple(audit_addresses)


def _preserve_admitted_failure(
    root: Path,
    *,
    bundle: VerifiedTrialBundle,
    canonical: _AuthenticatedCanonicalAdmission,
    environment: TrialEnvironmentAdmission,
    original: BaseException,
    cleanup_disposition: TrialCleanupDisposition,
    reached_states: tuple[RuntimeState, ...],
    preserved_artifacts: tuple[TrialArtifactRef, ...],
) -> str:
    if cleanup_disposition is TrialCleanupDisposition.FAILED:
        signal = TrialStopSignal(
            condition=TrialStopCondition.INFRASTRUCTURE_FAILURE,
            phase=TrialStopPhase.CLEANUP,
            reason="owned-resource cleanup failed after an admitted trial failure",
        )
    else:
        try:
            signal = _map_failure_to_stop(original)
        except TrialRehearsalError:
            signal = TrialStopSignal(
                condition=TrialStopCondition.INFRASTRUCTURE_FAILURE,
                phase=TrialStopPhase.EXECUTION,
                reason="the admitted installed rehearsal failed closed",
            )
    ledger = TrialStopLedger(
        attempt_receipt_hash=bundle.attempt.attempt_receipt_hash,
        manifest=bundle.manifest,
        environment=environment,
    )
    for state in reached_states:
        ledger.record_position(
            TrialRuntimePosition(
                mode=bundle.manifest.case_mode,
                state=state,
                case_revision=bundle.manifest.case_revision,
            ),
            controlling_ref=f"sbx5:admitted-real-failure:{state.value}",
            recorded_at=_RECORDED_AT,
        )
    ledger.record_artifacts(preserved_artifacts)
    ledger.signal(signal)
    stop, initial_result = ledger.freeze_terminal(
        stop_id="stop:sbx5-admitted-real-failure",
        result_id="result:sbx5-admitted-real-failure",
        trial_capability_acceptance=TrialCapabilityAcceptance.PASS,
        substantive_case_outcome=None,
        limitations=("Actual installed-rehearsal failure; no substantive Case outcome.",),
        stopped_at=_RECORDED_AT,
    )
    result_payload = initial_result.model_dump(
        mode="json", exclude={"result_hash"}, exclude_none=True
    )
    result_payload.update(
        audit_export_status=TrialAuditExportStatus.COMPLETE,
        cleanup_disposition=cleanup_disposition,
    )
    result = freeze_trial_result(TrialResultPayload.model_validate(result_payload))
    failure_audit_root = root / "actual-failure-audit"
    address = export_audit_bundle(
        failure_audit_root,
        attempt=bundle.attempt,
        input_bundle_receipt=bundle.receipt,
        manifest=bundle.manifest,
        canonical_admission=canonical,
        environment=environment,
        stop=stop,
        result=result,
    )
    verified = verify_audit_bundle(failure_audit_root)
    if verified.bundle_address != address or verified.result != result:
        raise TrialRehearsalError("admitted failure audit verification differs from export")
    return address


def run_installed_rehearsal(work_root: str | os.PathLike[str]) -> TrialInstalledRehearsalReceipt:
    """Run the exact package-owned integrated rehearsal in a new local work root."""

    root = Path(work_root)
    if root.exists() or root.is_symlink():
        raise TrialRehearsalError("rehearsal work root must not already exist")
    expected_build_commit_sha, installed_build_commit_sha = _verify_installed_build_identity()
    database_owner_token = secrets.token_hex(32)
    root_identity: tuple[int, int] | None = None
    manifest: TrialManifest | None = None
    bundle: VerifiedTrialBundle | None = None
    canonical: _AuthenticatedCanonicalAdmission | None = None
    environment: TrialEnvironmentAdmission | None = None
    reached_states: list[RuntimeState] = [RuntimeState.CASE_CREATED]
    preserved_artifacts: list[TrialArtifactRef] = []
    try:
        root_identity = _initialize_owned_root(root)
        _materialize_owned_input(root)
        _assert_owned_root(root, root_identity)
        input_root = root / "transient" / "input"
        bundle = verify_input_bundle(
            input_root,
            attempt_id="sbx5-installed-rehearsal",
            started_at=_RECORDED_AT,
            verified_at=_RECORDED_AT,
        )
        manifest = bundle.manifest
        canonical = _admit_pre_freeze_bundle(
            bundle,
            admission_id="canonical:sbx5-installed-rehearsal",
            frozen_at=_RECORDED_AT,
        )
        environment = evaluate_environment_admission(
            attempt=bundle.attempt,
            manifest=bundle.manifest,
            canonical_admission=canonical,
            facts=_materialize_and_probe_resources(
                root,
                manifest=bundle.manifest,
                database_owner_token=database_owner_token,
            ),
            admission_id="environment:sbx5-installed-rehearsal",
            frozen_at=_RECORDED_AT,
        )
        if environment.status is not TrialAdmissionStatus.PASS:
            raise TrialRehearsalError("package-owned rehearsal Environment did not PASS")
        _register_environment_provenance(environment, canonical)

        application_chain = _exercise_installed_application_chain(bundle.manifest)
        application_chain.assert_integrity()
        application_chain_bytes = (
            json.dumps(application_chain.to_document(), sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
        _write_new(root / _APPLICATION_CHAIN_RECEIPT_NAME, application_chain_bytes)
        reached_states = list(
            _BOOTSTRAP_CONTROL_STATES[
                : _BOOTSTRAP_CONTROL_STATES.index(RuntimeState.CRITICAL_NODE_REVIEW) + 1
            ]
        )
        preserved_artifacts.append(
            TrialArtifactRef(
                kind="INSTALLED_APPLICATION_CHAIN_RECEIPT",
                ref=_APPLICATION_CHAIN_RECEIPT_NAME,
                sha256=application_chain.receipt_hash,
            )
        )

        first = run_canonical_case_pack(
            bundle=bundle,
            canonical_admission=canonical,
            environment=environment,
            recorded_at=_RECORDED_AT,
        )
        replay = run_canonical_case_pack(
            bundle=bundle,
            canonical_admission=canonical,
            environment=environment,
            recorded_at=_RECORDED_AT,
        )
        if not first.all_accepted or first != replay:
            raise TrialRehearsalError("canonical case-pack replay did not deterministically PASS")
        furthest_record = max(
            first.records, key=lambda record: len(record.result.runtime_trajectory)
        )
        reached_states = [step.position.state for step in furthest_record.result.runtime_trajectory]

        case_audit_root = root / "case-audits"
        case_audit_addresses: list[tuple[str, str]] = []
        verified_case_result_hashes: list[tuple[str, str]] = []
        for index, record in enumerate(first.records, start=1):
            audit_path = case_audit_root / f"{index:02d}"
            case_address = _export_case_audit(
                audit_path,
                record=record,
                bundle_receipt=bundle.receipt,
                attempt=bundle.attempt,
                root_manifest=bundle.manifest,
                root_canonical=canonical.record,
                root_environment=environment,
            )
            verified_address, verified_record = _verify_case_audit(audit_path)
            if verified_address != case_address or verified_record != record:
                raise TrialRehearsalError(
                    f"canonical case audit verification failed: {record.case_key}"
                )
            case_audit_addresses.append((record.case_key, case_address))
            verified_case_result_hashes.append(
                (record.case_key, verified_record.result.result_hash)
            )
            preserved_artifacts.append(
                TrialArtifactRef(
                    kind="CANONICAL_CASE_AUDIT_BUNDLE",
                    ref=f"case-audits/{index:02d}",
                    sha256=case_address,
                )
            )

        fixture_result_hashes, fixture_audit_addresses = _exercise_sbx5_fixtures(
            root,
            bundle=bundle,
            canonical=canonical,
            environment=environment,
            preserved_artifacts=preserved_artifacts,
        )

        control = run_bootstrap_control_rehearsal(
            bundle=bundle,
            canonical_admission=canonical,
            environment=environment,
            recorded_at=_RECORDED_AT,
        )
        audit_root = root / "audit"
        audit_address = export_audit_bundle(
            audit_root,
            attempt=bundle.attempt,
            input_bundle_receipt=bundle.receipt,
            manifest=bundle.manifest,
            canonical_admission=canonical,
            environment=environment,
            stop=control.stop,
            result=control.result,
        )
        verified = verify_audit_bundle(audit_root)
        if verified.bundle_address != audit_address:
            raise TrialRehearsalError("independent audit verification differs from export")
        preserved_artifacts.append(
            TrialArtifactRef(kind="CONTROL_AUDIT_BUNDLE", ref="audit", sha256=audit_address)
        )

        _cleanup_postgres_resources(bundle.manifest, database_owner_token)
        _assert_application_resources_clean(bundle.manifest)
        _assert_owned_root(root, root_identity)
        transient_root = root / "transient"
        shutil.rmtree(transient_root)
        if transient_root.exists() or transient_root.is_symlink():
            raise TrialRehearsalError("transient resource cleanup did not complete")

        lifecycle_payload = control.result.model_dump(
            mode="json", exclude={"result_hash"}, exclude_none=True
        )
        lifecycle_payload.update(
            audit_export_status=TrialAuditExportStatus.COMPLETE,
            cleanup_disposition=TrialCleanupDisposition.COMPLETE,
        )
        lifecycle_result = freeze_trial_result(TrialResultPayload.model_validate(lifecycle_payload))
        lifecycle_audit_root = root / "lifecycle-audit"
        lifecycle_audit_address = export_audit_bundle(
            lifecycle_audit_root,
            attempt=bundle.attempt,
            input_bundle_receipt=bundle.receipt,
            manifest=bundle.manifest,
            canonical_admission=canonical,
            environment=environment,
            stop=control.stop,
            result=lifecycle_result,
        )
        verified_lifecycle = verify_audit_bundle(lifecycle_audit_root)
        if (
            verified_lifecycle.bundle_address != lifecycle_audit_address
            or verified_lifecycle.result != lifecycle_result
        ):
            raise TrialRehearsalError("audited lifecycle result verification differs from export")
        preserved_artifacts.append(
            TrialArtifactRef(
                kind="LIFECYCLE_AUDIT_BUNDLE",
                ref="lifecycle-audit",
                sha256=lifecycle_audit_address,
            )
        )

        seed = TrialInstalledRehearsalReceipt(
            status="PASS",
            expected_build_commit_sha=expected_build_commit_sha,
            installed_build_commit_sha=installed_build_commit_sha,
            case_pack_hash=first.pack_hash,
            first_run_hash=first.run_hash,
            replay_run_hash=replay.run_hash,
            installed_application_chain_receipt_hash=application_chain.receipt_hash,
            control_audit_bundle_address=audit_address,
            verified_control_audit_bundle_address=verified.bundle_address,
            lifecycle_audit_bundle_address=lifecycle_audit_address,
            verified_lifecycle_audit_bundle_address=verified_lifecycle.bundle_address,
            lifecycle_result_hash=lifecycle_result.result_hash,
            case_audit_addresses=tuple(case_audit_addresses),
            verified_case_result_hashes=tuple(verified_case_result_hashes),
            sbx5_fixture_result_hashes=fixture_result_hashes,
            sbx5_fixture_audit_addresses=fixture_audit_addresses,
            transient_resources_cleaned=True,
            audit_preserved=(
                audit_root.is_dir()
                and case_audit_root.is_dir()
                and (root / "failure-audits").is_dir()
                and lifecycle_audit_root.is_dir()
                and (root / _APPLICATION_CHAIN_RECEIPT_NAME).is_file()
            ),
            final_synthesis_authorized=False,
            publication_authorized=False,
            reality_execution_authorized=False,
            receipt_hash="",
        )
        receipt = TrialInstalledRehearsalReceipt(
            **{
                **seed.to_document(include_hash=False),
                "receipt_hash": canonical_document_sha256(seed.to_document(include_hash=False)),
            }
        )
        receipt.assert_integrity()
        receipt_bytes = (
            json.dumps(receipt.to_document(), sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        _write_new(root / _RECEIPT_NAME, receipt_bytes)
        return receipt
    except BaseException as original:
        cleanup_failures: list[BaseException] = []
        if isinstance(original, InstalledApplicationCleanupError):
            cleanup_failures.append(original)
        if manifest is not None:
            try:
                _cleanup_postgres_resources(manifest, database_owner_token)
            except (OSError, psycopg.Error, TrialRehearsalError) as exc:
                cleanup_failures.append(exc)
            try:
                _assert_application_resources_clean(manifest)
            except (OSError, psycopg.Error, TrialRehearsalError) as exc:
                cleanup_failures.append(exc)
        root_is_owned = False
        if root_identity is not None and root.exists() and not root.is_symlink():
            try:
                _assert_owned_root(root, root_identity)
            except (OSError, TrialRehearsalError) as exc:
                cleanup_failures.append(exc)
            else:
                root_is_owned = True
        admitted = (
            bundle is not None
            and canonical is not None
            and environment is not None
            and environment.status is TrialAdmissionStatus.PASS
        )
        if admitted and root_is_owned:
            assert bundle is not None
            assert canonical is not None
            assert environment is not None
            if (
                isinstance(original, InstalledApplicationChainError)
                and original.checkpoint is not None
            ):
                try:
                    original.checkpoint.assert_integrity()
                    checkpoint_bytes = (
                        json.dumps(
                            original.checkpoint.to_document(),
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n"
                    ).encode("utf-8")
                    _write_new(root / _APPLICATION_CHAIN_CHECKPOINT_NAME, checkpoint_bytes)
                    reached_states = list(
                        _BOOTSTRAP_CONTROL_STATES[
                            : _BOOTSTRAP_CONTROL_STATES.index(RuntimeState.CRITICAL_NODE_REVIEW) + 1
                        ]
                    )
                    preserved_artifacts.append(
                        TrialArtifactRef(
                            kind="INSTALLED_APPLICATION_CHAIN_CHECKPOINT",
                            ref=_APPLICATION_CHAIN_CHECKPOINT_NAME,
                            sha256=original.checkpoint.checkpoint_hash,
                        )
                    )
                except (OSError, ValueError) as exc:
                    cleanup_failures.append(exc)
            transient_root = root / "transient"
            if not cleanup_failures and (transient_root.exists() or transient_root.is_symlink()):
                try:
                    shutil.rmtree(transient_root)
                except OSError as exc:
                    cleanup_failures.append(exc)
            cleanup_disposition = (
                TrialCleanupDisposition.FAILED
                if cleanup_failures
                else TrialCleanupDisposition.COMPLETE
            )
            try:
                _preserve_admitted_failure(
                    root,
                    bundle=bundle,
                    canonical=canonical,
                    environment=environment,
                    original=original,
                    cleanup_disposition=cleanup_disposition,
                    reached_states=tuple(reached_states),
                    preserved_artifacts=tuple(preserved_artifacts),
                )
            except (OSError, psycopg.Error, TrialRehearsalError) as exc:
                cleanup_failures.append(exc)
        elif root_is_owned:
            try:
                shutil.rmtree(root)
            except OSError as exc:
                cleanup_failures.append(exc)
        if cleanup_failures:
            raise TrialRehearsalError(
                "owned resource cleanup failed during trial failure or interruption"
            ) from original
        raise
