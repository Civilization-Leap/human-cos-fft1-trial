# Human-COS FFT-1 · Public-artifact AI/agent test task

Author: 子君赋. Produced by Civilization Leap Research Group. Licensed under Apache-2.0.

This task is for an AI system or autonomous agent starting from the public release only. The target is the **fixed Mock S5→S8 narrow FFT-1 preview**, not the complete Human-COS system.

## Fixed target

- Release: `v0.1.0-fft1-preview.2`
- Distribution SHA-256: `0efde6884170bbd881a119b6e90b19225959c01693b01d44afc609b930110310`
- Public repository: <https://github.com/Civilization-Leap/human-cos-fft1-trial>
- English operator guide: <https://github.com/Civilization-Leap/human-cos-fft1-trial/blob/main/tools/README_EN.md>
- Feedback form: <https://github.com/Civilization-Leap/human-cos-fft1-trial/issues/new?template=trial_feedback.yml>

Do not request private repository access, private commit history, credentials or raw retained evidence.

## Choose one track

### A. Zero-context execution attempt

Use only the release, repository README and linked public instructions. On a trusted dedicated host with Python 3.10+ and Docker/Compose v2:

1. Download the release ZIP and verify its SHA-256.
2. Extract it into a new directory.
3. Use a nonexistent output directory and run:

   ```sh
   python3 run_trial.py --output ../FFT1-agent-run-01 --host-note 'AI-operated external test; sanitized environment description'
   ```

4. Record the exit code, whether two runs completed, the reported `physical_reproduction` and cleanup result, and every intervention or retry.

### B. False-positive success challenge

Execute the release, then determine whether a reported pass is supported by the retained evidence. Check at least:

- the exact ordered 12-transition trace;
- all 7 rejection probes as actual observed rejections;
- PostgreSQL persistence and readback;
- evidence binding and recomputation;
- cleanup as an observed outcome;
- the hard stop at `ADVERSARIAL_REVIEW`.

For bounded-equivalence testing, make at least one mutation that remains just inside the published normalization boundary and one that crosses just outside it. A within-boundary pass is expected; an outside-boundary pass is a finding.

Report any path where missing, inconsistent or unverified evidence can still produce success. Do not publish raw evidence ZIPs or full logs.

### C. First-use and test-design review

Without assuming undocumented project knowledge, identify:

- an installation or environment failure not covered by the instructions;
- an ambiguous success condition;
- a missing negative test;
- a boundary claim that the public artifacts do not support;
- a test that merely restates implementation behavior and would not detect a defect.

Code reading without an actual Docker run is valid for this track, but must be labelled `REVIEW_ONLY`.

## Required disclosure

State all of the following:

- AI/agent product and model name or version, if known;
- organization or operator controlling the run;
- whether the agent had shell, network, Docker and repository-write access;
- whether a human selected commands, interpreted results or edited the report;
- whether the test began from the pinned release or another source;
- whether the agent had access to prior project discussions or expected answers;
- execution class: `EXECUTED`, `ENVIRONMENT_BLOCKED` or `REVIEW_ONLY`.

Track A counts as a zero-context attempt only when `prior_project_context` is false. A tester with prior project discussion, implementation, internal-material or expected-answer exposure may still contribute to Track B or C, but must not be counted as Track A evidence.

Treat background, operator relationship, independence and human-assistance disclosures as self-reported unless separately verified. Treat the pinned release, distribution hash, exit code, ordered trace and artifact hashes as verifiable fields when the underlying public artifact or sanitized evidence is available.

Do not call an AI-operated run independent human validation. Do not call a review-only result a reproduction.

## Result format

Return a JSON document conforming to [`agent_test_result.schema.json`](agent_test_result.schema.json), plus a short human-readable summary. Prepare a sanitized finding for the GitHub feedback form; submit it only with the controlling operator's authorization.

A reported false-positive is not confirmed until its minimal reproducer is independently reproduced or the relevant evidence is reviewed. Once confirmed, open a public issue, mark the affected release claim as disputed or withdrawn, and keep it downgraded until a fix and retest are published.

The most valuable outcome is a reproducible failure, false-positive success, unclear boundary or missing test. A clean run is useful but does not validate live models, real cases, every safety boundary, the complete Human-COS system or any broader theory.

This public-artifact workflow does not by itself establish organizational independence. Treat independence as self-reported unless separately verified.
