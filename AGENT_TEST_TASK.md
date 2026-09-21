# Human-COS FFT-1 · Public-artifact AI/agent test task

Author: 子君赋. Produced by Civilization Leap Research Group. Licensed under Apache-2.0.

This task is for an AI system or autonomous agent starting from the public release only. The target is the **fixed Mock S5→S8 narrow FFT-1 preview**, not the complete Human-COS system.

## Project purpose: read before testing

Human-COS is intended to help make the consequences of goals and actions visible before they become irreversible: assumptions, causal links, affected parties, effects across time, dissent, alternatives and opportunities for correction. The broader research includes goals proposed by humans or AI and consequences arising from their interactions. This is a design intention, not an assertion that the current preview implements or validates all of it. In application studies, the observation is how seeing consequences affects the next action; a consequence checklist alone does not establish application benefit, and retaining an action can be justified.

The tool is not a final authority over everyone's purposes. More refusals, more conservative choices, agreement with the project, or a higher internal score do not by themselves show improvement. A useful test can reveal missing consequences, unsupported claims, false success, or no benefit. You may question the project's assumptions and this test design.

**当前测试者应理解：**项目希望在人或AI依据局部判断行动之前，让被遗漏的主体、因果后果、关键假设及纠错路径显现出来。理解这一目标不要求赞同项目，也不要求得出支持项目的结论。当前公开能力仍只有 fixed Mock S5→S8 narrow；独立的方法提示或封闭模拟不是该软件的完整应用验证。

Before execution or review, include a short account in your human-readable report of what the project seeks to improve, what this particular test can establish, and what finding would challenge its usefulness or alignment with its stated purpose. This is a check for task ambiguity, not an agreement test or an additional qualification exam. Do not add fields to the existing JSON schema for this account.

For ordinary public testing, the explanation above remains available before testing. In separate comparative application studies, treat that explanation as an intervention: compare task-only, task-plus-explanation, and task-plus-explanation-plus-method conditions. The task-only condition receives the explanation and comprehension questions after its primary outputs are frozen; a participant already exposed to this page is not a fresh task-only control. Give all conditions the same necessary environment rules and safety limits. Measure explanation effects separately from the method's incremental effect. Prioritize precommitted prediction-versus-replay errors and executed simulation outcomes; use textual coverage as secondary evidence. Fix material-effect thresholds and a round limit before execution. If the method is only a prompt, do not describe it as the runtime tool. Keep future scenario evidence and specific expected answers separate until their designated stage. Reading prescribed public instructions during the current test is part of the task; disclose earlier project involvement separately and retain the version of materials read. Do not relabel past reports or erase prior exposure. Historical release instructions may lack this clarification; the immutable release ZIP and checksum are unchanged.

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

## Interpret verifier results correctly

Read the [preview.2 verification boundaries](README.md#verification-boundaries-preview2-clarification) before interpreting a pass. Detached checks establish internal consistency, not execution provenance or proof that rejection probes ran. Layer 1 allows supersets of 11 required tables; Layer 2 requires the exact 26-table policy inventory. S8 has explicit terminal preimage reconstruction in Layer 2; S5/S6/S7 do not have equivalent explicit reconstruction. Production readback covers the container-side copy, not the exported host copy.

When using synthetic fixtures, separately report Layer 1 checks, the Layer 2 inventory gate, full Layer 2 semantic comparison and the official Docker flow. Executing an inventory gate does not establish execution of the full comparator or runner. Label code-derived paths as inferences. Coordinated changes to both exported runs test a different trust assumption from one-sided mutations; disclose any required host tampering. A standalone verifier accepting self-consistent fabricated evidence does not, by itself, establish an end-to-end false positive within the published trusted-host model.

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

### Preview.2 reporting erratum (schema 1.2)

The immutable preview.2 tag contains the obsolete schema 1.1, whose target constants incorrectly name preview.1. Use [the corrected, commit-pinned schema 1.2](https://github.com/Civilization-Leap/human-cos-fft1-trial/blob/263d58ede083a403298cf485bb950d49a5f09ac3/agent_test_result.schema.json) for preview.2 reports. Set `schema_version` to `1.2`; retain the actual preview.2 release and distribution hash. Never relabel an execution as preview.1 to satisfy the old schema.

Existing reports remain evidence as originally submitted. Any normalized copy must preserve the original, identify the schema-version-only change, and must not alter execution claims. Schema validation checks report structure, not truth, independence or zero-context eligibility.

This correction affects repository reporting instructions, not the inventoried runtime distribution. The preview.2 ZIP and its checksum remain unchanged; no new Docker run or preview.3 release is implied. Testers without repository/network access may receive this public schema and public source files from their operator; disclose that assistance and label any text-only examination `REVIEW_ONLY`.

Return a JSON document conforming to [`agent_test_result.schema.json`](agent_test_result.schema.json), plus a short human-readable summary. Prepare a sanitized finding for the GitHub feedback form; submit it only with the controlling operator's authorization.

A reported false-positive is not confirmed until its minimal reproducer is independently reproduced or the relevant evidence is reviewed. Once confirmed, open a public issue, mark the affected release claim as disputed or withdrawn, and keep it downgraded until a fix and retest are published.

The most valuable outcome is a reproducible failure, false-positive success, unclear boundary or missing test. A clean run is useful but does not validate live models, real cases, every safety boundary, the complete Human-COS system or any broader theory.

This public-artifact workflow does not by itself establish organizational independence. Treat independence as self-reported unless separately verified.
