# Human-COS FFT-1 · Public Mock Trial

作者：子君赋；出品：文明跃迁研究组。

A publicly runnable, fixed Mock S5→S8 narrow trial intended for reproducibility testing. This snapshot includes source files matching the project-maintained inventory, a Docker runner, evidence verification tools and Apache-2.0 documentation.

**Test question:** Can you reproduce the fixed Mock S5→S8 narrow trial, and find a case where it reports success incorrectly?

Test installation, the fixed mock pipeline, rejection checks, evidence verification and cleanup. This is **not** a complete Human-COS implementation, real-world decision authority, live-model validation, or evidence of effectiveness in real deployments. It does not validate the project's broader theory or every safety boundary.

A failure, false-positive success, reproducibility problem, unclear boundary or missing test case is more useful than a successful run. [Report a sanitized finding](https://github.com/Civilization-Leap/human-cos-fft1-trial/issues/new?template=trial_feedback.yml); do not upload raw evidence or credentials. The run command is directly below.

**首次测试：[中文快速上手](QUICKSTART_ZH.md) · [提交测试反馈](https://github.com/Civilization-Leap/human-cos-fft1-trial/issues/new?template=trial_feedback.yml)**

测试邀请 / Call for testing: [中文](TEST_INVITATION_ZH.md) · [English](TEST_INVITATION_EN.md)。包含可直接转发的简短版本 / Includes short versions for sharing.

AI / agent 可直接使用 [公开制品测试任务书](AGENT_TEST_TASK.md)，并按 [机器可读结果格式](agent_test_result.schema.json) 报告权限、协助程度、实际执行状态与发现。该流程本身不证明组织独立性。

## 下载与运行 / Download and run

Download [FFT1-distribution.zip](FFT1-distribution.zip), verify [SHA256SUMS](SHA256SUMS), and extract into a new directory. Requires Python 3.10+, Docker with Compose v2, and network access to download images/dependencies. No Git, private repository access or model API keys required.

```sh
python3 run_trial.py --output ../FFT1-run-01 --host-note 'actual host and interventions'
```

Use a nonexistent output directory on a trusted dedicated Docker host. Operator guides: [中文](tools/README_ZH.md) · [English](tools/README_EN.md). They describe evidence, results and cleanup. A clone of this public repository also supports the same launcher command from its root.

## 本次公开范围 / Scope

The fixed Mock chain exercises S5-CDE, S6-WCI, S7-SCS narrow and S8-EVAL narrow, then stops at ADVERSARIAL_REVIEW. The project's AI-operated harness checks 12 authorized transitions, 7 rejection probes, PostgreSQL persistence/readback, evidence and cleanup.

The historical preview.1 had project-operated Docker runs, but public review found verifier false-positive paths. Preview.2 hardens those checks and has passed local unit, archive-integrity and mutation tests plus a project-controlled clean-host Docker/Compose run and evidence intake. This is **not independent external validation**. No real-model or real-case effectiveness claim is made. See the sanitized [validation record](VALIDATION.md).

N-3 and two same-UID output-directory acquisition races remain OPEN. Do not run with a concurrent output mutator. Live provider NOT_RUN; REAL_CASE_EFFECTIVENESS NOT_DEMONSTRATED. No Final Synthesis, Final Claim, Controller D, Human Seal, Publication Authority, Reality Execution, S8 FULL or S9+ authority is enabled. Support boundaries do not add license restrictions.

The public Issues record includes the review findings that motivated preview.2. Treat this preview as testable and falsifiable, not independently validated.

## Verification boundaries (preview.2 clarification)

The detached verifier checks internal consistency, not provenance. It cannot by itself distinguish real execution evidence from an internally consistent fabricated evidence set, or prove that rejection probes actually ran. Matching hashes and seven matching probe records are not execution attestation. The official flow relies on the pinned runtime executing on a trusted dedicated host.

- **Layer 1 — `verify_directory`:** checks hashes, cross-file bindings, ordered transitions and reported probe fields. Its table gate requires an 11-table subset; a consistent superset can pass.
- **Layer 2 — `compare_directories`:** requires the exact 26-table inventory in the repeatability policy and compares both runs under that policy. It reconstructs the S8 terminal hash from its three artifact hashes. It does not explicitly reconstruct S5/S6/S7 terminal hashes from authoritative stage preimages; those terminals receive cross-file consistency and pairwise comparison checks, including graph normalization where resolvable.
- **Layer 3 — official runner:** runs both checks and performs production readback inside the container. That readback covers the container-side copy; the exported host copy is checked separately by the detached tools. These are different coverage scopes.

The pairwise comparator is not an external authenticity anchor. Identical coordinated changes to both runs are not generally detectable by comparison alone, although per-run invariants still reject some such changes (including an extra table). Neither standalone verifier should be used to authenticate an untrusted third party's claimed execution.

A project-controlled review and local rerun of synthetic fixtures confirmed Layer 1 acceptance of internally consistent fabricated evidence and Layer 2 inventory rejection. These fixtures did not complete the full Layer 2 semantic comparison or the official Docker flow. No end-to-end false positive within the published trusted-host model was established by this review; this is not independent physical reproduction.

This is a documentation clarification. The fixed Mock S5→S8 narrow scope, preview.2 release ZIP, checksum and runtime behavior are unchanged.

## Source and integrity (preview.2)

The candidate distribution ZIP SHA-256 is:

`0efde6884170bbd881a119b6e90b19225959c01693b01d44afc609b930110310`

This hash identifies the exact preview.2 distribution that passed the project-controlled Docker run and evidence intake. It does not establish independent reproduction or public-trial validation. The historical preview.1 release remains available for audit, with its verifier findings retained in Issues.

- Pinned public source snapshot: `ca93213174544f2ce5c3f862564a6cd5a3f0386f`.
- Pinned runtime subtree: `a19c96d76072a1bbf7e94bba03b372cb963c3593`.
- [runtime/](runtime/) exposes the same 140 selected files as `runtime-source.zip` for browsing. The launcher always uses the verified bundled ZIP.
- [PACKAGE_SHA256.json](PACKAGE_SHA256.json) covers the candidate distribution members, not additional repository presentation files.
- [Source inventory](tools/source_inventory.json) pins the selected public runtime blobs. An in-package hash manifest is not a publisher signature.

No original private Git history, raw host evidence, model credentials, dependency wheels or container images are included.

## 反馈 / Feedback

Use this repository's Issues for a sanitized summary: package SHA, operating system, Python/Docker/Compose versions, expected versus observed outcome, and a minimal reproducer. Do not upload raw evidence ZIPs, credentials, private paths, host identifiers or real-case material to public issues. Preserve raw evidence locally; redact a separate copy if excerpts are needed. Nothing is uploaded automatically.

## License

Original inventoried code, tools and supporting docs: [Apache-2.0](LICENSE), with [NOTICE](NOTICE) and [scope](LICENSE_SCOPE.md). Third-party dependencies retain their own terms.
