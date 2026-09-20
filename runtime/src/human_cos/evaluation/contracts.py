"""S8-EVAL1 immutable Evaluator task, disclosure, finding, and result contracts.

These contracts are sidecars over the frozen S7 common-mode result. They grant
no Runtime progression, Final Claim, Seal, tool, or reality-execution authority.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from human_cos.runtime.run import canonical_document_sha256
from human_cos.runtime.state_machine import CaseMode


class EvaluatorContractError(ValueError):
    """S8 Evaluator data violates the authorized narrow contract boundary."""


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("S8-EVAL timestamps require timezone-aware datetimes")
    return value


class _FrozenEvaluatorModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class EvaluationTaskType(str, Enum):
    """Only evaluation families authorized by the narrow S8-EVAL grant."""

    INTEGRATED_RESULT = "INTEGRATED_RESULT"
    HC_REGRESSION = "HC_REGRESSION"
    LOW_RECOGNITION = "LOW_RECOGNITION"


class EvaluationSourceLayer(str, Enum):
    """Frozen source layers visible to the S8 code-owned input packet."""

    S5 = "S5"
    S6 = "S6"
    S7 = "S7"
    RUNTIME = "RUNTIME"


class EvaluationFindingKind(str, Enum):
    SUPPORT = "SUPPORT"
    UNSUPPORTED_CLAIM = "UNSUPPORTED_CLAIM"
    MECHANISM_GAP = "MECHANISM_GAP"
    ROBUSTNESS_GAP = "ROBUSTNESS_GAP"
    REGRESSION = "REGRESSION"
    RECOGNITION = "RECOGNITION"
    UNCERTAINTY = "UNCERTAINTY"
    LIMITATION = "LIMITATION"
    DISSENT = "DISSENT"
    PROTOCOL_INVALID = "PROTOCOL_INVALID"


class EvaluationValidity(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"


_COMMON_EVALUATOR_MODES = frozenset(
    {
        CaseMode.LIVE_FORESIGHT,
        CaseMode.MECHANISM_BENCHMARK,
        CaseMode.SCENARIO_STRESS_TEST,
    }
)


def _assert_unique(values: tuple[str, ...], *, name: str) -> None:
    if len(values) != len(set(values)):
        raise EvaluatorContractError(f"{name} must not contain duplicates")


def _assert_no_authority(
    *,
    process_authority: bool,
    reality_execution_authorized: bool,
    final_claim_authorized: bool,
    seal_authorized: bool,
    object_name: str,
) -> None:
    if (
        process_authority
        or reality_execution_authorized
        or final_claim_authorized
        or seal_authorized
    ):
        raise EvaluatorContractError(
            f"{object_name} grants no process, execution, claim, or seal authority"
        )


class EvaluatorSourceRef(_FrozenEvaluatorModel):
    layer: EvaluationSourceLayer
    object_kind: str = Field(min_length=1)
    ref: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    purpose: str = Field(min_length=1)


class EvaluatorTaskPayload(_FrozenEvaluatorModel):
    task_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    case_mode: CaseMode
    evaluation_type: EvaluationTaskType
    evaluated_run_ids: tuple[str, ...] = Field(min_length=1)
    requested_evaluator_model_id: str = Field(min_length=1)
    requested_evaluator_model_family: str = Field(min_length=1)
    requested_evaluator_provider: str = Field(min_length=1)
    require_context_independence: Literal[True] = True
    require_model_family_independence: bool = False
    require_provider_independence: bool = False
    require_expert_independence: bool = False
    allowed_stage: Literal["ADVERSARIAL_REVIEW"] = "ADVERSARIAL_REVIEW"
    process_authority: Literal[False] = False
    reality_execution_authorized: Literal[False] = False
    final_claim_authorized: Literal[False] = False
    seal_authorized: Literal[False] = False
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class EvaluatorTask(EvaluatorTaskPayload):
    task_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"task_hash"}, exclude_none=True)
        if self.task_hash != canonical_document_sha256(payload):
            raise EvaluatorContractError("EvaluatorTask task_hash does not match payload")
        if self.case_mode not in _COMMON_EVALUATOR_MODES:
            raise EvaluatorContractError("S8-EVAL common-mode task excludes HISTORICAL_BLIND_EVAL")
        _assert_unique(self.evaluated_run_ids, name="EvaluatorTask evaluated_run_ids")
        _assert_no_authority(
            process_authority=self.process_authority,
            reality_execution_authorized=self.reality_execution_authorized,
            final_claim_authorized=self.final_claim_authorized,
            seal_authorized=self.seal_authorized,
            object_name="EvaluatorTask",
        )


def freeze_evaluator_task(payload: EvaluatorTaskPayload) -> EvaluatorTask:
    document = payload.to_document()
    task = EvaluatorTask.model_validate(
        {**document, "task_hash": canonical_document_sha256(document)}
    )
    task.assert_integrity()
    return task


class EvaluatorInputPacketPayload(_FrozenEvaluatorModel):
    packet_id: str = Field(min_length=1)
    task_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    evaluation_type: EvaluationTaskType
    evaluated_run_ids: tuple[str, ...] = Field(min_length=1)
    source_refs: tuple[EvaluatorSourceRef, ...] = Field(min_length=1)
    prior_evaluator_result_hashes: tuple[str, ...] = ()
    independent_required: Literal[True] = True
    allowed_stage: Literal["ADVERSARIAL_REVIEW"] = "ADVERSARIAL_REVIEW"
    process_authority: Literal[False] = False
    reality_execution_authorized: Literal[False] = False
    final_claim_authorized: Literal[False] = False
    seal_authorized: Literal[False] = False
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class EvaluatorInputPacket(EvaluatorInputPacketPayload):
    packet_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @property
    def source_hashes(self) -> frozenset[str]:
        return frozenset(item.sha256 for item in self.source_refs)

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"packet_hash"}, exclude_none=True)
        if self.packet_hash != canonical_document_sha256(payload):
            raise EvaluatorContractError("EvaluatorInputPacket packet_hash does not match payload")
        _assert_unique(self.evaluated_run_ids, name="EvaluatorInputPacket evaluated_run_ids")
        if self.prior_evaluator_result_hashes:
            raise EvaluatorContractError(
                "independent Evaluator packet cannot disclose prior Evaluator results pre-freeze"
            )
        identities = tuple(
            (item.layer.value, item.object_kind, item.ref) for item in self.source_refs
        )
        if len(identities) != len(set(identities)):
            raise EvaluatorContractError("EvaluatorInputPacket source identities must be unique")
        _assert_no_authority(
            process_authority=self.process_authority,
            reality_execution_authorized=self.reality_execution_authorized,
            final_claim_authorized=self.final_claim_authorized,
            seal_authorized=self.seal_authorized,
            object_name="EvaluatorInputPacket",
        )


def freeze_evaluator_input_packet(
    payload: EvaluatorInputPacketPayload,
) -> EvaluatorInputPacket:
    document = payload.to_document()
    packet = EvaluatorInputPacket.model_validate(
        {**document, "packet_hash": canonical_document_sha256(document)}
    )
    packet.assert_integrity()
    return packet


def assert_evaluator_packet_binding(
    task: EvaluatorTask,
    packet: EvaluatorInputPacket,
) -> None:
    task.assert_integrity()
    packet.assert_integrity()
    if packet.task_hash != task.task_hash:
        raise EvaluatorContractError("EvaluatorInputPacket does not bind the exact EvaluatorTask")
    if packet.case_id != task.case_id or packet.case_revision != task.case_revision:
        raise EvaluatorContractError(
            "EvaluatorInputPacket case identity differs from EvaluatorTask"
        )
    if packet.evaluation_type is not task.evaluation_type:
        raise EvaluatorContractError(
            "EvaluatorInputPacket evaluation type differs from EvaluatorTask"
        )
    if packet.evaluated_run_ids != task.evaluated_run_ids:
        raise EvaluatorContractError(
            "EvaluatorInputPacket evaluated runs differ from EvaluatorTask"
        )
    if packet.protocol_version != task.protocol_version:
        raise EvaluatorContractError(
            "EvaluatorInputPacket protocol version differs from EvaluatorTask"
        )
    if packet.frozen_at < task.frozen_at:
        raise EvaluatorContractError("EvaluatorInputPacket cannot predate its EvaluatorTask")


class EvaluatorFindingPayload(_FrozenEvaluatorModel):
    finding_id: str = Field(min_length=1)
    task_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    packet_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    evaluator_run_id: str = Field(min_length=1)
    evaluator_model_id: str = Field(min_length=1)
    evaluator_model_family: str = Field(min_length=1)
    evaluator_provider: str = Field(min_length=1)
    finding_kind: EvaluationFindingKind
    statement: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    source_hash_refs: tuple[str, ...] = Field(min_length=1)
    uncertainty: str = Field(min_length=1)
    limitations: tuple[str, ...] = ()
    dissent_refs: tuple[str, ...] = ()
    unresolved_condition_refs: tuple[str, ...] = ()
    process_authority: Literal[False] = False
    reality_execution_authorized: Literal[False] = False
    final_claim_authorized: Literal[False] = False
    seal_authorized: Literal[False] = False
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class EvaluatorFinding(EvaluatorFindingPayload):
    finding_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"finding_hash"}, exclude_none=True)
        if self.finding_hash != canonical_document_sha256(payload):
            raise EvaluatorContractError("EvaluatorFinding finding_hash does not match payload")
        _assert_unique(self.source_hash_refs, name="EvaluatorFinding source_hash_refs")
        _assert_unique(self.dissent_refs, name="EvaluatorFinding dissent_refs")
        _assert_unique(
            self.unresolved_condition_refs,
            name="EvaluatorFinding unresolved_condition_refs",
        )
        _assert_no_authority(
            process_authority=self.process_authority,
            reality_execution_authorized=self.reality_execution_authorized,
            final_claim_authorized=self.final_claim_authorized,
            seal_authorized=self.seal_authorized,
            object_name="EvaluatorFinding",
        )


def freeze_evaluator_finding(payload: EvaluatorFindingPayload) -> EvaluatorFinding:
    document = payload.to_document()
    finding = EvaluatorFinding.model_validate(
        {**document, "finding_hash": canonical_document_sha256(document)}
    )
    finding.assert_integrity()
    return finding


def assert_evaluator_finding_binding(
    task: EvaluatorTask,
    packet: EvaluatorInputPacket,
    finding: EvaluatorFinding,
) -> None:
    assert_evaluator_packet_binding(task, packet)
    finding.assert_integrity()
    if finding.task_hash != task.task_hash or finding.packet_hash != packet.packet_hash:
        raise EvaluatorContractError("EvaluatorFinding does not bind exact task and packet")
    if finding.evaluator_run_id in task.evaluated_run_ids:
        raise EvaluatorContractError(
            "evaluated Solver/Controller/Challenger Run cannot self-evaluate"
        )
    missing = sorted(set(finding.source_hash_refs).difference(packet.source_hashes))
    if missing:
        raise EvaluatorContractError(
            "EvaluatorFinding references source hashes outside code-owned input packet: "
            + ", ".join(missing)
        )
    if finding.protocol_version != task.protocol_version:
        raise EvaluatorContractError("EvaluatorFinding protocol version differs from EvaluatorTask")
    if finding.frozen_at < packet.frozen_at:
        raise EvaluatorContractError("EvaluatorFinding cannot predate its input packet")


class EvaluatorResultPayload(_FrozenEvaluatorModel):
    result_id: str = Field(min_length=1)
    task_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    packet_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    evaluator_run_id: str = Field(min_length=1)
    evaluator_model_id: str = Field(min_length=1)
    evaluator_model_family: str = Field(min_length=1)
    evaluator_provider: str = Field(min_length=1)
    validity: EvaluationValidity
    invalid_reasons: tuple[str, ...] = ()
    finding_hashes: tuple[str, ...] = Field(min_length=1)
    blocking_finding_hashes: tuple[str, ...] = ()
    advisory_finding_hashes: tuple[str, ...] = ()
    uncertainty: str = Field(min_length=1)
    limitations: tuple[str, ...] = ()
    dissent_refs: tuple[str, ...] = ()
    unresolved_condition_refs: tuple[str, ...] = ()
    process_authority: Literal[False] = False
    reality_execution_authorized: Literal[False] = False
    final_claim_authorized: Literal[False] = False
    seal_authorized: Literal[False] = False
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class EvaluatorResult(EvaluatorResultPayload):
    result_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @property
    def blocks_downstream(self) -> bool:
        return self.validity is EvaluationValidity.INVALID or bool(self.blocking_finding_hashes)

    def assert_integrity(self) -> None:
        payload = self.model_dump(mode="json", exclude={"result_hash"}, exclude_none=True)
        if self.result_hash != canonical_document_sha256(payload):
            raise EvaluatorContractError("EvaluatorResult result_hash does not match payload")
        _assert_unique(self.finding_hashes, name="EvaluatorResult finding_hashes")
        _assert_unique(
            self.blocking_finding_hashes,
            name="EvaluatorResult blocking_finding_hashes",
        )
        _assert_unique(
            self.advisory_finding_hashes,
            name="EvaluatorResult advisory_finding_hashes",
        )
        _assert_unique(self.invalid_reasons, name="EvaluatorResult invalid_reasons")
        _assert_unique(self.dissent_refs, name="EvaluatorResult dissent_refs")
        _assert_unique(
            self.unresolved_condition_refs,
            name="EvaluatorResult unresolved_condition_refs",
        )
        expected_validity = (
            EvaluationValidity.INVALID if self.invalid_reasons else EvaluationValidity.VALID
        )
        if self.validity is not expected_validity:
            raise EvaluatorContractError(
                "EvaluatorResult validity must be recomputable from invalid_reasons"
            )
        blocking = set(self.blocking_finding_hashes)
        advisory = set(self.advisory_finding_hashes)
        if blocking.intersection(advisory):
            raise EvaluatorContractError("blocking and advisory finding sets must be disjoint")
        if blocking.union(advisory) != set(self.finding_hashes):
            raise EvaluatorContractError(
                "blocking/advisory finding partition must cover exactly all findings"
            )
        _assert_no_authority(
            process_authority=self.process_authority,
            reality_execution_authorized=self.reality_execution_authorized,
            final_claim_authorized=self.final_claim_authorized,
            seal_authorized=self.seal_authorized,
            object_name="EvaluatorResult",
        )


def freeze_evaluator_result(payload: EvaluatorResultPayload) -> EvaluatorResult:
    document = payload.to_document()
    result = EvaluatorResult.model_validate(
        {**document, "result_hash": canonical_document_sha256(document)}
    )
    result.assert_integrity()
    return result


def assert_evaluator_result_binding(
    task: EvaluatorTask,
    packet: EvaluatorInputPacket,
    findings: tuple[EvaluatorFinding, ...],
    result: EvaluatorResult,
) -> None:
    assert_evaluator_packet_binding(task, packet)
    result.assert_integrity()
    if not findings:
        raise EvaluatorContractError("EvaluatorResult requires at least one frozen finding")
    for finding in findings:
        assert_evaluator_finding_binding(task, packet, finding)
    finding_ids = tuple(item.finding_id for item in findings)
    _assert_unique(finding_ids, name="EvaluatorResult finding_ids")
    expected_hashes = tuple(item.finding_hash for item in findings)
    if result.finding_hashes != expected_hashes:
        raise EvaluatorContractError("EvaluatorResult does not bind the exact ordered finding set")
    if result.task_hash != task.task_hash or result.packet_hash != packet.packet_hash:
        raise EvaluatorContractError("EvaluatorResult does not bind exact task and packet")
    if result.evaluator_run_id in task.evaluated_run_ids:
        raise EvaluatorContractError(
            "evaluated Solver/Controller/Challenger Run cannot self-evaluate"
        )
    identities = {
        (
            item.evaluator_run_id,
            item.evaluator_model_id,
            item.evaluator_model_family,
            item.evaluator_provider,
        )
        for item in findings
    }
    result_identity = (
        result.evaluator_run_id,
        result.evaluator_model_id,
        result.evaluator_model_family,
        result.evaluator_provider,
    )
    if identities != {result_identity}:
        raise EvaluatorContractError(
            "EvaluatorResult and all findings must share one exact Evaluator Run identity"
        )
    if result.protocol_version != task.protocol_version:
        raise EvaluatorContractError("EvaluatorResult protocol version differs from EvaluatorTask")
    latest_finding_time = max(item.frozen_at for item in findings)
    if result.frozen_at < latest_finding_time:
        raise EvaluatorContractError("EvaluatorResult cannot predate its frozen findings")
