"""Installed TRIAL-SBX verification and package-owned rehearsal CLI.

It has no custom-input run, provider, publication, or reality-execution command.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from .audit import TrialAuditError, verify_audit_bundle
from .bundle import TrialBundleError, verify_input_bundle
from .full_function import FullFunctionTrialError, run_full_function_trial
from .rehearsal import TrialRehearsalError, run_installed_rehearsal


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="human-cos-trial")
    subparsers = parser.add_subparsers(dest="command", required=True)

    input_parser = subparsers.add_parser(
        "verify-input",
        help="verify a detached trial input bundle; grants no execution authority",
    )
    input_parser.add_argument("input_root")

    audit_parser = subparsers.add_parser(
        "verify-audit",
        help="verify a detached local trial audit bundle",
    )
    audit_parser.add_argument("audit_root")

    rehearsal_parser = subparsers.add_parser(
        "rehearse-installed",
        help="run the exact package-owned Mock-only SBX5 rehearsal in a new work root",
    )
    rehearsal_parser.add_argument("work_root")

    fft_parser = subparsers.add_parser(
        "full-function-trial",
        help="run the Mock-only FFT-1A S5--S8 narrow chain against disposable PostgreSQL",
    )
    fft_parser.add_argument("output_root")
    fft_parser.add_argument("--database-url")
    return parser


def _verify_input(path: str) -> dict[str, object]:
    bundle = verify_input_bundle(path)
    return {
        "status": "VERIFIED",
        "authority_granted": False,
        "detached_input_address": bundle.receipt.detached_input_address,
        "bundle_receipt_hash": bundle.receipt.bundle_receipt_hash,
        "trial_manifest_hash": bundle.manifest.manifest_hash,
        "case_id": bundle.manifest.case_id,
        "case_revision": bundle.manifest.case_revision,
        "case_mode": bundle.manifest.case_mode.value,
    }


def _verify_audit(path: str) -> dict[str, object]:
    record = verify_audit_bundle(path)
    return {
        "status": "VERIFIED",
        "authority_granted": False,
        "bundle_address": record.bundle_address,
        "trial_result_hash": record.result.result_hash,
        "outcome": record.result.outcome.value,
        "stop_condition": record.result.stop_condition.value,
        "final_runtime_state": (
            record.result.final_runtime_position.state.value
            if record.result.final_runtime_position is not None
            else None
        ),
    }


def _rehearse_installed(path: str) -> dict[str, object]:
    return run_installed_rehearsal(path).to_document()


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "verify-input":
            result = _verify_input(args.input_root)
        elif args.command == "verify-audit":
            result = _verify_audit(args.audit_root)
        elif args.command == "rehearse-installed":
            result = _rehearse_installed(args.work_root)
        elif args.command == "full-function-trial":
            result = run_full_function_trial(
                args.output_root, database_url=args.database_url
            ).document
        else:  # pragma: no cover - argparse owns the closed command vocabulary.
            parser.error("unsupported command")
    except KeyboardInterrupt:
        print(
            json.dumps(
                {
                    "status": "ABORTED",
                    "authority_granted": False,
                    "reason": "operator interrupted the trial; owned resources were cleaned",
                }
            )
        )
        return 130
    except (
        TrialBundleError,
        TrialAuditError,
        TrialRehearsalError,
        FullFunctionTrialError,
        ValueError,
    ) as exc:
        print(json.dumps({"status": "REJECTED", "authority_granted": False, "reason": str(exc)}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
