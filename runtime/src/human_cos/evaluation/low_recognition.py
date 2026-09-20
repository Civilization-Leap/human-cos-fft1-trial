"""S8-EVAL4 deterministic low-recognition visibility and contamination sidecar.

Low recognition is established by explicit code-owned visibility and
contamination facts, not by prompt instructions.  The gate grants no Runtime,
Final Claim, Seal, or reality-execution authority and does not activate Final
Synthesis.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from human_cos.runtime.run import canonical_document_sha256

from .contracts import (
    EvaluationTaskType,
    EvaluatorInputPacket,
    EvaluatorTask,
    assert_evaluator_packet_binding,
)


class LowRecognitionError(ValueError):
    """S8 low-recognition lineage, timing, or visibility discipline failed."""


class LowRecognitionGateStatus(str, Enum):
    PASS = "PASS"
    BLOCK = "BLOCK"
    INVALID = "INVALID"


class LowRecognitionInvalidFact(str, Enum):
    ENTITY_SYSTEM_IDENTITY_EXPOSED = "ENTITY_SYSTEM_IDENTITY_EXPOSED"
    PROVENANCE_LABEL_EXPOSED = "PROVENANCE_LABEL_EXPOSED"
    SOLVER_CONTROLLER_IDENTITY_EXPOSED = "SOLVER_CONTROLLER_IDENTITY_EXPOSED"
    COMPARISON_LABEL_EXPOSED = "COMPARISON_LABEL_EXPOSED"
    MATERIAL_REVEALED_BEFORE_FREEZE = "MATERIAL_REVEALED_BEFORE_FREEZE"
    SAME_SESSION_OR_INHERITED_KNOWLEDGE = "SAME_SESSION_OR_INHERITED_KNOWLEDGE"
    CROSS_EVALUATOR_CONTAMINATION = "CROSS_EVALUATOR_CONTAMINATION"
    CROSS_COMPARISON_CONTAMINATION = "CROSS_COMPARISON_CONTAMINATION"
    UNRESOLVED_PROTOCOL_INVALID = "UNRESOLVED_PROTOCOL_INVALID"


class _FrozenLowRecognitionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("S8 low-recognition timestamps require timezone-aware datetimes")
    return value


def _payload_without_hash(model: BaseModel, hash_field: str) -> dict[str, Any]:
    return model.model_dump(mode="json", exclude={hash_field}, exclude_none=True)


def _assert_unique(values: tuple[str, ...], *, name: str) -> None:
    if len(values) != len(set(values)):
        raise LowRecognitionError(f"{name} must not contain duplicates")


def _assert_low_recognition_task(
    task: EvaluatorTask,
    packet: EvaluatorInputPacket,
) -> None:
    assert_evaluator_packet_binding(task, packet)
    if task.evaluation_type is not EvaluationTaskType.LOW_RECOGNITION:
        raise LowRecognitionError("S8-EVAL4 requires a LOW_RECOGNITION EvaluatorTask")


class LowRecognitionVisibilityPolicyPayload(_FrozenLowRecognitionModel):
    policy_id: str = Field(min_length=1)
    task_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    packet_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    hide_entity_system_identity: bool
    hide_provenance_labels: bool
    hide_solver_controller_identity: bool
    hide_comparison_labels: bool
    material_hidden_until_freeze: tuple[str, ...] = Field(min_length=1)
    post_freeze_reveal_plan: tuple[str, ...] = Field(min_length=1)
    same_session_or_inherited_knowledge_allowed: Literal[False] = False
    cross_evaluator_contamination_allowed: Literal[False] = False
    cross_comparison_contamination_allowed: Literal[False] = False
    prompt_only_blindness_sufficient: Literal[False] = False
    process_authority: Literal[False] = False
    reality_execution_authorized: Literal[False] = False
    final_claim_authorized: Literal[False] = False
    seal_authorized: Literal[False] = False
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class LowRecognitionVisibilityPolicy(LowRecognitionVisibilityPolicyPayload):
    policy_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        _assert_unique(
            self.material_hidden_until_freeze,
            name="low-recognition hidden material",
        )
        _assert_unique(
            self.post_freeze_reveal_plan,
            name="low-recognition reveal plan",
        )
        if not all(
            (
                self.hide_entity_system_identity,
                self.hide_provenance_labels,
                self.hide_solver_controller_identity,
                self.hide_comparison_labels,
            )
        ):
            raise LowRecognitionError(
                "LOW_RECOGNITION requires identity, provenance, solver, "
                "and comparison labels hidden"
            )
        payload = _payload_without_hash(self, "policy_hash")
        if self.policy_hash != canonical_document_sha256(payload):
            raise LowRecognitionError("low-recognition visibility policy hash mismatch")


def freeze_low_recognition_visibility_policy(
    payload: LowRecognitionVisibilityPolicyPayload,
    *,
    task: EvaluatorTask,
    packet: EvaluatorInputPacket,
) -> LowRecognitionVisibilityPolicy:
    _assert_low_recognition_task(task, packet)
    if payload.task_hash != task.task_hash or payload.packet_hash != packet.packet_hash:
        raise LowRecognitionError("low-recognition policy must bind exact task and packet")
    if payload.case_id != task.case_id or payload.case_revision != task.case_revision:
        raise LowRecognitionError("low-recognition policy Case binding differs from task")
    if payload.protocol_version != task.protocol_version:
        raise LowRecognitionError("low-recognition policy protocol differs from task")
    if payload.frozen_at < packet.frozen_at:
        raise LowRecognitionError("low-recognition policy cannot predate its source packet")
    document = payload.to_document()
    policy = LowRecognitionVisibilityPolicy.model_validate(
        {**document, "policy_hash": canonical_document_sha256(document)}
    )
    policy.assert_integrity()
    return policy


class LowRecognitionExposureSnapshotPayload(_FrozenLowRecognitionModel):
    snapshot_id: str = Field(min_length=1)
    task_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    packet_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    policy_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    exposure_evidence_hashes: tuple[str, ...] = Field(min_length=1)
    entity_system_identity_exposed: bool
    provenance_label_exposed: bool
    solver_controller_identity_exposed: bool
    comparison_label_exposed: bool
    material_revealed_before_freeze: tuple[str, ...] = ()
    same_session_or_inherited_knowledge: bool
    cross_evaluator_contamination: bool
    cross_comparison_contamination: bool
    unresolved_protocol_invalid: bool
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class LowRecognitionExposureSnapshot(LowRecognitionExposureSnapshotPayload):
    snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        _assert_unique(
            self.exposure_evidence_hashes,
            name="low-recognition exposure evidence hashes",
        )
        _assert_unique(
            self.material_revealed_before_freeze,
            name="low-recognition prematurely revealed material",
        )
        payload = _payload_without_hash(self, "snapshot_hash")
        if self.snapshot_hash != canonical_document_sha256(payload):
            raise LowRecognitionError("low-recognition exposure snapshot hash mismatch")


def freeze_low_recognition_exposure_snapshot(
    payload: LowRecognitionExposureSnapshotPayload,
    *,
    task: EvaluatorTask,
    packet: EvaluatorInputPacket,
    policy: LowRecognitionVisibilityPolicy,
) -> LowRecognitionExposureSnapshot:
    _assert_low_recognition_task(task, packet)
    policy.assert_integrity()
    if payload.task_hash != task.task_hash or payload.packet_hash != packet.packet_hash:
        raise LowRecognitionError("low-recognition exposure must bind exact task and packet")
    if payload.policy_hash != policy.policy_hash:
        raise LowRecognitionError("low-recognition exposure must bind exact visibility policy")
    if payload.protocol_version != task.protocol_version:
        raise LowRecognitionError("low-recognition exposure protocol differs from task")
    if payload.frozen_at < policy.frozen_at:
        raise LowRecognitionError("low-recognition exposure cannot predate visibility policy")
    outside_packet = sorted(set(payload.exposure_evidence_hashes).difference(packet.source_hashes))
    if outside_packet:
        raise LowRecognitionError(
            "low-recognition exposure evidence is outside code-owned packet: "
            + ", ".join(outside_packet)
        )
    document = payload.to_document()
    snapshot = LowRecognitionExposureSnapshot.model_validate(
        {**document, "snapshot_hash": canonical_document_sha256(document)}
    )
    snapshot.assert_integrity()
    return snapshot


def _invalid_facts(
    snapshot: LowRecognitionExposureSnapshot,
) -> tuple[LowRecognitionInvalidFact, ...]:
    invalid: list[LowRecognitionInvalidFact] = []
    if snapshot.entity_system_identity_exposed:
        invalid.append(LowRecognitionInvalidFact.ENTITY_SYSTEM_IDENTITY_EXPOSED)
    if snapshot.provenance_label_exposed:
        invalid.append(LowRecognitionInvalidFact.PROVENANCE_LABEL_EXPOSED)
    if snapshot.solver_controller_identity_exposed:
        invalid.append(LowRecognitionInvalidFact.SOLVER_CONTROLLER_IDENTITY_EXPOSED)
    if snapshot.comparison_label_exposed:
        invalid.append(LowRecognitionInvalidFact.COMPARISON_LABEL_EXPOSED)
    if snapshot.material_revealed_before_freeze:
        invalid.append(LowRecognitionInvalidFact.MATERIAL_REVEALED_BEFORE_FREEZE)
    if snapshot.same_session_or_inherited_knowledge:
        invalid.append(LowRecognitionInvalidFact.SAME_SESSION_OR_INHERITED_KNOWLEDGE)
    if snapshot.cross_evaluator_contamination:
        invalid.append(LowRecognitionInvalidFact.CROSS_EVALUATOR_CONTAMINATION)
    if snapshot.cross_comparison_contamination:
        invalid.append(LowRecognitionInvalidFact.CROSS_COMPARISON_CONTAMINATION)
    if snapshot.unresolved_protocol_invalid:
        invalid.append(LowRecognitionInvalidFact.UNRESOLVED_PROTOCOL_INVALID)
    return tuple(invalid)


class LowRecognitionGatePayload(_FrozenLowRecognitionModel):
    gate_id: str = Field(min_length=1)
    task_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    packet_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    policy_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    exposure_snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    invalid_facts: tuple[LowRecognitionInvalidFact, ...]
    status: LowRecognitionGateStatus
    process_authority: Literal[False] = False
    reality_execution_authorized: Literal[False] = False
    final_claim_authorized: Literal[False] = False
    seal_authorized: Literal[False] = False
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime

    _frozen_at_must_be_aware = field_validator("frozen_at")(_aware)


class LowRecognitionGate(LowRecognitionGatePayload):
    gate_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @property
    def low_recognition_passed(self) -> bool:
        return self.status is LowRecognitionGateStatus.PASS

    def assert_integrity(
        self,
        *,
        snapshot: LowRecognitionExposureSnapshot,
    ) -> None:
        expected_invalid = _invalid_facts(snapshot)
        expected_status = (
            LowRecognitionGateStatus.PASS
            if not expected_invalid
            else LowRecognitionGateStatus.BLOCK
        )
        if self.invalid_facts != expected_invalid or self.status is not expected_status:
            raise LowRecognitionError(
                "low-recognition gate is not recomputable from exposure facts"
            )
        payload = _payload_without_hash(self, "gate_hash")
        if self.gate_hash != canonical_document_sha256(payload):
            raise LowRecognitionError("low-recognition gate hash mismatch")


def evaluate_low_recognition_gate(
    *,
    task: EvaluatorTask,
    packet: EvaluatorInputPacket,
    policy: LowRecognitionVisibilityPolicy,
    snapshot: LowRecognitionExposureSnapshot,
    gate_id: str,
    frozen_at: datetime,
) -> LowRecognitionGate:
    _assert_low_recognition_task(task, packet)
    policy.assert_integrity()
    snapshot.assert_integrity()
    _aware(frozen_at)
    if snapshot.task_hash != task.task_hash or snapshot.packet_hash != packet.packet_hash:
        raise LowRecognitionError("low-recognition snapshot lineage differs from task/packet")
    if snapshot.policy_hash != policy.policy_hash:
        raise LowRecognitionError("low-recognition snapshot policy lineage differs")
    if frozen_at < snapshot.frozen_at:
        raise LowRecognitionError("low-recognition gate cannot predate exposure snapshot")
    invalid = _invalid_facts(snapshot)
    status = LowRecognitionGateStatus.PASS if not invalid else LowRecognitionGateStatus.BLOCK
    payload = LowRecognitionGatePayload(
        gate_id=gate_id,
        task_hash=task.task_hash,
        packet_hash=packet.packet_hash,
        policy_hash=policy.policy_hash,
        exposure_snapshot_hash=snapshot.snapshot_hash,
        invalid_facts=invalid,
        status=status,
        protocol_version=task.protocol_version,
        frozen_at=frozen_at,
    )
    document = payload.to_document()
    gate = LowRecognitionGate.model_validate(
        {**document, "gate_hash": canonical_document_sha256(document)}
    )
    gate.assert_integrity(snapshot=snapshot)
    return gate


class LowRecognitionRevealPayload(_FrozenLowRecognitionModel):
    reveal_id: str = Field(min_length=1)
    task_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    packet_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    policy_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    gate_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    revealed_material: tuple[str, ...] = Field(min_length=1)
    protocol_version: str = Field(min_length=1)
    revealed_at: datetime

    _revealed_at_must_be_aware = field_validator("revealed_at")(_aware)


class LowRecognitionReveal(LowRecognitionRevealPayload):
    reveal_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def assert_integrity(self) -> None:
        _assert_unique(self.revealed_material, name="low-recognition revealed material")
        payload = _payload_without_hash(self, "reveal_hash")
        if self.reveal_hash != canonical_document_sha256(payload):
            raise LowRecognitionError("low-recognition reveal hash mismatch")


def freeze_low_recognition_reveal(
    payload: LowRecognitionRevealPayload,
    *,
    task: EvaluatorTask,
    packet: EvaluatorInputPacket,
    policy: LowRecognitionVisibilityPolicy,
    gate: LowRecognitionGate,
) -> LowRecognitionReveal:
    _assert_low_recognition_task(task, packet)
    policy.assert_integrity()
    if payload.task_hash != task.task_hash or payload.packet_hash != packet.packet_hash:
        raise LowRecognitionError("low-recognition reveal must bind exact task and packet")
    if payload.policy_hash != policy.policy_hash or payload.gate_hash != gate.gate_hash:
        raise LowRecognitionError("low-recognition reveal must bind exact policy and frozen gate")
    if payload.revealed_at <= gate.frozen_at:
        raise LowRecognitionError("low-recognition reveal is allowed only after gate freeze")
    allowed = set(policy.post_freeze_reveal_plan)
    if not set(payload.revealed_material).issubset(allowed):
        raise LowRecognitionError("low-recognition reveal exceeds frozen post-freeze reveal plan")
    document = payload.to_document()
    reveal = LowRecognitionReveal.model_validate(
        {**document, "reveal_hash": canonical_document_sha256(document)}
    )
    reveal.assert_integrity()
    return reveal
