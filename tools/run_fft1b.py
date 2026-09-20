#!/usr/bin/env python3
"""Run a pinned FFT candidate on an independently supplied Docker host.

No repository mutation, no remote writes, no provider calls, no readiness verdict.
"""
import argparse
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import uuid
import zipfile

from verify_fft1b import SHA, TREE, differences, require, verify_directory
from compare_repeat import compare_directories


def save(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


class Commands:
    def __init__(self, root):
        self.root = root
        self.counter = 0
        self.env = os.environ.copy()
        self.env["HUMAN_COS_BUILD_COMMIT_SHA"] = SHA
        self.env["COMPOSE_ANSI"] = "never"

    def run(self, args, *, check=True, cwd=None):
        self.counter += 1
        print(f"[{self.counter}] {args[0]} {args[1] if len(args) > 1 else ''}", flush=True)
        proc = subprocess.run(args, cwd=cwd, env=self.env, capture_output=True, text=True)
        save(self.root / f"command-{self.counter:03}.json", {
            "argv": args, "returncode": proc.returncode,
            "stdout": proc.stdout, "stderr": proc.stderr,
            "time_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })
        if check and proc.returncode:
            raise RuntimeError(f"command {self.counter} failed; inspect command log")
        return proc


def export_source(repo, target, commands):
    require(commands.run(["git", "-C", str(repo), "rev-parse", SHA + "^{commit}"]).stdout.strip() == SHA,
            "pinned commit unavailable")
    require(commands.run(["git", "-C", str(repo), "rev-parse", SHA + "^{tree}"]).stdout.strip() == TREE,
            "pinned tree mismatch")
    archive = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", SHA],
                             check=True, capture_output=True).stdout
    target.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            destination = target / member.name
            require(destination.resolve().is_relative_to(target.resolve()), "unsafe archive path")
            require(member.isfile() or member.isdir(), "non-regular source archive member")
        tar.extractall(target, filter="data") if sys.version_info >= (3, 12) else tar.extractall(target)
    (target / ".human-cos-checked-out-commit").write_text(SHA + "\n", encoding="ascii")
    save(target.parent / "source-identity.json", {
        "commit": SHA, "tree": TREE, "archive_sha256": hashlib.sha256(archive).hexdigest(),
        "export": "git archive of exact commit, excluding uncommitted/untracked local files",
        "build_marker": ".human-cos-checked-out-commit",
    })


IDENTITY = """
import importlib.metadata as m, json, pathlib, platform, sys
import human_cos.trial.full_function as f
p = pathlib.Path(f.__file__).parents[1] / '_build_commit.txt'
print(json.dumps({'python': platform.python_version(), 'executable': sys.executable,
 'package_version': m.version('human-cos-runtime'), 'module_file': f.__file__,
 'build_commit': p.read_text().strip(),
 'installed': sorted((d.metadata['Name'], d.version) for d in m.distributions())}))
"""

PRODUCTION_READBACK = """
import json, os, pathlib, psycopg
from human_cos.trial.full_function import FullFunctionTrialResult, _verify_package
from human_cos.trial.integrated_chain import (
 InstalledApplicationChainReceipt, InstalledApplicationChainCheckpoint,
 assert_installed_application_resources_clean)
p = pathlib.Path('/trial/fft1b-RUN')
d = json.loads((p/'full_function_trial_result.json').read_text())
FullFunctionTrialResult(d, p).assert_integrity()
_verify_package(p, json.loads((p/'evidence_manifest.json').read_text()))
for filename, cls in [('application_chain_receipt.json', InstalledApplicationChainReceipt),
                      ('application_chain_checkpoint.json', InstalledApplicationChainCheckpoint)]:
 v = json.loads((p/'evidence_package'/filename).read_text())
 for key in ('migration_names', 'tables_exercised', 'stage_trace'):
  if key in v: v[key] = tuple(v[key])
 cls(**v).assert_integrity()
with psycopg.connect(os.environ['HUMAN_COS_TRIAL_DATABASE_URL']) as c:
 assert_installed_application_resources_clean(c)
print('PRODUCTION_EVIDENCE_READBACK_AND_DATABASE_CLEAN=PASS')
"""


def package_evidence(root):
    files = sorted(p for p in root.rglob("*") if p.is_file()
                   and "source" not in p.relative_to(root).parts and p.suffix != ".zip")
    save(root / "host-file-hashes.json", {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files
    })
    path = root / "FFT1B-evidence.zip"
    with zipfile.ZipFile(path, "x", zipfile.ZIP_DEFLATED) as z:
        for p in files + [root / "host-file-hashes.json"]:
            z.write(p, str(p.relative_to(root)))
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source_input = parser.add_mutually_exclusive_group(required=True)
    source_input.add_argument("--repo", type=Path, help="existing authorized local private clone")
    source_input.add_argument("--source-bundle", type=Path, help="verified fixed source ZIP")
    parser.add_argument("--output", required=True, type=Path, help="new, nonexistent output directory")
    parser.add_argument("--host-note", required=True,
                        help="host provenance and independence from implementation/CI; no credentials")
    args = parser.parse_args()
    root = args.output.resolve()
    require(not root.exists(), "output must not exist; use a fresh path")
    root.mkdir(parents=True)
    commands = Commands(root)
    project = "fft1b-" + uuid.uuid4().hex[:12]
    compose = None
    resources_started = False
    cleanup_safe = False
    report = {
        "format": "fft1b-independent-host-harness-v1", "source_commit": SHA, "source_tree": TREE,
        "physical_reproduction": "NOT_RUN", "candidate_review": "NOT_RUN",
        "public_test_ready": False, "n3_status": "OPEN", "sbx7_frozen": False,
        "real_case_effectiveness": "NOT_DEMONSTRATED", "live_provider": "NOT_RUN",
        "human_independent_review": "NOT_CLAIMED", "host_independence": "OPERATOR_DECLARED_NOT_VERIFIED",
        "host_note": args.host_note, "host_platform": platform.platform(),
        "host_python": platform.python_version(), "project": project,
        "manual_interventions": ["operator supplied host and invoked harness"],
        "source_input": "git" if args.repo is not None else "verified-source-bundle",
        "cleanup": "NOT_RUN", "full_ci_rerun": "NOT_VERIFIED_BY_HARNESS; bind exact source SHA to CI separately during intake",
    }
    try:
        require(sys.version_info >= (3, 10), "host Python >=3.10 required")
        if args.repo is not None:
            require(shutil.which("git") is not None, "git command unavailable")
        require(shutil.which("docker") is not None, "Docker command unavailable; physical run NOT_RUN")
        commands.run(["docker", "version"])
        commands.run(["docker", "info", "--format", "{{.OSType}} {{.Architecture}} {{.ServerVersion}}"])
        commands.run(["docker", "compose", "version"])
        source = root / "source"
        if args.repo is not None:
            commands.run(["git", "--version"])
            export_source(args.repo.resolve(), source, commands)
        else:
            from source_bundle import export_bundle
            export_bundle(args.source_bundle.resolve(), source)
        save(root / "compose.override.json", {"services": {
            "trial-runner": {"command": ["full-function-trial", "/trial/fft1b-1"]}}})
        compose = ["docker", "compose", "--project-directory", str(source),
                   "-p", project, "-f", str(source / "docker-compose.trial.yml"),
                   "-f", str(root / "compose.override.json")]
        config = json.loads(commands.run(compose + ["config", "--format", "json"]).stdout)
        runner = config["services"]["trial-runner"]
        require(runner["command"][0] == "full-function-trial", "default SBX5 must not execute")
        require(runner["read_only"] is True and "ALL" in runner["cap_drop"], "isolation drift")
        require(config["networks"]["trial-internal"]["internal"] is True, "network not internal")
        require(not any(s.get("ports") or s.get("privileged") for s in config["services"].values()),
                "unexpected exposed ports/privilege")
        commands.run(compose + ["build", "--pull", "trial-runner"])
        resources_started = True
        commands.run(compose + ["up", "-d", "--wait", "trial-postgres"])
        identity = json.loads(commands.run(compose + ["run", "--rm", "--no-deps", "-T",
            "--entrypoint", "python", "trial-runner", "-c", IDENTITY]).stdout)
        require(identity["build_commit"] == SHA and "/site-packages/" in identity["module_file"],
                "wrong installed wheel identity")
        save(root / "installed-identity.json", identity)
        commands.run(compose + ["images", "--format", "json"])
        commands.run(["docker", "image", "inspect", "postgres:16", "--format",
                      "{{.Id}} {{json .RepoDigests}} {{.Os}} {{.Architecture}}"])
        results = []
        invocation_windows = []
        for run in (1, 2):
            name = project + f"-run-{run}"
            invoked_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            proc = commands.run(compose + ["run", "--no-deps", "-T", "--name", name,
                "trial-runner", "full-function-trial", f"/trial/fft1b-{run}"], check=False)
            invocation_windows.append([invoked_at, datetime.datetime.now(datetime.timezone.utc).isoformat()])
            commands.run(["docker", "inspect", "--format",
                "{{.Image}} {{.Config.User}} {{.State.ExitCode}}", name])
            # Even on failure attempt export; do not destroy unexported volume evidence.
            copied = commands.run(["docker", "cp", f"{name}:/trial/fft1b-{run}",
                                   str(root / f"run-{run}")], check=False)
            require(proc.returncode == 0 and copied.returncode == 0,
                    "trial/export failed; resources retained for diagnosis")
            results.append(verify_directory(root / f"run-{run}"))
            commands.run(compose + ["run", "--rm", "--no-deps", "-T", "--entrypoint", "python",
                "trial-runner", "-c", PRODUCTION_READBACK.replace("fft1b-RUN", f"fft1b-{run}")])
            commands.run(["docker", "rm", name])
        changed = differences(results[0], results[1])
        evidence_changed = differences(
            json.loads((root / "run-1/evidence_manifest.json").read_text()),
            json.loads((root / "run-2/evidence_manifest.json").read_text()))
        save(root / "repeat-comparison.json", {"result_differences": changed,
             "evidence_hash_differences": evidence_changed, "ignored_fields": [],
             "normalization": "NONE; all differences require explanation/review"})
        bounded = compare_directories(root / "run-1", root / "run-2", invocation_windows)
        save(root / "bounded-repeat-comparison.json", bounded)
        report["repeatability"] = {
            "raw_byte_identical": not changed and not evidence_changed,
            "bounded_equivalence_accepted": bounded["accepted"],
            "policy_sha256": bounded["policy_sha256"],
        }
        report["physical_reproduction"] = (
            "TWO_RUNS_VERIFIED_AWAITING_REVIEW" if not changed and not evidence_changed
            else "TWO_RUNS_BOUNDED_EQUIVALENCE_AWAITING_REVIEW" if bounded["accepted"]
            else "TWO_RUNS_EXECUTED_DIFFERENCES_REQUIRE_REVIEW")
        cleanup_safe = True
    except (Exception, KeyboardInterrupt) as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["physical_reproduction"] = "BLOCKED_OR_FAILED_NOT_ACCEPTED"
    finally:
        if resources_started and compose:
            try:
                commands.run(compose + ["logs", "--no-color"], check=False)
            except Exception as exc:
                report["logs_error"] = str(exc)
            if cleanup_safe:
                try:
                    commands.run(compose + ["down", "--volumes", "--remove-orphans"])
                    for kind in ("container", "network", "volume"):
                        remaining = commands.run(["docker", kind, "ls", "-q", "--filter",
                            "label=com.docker.compose.project=" + project]).stdout.strip()
                        require(not remaining, "owned " + kind + " remains")
                    report["cleanup"] = "OWNED_CONTAINERS_NETWORKS_VOLUMES_ABSENT"
                except Exception as exc:
                    report["cleanup"] = "FAILED: " + str(exc)
            else:
                report["cleanup"] = "RETAINED_FOR_DIAGNOSIS; export/readback did not fully pass"
                report["manual_cleanup_after_evidence_review"] = compose + ["down", "--volumes", "--remove-orphans"]
        report["retained_local_material"] = "output evidence, exact source export; Docker image/build cache may remain"
        save(root / "host-report.json", report)
        artifact = package_evidence(root)
        print(f"Report: {root / 'host-report.json'}\nEvidence: {artifact}")
    return 0 if (report["physical_reproduction"] in {"TWO_RUNS_VERIFIED_AWAITING_REVIEW",
                    "TWO_RUNS_BOUNDED_EQUIVALENCE_AWAITING_REVIEW"}
                 and report["cleanup"] == "OWNED_CONTAINERS_NETWORKS_VOLUMES_ABSENT") else 2


if __name__ == "__main__":
    sys.exit(main())
