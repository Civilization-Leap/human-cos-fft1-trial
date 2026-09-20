"""Pinned-fixture bounded repeatability, retaining raw hashes and all raw evidence.

Every substituted hash has a recomputed original preimage. Unknown hashes remain
literal. Only enumerated clocks inside each invocation window may vary; their
complete equality/order relation is preserved using timestamp ranks. This is
not byte determinism, real-case validation, or a generic Domain Context verifier.
"""
import datetime as dt
import hashlib
import json
from pathlib import Path
import re

from verify_fft1b import SHA, canonical_hash, differences, read, require, verify_directory

HASH = re.compile(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")
POLICY = read(Path(__file__).with_name("repeat_policy.json"))


def instant(value):
    value = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(value.utcoffset() is not None, "naive clock")
    return value.astimezone(dt.timezone.utc)


def iso(value):
    # ContextAdmissionRecord hashes datetime.isoformat(), not its Pydantic Z form.
    if isinstance(value, str) and re.match(r"^\d{4}-\d\d-\d\dT", value) and value.endswith("Z"):
        return value[:-1] + "+00:00"
    return value


class EvidenceGraph:
    def __init__(self, snapshot, window, policy=None):
        self.policy = POLICY if policy is None else policy
        require(self.policy["candidate_sha"] == SHA, "policy candidate mismatch")
        self.low, self.high = map(instant, window)
        require(0 < (self.high - self.low).total_seconds() <= 1800, "invalid invocation window")
        self.snapshot = snapshot
        self.definitions = {}
        self.memo = {}
        self.resolving = set()
        self.references = set()
        self.clocks = []
        self.hash_proofs = {}
        self.clock_paths = set(self.policy["clock_paths"])
        self.unordered = set(self.policy["unordered_paths"])
        tables = snapshot["tables"]
        require(len({t["table"] for t in tables}) == len(tables), "duplicate table")
        require({t["table"] for t in tables} == set(self.policy["storage_created_at_tables"]),
                "snapshot table inventory changed")
        self.tables = {t["table"]: t["rows"] for t in tables}
        # S8 paths carry the owner identity, so an exemption cannot leak to
        # another artifact of the same kind or to an unrelated clock field.
        s8_prefix = "human_cos_s8_artifact/"
        s8_clock_paths = {p for p in self.clock_paths if p.startswith(s8_prefix)}
        self.clock_paths -= s8_clock_paths
        for row in self.tables.get("human_cos_s8_artifact", []):
            kind_prefix = s8_prefix + row.get("artifact_kind", "") + "."
            for path in s8_clock_paths:
                if path.startswith(kind_prefix):
                    self.clock_paths.add(self.row_path("human_cos_s8_artifact", row)
                                         + "." + path[len(kind_prefix):])
        self.synthetic_clocks = set()
        offsets = self.policy.get("synthetic_s8_offsets_seconds", {})
        if offsets:
            final_runs = [r["payload"] for r in self.tables["human_cos_run_manifest_revision"]
                          if r["payload"].get("run_id") == "run:evaluator:sbx5" and r["sequence"] == 3]
            require(len(final_runs) == 1, "missing evaluator clock anchor")
            base = instant(final_runs[0]["finished_at"])
            require(self.low <= base <= self.high, "evaluator clock outside invocation")
            for artifact_id, fields in offsets.items():
                rows = [r for r in self.tables["human_cos_s8_artifact"] if r["artifact_id"] == artifact_id]
                require(len(rows) == 1, "missing synthetic S8 clock owner")
                for key, seconds in fields.items():
                    expected = base + dt.timedelta(seconds=seconds)
                    require(instant(rows[0]["payload"][key]) == expected,
                            "synthetic S8 clock offset changed: " + artifact_id + "." + key)
                    path = self.row_path("human_cos_s8_artifact", rows[0]) + ".payload." + key
                    self.synthetic_clocks.add((path, expected))
        for table in tables:
            require(table["row_count"] == len(table["rows"]), "row count mismatch")
            for row in table["rows"]:
                self.index(row, self.row_path(table["table"], row))
        self.ranks = {value: i for i, value in enumerate(sorted({v for _, v in self.clocks}))}
        self.reconstruct_contexts()

    @staticmethod
    def row_path(table, row):
        path = table + "/" + row.get("artifact_kind", "")
        if table == "human_cos_s8_artifact":
            path += "/" + row["artifact_id"]
        return path

    def clock_allowed(self, path):
        return path in self.clock_paths or (
            path.endswith(".created_at") and path.count(".") == 1
            and path.split("/", 1)[0] in self.policy["storage_created_at_tables"])

    def clock_value(self, value, path):
        if self.clock_allowed(path) and isinstance(value, str):
            timestamp = instant(value)
            if self.low <= timestamp <= self.high or (path, timestamp) in self.synthetic_clocks:
                return timestamp
        return None

    def define(self, digest, body, path, method):
        # The caller establishes digest==hash(original preimage); no hash pairing
        # by position, length or mere field name is ever admitted.
        self.definitions[digest] = (body, path)
        self.hash_proofs[digest] = {"path": path, "method": method}

    def index(self, value, path):
        if self.clock_allowed(path) or path == "human_cos_raw_output/.raw_bytes":
            require(isinstance(value, str), "clock/raw field type changed: " + path)
        if isinstance(value, dict):
            self.define(canonical_hash(value), value, path, "canonical complete object")
            for key, item in value.items():
                if isinstance(item, str) and HASH.fullmatch(item):
                    body = {k: v for k, v in value.items() if k != key}
                    adapted = {k: iso(v) for k, v in body.items()}
                    if canonical_hash(body) == item:
                        self.define(item, body, path, "canonical object excluding " + key)
                    elif canonical_hash(adapted) == item:
                        self.define(item, adapted, path, "ISO-offset object excluding " + key)
                self.index(item, path + "." + key)
        elif isinstance(value, list):
            self.define(canonical_hash(value), value, path, "canonical array")
            for item in value:
                self.index(item, path + "[]")
        elif isinstance(value, str):
            self.references.update(HASH.findall(value))
            clock = self.clock_value(value, path)
            if clock is not None:
                self.clocks.append((path, clock))
            if path == "human_cos_raw_output/.raw_bytes":
                require(value.startswith("\\x"), "unexpected raw byte encoding")
                raw = bytes.fromhex(value[2:])
                body = json.loads(raw)
                require(raw == json.dumps(body, sort_keys=True).encode(),
                        "raw output serialization changed")
                self.define(hashlib.sha256(raw).hexdigest(), body, path + "<json>", "raw byte SHA256")
                self.index(body, path + "<json>")

    def reconstruct_contexts(self):
        # Only the pinned empty-evidence mock fixture. All seven full preimages
        # must reproduce the original hash. This does NOT resolve N-3.
        for row in self.tables["human_cos_context_admission"]:
            p = row["payload"]
            require(p["evidence"] == [] and p["actor_id"] is None,
                    "nonempty Domain Context requires separate verification")
            runs = [r["payload"] for r in self.tables["human_cos_run_manifest_revision"]
                    if r["sequence"] == 1 and r["payload"]["context_manifest_hash"] == p["manifest_hash"]]
            require(len(runs) == 1, "context has no unique initial run")
            run = runs[0]
            body = {key: run[key] for key in (
                "case_id", "run_id", "stage", "protocol_version", "model_id", "prompt_version", "tool_permissions")}
            body.update(context_manifest_id=p["context_manifest_id"], role_id=p["role_id"],
                        evidence_ids=[], prior_run_ids=[], forbidden_scopes=[],
                        time_boundary=iso(p["reference_time"]))
            require(canonical_hash(body) == p["manifest_hash"], "context preimage mismatch")
            # The time boundary must use the same clock policy as its admission.
            path = "reconstructed-context"
            self.clock_paths.add(path + ".time_boundary")
            self.define(p["manifest_hash"], body, path, "reconstructed exact empty-context preimage")

    def resolve(self, digest):
        if digest not in self.definitions:
            return digest
        if digest in self.memo:
            return self.memo[digest]
        require(digest not in self.resolving, "hash-reference cycle")
        self.resolving.add(digest)
        body, path = self.definitions[digest]
        semantic = canonical_hash(self.normalize(body, path))
        self.resolving.remove(digest)
        self.memo[digest] = semantic
        return semantic

    def normalize(self, value, path):
        if self.clock_allowed(path) or path == "human_cos_raw_output/.raw_bytes":
            require(isinstance(value, str), "clock/raw field type changed: " + path)
        if isinstance(value, dict):
            return {key: self.normalize(item, path + "." + key) for key, item in value.items()}
        if isinstance(value, list):
            items = [self.normalize(item, path + "[]") for item in value]
            if path in self.unordered:
                items.sort(key=lambda item: json.dumps(item, sort_keys=True))
            return items
        if isinstance(value, str):
            clock = self.clock_value(value, path)
            if clock is not None:
                require(clock in self.ranks, "clock absent from original snapshot")
                return {"observed_clock_rank": self.ranks[clock]}
            if path == "human_cos_raw_output/.raw_bytes":
                return self.normalize(json.loads(bytes.fromhex(value[2:])), path + "<json>")
            return HASH.sub(lambda match: self.resolve(match.group()), value)
        return value

    def semantic_snapshot(self):
        tables = []
        for table in self.snapshot["tables"]:
            rows = [self.normalize(row, self.row_path(table["table"], row)) for row in table["rows"]]
            rows.sort(key=lambda row: json.dumps(row, sort_keys=True))
            tables.append({**table, "rows": rows})
        return {**self.snapshot, "tables": tables}

    def audit(self):
        return {
            "clock_occurrences": [{"path": p, "raw_utc": v.isoformat(), "rank": self.ranks[v]}
                                  for p, v in self.clocks],
            "clock_distinct_count": len(self.ranks),
            "resolved_hashes": {key: {**self.hash_proofs[key], "semantic_hash": value}
                                for key, value in sorted(self.memo.items())},
            "opaque_hashes_retained_literal": sorted(self.references - self.definitions.keys()),
        }


def compare_snapshots(left, right, windows, policy=None):
    graphs = [EvidenceGraph(s, w, policy) for s, w in zip((left, right), windows)]
    semantic = [g.semantic_snapshot() for g in graphs]
    changed = differences(*semantic)
    return {
        "policy": "fft1b-bounded-clock-policy-v1",
        "policy_sha256": canonical_hash(POLICY if policy is None else policy),
        "semantic_snapshot_hashes": [canonical_hash(s) for s in semantic],
        "semantic_differences": changed,
        "accepted": not changed,
        "byte_deterministic": left == right,
        "windows": windows,
        "audit": [g.audit() for g in graphs],
    }, graphs


def compare_directories(left, right, windows):
    roots = [Path(left), Path(right)]
    results = [verify_directory(root) for root in roots]
    snapshots = [read(root / "evidence_package/persistence_snapshot.json") for root in roots]
    report, graphs = compare_snapshots(*snapshots, windows)
    # Result/receipt wrappers are already byte-hash-verified by verify_directory.
    # Prove each wrapper differs ONLY through the same verified snapshot graph.
    normalized_results = []
    for root, result, graph, snapshot in zip(roots, results, graphs, snapshots):
        terminal = {}
        for kind, key in (("EVALUATOR_RESULT", "evaluator_result_hash"),
                          ("HC_REGRESSION_REPORT", "hc_regression_report_hash"),
                          ("LOW_RECOGNITION_GATE", "low_recognition_gate_hash")):
            rows = [r for r in graph.tables["human_cos_s8_artifact"] if r["artifact_kind"] == kind]
            require(len(rows) == 1, "ambiguous S8 terminal component")
            terminal[key] = rows[0]["artifact_hash"]
        terminal_hash = canonical_hash(terminal)
        require(terminal_hash == result["stage_terminal_hashes"]["S8_EVAL_NARROW"],
                "S8 terminal preimage mismatch")
        graph.define(terminal_hash, terminal, "s8-terminal", "three authoritative S8 terminal components")
        receipt = read(root / "evidence_package/application_chain_receipt.json")
        require(json.loads(receipt["evidence_snapshot_json"]) == snapshot, "receipt snapshot differs")
        normalized_receipt = {k: graph.normalize(v, "receipt." + k)
                              for k, v in receipt.items() if k not in {"receipt_hash", "evidence_snapshot_json", "evidence_snapshot_hash"}}
        normalized_receipt["semantic_snapshot_hash"] = canonical_hash(graph.semantic_snapshot())
        normalized = {k: graph.normalize(v, "result." + k)
                      for k, v in result.items() if k not in {"result_hash", "application_chain_receipt_hash", "persistence"}}
        normalized["persistence"] = {k: graph.normalize(v, "persistence." + k)
                                     for k, v in result["persistence"].items() if k != "snapshot_hash"}
        normalized["semantic_receipt"] = normalized_receipt
        normalized_results.append(normalized)
    report["semantic_result_differences"] = differences(*normalized_results)
    report["accepted"] = report["accepted"] and not report["semantic_result_differences"]
    report["raw_result_differences"] = differences(*results)
    report["raw_manifest_differences"] = differences(*[read(p / "evidence_manifest.json") for p in roots])
    report["audit"] = [g.audit() for g in graphs]
    report["raw_evidence_preserved"] = True
    report["normalization_scope"] = "listed in-window clocks with full order/equality ranks; recomputed preimage hash graph; relational rows and two explicit scenario sets"
    return report
