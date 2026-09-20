"""Deterministic, fail-closed Environment Admission for TRIAL-SBX1.

This module evaluates supplied observable sandbox facts. It does not create a
database, probe a network, invoke a provider, or grant execution authority.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .bundle import (
    _AuthenticatedCanonicalAdmission,
    _canonical_is_authenticated,
    _canonical_matches_provenance,
    _canonical_record,
)
from .contracts import (
    TRIAL_HARD_CAPS,
    TrialAdapterLane,
    TrialAdmissionStatus,
    TrialAttemptReceipt,
    TrialCanonicalAdmission,
    TrialCanonicalAdmissionStatus,
    TrialDataClass,
    TrialEnvironmentAdmission,
    TrialEnvironmentAdmissionPayload,
    TrialManifest,
    assert_environment_admission_binding,
    freeze_trial_environment_admission,
)


class TrialEnvironmentError(ValueError):
    """Observed environment facts cannot support the requested sandbox admission."""


class TrialEnvironmentFacts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    observed_source_commit_sha: str | None = Field(default=None, pattern=r"^[a-f0-9]{40}$")
    observed_database_target: str | None = None
    observed_output_root: str | None = None
    sandbox_mode: bool
    live_provider_enabled: bool
    outbound_network_enabled: bool
    external_tools_enabled: bool
    reality_execution_enabled: bool
    sensitive_data_present: bool
    real_experts_enabled: bool
    provider_secrets_present: bool
    trial_database_disposable: bool
    database_ownership_marker_present: bool
    output_root_disposable: bool
    output_root_ownership_marker_present: bool
    public_historical_approval_proven: bool = False


def _resource_limits_admitted(manifest: TrialManifest) -> bool:
    return all(
        getattr(manifest.resource_limits, name) <= getattr(TRIAL_HARD_CAPS, name)
        for name in type(TRIAL_HARD_CAPS).model_fields
    )


def evaluate_environment_admission(
    *,
    attempt: TrialAttemptReceipt,
    manifest: TrialManifest,
    canonical_admission: TrialCanonicalAdmission | _AuthenticatedCanonicalAdmission,
    facts: TrialEnvironmentFacts,
    admission_id: str,
    frozen_at: datetime,
) -> TrialEnvironmentAdmission:
    attempt.assert_integrity()
    manifest.assert_integrity()
    canonical = _canonical_record(canonical_admission)
    canonical.assert_integrity()
    authenticated = _canonical_is_authenticated(canonical_admission)
    reasons: list[str] = []

    if not authenticated:
        reasons.append("canonical admission lacks verifier-authenticated package provenance")
    elif not _canonical_matches_provenance(
        canonical_admission,
        attempt_receipt_hash=attempt.attempt_receipt_hash,
        manifest_hash=manifest.manifest_hash,
    ):
        reasons.append("canonical admission provenance differs from Attempt or Manifest")
    if canonical.status is not TrialCanonicalAdmissionStatus.PASS:
        reasons.append("code-owned canonical bundle admission did not PASS")
    if not canonical.pre_freeze_admitted:
        reasons.append("bundle lacks pre-freeze canonical admission")
    if canonical.bundle_receipt_hash == "0" * 64:
        reasons.append("canonical admission lacks a real bundle receipt")
    if attempt.detached_input_address != canonical.detached_input_address:
        reasons.append("Attempt Receipt address differs from canonical admission")
    if manifest.adapter_lane is not TrialAdapterLane.MOCK:
        reasons.append("only MOCK adapter lane is admitted")
    if manifest.data_class is TrialDataClass.PUBLIC_HISTORICAL:
        if not facts.public_historical_approval_proven:
            reasons.append("public-historical approval is not proven")
    elif manifest.data_class is not TrialDataClass.SYNTHETIC:
        reasons.append("sensitive/private data is not admitted")
    if manifest.publication_policy != "RESTRICTED":
        reasons.append("publication policy must remain RESTRICTED")
    if not facts.sandbox_mode:
        reasons.append("sandbox mode is not proven")
    if facts.live_provider_enabled:
        reasons.append("live provider use is forbidden")
    if facts.outbound_network_enabled:
        reasons.append("outbound network must be disabled")
    if facts.external_tools_enabled:
        reasons.append("external tools must be disabled")
    if facts.reality_execution_enabled:
        reasons.append("reality execution must be disabled")
    if facts.sensitive_data_present:
        reasons.append("sensitive data is forbidden")
    if facts.real_experts_enabled:
        reasons.append("real human expert operations are forbidden")
    if facts.provider_secrets_present:
        reasons.append("provider secrets must not be present")
    if not facts.trial_database_disposable:
        reasons.append("trial database is not proven disposable")
    if not facts.database_ownership_marker_present:
        reasons.append("trial database ownership marker is absent")
    if facts.observed_database_target is None:
        reasons.append("observed trial database target is unavailable")
    elif facts.observed_database_target != manifest.database_target:
        reasons.append("observed trial database target differs from Trial Manifest")
    if not facts.output_root_disposable:
        reasons.append("trial output root is not proven disposable")
    if not facts.output_root_ownership_marker_present:
        reasons.append("trial output-root ownership marker is absent")
    if facts.observed_output_root is None:
        reasons.append("observed trial output root is unavailable")
    elif facts.observed_output_root != manifest.output_root:
        reasons.append("observed trial output root differs from Trial Manifest")
    if facts.observed_source_commit_sha is None:
        reasons.append("observed source/build identity is unavailable")
    elif facts.observed_source_commit_sha != manifest.source_commit_sha:
        reasons.append("observed source/build identity differs from Trial Manifest")
    resource_limits_admitted = _resource_limits_admitted(manifest)
    if not resource_limits_admitted:
        reasons.append("requested resource limits exceed code-owned hard caps")

    admission = freeze_trial_environment_admission(
        TrialEnvironmentAdmissionPayload(
            admission_id=admission_id,
            attempt_receipt_hash=attempt.attempt_receipt_hash,
            manifest_hash=manifest.manifest_hash,
            canonical_admission_hash=canonical.canonical_admission_hash,
            canonical_registry_entry_id=canonical.registry_entry_id,
            detached_input_address=canonical.detached_input_address,
            observed_source_commit_sha=facts.observed_source_commit_sha,
            observed_database_target=facts.observed_database_target,
            observed_output_root=facts.observed_output_root,
            sandbox_mode=facts.sandbox_mode,
            mock_only=not facts.live_provider_enabled,
            live_provider_disabled=not facts.live_provider_enabled,
            outbound_network_disabled=not facts.outbound_network_enabled,
            external_tools_disabled=not facts.external_tools_enabled,
            reality_execution_disabled=not facts.reality_execution_enabled,
            sensitive_data_absent=not facts.sensitive_data_present,
            real_experts_disabled=not facts.real_experts_enabled,
            provider_secrets_disabled=not facts.provider_secrets_present,
            trial_database_disposable=facts.trial_database_disposable,
            database_ownership_marker_present=facts.database_ownership_marker_present,
            output_root_disposable=facts.output_root_disposable,
            output_root_ownership_marker_present=(facts.output_root_ownership_marker_present),
            resource_limits_admitted=resource_limits_admitted,
            status=(TrialAdmissionStatus.PASS if not reasons else TrialAdmissionStatus.REJECTED),
            reasons=tuple(reasons),
            frozen_at=frozen_at,
        )
    )
    if admission.status is TrialAdmissionStatus.PASS:
        if not authenticated:
            raise TrialEnvironmentError(
                "Environment PASS cannot be produced without package provenance"
            )
        assert_environment_admission_binding(
            attempt,
            manifest,
            canonical,
            admission,
        )
    return admission
