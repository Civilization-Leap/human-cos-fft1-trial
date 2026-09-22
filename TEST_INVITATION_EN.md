# Call for testing: can the evidence support the reported pass?

Author: 子君赋. Produced by Civilization Leap Research Group. This document is licensed under Apache-2.0.

Human-COS FFT-1 is now available as a public trial preview. We invite developers and researchers working on Python, Docker, AI evaluation or reproducible systems to test a concrete question: does this fixed analysis pipeline actually perform the transitions, rejections, evidence readback and cleanup that it reports?

**Lowest-cost entry:** if you do not already have a suitable Docker host, take the [15-minute read-only route](AGENT_TEST_TASK.md#low-cost-first-contribution). Compare one claim with one public source path; submit one concrete discrepancy or unresolved question as `REVIEW_ONLY`. No host rental or model API purchase is requested. A limited review with no finding is not validation.

## Pick one contribution

- **Reproduce a run.** Download the pinned release and invoke its launcher on a trusted dedicated Docker host. One invocation runs the chain twice. Success, failure and inability to start are all useful findings.
- **Challenge a reported pass.** Inspect the evidence for the exact 12 ordered transitions, 7 negative-path/boundary probes, PostgreSQL persistence/readback and cleanup. The set contains five BLOCK/REJECTED/DENIED outcomes, one OPEN capability gap and one AUTHORIZATION_REQUIRED boundary; do not describe all seven as rejections. Look for false success, missing failures or results that cannot be recomputed.
- **Find a first-use obstacle.** Report a specific problem with installation, checksum verification, launch instructions or interpretation of results, preferably with a minimal reproducer.

You do not need to read the entire project or endorse its broader theory. AI-assisted testing is welcome; identify whether the run was AI-operated, human-operated or collaborative.

## Scope and limitations

The release uses a fixed synthetic case and Mock model outputs through S5–S8 narrow, stopping at `ADVERSARIAL_REVIEW`. Engineering verification included two actual Docker executions and evidence readback: Mock describes the model-output lane, not a simulated Docker run.

This is not evidence of live-model reasoning quality, real-case effectiveness, independent human review or readiness of the full Human-COS system. N-3 and two same-UID directory-acquisition races remain OPEN. Use a trusted dedicated host without a concurrent output-directory mutator. No reality-execution or Final Synthesis authority is enabled.

## Optional national-purpose case analysis

No Docker is needed for the separate [Singapore SG-01 exercise](AGENT_TEST_TASK.md#optional-application-exercise-singapore-sg-01). It asks whether analysis can preserve national survival, development, influence and civilizational contribution while examining Singapore's changing position in an AGI-era world value structure.

Submit one bounded response in [Issue #5](https://github.com/Civilization-Leap/human-cos-fft1-trial/issues/5). AI/agent participation is welcome with disclosure. This is external case analysis, not execution of the fixed Mock runtime or evidence of method effectiveness.

## Start here

- [Pinned release and checksums](https://github.com/Civilization-Leap/human-cos-fft1-trial/releases/tag/v0.1.0-fft1-preview.2)
- [Repository and launch instructions](https://github.com/Civilization-Leap/human-cos-fft1-trial)
- [Structured feedback](https://github.com/Civilization-Leap/human-cos-fft1-trial/issues/new?template=trial_feedback.yml)

Requires Python 3.10+, Docker/Compose v2 and network access for images and dependencies. No model keys, private-repository access or inbound ports are required. Initial build time depends on the host and network.

Please submit only a sanitized summary: release/package hash, environment versions, exit code, expected versus observed behavior and minimal reproduction steps. **Do not post raw evidence ZIPs, full logs, secrets, private paths or real-case material.** Keep originals locally; there is no automatic upload or configured private evidence intake endpoint.

Original released code, tools and supporting docs use Apache-2.0; third-party terms are unchanged.

## Short version for sharing

Human-COS FFT-1 public preview seeks reproducibility and failure-reporting tests: a fixed Mock S5–S8 narrow pipeline checking 12 ordered transitions, 7 negative-path/boundary probes, PostgreSQL readback and cleanup. Python + a trusted dedicated Docker host; no model keys. Help find failed runs, false passes or onboarding obstacles. Live-model quality and real-case effectiveness are not established; known limitations remain documented. Source and instructions: https://github.com/Civilization-Leap/human-cos-fft1-trial . Sanitized feedback only—no raw evidence uploads.
