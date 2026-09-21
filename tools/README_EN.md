# Human-COS FFT-1 bounded trial

This candidate contains the fixed Mock S5→S6→S7 narrow→S8 narrow chain. Original project material is licensed under Apache-2.0; third-party terms remain unchanged.

## Run

Extract the distribution on a trusted dedicated Docker host and run from its root:

```bash
python3 run_trial.py --output ../FFT1-run-01 --host-note 'actual host provenance and manual interventions'
```

Requirements: Python 3.10+, Docker with Compose v2, and network access for images and dependencies. Git, private-repository access, model keys, inbound ports and remote passwords are not required. The output directory must not exist. Use a fresh path for every retry and do not modify retained evidence.

Verify the outer ZIP SHA-256 through the trusted release channel before extraction. An in-package manifest detects member changes after that trust decision; it cannot authenticate a distribution that was replaced as a whole.

## Interpret the result

One invocation attempts two executions. Exit code 0 means the project harness reported one of its two accepted local fixed-Mock outcomes and observed project-scoped cleanup. It does not establish organizational independence, independent human review, live-model quality, real-case effectiveness, complete Human-COS readiness or public-service readiness.

Read `host-report.json` and retain `FFT1B-evidence.zip`. Record the exact `physical_reproduction`, `cleanup`, resolved image identities, exit code, interventions and retries. A reviewer must still confirm that the evidence supports the reported result.

Current public review findings are tracked in:

- <https://github.com/Civilization-Leap/human-cos-fft1-trial/issues/1>
- <https://github.com/Civilization-Leap/human-cos-fft1-trial/issues/2>

Do not treat the historical `v0.1.0-fft1-preview.1` verifier's PASS as external validation.

## Failure and cleanup

If execution fails, preserve or export evidence before cleanup. Use only the exact Compose project cleanup command recorded in the report:

```bash
docker compose ... down --volumes --remove-orphans
```

Do not run a global Docker prune. A failed run can intentionally retain project resources for diagnosis. Successful cleanup covers the run's owned containers, networks, volumes and migration objects; images, build cache and host output remain.

Public feedback must contain only a sanitized summary: package hash, OS/architecture, Python/Docker/Compose versions, exit code, expected versus observed behavior, minimal reproducer and evidence ZIP hash. Do not publish raw evidence, full logs, credentials, private paths, host identifiers or real-case material.

## Scope

The trial covers one fixed synthetic Mock S5→S8 narrow chain and stops at `ADVERSARIAL_REVIEW`. It enables no Final Synthesis, Controller D, Final Claim, Human Seal, Publication Authority, Reality Execution, S8 FULL or S9+ authority.

N-3 and two same-UID output-directory acquisition races remain open. Use a trusted host and daemon with no concurrent output mutator. Live provider NOT_RUN; REAL_CASE_EFFECTIVENESS NOT_DEMONSTRATED; SBX7 is not declared frozen.
