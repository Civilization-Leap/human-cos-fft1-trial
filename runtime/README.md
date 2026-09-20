# Human-COS FFT-1 narrow trial

A reproducible **fixed Mock S5 → S6 → S7 narrow → S8 narrow** engineering trial.
It uses existing runtime modules and stops at `ADVERSARIAL_REVIEW`.

## Run the distribution

Extract the release candidate ZIP into a new directory on a trusted dedicated
Docker host, then run:

```bash
python3 run_trial.py --output ../FFT1-run-01 --host-note 'actual host and interventions'
```

The launcher is at the outer distribution root, not inside runtime-source.zip.
Requires Python 3.10+, Docker and Compose v2, plus network access for image and
locked dependency downloads. Git, private repository access and model keys are
not needed. The output directory must not exist. Use a new path for each attempt.

The launcher builds the pinned source, runs the chain twice, checks twelve ordered
transitions and seven rejection probes, verifies S8 persistence/readback, preserves
original evidence and removes only owned runtime resources after readback.
`FFT1B-evidence.zip` contains the resulting evidence. Exit 0 is wrapper success,
not a declaration of independent review or effectiveness on real-world cases.

## Supported scope

The supplied entry uses synthetic fixed data and Mock adapters. Provider adapters
and other runtime modules may be present in the source, but they are not validated
by this trial. No provider credentials or real-case data are needed.
No Final Synthesis, Controller D, Final Claim, Human Seal, Publication Authority,
Reality Execution, S8 FULL or S9+ is enabled by this entry.

Two same-UID directory acquisition races remain OPEN: a concurrent process can
replace an empty output directory before its identity is captured. Use trusted
host/daemon and package/output directories with no concurrent mutator. This is
not support for hostile shared hosts or public online services.
N-3 remains OPEN; SBX7 is not declared frozen; live provider is NOT_RUN;
REAL_CASE_EFFECTIVENESS=NOT_DEMONSTRATED.

Keep original evidence unchanged and share it privately: logs may include local
paths and host descriptions. On failure, preserve evidence before removing the
specific owned resources identified in host-report.json; never use global prune.
Images, build caches and local output remain for diagnosis.

## License

Original project material listed in LICENSE_SCOPE.md is licensed under Apache-2.0.
See LICENSE and NOTICE. Third-party terms remain unchanged. These statements about
support and validation do not add restrictions to the Apache license.
