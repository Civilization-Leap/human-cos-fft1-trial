"""Detached, standard-library evidence checks; never grants publication authority."""
import hashlib
import json
from pathlib import Path

SHA = "bc324b68814dddb388e3e6cebab0d31a38ef6817"
TREE = "241ae0a97d642792ef40176268293b76194b7d3c"
STATES = [
    "BOUNDARY_AND_POLICY_FROZEN", "FRAMING_INDEPENDENT", "FRAMING_REVIEWED",
    "DOMAIN_ROUTED", "DOMAIN_INDEPENDENT_RUN", "DOMAIN_OUTPUT_FROZEN",
    "CROSS_EXAMINATION", "WORLD_CAUSAL_INTEGRATION", "CRITICAL_NODE_DETECTION",
    "CRITICAL_NODE_REVIEW", "SCENARIO_GENERATION", "SCENARIO_RESIMULATION",
    "ADVERSARIAL_REVIEW",
]
NEGATIVES = {
    "research_safety_block", "challenger_block", "capability_gap",
    "evidence_mismatch_or_forgery", "invalid_evaluator_or_independence",
    "final_synthesis_attempt", "reality_execution_attempt",
}
AUTHORITY = {
    "controller_d", "final_synthesis", "final_claim", "human_seal",
    "publication", "reality_execution", "s8_full", "s9_plus",
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical_hash(obj):
    return digest(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode())


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify_result(doc):
    require(doc["result_hash"] == canonical_hash(
        {k: v for k, v in doc.items() if k != "result_hash"}), "result hash mismatch")
    require(doc["status"] == "PASS" and doc["adapter_lane"] == "MOCK_ONLY", "wrong lane/status")
    require(doc["package_source_identity"] == {
        "kind": "package_build_commit", "commit_sha": SHA}, "installed build identity mismatch")
    require(doc["transition_count"] == 12, "wrong edge count")
    trace = doc["stage_trace"]
    require([(t["source"], t["target"]) for t in trace] == list(zip(STATES, STATES[1:])),
            "wrong ordered trace")
    require(all(t["sequence"] == i and t["status"] == "ALLOWED"
                for i, t in enumerate(trace, 1)), "invalid transition decision")
    require(doc["final_runtime_state"] == STATES[-1], "terminal state escaped")
    require(doc["migrations_applied"] == [f"{i:04}" for i in range(1, 8)], "missing migration")
    require(set(doc["authority"]) == AUTHORITY
            and all(v is False for v in doc["authority"].values()), "authority expanded")
    require(doc["n3_status"] == "OPEN" and doc["sbx7_freeze"] is False
            and doc["real_case_effectiveness"] == "NOT_DEMONSTRATED", "boundary claim drift")
    rows = doc["negative_matrix"]
    require(len(rows) == 7 and {r["case"] for r in rows} == NEGATIVES, "negative coverage differs")
    require(doc["negative_matrix_passed"] is True
            and all(r["passed"] is True for r in rows), "negative failed")
    safety = next(r for r in rows if r["case"] == "research_safety_block")
    require(safety["guard_name"] == "scenario_generation_admission_frozen"
            and safety["guard_status"] == "FAIL" and "BLOCK" in safety["decision_reason"]
            and safety["observed"] == "BLOCK;S7_ENTRY_GUARD_FAILED"
            and safety["downstream_invocation_count"] == 1
            and safety["blocked_downstream_invocation_count"] == 0, "Safety control invalid")
    require(doc["persistence"]["readback_verified"] is True
            and doc["persistence"]["cleanup_verified"] is True
            and doc["s8_narrow_sidecars"]["persisted"] is True, "persistence incomplete")


def verify_directory(root):
    root = Path(root).resolve()
    doc = read(root / "full_function_trial_result.json")
    verify_result(doc)
    manifest = read(root / "evidence_manifest.json")
    names = {"application_chain_checkpoint.json", "persistence_snapshot.json",
             "stage_trace.json", "application_chain_receipt.json"}
    require(set(manifest) == {"evidence_package/" + name for name in names}, "manifest set differs")
    for name, expected in manifest.items():
        path = root / name
        require(not path.is_symlink() and path.is_file()
                and path.resolve().is_relative_to(root), "invalid evidence file")
        require(digest(path.read_bytes()) == expected, "evidence hash mismatch: " + name)
    evidence = root / "evidence_package"
    require(read(evidence / "stage_trace.json") == doc["stage_trace"], "trace binding mismatch")
    receipt = read(evidence / "application_chain_receipt.json")
    require(receipt["receipt_hash"] == canonical_hash(
        {k: v for k, v in receipt.items() if k != "receipt_hash"}), "receipt hash mismatch")
    require(receipt["receipt_hash"] == doc["application_chain_receipt_hash"], "receipt binding mismatch")
    require(receipt["stage_trace"] == doc["stage_trace"]
            and receipt["migrations_rolled_back"] is True
            and receipt["final_runtime_state"] == STATES[-1], "receipt state differs")
    checkpoint = read(evidence / "application_chain_checkpoint.json")
    require(checkpoint["checkpoint_hash"] == canonical_hash(
        {k: v for k, v in checkpoint.items() if k != "checkpoint_hash"}), "checkpoint hash mismatch")
    for stage, key in [("S5_CDE", "s5_terminal_hash"), ("S6_WCI", "s6_terminal_hash"),
                       ("S7_SCS_NARROW", "s7_terminal_hash"), ("S8_EVAL_NARROW", "s8_terminal_hash")]:
        require(doc["stage_terminal_hashes"][stage] == receipt[key] == checkpoint[key],
                "stage binding mismatch: " + stage)
    snapshot = read(evidence / "persistence_snapshot.json")
    require(canonical_hash(snapshot) == doc["persistence"]["snapshot_hash"]
            == receipt["evidence_snapshot_hash"], "snapshot binding mismatch")
    require(json.loads(receipt["evidence_snapshot_json"]) == snapshot, "receipt snapshot differs")
    require(json.loads(checkpoint["evidence_snapshot_json"]) == snapshot
            and checkpoint["evidence_snapshot_hash"] == receipt["evidence_snapshot_hash"],
            "checkpoint snapshot differs")
    return doc


def differences(a, b, path="$"):
    if type(a) is not type(b):
        return [path]
    if isinstance(a, dict):
        return [p for k in sorted(a.keys() | b.keys()) for p in (
            [path + "." + k] if k not in a or k not in b
            else differences(a[k], b[k], path + "." + k))]
    if isinstance(a, list):
        if len(a) != len(b):
            return [path + ".length"]
        return [p for i, (x, y) in enumerate(zip(a, b))
                for p in differences(x, y, f"{path}[{i}]")]
    return [] if a == b else [path]
