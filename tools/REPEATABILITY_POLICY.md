# FFT-1B 有界重复性规则（仅固定 Mock 候选）

适用源码：bc324b68814dddb388e3e6cebab0d31a38ef6817；不修改运行时。
依据 Issue #114 已允许的 “replay/determinism or explicitly bounded nondeterminism”。

原始结果、原始哈希、完整数据库快照、逐字差异一律保留。此前失败运行仍为失败，不修改历史结论。新规则通过时只表示有界重复性通过，仍待候选集中审查，不表示逐字确定性、外部独立审查或公开测试就绪。

## 允许变化的准确范围

1. `repeat_policy.json` 明列的数据库写入时间与运行时间字段。运行时间必须在宿主记录的单轮调用窗口内，窗口最长30分钟。案例固定时间、其它字段、文本内时间及未列入字段保持原值。
2. 所有可变时间按实际先后排名替换为比较令牌；保留完整顺序和相等关系，并输出原值/排名。执行时长差异不作为语义差异，但时钟顺序或相等关系改变会拒绝。
3. `_exercise_s8_evidence_sidecars` 明确定义基于 Evaluator 完成时间的 +1…+7 秒合成时间。逐个 artifact_id/字段验证精确偏移；锚点必须来自本次调用窗口内的已冻结 Evaluator run，偏移改变会拒绝。窗口外例外仅适用于已验证的具体 artifact_id/字段；同值出现在其它字段或同类其它产物中不能借用例外。这些是合成试验的逻辑时刻，不冒充墙上时间。
4. 数据库关系行按规范化后的完整行排序，保留数量、重复行和所有字段。原源码 `_capture_installed_evidence` 按 `to_jsonb(record)::text` 排序，哈希变化会带来行位置变化，不能按位置认定内容改变。
5. 仅 ScenarioSet.paths 和 ControllerCOutput.scenario_path_hashes 按集合比较；原契约以唯一 path ID/类型与哈希成员关系约束它们（scenario/contracts.py、scenario/resimulation.py）。其它数组保持顺序，特别是状态转换与业务序列。

## 哈希必须有可重算原文

每个转换后的哈希都必须有满足原 SHA256 的原文：完整规范 JSON，去掉已核验自哈希字段的 JSON，ContextAdmission 的 ISO 日期表达，或原始输出字节。原始输出序列化还必须符合本候选的 `json.dumps(..., sort_keys=True)` 字节格式；不能悄悄忽略空白或键顺序变化。时钟及原始字节字段类型改变直接拒绝。递归解析引用并重新计算比较哈希；发现引用环即拒绝。报告列出每个原哈希、原文位置、验证方式与比较哈希。

无原文哈希保持字面量，不能以“都是64位”配对或抹掉。七份 ContextManifest 仅在本候选空 Evidence、无 actor、无 prior-run、空 forbidden_scopes 的 Mock 前提下，按 core/context.py 的文档结构重构；完整原 SHA256 必须吻合，否则拒绝。**这不解决 N-3，也不得用于放宽一般 Domain Context 等价性。**

S8 terminal 按原实现三项 component hash 重构，必须匹配原结果。外层 result/receipt/checkpoint/manifest 原始完整性先通过旧 verifier，再校验同一引用图。不得只比较“PASS”字段。

## 证据与验证

- `repeat-comparison.json`：原始逐字差异，未忽略字段。
- `bounded-repeat-comparison.json`：规则文件哈希、调用窗口、时间排名、原文哈希证明、未解析哈希、语义差异与裁决。
- 反例包括重算哈希后的业务篡改、引用替换、未知哈希、非许可时钟、越界时钟、时间顺序/相等关系、非集合数组顺序、重复行、额外表、Context 原文不足、非空 Evidence 与引用环。
- 仅在完整链、原始证据完整性、数据库清理、此比较与专属 Docker 资源清理均通过后，包装才返回0。

这是一份 AI 编写并执行的工程校验；N-3 OPEN；REAL_CASE_EFFECTIVENESS=NOT_DEMONSTRATED；不授予任何系统权限。
