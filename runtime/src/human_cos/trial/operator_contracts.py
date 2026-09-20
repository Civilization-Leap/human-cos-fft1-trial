"""Non-authoritative metadata contracts for RFC 0001 operator approval lookup.

These records neither verify bundle bytes nor grant execution or Environment PASS.
They are deliberately separate from the frozen canonical admission contracts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

_INPUT_VERSION = "operator-synthetic-v1"
_BASELINE_VERSION = "V0.2"
_CASE_MODE = "MECHANISM_BENCHMARK"
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_HASH = re.compile(r"[0-9a-f]{64}")
_OWNER_REFERENCE = re.compile(
    r"https://github\.com/Civilization-Leap/human-cos-runtime/"
    r"(?:issues|pull)/[1-9][0-9]*#issuecomment-[1-9][0-9]*"
)


class OperatorAdmissionError(ValueError):
    """Invalid metadata or trusted catalogue; messages never echo input content."""


def _token(value: str) -> None:
    if type(value) is not str or _TOKEN.fullmatch(value) is None:
        raise OperatorAdmissionError("invalid operator identity token")


def _hash(value: str) -> None:
    if type(value) is not str or _HASH.fullmatch(value) is None:
        raise OperatorAdmissionError("invalid operator content hash")


@dataclass(frozen=True)
class OperatorInputIdentity:
    """Claimed metadata only; the future loader must derive it from verified bytes."""

    detached_input_address: str
    case_id: str
    case_revision: int
    profile_hashes: tuple[tuple[str, str], ...]
    input_version: str = _INPUT_VERSION
    baseline_version: str = _BASELINE_VERSION
    case_mode: str = _CASE_MODE

    def __post_init__(self) -> None:
        self.assert_integrity()

    def assert_integrity(self) -> None:
        _hash(self.detached_input_address)
        _token(self.case_id)
        if type(self.case_revision) is not int or self.case_revision < 1:
            raise OperatorAdmissionError("invalid operator case revision")
        for observed, required in (
            (self.input_version, _INPUT_VERSION),
            (self.baseline_version, _BASELINE_VERSION),
            (self.case_mode, _CASE_MODE),
        ):
            if type(observed) is not str or observed != required:
                raise OperatorAdmissionError("unsupported operator version or mode")
        if type(self.profile_hashes) is not tuple or not 1 <= len(self.profile_hashes) <= 128:
            raise OperatorAdmissionError("invalid operator profile inventory")
        identifiers: list[str] = []
        for pair in self.profile_hashes:
            if type(pair) is not tuple or len(pair) != 2:
                raise OperatorAdmissionError("invalid operator profile binding")
            identifier, digest = pair
            _token(identifier)
            _hash(digest)
            identifiers.append(identifier)
        if identifiers != sorted(set(identifiers)):
            raise OperatorAdmissionError("operator profiles must be unique and sorted")


@dataclass(frozen=True)
class OperatorApprovedInput:
    """Code-owned approval-table entry, not an operator-supplied approval assertion."""

    slot: Literal["A", "B"]
    identity: OperatorInputIdentity
    owner_approval_reference: str

    def __post_init__(self) -> None:
        self.assert_integrity()

    def assert_integrity(self) -> None:
        if type(self.slot) is not str or self.slot not in ("A", "B"):
            raise OperatorAdmissionError("unsupported operator approval slot")
        if type(self.identity) is not OperatorInputIdentity:
            raise OperatorAdmissionError("invalid operator approval identity")
        self.identity.assert_integrity()
        reference = self.owner_approval_reference
        if type(reference) is not str or _OWNER_REFERENCE.fullmatch(reference) is None:
            raise OperatorAdmissionError("invalid owner approval reference")


class OperatorApprovalStatus(str, Enum):
    NOT_APPROVED = "NOT_APPROVED"
    MATCHED_REQUIRES_VERIFICATION = "MATCHED_REQUIRES_VERIFICATION"


@dataclass(frozen=True)
class OperatorApprovalDecision:
    """Lookup result only: never a capability token, bundle receipt or runtime gate."""

    identity: OperatorInputIdentity
    status: OperatorApprovalStatus
    approval_slot: Literal["A", "B"] | None = None
    owner_approval_reference: str | None = None
    execution_authorized: Literal[False] = field(default=False, init=False)

    def __post_init__(self) -> None:
        self.assert_integrity()

    def assert_integrity(self) -> None:
        if type(self.identity) is not OperatorInputIdentity:
            raise OperatorAdmissionError("invalid operator decision identity")
        self.identity.assert_integrity()
        if self.execution_authorized is not False:
            raise OperatorAdmissionError("operator lookup cannot authorize execution")
        if type(self.status) is not OperatorApprovalStatus:
            raise OperatorAdmissionError("invalid operator decision status")
        if self.status is OperatorApprovalStatus.NOT_APPROVED:
            if self.approval_slot is not None or self.owner_approval_reference is not None:
                raise OperatorAdmissionError("unapproved decision cannot claim an approval")
        else:
            if self.approval_slot is None or self.owner_approval_reference is None:
                raise OperatorAdmissionError("matched decision requires approval metadata")
            OperatorApprovedInput(
                self.approval_slot, self.identity, self.owner_approval_reference
            ).assert_integrity()
