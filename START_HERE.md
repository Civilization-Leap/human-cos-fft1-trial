# Human-COS FFT-1 Apache-2.0 release candidate

Not yet publicly released. Original project source, tools and documentation in
this package are licensed under Apache-2.0. See LICENSE, NOTICE and LICENSE_SCOPE.md.
Third-party terms are unchanged. Supported behavior is the fixed Mock S5-S8 narrow
chain on a trusted dedicated Docker host. Support limits are not extra license terms.

Extract into a new directory. Requires Python 3.10+, Docker and Compose v2, and
network access for container/dependency downloads. Git and repository login are
not required. No model keys or real-case material are needed.

    python3 run_trial.py --output ../FFT1-run-01 --host-note 'actual host and interventions'

Use a nonexistent output directory. See tools/README_ZH.md for results and cleanup.
Keep raw evidence unchanged and share it privately, not in a public issue: it may
contain host paths and descriptions. No upload happens automatically.
Two same-UID directory acquisition races and N-3 remain OPEN; do not run with a
concurrent output mutator. Live provider NOT_RUN; real-case effectiveness NOT_DEMONSTRATED.

Only selected runtime blobs from the pinned public candidate snapshot are included;
no private Git history or old private evidence is present. This preview.2 candidate
hardens result semantics and evidence binding relative to preview.1. The inventory does
not reconstruct the complete public repository. Obtain the outer archive hash through a
trusted publisher channel: an in-archive manifest is not a signature.
