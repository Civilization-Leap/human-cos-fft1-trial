# 公开测试邀请：让一次“通过”经得起复算

作者：子君赋；出品：文明跃迁研究组。本文采用 Apache-2.0。

一个分析系统不仅要给出结果，还应让人看见：结果经过哪些步骤，哪些请求被拒绝，证据能否回读，测试资源是否真正清理。

Human-COS FFT-1 已公开首个试运行预览版。现邀请熟悉 Python、Docker、AI 评估或可复现工程的开发者与研究者，帮助检验这些具体承诺。

## 我们邀请你做什么

选择一项即可，不需要通读全部项目：

1. **复现运行**：下载固定版本，在可信专用 Docker 主机运行一次启动命令。程序会执行两轮，检查完整链、负路径／边界探针、证据与清理。报告成功、失败或无法启动，均有价值。
2. **核验证据**：检查报告是否支持“通过”的结论，尤其是精确的 12 条有序转换、7 项负路径／边界探针、持久化回读与清理状态。找出误报成功、遗漏失败或不可复算之处。

七项探针中，五项以 `BLOCK`／`REJECTED`／`DENIED` 收束，另有一项 `OPEN` 能力缺口和一项 `AUTHORIZATION_REQUIRED` 权限边界；不得把七项全部表述为拒绝。
3. **改善可用性**：指出安装、下载校验、首次运行或结果说明中真正阻碍使用的地方，并给出最小复现。

## 现在能测试什么，不能证明什么

本版使用固定合成案例和 Mock 输出，串联 S5→S8 narrow，并停在 `ADVERSARIAL_REVIEW`。已完成的工程验证包括两次真实 Docker 运行与证据回读；**Mock 指模型输出，不是模拟 Docker 运行。**

它尚不证明真实模型的分析质量、现实案例有效性或完整 Human-COS 已就绪。AI 参与实现与核验，不冒充外部独立人工审查。欢迎 AI 辅助测试，只需如实注明执行方式。

N-3 和两项同 UID 目录获取竞态仍为 OPEN。请使用可信专用主机，不与可能并发修改输出目录的进程共享测试环境。不开放现实执行、Final Synthesis 或其它未授权能力。

## 可选：国家应用目的案例分析

不具备 Docker 环境，也可参与独立的[新加坡 SG-01 应用目的测试](AGENT_TEST_TASK.md#optional-application-exercise-singapore-sg-01)。该测试观察分析能否保持国家生存发展、影响力与文明贡献尺度，并识别把目的降维成收入、排名、声量或项目绩效的问题。

AI／Agent 可以参与，但须披露模型、控制者、既往项目接触、资料来源与人工介入。请在 [Issue #5](https://github.com/Civilization-Leap/human-cos-fft1-trial/issues/5) 提交一次不超过三页的分析。它属于软件外案例分析，不计作 fixed Mock 运行或方法有效性证据。

## 参与入口

- [下载固定预览版与校验值](https://github.com/Civilization-Leap/human-cos-fft1-trial/releases/tag/v0.1.0-fft1-preview.2)
- [中文快速上手](https://github.com/Civilization-Leap/human-cos-fft1-trial/blob/main/QUICKSTART_ZH.md)
- [提交测试反馈](https://github.com/Civilization-Leap/human-cos-fft1-trial/issues/new?template=trial_feedback.yml)

需要 Python 3.10+、Docker/Compose v2 和依赖下载网络；无需模型密钥、私有仓库权限或开放入站端口。首次构建耗时取决于网络和主机，不承诺固定完成时间。

反馈只提交脱敏摘要：版本与包哈希、环境版本、退出码、预期与实际差异、最小复现。**不要公开原始证据 ZIP、完整日志、密钥、私人路径或现实案例资料。** 原件留在本地；当前没有自动上传或私密证据接收端点。

原创发布内容采用 Apache-2.0，第三方条款保持不变。无需先认同项目的全部理论；一个能被复现的问题，就是有效贡献。

## 简短转发版

Human-COS FFT-1 首个公开预览版邀请测试：固定 Mock S5→S8 narrow 链，验证 12 条有序转换、7 项负路径／边界探针、PostgreSQL 回读与清理。需要 Python 和可信专用 Docker 主机，无需模型密钥。欢迎报告运行失败、误报成功或上手障碍；不宣称真实模型或现实案例有效性，已知限制公开保留。源码及入口：https://github.com/Civilization-Leap/human-cos-fft1-trial 。请只提交脱敏反馈，不上传原始证据包。
