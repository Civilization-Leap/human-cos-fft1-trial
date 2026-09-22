# Human-COS FFT-1：首次公开测试

本说明采用 Apache-2.0。作者：子君赋；出品：文明跃迁研究组。

这次测试回答的是：固定合成案例能否完整通过既定分析链，并真实拒绝越界请求、保存可核验结果、完成清理。它不回答真实模型分析质量或现实案例有效性。

## 0. 先选最低成本入口

没有现成的专用 Docker 主机，不必为本测试租主机或购买模型 API。可先做一次最多15分钟的[只读测试](AGENT_TEST_TASK.md#low-cost-first-contribution)：只核对一个公开声明与对应源码，提交一个具体差异或未解决问题，标记 `REVIEW_ONLY`。若仅能看到任务文本，就注明“仅任务文本预审”；未取得源码不能写成代码审查。已有合适主机，再按下文实际运行。

反馈中可如实写“未下载／未独立校验哈希”，提供实际读过的文件链接或提交版本。不要为了填表猜测版本、退出码或成功状态。

项目固定参照是“利他为先的利己”；参数、算法、过程逻辑和具体手段可修正，效率、测试通过和系统存续不能取代其服务的目的。这是设计原则，不是有效性结论。当前角色分析均来自预写Mock，公开入口不能运行自定义案例；持续因果记忆及其对下一轮目的生成的作用仍未在本preview中检验。

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
| 两轮结果 | 各 12 条有序转换、7 项负路径／边界探针，停在 `ADVERSARIAL_REVIEW` |

七项探针包括五项 `BLOCK`／`REJECTED`／`DENIED` 结果、一项 `OPEN` 能力缺口和一项 `AUTHORIZATION_REQUIRED` 权限边界。

`AWAITING_REVIEW` 不等于失败：它表示程序已经完成自身核验，但不冒充外部独立审查。原始字节可能因时间戳不同而变化；通过的是已限定策略下的语义重复性，不是逐字节确定性。`public_test_ready: false` 等原始包装字段不应手工改成 true；发布授权与人工/AI证据判定是分开的记录。

遇到非零退出码、拒绝、清理失败或报告缺失，均报告实际结果，不标为通过。失败时先保留证据；如报告提供本次 Compose project 的清理命令，再据此清理。不要执行全局 `docker system prune`，也不要删除其它项目资源。成功清理不包含镜像、构建缓存及宿主输出目录。

## 4.1 验证器能证明什么

**独立验证器检查证据内部一致性，不能单独证明证据来自真实运行，也不能证明负路径／边界探针实际执行过。** 自洽的虚构证据可以通过第一层检查。哈希匹配和七行边界探针记录均不等于执行真实性证明；官方流程还依赖固定运行时在可信专用主机上实际执行。

| 检查层 | 覆盖范围与限制 |
| --- | --- |
| 第一层 `verify_directory` | 核对哈希、跨文件绑定、有序转换及探针记录字段；表清单要求包含 11 张必需表，允许自洽的超集。 |
| 第二层 `compare_directories` | 要求策略列出的恰好 26 张表，并比较两轮有限等价性；从三个 S8 制品哈希重构 S8 终态。没有对 S5/S6/S7 终态实施同样的显式阶段原像重构，相关检查依赖跨文件一致性、成对比较及可解析时的图归一化。 |
| 第三层官方流程 | 执行上述检查及容器内生产回读。回读覆盖容器侧副本，导出的主机副本由独立工具另行检查，两者覆盖对象不同。 |

成对比较没有外部真实性锚点，不能普遍识别两轮同时遭受相同改写；各轮自身约束仍能拒绝部分此类改写，例如增加额外表。不要把单独验证器通过当作第三方运行证据的真实性认证。

项目方受控复核已在合成夹具上确认第一层接受自洽虚构证据、第二层拒绝错误表清单；未用这些夹具完成完整第二层语义比较或第三层 Docker 流程。本轮未确立公开可信主机模型内的端到端误报，也不新增独立物理复现。详见 [英文验证边界说明](README.md#verification-boundaries-preview2-clarification)。

本节只补充说明；preview.2 分发 ZIP、哈希、运行行为及 fixed Mock S5→S8 narrow 范围不变。

## 5. 提交最小反馈

使用 [测试反馈表单](https://github.com/Civilization-Leap/human-cos-fft1-trial/issues/new?template=trial_feedback.yml)。成功、失败和未能启动都可以提交，并注明实际执行者是人、AI还是协作。

仅需提供版本、系统及工具版本、退出码、脱敏后的状态字段、预期与实际结果。不要附上原始 `FFT1B-evidence.zip`、完整日志、密钥、私有路径、主机标识或现实案例资料。保留原件，只在独立副本上脱敏。当前没有自动上传或私密证据接收端点；涉及敏感问题先只说明需要私密渠道，不公开漏洞利用细节。

已知限制继续公开保留：N-3 与两项同 UID 目录获取竞态 OPEN；真实模型 NOT_RUN；现实案例有效性 NOT_DEMONSTRATED。完整边界见 [包内中文说明](tools/README_ZH.md)。
