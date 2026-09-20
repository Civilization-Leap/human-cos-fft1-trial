# Human-COS FFT-1 限定试运行

本分发候选包含固定 Mock S5→S6→S7 narrow→S8 narrow 链。项目原创内容依 Apache-2.0 授权，见包根目录 LICENSE、NOTICE 和 LICENSE_SCOPE.md；第三方条款不变。发布候选尚不等于已经公开上线。

## 运行

在可信专用 Docker 主机上解压，在包根目录执行：

```bash
python3 run_trial.py --output ../FFT1-run-01 --host-note '实际主机来源、独立性及手动操作'
```

需要 Python 3.10+、Docker/Compose v2 和镜像/依赖下载网络。无需 Git、私有仓库登录、模型密钥、入站端口或远程密码。输出目录必须不存在；重跑使用新目录。不要修改原始证据。

来源提交与 tree 在 tools/source_inventory.json 中；build identity 来自该固定源码身份，所有打包原始文件逐一校验。包内哈希不能认证被整体替换的包，应通过可信发布渠道核对外层 ZIP SHA-256。

## 结果与反馈

两轮运行验证精确12条有序转换、七个真实拒绝探针、S8 narrow 持久化/回读、原始证据及有界重复性，最后停在 ADVERSARIAL_REVIEW。

退出码0代表包装核验完成，不能单凭此宣称独立评审、现实有效性或公共在线服务就绪。输出中的 host-report.json 记录实际状态，FFT1B-evidence.zip 保留证据。不会自动上传反馈。

反馈请提供：包SHA-256、主机来源、退出码、首个失败命令、手动修改/重试情况及证据ZIP哈希。原始证据可能含主机路径和描述，应通过双方确认的私密渠道交付；公开问题只报告不敏感摘要。当前包不配置自动收集端点。

若失败，先保留/导出证据，再依报告的精确 Compose project 清理命令处理本次资源；不要全局 prune。成功清理仅指所属容器、网络、卷及迁移对象，镜像/构建缓存及宿主输出会保留。

## 支持范围与已知问题

只验证固定合成案例的 Mock 链；源码中存在的真实模型适配器与其它入口不继承本次结论。无 Final Synthesis、Controller D、Final Claim、Human Seal、Publication Authority、Reality Execution、S8 FULL 或 S9+。

两项同UID空目录获取竞态仍OPEN：其它进程可能在创建目录后、身份获取前替换目录。主机/daemon及源码/输出目录必须可信，无并发篡改者；此包不支持恶意共享主机，也不是在线服务。

N-3 OPEN；SBX7未声明冻结；live provider NOT_RUN；REAL_CASE_EFFECTIVENESS NOT_DEMONSTRATED。AI参与实现和核验，不冒充独立人工审查。上述是实现及支持边界，不是 Apache-2.0 的附加用途限制。
