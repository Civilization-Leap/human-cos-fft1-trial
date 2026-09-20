"""PostgreSQL repositories for immutable Human-COS S1 and S3-N data boundaries."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from psycopg import Connection, errors
from psycopg.types.json import Jsonb

from human_cos.core.context import AdmittedEvidence, ContextAdmissionRecord
from human_cos.core.models import Case, Evidence, parse_case, parse_evidence
from human_cos.core.visibility import temporal_allows, visibility_basis
from human_cos.runtime.run import (
    AuditEvent,
    RawOutputRecord,
    ReplayLineage,
    RunIntegrityError,
    RunManifest,
    RunTransitionError,
    canonical_document_sha256,
    make_raw_output_record,
    parse_audit_event,
    parse_run_manifest,
    validate_run_snapshot_transition,
)


class RepositoryError(RuntimeError):
    """Base storage error."""


class DuplicateRevisionError(RepositoryError):
    """A revision already exists."""


class MissingRecordError(RepositoryError):
    """Requested record does not exist."""


class InvalidRevisionError(RepositoryError):
    """A requested revision does not continue the immutable lineage."""


class PostgresRepository:
    def __init__(self, connection: Connection[Any]) -> None:
        self.connection = connection

    def create_case(self, document: dict[str, Any]) -> Case:
        case = parse_case(document)
        if case.revision != 1:
            raise InvalidRevisionError("initial Case revision must be 1")
        try:
            self.connection.execute(
                """
                INSERT INTO human_cos_case_revision (case_id, revision, payload)
                VALUES (%s, %s, %s)
                """,
                (case.case_id, case.revision, Jsonb(case.to_document())),
            )
            self.connection.commit()
        except errors.UniqueViolation as exc:
            self.connection.rollback()
            raise DuplicateRevisionError(
                f"case revision exists: {case.case_id}@{case.revision}"
            ) from exc
        return case

    def revise_case(self, document: dict[str, Any]) -> Case:
        case = parse_case(document)
        with self.connection.transaction():
            self.connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (case.case_id,))
            row = self.connection.execute(
                """
                SELECT revision
                FROM human_cos_case_revision
                WHERE case_id = %s
                ORDER BY revision DESC
                LIMIT 1
                """,
                (case.case_id,),
            ).fetchone()
            if row is None:
                raise MissingRecordError(f"case not found: {case.case_id}")
            expected = int(row[0]) + 1
            if case.revision != expected:
                raise InvalidRevisionError(
                    f"Case revision must continue lineage: expected {expected}, got {case.revision}"
                )
            self.connection.execute(
                """
                INSERT INTO human_cos_case_revision (case_id, revision, payload)
                VALUES (%s, %s, %s)
                """,
                (case.case_id, case.revision, Jsonb(case.to_document())),
            )
        return case

    def get_case(self, case_id: str, revision: int | None = None) -> Case:
        if revision is None:
            row = self.connection.execute(
                """
                SELECT payload
                FROM human_cos_case_revision
                WHERE case_id = %s
                ORDER BY revision DESC
                LIMIT 1
                """,
                (case_id,),
            ).fetchone()
        else:
            row = self.connection.execute(
                """
                SELECT payload
                FROM human_cos_case_revision
                WHERE case_id = %s AND revision = %s
                """,
                (case_id, revision),
            ).fetchone()
        if row is None:
            raise MissingRecordError(f"case not found: {case_id}@{revision or 'latest'}")
        return parse_case(dict(row[0]))

    def create_evidence(self, document: dict[str, Any]) -> Evidence:
        evidence = parse_evidence(document)
        self.get_case(evidence.case_id)
        self._insert_evidence(evidence, revision=1, parent_revision=None)
        return evidence

    def revise_evidence(self, document: dict[str, Any]) -> tuple[Evidence, int]:
        """Append a new immutable revision; never UPDATE the prior row."""
        evidence = parse_evidence(document)
        with self.connection.transaction():
            self.connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))", (evidence.evidence_id,)
            )
            row = self.connection.execute(
                """
                SELECT revision, case_id
                FROM human_cos_evidence_revision
                WHERE evidence_id = %s
                ORDER BY revision DESC
                LIMIT 1
                """,
                (evidence.evidence_id,),
            ).fetchone()
            if row is None:
                raise MissingRecordError(f"evidence not found: {evidence.evidence_id}")
            parent_revision, case_id = int(row[0]), str(row[1])
            if evidence.case_id != case_id:
                raise InvalidRevisionError("evidence revision cannot change case_id")
            revision = parent_revision + 1
            self.connection.execute(
                """
                INSERT INTO human_cos_evidence_revision
                    (evidence_id, revision, case_id, parent_revision, payload, snapshot_hash)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    evidence.evidence_id,
                    revision,
                    evidence.case_id,
                    parent_revision,
                    Jsonb(evidence.to_document()),
                    evidence.snapshot_hash,
                ),
            )
        return evidence, revision

    def _insert_evidence(
        self,
        evidence: Evidence,
        *,
        revision: int,
        parent_revision: int | None,
    ) -> None:
        try:
            self.connection.execute(
                """
                INSERT INTO human_cos_evidence_revision
                    (evidence_id, revision, case_id, parent_revision, payload, snapshot_hash)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    evidence.evidence_id,
                    revision,
                    evidence.case_id,
                    parent_revision,
                    Jsonb(evidence.to_document()),
                    evidence.snapshot_hash,
                ),
            )
            self.connection.commit()
        except errors.UniqueViolation as exc:
            self.connection.rollback()
            raise DuplicateRevisionError(
                f"evidence revision exists: {evidence.evidence_id}@{revision}"
            ) from exc

    def get_evidence(self, evidence_id: str, revision: int | None = None) -> tuple[Evidence, int]:
        if revision is None:
            row = self.connection.execute(
                """
                SELECT payload, revision
                FROM human_cos_evidence_revision
                WHERE evidence_id = %s
                ORDER BY revision DESC
                LIMIT 1
                """,
                (evidence_id,),
            ).fetchone()
        else:
            row = self.connection.execute(
                """
                SELECT payload, revision
                FROM human_cos_evidence_revision
                WHERE evidence_id = %s AND revision = %s
                """,
                (evidence_id, revision),
            ).fetchone()
        if row is None:
            raise MissingRecordError(f"evidence not found: {evidence_id}@{revision or 'latest'}")
        return parse_evidence(dict(row[0])), int(row[1])

    def list_latest_evidence(self, case_id: str) -> list[Evidence]:
        rows = self.connection.execute(
            """
            SELECT DISTINCT ON (evidence_id) payload
            FROM human_cos_evidence_revision
            WHERE case_id = %s
            ORDER BY evidence_id, revision DESC
            """,
            (case_id,),
        ).fetchall()
        return [parse_evidence(dict(row[0])) for row in rows]

    def list_context_evidence(
        self,
        case: Case,
        *,
        actor_id: str | None,
        role_id: str | None,
        as_of: datetime,
    ) -> Sequence[AdmittedEvidence]:
        """Select latest temporally admissible revision, then enforce ACL.

        ACL is evaluated only on the selected revision; the code never falls
        back to an older revision merely because a newer admissible revision is
        more restrictive.
        """
        rows = self.connection.execute(
            """
            SELECT evidence_id, revision, payload
            FROM human_cos_evidence_revision
            WHERE case_id = %s
            ORDER BY evidence_id, revision DESC
            """,
            (case.case_id,),
        ).fetchall()

        selected: dict[str, tuple[Evidence, int]] = {}
        exhausted: set[str] = set()
        for evidence_id_raw, revision_raw, payload in rows:
            evidence_id = str(evidence_id_raw)
            if evidence_id in exhausted:
                continue
            evidence = parse_evidence(dict(payload))
            if temporal_allows(case, evidence, as_of=as_of):
                selected[evidence_id] = (evidence, int(revision_raw))
                exhausted.add(evidence_id)

        admitted: list[AdmittedEvidence] = []
        for evidence_id in sorted(selected):
            evidence, revision = selected[evidence_id]
            basis = visibility_basis(evidence.visibility, actor_id=actor_id, role_id=role_id)
            if basis is not None:
                admitted.append(
                    AdmittedEvidence(evidence=evidence, revision=revision, visibility_basis=basis)
                )
        return admitted

    def store_context_admission(self, record: ContextAdmissionRecord) -> None:
        try:
            self.connection.execute(
                """
                INSERT INTO human_cos_context_admission
                    (context_manifest_id, manifest_hash, record_hash, payload)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    record.context_manifest_id,
                    record.manifest_hash,
                    record.record_hash,
                    Jsonb(record.to_document()),
                ),
            )
            self.connection.commit()
        except errors.UniqueViolation as exc:
            self.connection.rollback()
            raise DuplicateRevisionError(
                f"context admission exists: {record.context_manifest_id}"
            ) from exc

    def get_context_admission(self, context_manifest_id: str) -> ContextAdmissionRecord:
        row = self.connection.execute(
            """
            SELECT payload
            FROM human_cos_context_admission
            WHERE context_manifest_id = %s
            """,
            (context_manifest_id,),
        ).fetchone()
        if row is None:
            raise MissingRecordError(f"context admission not found: {context_manifest_id}")
        return ContextAdmissionRecord.model_validate(dict(row[0]))

    def store_raw_output(
        self,
        *,
        run_id: str,
        output_ref: str,
        content: str | bytes,
    ) -> RawOutputRecord:
        self.get_run_manifest(run_id)
        record = make_raw_output_record(run_id=run_id, output_ref=output_ref, content=content)
        try:
            self.connection.execute(
                """
                INSERT INTO human_cos_raw_output
                    (output_ref, run_id, raw_bytes, raw_output_hash)
                VALUES (%s, %s, %s, %s)
                """,
                (record.output_ref, record.run_id, record.content, record.sha256),
            )
            self.connection.commit()
        except errors.UniqueViolation as exc:
            self.connection.rollback()
            raise DuplicateRevisionError(f"raw output exists: {record.output_ref}") from exc
        return record

    def get_raw_output(self, output_ref: str) -> RawOutputRecord:
        row = self.connection.execute(
            """
            SELECT run_id, raw_bytes, raw_output_hash
            FROM human_cos_raw_output
            WHERE output_ref = %s
            """,
            (output_ref,),
        ).fetchone()
        if row is None:
            raise MissingRecordError(f"raw output not found: {output_ref}")
        return RawOutputRecord(
            output_ref=output_ref,
            run_id=str(row[0]),
            content=bytes(row[1]),
            sha256=str(row[2]),
        )

    def append_run_manifest(self, document: dict[str, Any]) -> tuple[RunManifest, int, str]:
        manifest = parse_run_manifest(document)
        if (manifest.raw_output_ref is None) != (manifest.raw_output_hash is None):
            raise RunIntegrityError("raw_output_ref and raw_output_hash must be recorded together")

        with self.connection.transaction():
            self.connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                (manifest.run_id,),
            )
            row = self.connection.execute(
                """
                SELECT sequence, payload
                FROM human_cos_run_manifest_revision
                WHERE run_id = %s
                ORDER BY sequence DESC
                LIMIT 1
                """,
                (manifest.run_id,),
            ).fetchone()

            if row is None:
                if manifest.status != "CREATED":
                    raise RunTransitionError(
                        "initial Run Manifest snapshot must have status CREATED"
                    )
                self.get_case(manifest.case_id)
                context_row = self.connection.execute(
                    """
                    SELECT 1
                    FROM human_cos_context_admission
                    WHERE manifest_hash = %s
                    LIMIT 1
                    """,
                    (manifest.context_manifest_hash,),
                ).fetchone()
                if context_row is None:
                    raise RunIntegrityError(
                        "Run Manifest context_manifest_hash has no admitted Context binding"
                    )
                sequence = 1
                if manifest.parent_run_id is not None:
                    self.get_run_manifest(manifest.parent_run_id)
            else:
                previous = parse_run_manifest(dict(row[1]))
                validate_run_snapshot_transition(previous, manifest)
                sequence = int(row[0]) + 1

            if manifest.raw_output_ref is not None:
                raw_row = self.connection.execute(
                    """
                    SELECT run_id, raw_output_hash
                    FROM human_cos_raw_output
                    WHERE output_ref = %s
                    """,
                    (manifest.raw_output_ref,),
                ).fetchone()
                if raw_row is None:
                    raise RunIntegrityError(
                        f"bound raw output does not exist: {manifest.raw_output_ref}"
                    )
                if str(raw_row[0]) != manifest.run_id:
                    raise RunIntegrityError("raw output belongs to a different run_id")
                if str(raw_row[1]) != manifest.raw_output_hash:
                    raise RunIntegrityError("raw output hash does not match stored artifact")

            manifest_hash = canonical_document_sha256(manifest.to_document())
            self.connection.execute(
                """
                INSERT INTO human_cos_run_manifest_revision
                    (run_id, sequence, case_id, status, parent_run_id, fallback_from,
                     manifest_hash, payload)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    manifest.run_id,
                    sequence,
                    manifest.case_id,
                    manifest.status,
                    manifest.parent_run_id,
                    manifest.fallback_from,
                    manifest_hash,
                    Jsonb(manifest.to_document()),
                ),
            )
        return manifest, sequence, manifest_hash

    def get_run_manifest(
        self,
        run_id: str,
        sequence: int | None = None,
    ) -> tuple[RunManifest, int, str]:
        if sequence is None:
            row = self.connection.execute(
                """
                SELECT sequence, manifest_hash, payload
                FROM human_cos_run_manifest_revision
                WHERE run_id = %s
                ORDER BY sequence DESC
                LIMIT 1
                """,
                (run_id,),
            ).fetchone()
        else:
            row = self.connection.execute(
                """
                SELECT sequence, manifest_hash, payload
                FROM human_cos_run_manifest_revision
                WHERE run_id = %s AND sequence = %s
                """,
                (run_id, sequence),
            ).fetchone()
        if row is None:
            raise MissingRecordError(f"run manifest not found: {run_id}@{sequence or 'latest'}")
        return parse_run_manifest(dict(row[2])), int(row[0]), str(row[1])

    def list_run_manifests(self, run_id: str) -> tuple[RunManifest, ...]:
        rows = self.connection.execute(
            """
            SELECT payload
            FROM human_cos_run_manifest_revision
            WHERE run_id = %s
            ORDER BY sequence
            """,
            (run_id,),
        ).fetchall()
        if not rows:
            raise MissingRecordError(f"run manifest not found: {run_id}")
        return tuple(parse_run_manifest(dict(row[0])) for row in rows)

    def store_audit_event(self, document: dict[str, Any]) -> tuple[AuditEvent, str]:
        event = parse_audit_event(document)
        if event.run_id is not None:
            self.get_run_manifest(event.run_id)
        event_hash = canonical_document_sha256(event.to_document())
        try:
            self.connection.execute(
                """
                INSERT INTO human_cos_audit_event
                    (event_id, run_id, event_type, event_hash, payload)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    event.event_id,
                    event.run_id,
                    event.event_type,
                    event_hash,
                    Jsonb(event.to_document()),
                ),
            )
            self.connection.commit()
        except errors.UniqueViolation as exc:
            self.connection.rollback()
            raise DuplicateRevisionError(f"audit event exists: {event.event_id}") from exc
        return event, event_hash

    def list_audit_events(self, run_id: str) -> tuple[AuditEvent, ...]:
        rows = self.connection.execute(
            """
            SELECT payload
            FROM human_cos_audit_event
            WHERE run_id = %s
            ORDER BY created_at, event_id
            """,
            (run_id,),
        ).fetchall()
        return tuple(parse_audit_event(dict(row[0])) for row in rows)

    def get_replay_lineage(self, run_id: str) -> ReplayLineage:
        snapshots = self.list_run_manifests(run_id)
        chain_reversed: list[str] = []
        current_run_id: str | None = run_id
        seen: set[str] = set()
        while current_run_id is not None:
            if current_run_id in seen:
                raise RunIntegrityError("parent_run_id cycle detected")
            seen.add(current_run_id)
            chain_reversed.append(current_run_id)
            current_manifest, _, _ = self.get_run_manifest(current_run_id)
            current_run_id = current_manifest.parent_run_id

        return ReplayLineage(
            run_id=run_id,
            run_chain=tuple(reversed(chain_reversed)),
            snapshots=snapshots,
            audit_events=self.list_audit_events(run_id),
        )
