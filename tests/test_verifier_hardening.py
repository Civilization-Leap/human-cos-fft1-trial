import copy
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from compare_repeat import compare_snapshots
from verify_fft1b import SHA, canonical_hash, verify_cross_bindings, verify_negative_matrix


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
