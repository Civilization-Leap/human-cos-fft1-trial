import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from compare_repeat import compare_snapshots
from verify_fft1b import (
    AUTHORITY,
    REQUIRED_TABLES,
    SHA,
    STATES,
    canonical_hash,
    verify_cross_bindings,
    verify_directory,
    verify_negative_matrix,
)


def valid_negative_matrix():
    return [
        {
            "case": "research_safety_block",
            "expected": "BLOCK",
            "observed": "BLOCK;S7_ENTRY_GUARD_FAILED",
            "passed": True,
            "boundary": "code-owned S7 Research Safety admission",
            "decision_reason": "Research Safety outcome BLOCK",
            "guard_name": "scenario_generation_admission_frozen",
            "guard_status": "FAIL",
            "downstream_invocation_count": 1,
            "blocked_downstream_invocation_count": 0,
        },
        {
            "case": "challenger_block",
            "expected": "BLOCK",
            "observed": "REJECTED",
            "passed": True,
            "boundary": "Challenger downstream-clearance gate",
            "decision_reason": "blocking finding",
        },
        {
            "case": "capability_gap",
            "expected": "CAPABILITY_GAP",
            "observed": "OPEN",
            "passed": True,
            "boundary": "qualified Domain route required",
            "decision_reason": "missing capability",
        },
        {
            "case": "evidence_mismatch_or_forgery",
            "expected": "REJECT",
            "observed": "REJECTED",
            "passed": True,
            "boundary": "S8 exact evaluator task/packet evidence binding",
            "decision_reason": "task hash differs",
        },
        {
            "case": "invalid_evaluator_or_independence",
            "expected": "REJECT",
            "observed": "REJECTED",
            "passed": True,
            "boundary": "Evaluator qualification gate",
            "decision_reason": "role not eligible",
        },
        {
            "case": "final_synthesis_attempt",
            "expected": "AUTHORIZATION_REQUIRED",
            "observed": "AUTHORIZATION_REQUIRED",
            "passed": True,
            "boundary": "ADVERSARIAL_REVIEW -> FINAL_SYNTHESIS authorization gate",
            "decision_reason": "authorization absent",
        },
        {
            "case": "reality_execution_attempt",
            "expected": "DENIED",
            "observed": "DENIED",
            "passed": True,
            "boundary": "ToolPolicy REALITY_EXECUTION global deny",
            "decision_reason": "globally denied",
        },
    ]


def write_self_consistent_fixture(root, verdict):
    evidence = root / "evidence_package"
    evidence.mkdir(parents=True)
    tables = sorted(REQUIRED_TABLES)
    snapshot = {
        "tables": [
            {
                "table": table,
                "row_count": 1,
                "rows": [{"content": {"verdict": verdict}}],
            }
            for table in tables
        ]
    }
    snapshot_hash = canonical_hash(snapshot)
    snapshot_json = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    terminals = {
        "S5_CDE": hashlib.sha256(b"s5").hexdigest(),
        "S6_WCI": hashlib.sha256(b"s6").hexdigest(),
        "S7_SCS_NARROW": hashlib.sha256(b"s7").hexdigest(),
        "S8_EVAL_NARROW": hashlib.sha256(b"s8").hexdigest(),
    }
    trace = [
        {
            "sequence": index,
            "source": source,
            "target": target,
            "status": "ALLOWED",
        }
        for index, (source, target) in enumerate(zip(STATES, STATES[1:]), 1)
    ]
    receipt = {
        "migration_names": [f"{index:04}" for index in range(1, 8)],
        "s5_terminal_hash": terminals["S5_CDE"],
        "s6_terminal_hash": terminals["S6_WCI"],
        "s7_terminal_hash": terminals["S7_SCS_NARROW"],
        "s8_terminal_hash": terminals["S8_EVAL_NARROW"],
        "tables_exercised": tables,
        "evidence_snapshot_json": snapshot_json,
        "evidence_snapshot_hash": snapshot_hash,
        "stage_trace": trace,
        "final_runtime_state": STATES[-1],
        "migrations_rolled_back": True,
    }
    receipt["receipt_hash"] = canonical_hash(receipt)
    checkpoint = {
        "s5_terminal_hash": terminals["S5_CDE"],
        "s6_terminal_hash": terminals["S6_WCI"],
        "s7_terminal_hash": terminals["S7_SCS_NARROW"],
        "s8_terminal_hash": terminals["S8_EVAL_NARROW"],
        "tables_exercised": tables,
        "evidence_snapshot_json": snapshot_json,
        "evidence_snapshot_hash": snapshot_hash,
    }
    checkpoint["checkpoint_hash"] = canonical_hash(checkpoint)
    result = {
        "status": "PASS",
        "adapter_lane": "MOCK_ONLY",
        "package_source_identity": {
            "kind": "package_build_commit",
            "commit_sha": SHA,
        },
        "transition_count": 12,
        "stage_trace": trace,
        "final_runtime_state": STATES[-1],
        "migrations_applied": [f"{index:04}" for index in range(1, 8)],
        "authority": {key: False for key in AUTHORITY},
        "n3_status": "OPEN",
        "sbx7_freeze": False,
        "real_case_effectiveness": "NOT_DEMONSTRATED",
        "negative_matrix": valid_negative_matrix(),
        "negative_matrix_passed": True,
        "persistence": {
            "readback_verified": True,
            "cleanup_verified": True,
            "tables_exercised": tables,
            "snapshot_hash": snapshot_hash,
        },
        "s8_narrow_sidecars": {
            "persisted": True,
            "terminal_hash": terminals["S8_EVAL_NARROW"],
        },
        "stage_terminal_hashes": terminals,
        "application_chain_receipt_hash": receipt["receipt_hash"],
    }
    result["result_hash"] = canonical_hash(result)
    files = {
        "stage_trace.json": trace,
        "application_chain_receipt.json": receipt,
        "application_chain_checkpoint.json": checkpoint,
        "persistence_snapshot.json": snapshot,
    }
    for name, value in files.items():
        (evidence / name).write_text(json.dumps(value), encoding="utf-8")
    (root / "full_function_trial_result.json").write_text(
        json.dumps(result), encoding="utf-8"
    )
    manifest = {
        f"evidence_package/{name}": hashlib.sha256(
            (evidence / name).read_bytes()
        ).hexdigest()
        for name in files
    }
    (root / "evidence_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )


class VerifierHardeningTests(unittest.TestCase):
    def test_all_seven_semantics_are_required(self):
        verify_negative_matrix(valid_negative_matrix(), True)

    def test_final_synthesis_allowed_is_rejected_even_if_passed_true(self):
        rows = valid_negative_matrix()
        row = next(item for item in rows if item["case"] == "final_synthesis_attempt")
        row["observed"] = "ALLOWED"
        with self.assertRaisesRegex(ValueError, "final_synthesis_attempt"):
            verify_negative_matrix(rows, True)

    def test_each_non_safety_probe_rejects_observed_mutation(self):
        for index in range(1, 7):
            with self.subTest(case=valid_negative_matrix()[index]["case"]):
                rows = copy.deepcopy(valid_negative_matrix())
                rows[index]["observed"] = "ALLOWED"
                with self.assertRaises(ValueError):
                    verify_negative_matrix(rows, True)

    def test_persistence_and_s8_cross_bindings(self):
        tables = [
            "human_cos_framing_requirement",
            "human_cos_domain_output",
            "human_cos_s6_disclosure_grant",
            "human_cos_s6_world_state_revision",
            "human_cos_s6_critical_review_plan",
            "human_cos_s7_artifact",
            "human_cos_s8_artifact",
            "human_cos_context_admission",
            "human_cos_run_manifest_revision",
            "human_cos_raw_output",
            "human_cos_audit_event",
        ]
        s8_hash = "a" * 64
        doc = {
            "persistence": {"tables_exercised": tables},
            "s8_narrow_sidecars": {"terminal_hash": s8_hash},
            "stage_terminal_hashes": {"S8_EVAL_NARROW": s8_hash},
        }
        receipt = {"tables_exercised": tables, "s8_terminal_hash": s8_hash}
        checkpoint = {"tables_exercised": tables, "s8_terminal_hash": s8_hash}
        snapshot = {
            "tables": [
                {"table": name, "row_count": 1, "rows": [{"id": index}]}
                for index, name in enumerate(tables)
            ]
        }
        verify_cross_bindings(doc, receipt, checkpoint, snapshot)
        bad = copy.deepcopy(doc)
        bad["persistence"]["tables_exercised"] = []
        with self.assertRaisesRegex(ValueError, "table binding"):
            verify_cross_bindings(bad, receipt, checkpoint, snapshot)
        bogus_tables = ["bogus_table"]
        bogus = {
            "persistence": {"tables_exercised": bogus_tables},
            "s8_narrow_sidecars": {"terminal_hash": s8_hash},
            "stage_terminal_hashes": {"S8_EVAL_NARROW": s8_hash},
        }
        bogus_receipt = {"tables_exercised": bogus_tables, "s8_terminal_hash": s8_hash}
        bogus_checkpoint = {
            "tables_exercised": bogus_tables,
            "s8_terminal_hash": s8_hash,
        }
        bogus_snapshot = {
            "tables": [{"table": "bogus_table", "row_count": 1, "rows": [{"id": 1}]}]
        }
        with self.assertRaisesRegex(ValueError, "table binding"):
            verify_cross_bindings(
                bogus, bogus_receipt, bogus_checkpoint, bogus_snapshot
            )
        bad = copy.deepcopy(doc)
        bad["s8_narrow_sidecars"]["terminal_hash"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "S8 sidecar"):
            verify_cross_bindings(bad, receipt, checkpoint, snapshot)

    def test_single_round_accepts_consistently_rebound_row_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline"
            mutated = root / "mutated"
            write_self_consistent_fixture(baseline, "DENY")
            write_self_consistent_fixture(mutated, "ALLOW")
            self.assertEqual(verify_directory(baseline)["status"], "PASS")
            self.assertEqual(verify_directory(mutated)["status"], "PASS")

    def test_bounded_comparator_rejects_equal_inventory_row_content_change(self):
        policy = {
            "candidate_sha": SHA,
            "storage_created_at_tables": [
                "human_cos_initial_framing",
                "human_cos_context_admission",
                "human_cos_run_manifest_revision",
            ],
            "clock_paths": ["human_cos_initial_framing/.payload.finished_at"],
            "unordered_paths": [],
        }
        windows = [
            ["2026-09-22T10:00:00+00:00", "2026-09-22T10:00:10+00:00"],
            ["2026-09-22T11:00:00+00:00", "2026-09-22T11:00:10+00:00"],
        ]

        def snapshot(hour):
            payload = {
                "run_id": "run-1",
                "content": {"verdict": "DENY"},
                "finished_at": f"2026-09-22T{hour}:00:01+00:00",
                "source_hash": "e" * 64,
            }
            digest = canonical_hash(payload)
            return {
                "format": "synthetic-only",
                "tables": [
                    {
                        "table": "human_cos_initial_framing",
                        "row_count": 1,
                        "rows": [
                            {
                                "run_id": "run-1",
                                "record_hash": digest,
                                "payload": {**payload, "record_hash": digest},
                                "created_at": f"2026-09-22T{hour}:00:02+00:00",
                            }
                        ],
                    },
                    {
                        "table": "human_cos_context_admission",
                        "row_count": 0,
                        "rows": [],
                    },
                    {
                        "table": "human_cos_run_manifest_revision",
                        "row_count": 0,
                        "rows": [],
                    },
                ],
            }

        left, right = snapshot("10"), snapshot("11")
        baseline, _ = compare_snapshots(left, right, windows, policy)
        self.assertTrue(baseline["accepted"])

        row = right["tables"][0]["rows"][0]
        row["payload"].pop("record_hash")
        row["payload"]["content"]["verdict"] = "ALLOW"
        digest = canonical_hash(row["payload"])
        row["payload"]["record_hash"] = row["record_hash"] = digest

        changed, _ = compare_snapshots(left, right, windows, policy)
        self.assertFalse(changed["accepted"])
        self.assertTrue(changed["semantic_differences"])

    def test_public_launcher_help_hides_private_source_options(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "run_trial.py"), "--help"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertNotIn("--repo", completed.stdout)
        self.assertNotIn("--source-bundle", completed.stdout)
        self.assertIn("--output", completed.stdout)
        self.assertIn("--host-note", completed.stdout)


if __name__ == "__main__":
    unittest.main()
