"""Code-owned approval lookup for the first operator-synthetic-v1 slice.

No files, network, database, providers, environment variables or canonical fallback.
The registry is empty until the owner approves exact A/B bundle content addresses.
A metadata match is NOT byte verification, qualification or execution admission.
"""

from __future__ import annotations

from .operator_contracts import (
    OperatorAdmissionError,
    OperatorApprovalDecision,
    OperatorApprovalStatus,
    OperatorApprovedInput,
    OperatorInputIdentity,
)

# Amend only through exact-input owner approval and the normal reviewed change gates.
# Never populate from CLI arguments, submitted payloads, environment or local config.
_APPROVED_INPUTS: tuple[OperatorApprovedInput, ...] = ()


def _assert_catalogue() -> None:
    if type(_APPROVED_INPUTS) is not tuple or len(_APPROVED_INPUTS) > 2:
        raise OperatorAdmissionError("invalid operator approval catalogue")
    slots: set[str] = set()
    addresses: set[str] = set()
    cases: set[tuple[str, int]] = set()
    for entry in _APPROVED_INPUTS:
        if type(entry) is not OperatorApprovedInput:
            raise OperatorAdmissionError("invalid operator approval catalogue entry")
        entry.assert_integrity()
        identity = entry.identity
        case = (identity.case_id, identity.case_revision)
        if entry.slot in slots or identity.detached_input_address in addresses or case in cases:
            raise OperatorAdmissionError("ambiguous operator approval catalogue")
        slots.add(entry.slot)
        addresses.add(identity.detached_input_address)
        cases.add(case)


def evaluate_operator_approval(identity: OperatorInputIdentity) -> OperatorApprovalDecision:
    """Match all identity fields against trusted entries, never a caller's registry."""

    if type(identity) is not OperatorInputIdentity:
        raise OperatorAdmissionError("invalid operator input identity")
    identity.assert_integrity()
    _assert_catalogue()
    for entry in _APPROVED_INPUTS:
        if entry.identity == identity:
            return OperatorApprovalDecision(
                identity=identity,
                status=OperatorApprovalStatus.MATCHED_REQUIRES_VERIFICATION,
                approval_slot=entry.slot,
                owner_approval_reference=entry.owner_approval_reference,
            )
    return OperatorApprovalDecision(identity=identity, status=OperatorApprovalStatus.NOT_APPROVED)


def assert_current_operator_decision(decision: OperatorApprovalDecision) -> None:
    """Recompute against current trusted entries; serialized assertions are not proof."""

    if type(decision) is not OperatorApprovalDecision:
        raise OperatorAdmissionError("invalid operator approval decision")
    decision.assert_integrity()
    if decision != evaluate_operator_approval(decision.identity):
        raise OperatorAdmissionError("operator approval decision differs from current catalogue")
