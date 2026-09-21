# Human-COS FFT-1：首次公开测试

本说明采用 Apache-2.0。作者：子君赋；出品：文明跃迁研究组。

这次测试回答的是：固定合成案例能否完整通过既定分析链，并真实拒绝越界请求、保存可核验结果、完成清理。它不回答真实模型分析质量或现实案例有效性。

## 1. 准备环境

使用自己信任的专用 Linux Docker 主机。项目方受控验证环境为 Ubuntu 24.04、Python 3.12、Docker/Compose v2；这不是外部独立验证，其它系统也不应当作已经验证。最低需要 Python 3.10+、可工作的 Docker daemon、Compose v2，以及镜像与依赖下载网络。

```sh
python3 --version
docker version
docker compose version
```

`docker version` 必须能连接服务端，而不只是显示客户端。不要为运行测试关闭主机安全设置；没有 Docker 权限时请由主机管理员处理。无需模型密钥、GitHub 登录或开放入站端口。不要在有并发目录修改者的共享环境中运行。

## 2. 下载并核对

打开 [Preview 2 发布页](https://github.com/Civilization-Leap/human-cos-fft1-trial/releases/tag/v0.1.0-fft1-preview.2)，下载附件 **FFT1-distribution.zip** 和 **SHA256SUMS**。不要把 GitHub 自动生成的 Source code ZIP 当作同一文件计算哈希。

在两个附件所在目录运行：

```sh
sha256sum -c SHA256SUMS
```

应显示 `FFT1-distribution.zip: OK`。发布包的 SHA-256 为：

`0efde6884170bbd881a119b6e90b19225959c01693b01d44afc609b930110310`

不一致就停止，不要运行。解压到新的空目录，进入包含 `run_trial.py` 的目录。包内保留发布前的“候选”字样，是为了不改变已验证 ZIP；公开状态以发布页为准。

## 3. 运行两轮完整链

```sh
python3 run_trial.py --output ../FFT1-run-01 --host-note '专用测试主机；本次未修改程序'
echo $?
```

请按实际情况填写主机说明，不必提供 IP、账号或其它私人标识。程序一次调用会执行两轮，不需要手动启动两次。`FFT1-run-01` 必须事先不存在；再次测试使用新目录，例如 `FFT1-run-02`。不要覆盖旧证据。

## 4. 判断结果

检查输出目录中的 `host-report.json`：

| 检查项 | 包装验证成功时应看到 |
| --- | --- |
| 进程退出码 | `0` |
| `physical_reproduction` | `TWO_RUNS_VERIFIED_AWAITING_REVIEW` 或 `TWO_RUNS_BOUNDED_EQUIVALENCE_AWAITING_REVIEW` |
| `cleanup` | `OWNED_CONTAINERS_NETWORKS_VOLUMES_ABSENT` |
| 两轮结果 | 各 12 条有序转换、7 项拒绝探针，停在 `ADVERSARIAL_REVIEW` |

`AWAITING_REVIEW` 不等于失败：它表示程序已经完成自身核验，但不冒充外部独立审查。原始字节可能因时间戳不同而变化；通过的是已限定策略下的语义重复性，不是逐字节确定性。`public_test_ready: false` 等原始包装字段不应手工改成 true；发布授权与人工/AI证据判定是分开的记录。

遇到非零退出码、拒绝、清理失败或报告缺失，均报告实际结果，不标为通过。失败时先保留证据；如报告提供本次 Compose project 的清理命令，再据此清理。不要执行全局 `docker system prune`，也不要删除其它项目资源。成功清理不包含镜像、构建缓存及宿主输出目录。

## 5. 提交最小反馈

使用 [测试反馈表单](https://github.com/Civilization-Leap/human-cos-fft1-trial/issues/new?template=trial_feedback.yml)。成功、失败和未能启动都可以提交，并注明实际执行者是人、AI还是协作。

仅需提供版本、系统及工具版本、退出码、脱敏后的状态字段、预期与实际结果。不要附上原始 `FFT1B-evidence.zip`、完整日志、密钥、私有路径、主机标识或现实案例资料。保留原件，只在独立副本上脱敏。当前没有自动上传或私密证据接收端点；涉及敏感问题先只说明需要私密渠道，不公开漏洞利用细节。

已知限制继续公开保留：N-3 与两项同 UID 目录获取竞态 OPEN；真实模型 NOT_RUN；现实案例有效性 NOT_DEMONSTRATED。完整边界见 [包内中文说明](tools/README_ZH.md)。
