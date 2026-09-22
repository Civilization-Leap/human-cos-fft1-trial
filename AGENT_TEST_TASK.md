# Human-COS FFT-1 · Public-artifact AI/agent test task

Author: 子君赋. Produced by Civilization Leap Research Group. Licensed under Apache-2.0.

This task is for an AI system or autonomous agent starting from the public release only. The target is the **fixed Mock S5→S8 narrow FFT-1 preview**, not the complete Human-COS system.

## Project purpose: read before testing

Human-COS is intended to help make the consequences of goals and actions visible before they become irreversible: assumptions, causal links, affected parties, effects across time, dissent, alternatives and opportunities for correction. The broader research includes goals proposed by humans or AI and consequences arising from their interactions. This is a design intention, not an assertion that the current preview implements or validates all of it. In application studies, the observation is how seeing consequences affects the next action; a consequence checklist alone does not establish application benefit, and retaining an action can be justified.

The tool is not a final authority over everyone's purposes. More refusals, more conservative choices, agreement with the project, or a higher internal score do not by themselves show improvement. A useful test can reveal missing consequences, unsupported claims, false success, or no benefit. You may question the project's assumptions and this test design.

**当前测试者应理解：**项目希望在人或AI依据局部判断行动之前，让被遗漏的主体、因果后果、关键假设及纠错路径显现出来。理解这一目标不要求赞同项目，也不要求得出支持项目的结论。当前公开能力仍只有 fixed Mock S5→S8 narrow；独立的方法提示或封闭模拟不是该软件的完整应用验证。

Before execution or review, include a short account in your human-readable report of what the project seeks to improve, what this particular test can establish, and what finding would challenge its usefulness or alignment with its stated purpose. This is a check for task ambiguity, not an agreement test or an additional qualification exam. Do not add fields to the existing JSON schema for this account.

For ordinary public testing, the explanation above remains available before testing. In separate comparative application studies, treat that explanation as an intervention: compare task-only, task-plus-explanation, and task-plus-explanation-plus-method conditions. The task-only condition receives the explanation and comprehension questions after its primary outputs are frozen; a participant already exposed to this page is not a fresh task-only control. Give all conditions the same necessary environment rules and safety limits. Measure explanation effects separately from the method's incremental effect. Prioritize precommitted prediction-versus-replay errors and executed simulation outcomes; use textual coverage as secondary evidence. Fix material-effect thresholds and a round limit before execution. If the method is only a prompt, do not describe it as the runtime tool. Keep future scenario evidence and specific expected answers separate until their designated stage. Reading prescribed public instructions during the current test is part of the task; disclose earlier project involvement separately and retain the version of materials read. Do not relabel past reports or erase prior exposure. Historical release instructions may lack this clarification; the immutable release ZIP and checksum are unchanged.

## Fixed reference, revisable means

The project adopts **“利他为先的利己” — pursuing one's own benefit by giving priority to benefiting others** as its fixed guiding principle. Parameters, algorithms, process logic and intermediate goals can change in light of consequences. Efficiency, test scores, task completion and system continuation are intermediate objectives, not ultimate ends. Ask what purpose a process objective serves, whether observed consequences still support it, and how a deviation can be corrected. This is the project's normative commitment, not an empirical result or a requirement that testers agree.

For this release, the role analyses are prewritten Mock content. Running them tests processing and verification, not the tool's ability to discover new consequences. A continuous reference/causal-memory/next-purpose-generation loop is not demonstrated by this preview. No custom-case or live-model execution authority is added by these instructions. Do not request or approve an input merely to turn an execution gate green.

### 原则与缘由：利他为先的利己

**“利他为先的利己”是本项目固定的底层原则。** 在形成目的、选择方向和设计规则时，先考虑他者的真实需要、发展能力及共同存续条件，使自身的发展建立在增进这些条件之上。它不要求放弃自身利益，也不以他者依赖自己作为成功标准。

这一原则的因果缘由是：主体的长期发展包含跨时间、跨地域的关系与相互依赖。若各方持续通过削弱、控制或排除他者获益，并把他者的自保视为威胁，就可能形成“自保—威胁—反制—更强自保”的升级循环；在出路被相互封闭、目的又不允许修正的条件下，对立将失去内部化解的可能。反之，回应真实需要、增强他者能力，可以通过信任、合作、知识共享和共同韧性，支持自身持续发展。这是需要逐环检验的因果解释，不是对任何具体方案必然成功的证明。

资源、人才和知识的汇聚还可能创造新增能力，再反向、多向输出，促进多地发展，并反馈为新的创造与合作。测试不能只按一时一地的存量得失判断；也不能假定汇聚自动产生普惠输出。须检查输出的具体渠道、受益主体、成本承担、时间尺度及反向反馈。

**测试怎样使用这一参照：**
- 说明案例的应用目的，以及效率、收益、排名、规模等过程目标服务于什么。
- 追踪不同主体及未来阶段的收益、损失、能力变化与纠错空间；检查是否以损害共同发展基础换取局部成功。
- 展开“汇聚—新增能力—多向输出—多地发展—反馈”的实际或假设链条，区分来源事实、因果推断、模拟结果和未知。
- 主动寻找反例、替代解释和使结论失效的条件。只有前提与机制得到支持时，才讨论方向判断的强度；不能把固定原则当作经验结论的证明。
- 参数、算法、过程逻辑、中间目标和具体方案可依据证据修正。保持原目标同样可以合理；不能为了显示“发生改变”而强行改目的。

评分不奖励复述原则、赞同项目或使用安全措辞。测试者可以质疑该原则及其因果解释，结论允许无增益或反向结果；项目的固定设计参照与测试者的独立判断须同时保留。报告中的事实性结论必须有相应证据，不以短期互惠或回报是否立即发生衡量原则是否得到贯彻。

本节是目的说明与分析要求，不是新增运行能力或现实执行授权。当前 fixed Mock preview 只能提供其已公开的工程测试；软件外的案例推演应单列为案例分析，不能记作运行时产生的分析或现实有效性验证。比较研究继续遵循上文对说明干预、先前接触和冻结结果的规定。

### Rationale and testing implications (English)

The fixed principle is to pursue one's own benefit by giving priority to benefiting others, starting at purpose formation and rule design. Long-term development depends on relationships across actors, places and time. Repeatedly gaining by weakening or controlling others can create reinforcing threat–defence cycles; closing every corrective route while refusing to revise purposes can make such conflict internally irresolvable. Meeting real needs and strengthening others' capabilities can instead support trust, cooperation and shared resilience. Each causal link requires examination; this rationale does not prove that a particular policy will succeed.

Concentrating talent, knowledge and resources can generate new capabilities, with reciprocal and multidirectional diffusion that supports development elsewhere and feeds back into further creation. Examine mechanisms, beneficiaries, costs, time horizons and counterexamples; neither assume a zero-sum transfer nor automatic shared benefit. Distinguish facts, hypotheses, simulations and unknowns. Keep means revisable and do not let scores, efficiency, scale or system continuation replace the purpose they serve.

Agreement with the principle earns no test credit. Testers may challenge it and report no benefit or adverse outcomes. A justified unchanged goal is valid. This explanation adds no runtime capability, approval or real-world authority; external case analysis is not a result produced by the fixed Mock runtime. The comparative-study controls above still apply.

## Low-cost first contribution

Choose **one** route; do not acquire a new host or API subscription solely to participate.

- **Public text or source available, no Docker:** spend at most 15 minutes on Track C. Compare one claim with its source: custom-case support in [the launcher](run_trial.py) and [CLI](runtime/src/human_cos/trial/cli.py), or consistency versus authenticity in [the verifier](tools/verify_fft1b.py). Return one exact file/function reference and one finding or unresolved question. Report `REVIEW_ONLY`, materials actually read, earlier project exposure and no execution. If only this task text is available, label the scope “task-text review only”; do not claim code review. A time-limited “no finding” does not establish correctness.
- **A trusted dedicated Docker host is already available:** choose Track A or B and use the pinned release below. Verify the checksum before running. One launcher invocation already performs two runs; do not add repeats merely to seek a pass.
- **No public materials or execution access:** record `ENVIRONMENT_BLOCKED` for an execution attempt. State what was inaccessible and stop; do not repeatedly attempt installation in a restricted sandbox. An operator may supply public files offline, with their version/hash and that assistance disclosed.

Use the [feedback form](https://github.com/Civilization-Leap/human-cos-fft1-trial/issues/new?template=trial_feedback.yml). For a read-only report, give the source commit or exact file URL when known. State “not downloaded / checksum not independently verified” instead of claiming you measured the published distribution hash. Unknown exit codes and runtime statuses remain NOT_RUN, not zero or PASS. The full machine-readable schema remains unchanged; a short issue is sufficient for an initial finding.

## Optional application exercise: Singapore SG-01

### 新加坡：重塑世界价值结构中的位置与发展方向

**用途与范围。** 这是一项软件外的探索性案例分析，用于识别 Human-COS 方法在复杂国家战略问题上的能力与问题。它不是 Track A/B/C 的替代执行路线，不调用当前 fixed Mock preview 处理自定义案例，也不证明方法增益、现实有效性或国家认可。输出最多是提案与建议。无需 Docker、API 订阅或新增主机；一次完成后停止。

**近期战略目标。**

> 面对世界传统价值创造与分配结构的变化，新加坡如何利用现有能力与优势，重塑其在 AGI 时代世界价值结构中的位置和发展方向，为自身与世界创造更大的价值、机遇与未来？

不得把这一目的降为单项产业发展、收入增长、中心排名、投资规模或一次项目绩效。经济能力是国家生存发展的基础之一；还应分析国家影响力、问题发现与议程组织能力、可信协作能力以及文明贡献力。文明贡献力指形成能够帮助更多主体打开发展可能的知识、制度、实践或协作方式，不以他者服从、依赖或赞同新加坡为标准。

**给测试者的任务。** 理解本页“利他为先的利己”的固定参照及其缘由，但不要把它当作事实证据或预定答案。比较至少两条可行发展路径，并允许提出组合路径。分析必须从新加坡现有能力与优势及其成立条件开始，再判断当下世界格局变化和不同 AGI 情景如何削弱、强化或改变这些优势的价值。金融中心、人才中心、资源管理中心、文明高地或文明中心只能作为候选定位，不能预先当作结论。

**目的层级必须保留：**

| 层级 | 本案例要回答的问题 |
| --- | --- |
| 根本参照 | 是否通过增进他者与共同发展的条件，拓展自身长期存续、福祉、创造与文明发展的空间？ |
| 近期国家目标 | 怎样应对世界价值结构变化，重塑新加坡的位置、作用与发展方向？ |
| 战略目标 | 哪些原有优势需要延续、重组或转化？需要生成哪些新的经济、影响与文明贡献能力？ |
| 实施手段 | 金融、人才、资源、科研、治理与城市协作如何相互支撑？具体项目只能检验其中哪些环节？ |
| 观察指标 | 收入、投资、就业、排名、传播量和项目完成度说明了什么，又不能说明什么？ |

如果分析从上一层滑到下一层并用局部指标替代上层目的，须明确标记 **PURPOSE_REDUCTION_RISK**，回到上层重新判断。小规模试点可以验证因果环节，不能取代国家方向或以局部结果裁决国家未来。

**材料与事实纪律。** 本页不是新加坡国情资料库。优先核验带日期的一手资料，至少区分：

1. **当下事实：** 已观察到的政策、能力、约束、世界格局变化和现有结果。
2. **因果推断：** 从事实推到优势强化、削弱或转化的理由。
3. **AGI 情景：** 明确条件的未来假设，不得写成已经发生。
4. **价值选择：** 为什么一种未来更值得追求。
5. **未知：** 目前缺少什么证据，什么发现会改变判断。

无法联网或资料不足时，标为条件性推演。若使用历史提案，披露版本，把其中预测、目标和未经复核的数字保留为候选主张，不自动升级为事实。

**一次完成四个步骤：**

1. **冻结初始判断。** 写明国家目的、近期目标、候选路径和暂时倾向；列出至少一项会改变判断的证据条件。
2. **建立现有能力与优势基线。** 对每项优势说明其来源、依赖条件、当前强度证据、外部依赖、可替代性，以及世界变化可能带来的削弱、强化和转化。
3. **展开跨时间、多主体因果链。** 检查汇聚是否生成新增能力，这些能力怎样反向、多向输出，多地发展怎样反馈为新的创造、影响、合作与自身发展空间；同时追踪居民、合作方、未来世代的收益、成本与纠错空间。
4. **形成条件性建议。** 说明保留与修正了什么、依据是什么、哪些仍未知。保持原目标可以合理；改变行动不自动等于目的得到改善。

| 待检验环节 | 所需内容 |
| --- | --- |
| 原有能力与优势 | 为什么成立？依赖哪些世界结构？哪些仍稀缺，哪些可能被替代？ |
| 世界价值结构变化 | 价值在哪里生成、由谁分配、哪些连接与规则正在变化？ |
| 新能力生成 | 哪种汇聚与协作产生了原先不存在的能力？证据或可检验预测是什么？ |
| 多向输出与文明贡献 | 通过什么渠道帮助其他主体获得真实、可自主使用的发展能力？ |
| 影响力形成 | 是否来自可核查的贡献、可信协作与示范，还是只来自声量、地位或控制？ |
| 多地发展与反馈 | 他者变强后怎样形成新的知识、需要、合作与共同机会？ |
| 国家生存发展 | 上述变化怎样影响居民福祉、韧性、选择空间与长期作用？ |
| 失效和修正 | 哪个前提失效会改变方向？怎样避免过程目标成为终极目标？ |

**共同可见的压力问题（是假设检验，不是隐藏答案）：**

- 如果经济指标继续增长，但关键规则、问题定义与原创能力主要由外部主体决定，新加坡的未来位置是否真的更稳固？
- 如果合作方增强自主能力、对某项旧服务的依赖下降，同时共同发展空间扩大，应如何判断成功并更新下一阶段目标？
- 如果国际声望上升，却没有产生可复用的知识、协作能力或生活改善，影响力是否被高估？
- 如果人才、知识和资源汇聚产生新增能力，却缺少多向输出渠道，应如何区分建设阶段与长期封闭？
- 如果文明贡献短期压低某些收入，却显著扩大长期合作与创造空间，应依据什么比较跨期价值？
- 如果高声望的“文明中心”方案不如一个低成本分布式网络有效，应保留目的并替换哪些手段？

**交付与停止线。** 一份不超过三页的报告即可：背景与材料、初始判断、目的层级检查、能力优势基线、关键因果链、反例或失效条件、最终建议和未解决问题。标注“软件外案例分析 / EXTERNAL_CASE_ANALYSIS”，这是标题标签，不是现有 JSON schema 枚举；不要伪造程序输出。若发生目的降维，保留原回答与纠正记录。交付后停止，等待新的真实事实或外部反馈。

**如何读结果。** 主要看是否保持国家与文明尺度，是否准确识别现有优势及其依赖条件，能否区分事实、推断、情景和价值选择，能否揭示跨主体、跨地域、跨时间的反馈，并给出可反驳条件。复述原则、赞美新加坡、方案宏大、收入增长或回答改动次数均不构成通过。“高必然”只能表示：在明确且受支持的前提下，多条独立因果链持续指向某个方向；它不是概率承诺，也不能证明某项制度必然成功。

本练习不测量方法净增益。读过这些说明与压力问题的执行者不能作为未接触说明的对照组。若以后开展对照研究，应另行事前冻结条件、资料、评分和停止规则，不回写本次记录。

### English entry

SG-01 is an optional external case-analysis exercise for identifying method capabilities and failures on a complex national-strategy question. Its near-term objective is to examine how Singapore could use existing capabilities and advantages to reshape its position and direction as global value creation and allocation change in an AGI era, creating greater value and opportunity for Singapore and the wider world.

Preserve the hierarchy from the fixed principle and national survival, welfare, agency and civilizational contribution, through strategic objectives, to implementation means and indicators. Do not replace the purpose with sector growth, income, rankings, investment volume, publicity or project performance. Mark such substitution as **PURPOSE_REDUCTION_RISK** and reassess from the higher level.

Compare at least two paths or a justified combination. Begin with the sources, dependencies, evidence, substitutability and changing relevance of Singapore's existing advantages. Separate current facts, causal inferences, AGI scenarios, value choices and unknowns. Examine economic capability, influence based on credible contribution, and civilizational contribution through knowledge, institutions, practices and cooperation that expand others' capabilities. Trace concentration, new capability generation, reciprocal and multidirectional diffusion, development elsewhere, feedback and long-term national effects.

Submit one report of at most three pages and then stop. Label it EXTERNAL_CASE_ANALYSIS in prose, not in the execution schema. It is not a runtime result, method-effect estimate, proof of real-world effectiveness or national endorsement.


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
