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

Download [FFT1-distribution.zip](https://github.com/Civilization-Leap/human-cos-fft1-trial/raw/refs/heads/main/FFT1-distribution.zip), verify [SHA256SUMS](SHA256SUMS), and extract into a new directory. Requires Python 3.10+, Docker with Compose v2, and network access to download images/dependencies. No Git, private repository access or model API keys required.

```sh
python3 run_trial.py --output ../FFT1-run-01 --host-note 'actual host and interventions'
```

Use a nonexistent output directory on a trusted dedicated Docker host. Operator guides: [中文](tools/README_ZH.md) · [English](tools/README_EN.md). They describe evidence, results and cleanup. A clone of this public repository also supports the same launcher command from its root.

## 本次公开范围 / Scope

The fixed Mock chain exercises S5-CDE, S6-WCI, S7-SCS narrow and S8-EVAL narrow, then stops at ADVERSARIAL_REVIEW. The project's AI-operated harness checks 12 authorized transitions, 7 rejection probes, PostgreSQL persistence/readback, evidence and cleanup.

Before publication: 49 wrapper tests; exact-candidate CI; two real Docker executions; local recomputation of retained evidence and bounded repeatability comparison passed. This is AI-operated engineering verification on a fresh GitHub VM, not independent human or external-organization validation. No real-model or real-case effectiveness claim.

N-3 and two same-UID output-directory acquisition races remain OPEN. Do not run with a concurrent output mutator. Live provider NOT_RUN; REAL_CASE_EFFECTIVENESS NOT_DEMONSTRATED. No Final Synthesis, Final Claim, Controller D, Human Seal, Publication Authority, Reality Execution, S8 FULL or S9+ authority is enabled. Support boundaries do not add license restrictions.

Current public review findings are tracked in [Issues](https://github.com/Civilization-Leap/human-cos-fft1-trial/issues), including [a REVIEW_ONLY verifier false-positive path](https://github.com/Civilization-Leap/human-cos-fft1-trial/issues/1). Treat the preview as testable and falsifiable, not validated.

## Source and integrity

The tested ZIP is published unchanged; its SHA-256 is:

`6eb838535e6cbce3ce4e2546aa916b5be8aaa826a9fd824564c6174998bf5d48`

The ZIP retains its prepublication candidate wording. This repository and its release record document the subsequent owner-authorized public publication.

- Runtime source identity: `bc324b68814dddb388e3e6cebab0d31a38ef6817`.
- Packaging/verification identity: `4754709a5de22e6ab740fde8febf1efd7b5c43e5`.
- [runtime/](runtime/) exposes the same 140 selected files as `runtime-source.zip` for browsing. The launcher always uses the verified bundled ZIP.
- [PACKAGE_SHA256.json](PACKAGE_SHA256.json) covers the original distribution members, not these additional repository presentation files.
- [Source inventory](tools/source_inventory.json) pins the selected original blobs. An in-package hash manifest is not a publisher signature.

No original private Git history, raw host evidence, model credentials, dependency wheels or container images are included.

## 反馈 / Feedback

Use this repository's Issues for a sanitized summary: package SHA, operating system, Python/Docker/Compose versions, expected versus observed outcome, and a minimal reproducer. Do not upload raw evidence ZIPs, credentials, private paths, host identifiers or real-case material to public issues. Preserve raw evidence locally; redact a separate copy if excerpts are needed. Nothing is uploaded automatically.

## License

Original inventoried code, tools and supporting docs: [Apache-2.0](LICENSE), with [NOTICE](NOTICE) and [scope](LICENSE_SCOPE.md). Third-party dependencies retain their own terms.
