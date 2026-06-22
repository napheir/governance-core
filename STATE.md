# STATE — governance-core

Session-bridge log. `/wrap-up` Step 1 prepends a dated entry under
"Updates in This Session"; `tools/rotate_state.py` archives entries older
than 7 days to `STATE_ARCHIVE.md`; `session-context.py` surfaces recent
entries at SessionStart.

This file is committed (authored governance record). Adopted by P-0068
Phase 3c — single-agent governance-core still needs a session-state bridge,
so the STATE.md capability is provided by the package (the installer seeds
an initial copy; `rotate_state.py` ships in `tools/`).

## 1. Updates in This Session

<!-- Newest entry on top. Format:
### YYYY-MM-DD — <short title>
- 改动摘要 / 涉及文件 / 关键决策 / 测试结果
-->

### 2026-06-22 — P-0108 实现：把 Plan-mode 工程 rigor 嫁接到 proposal 管线（gc #104，发布 0.35.0）

- **来源**：trade-agent consumer 以 plain issue **#104**（P-0118）报"pipeline 在治理
  轴是 plan-mode 超集、工程 rigor 轴是子集"。策展判定：issue 正文 + **2 条评论**，
  评论 2（`444f837a`）把 G1 从软 WARN 演进到 **level-D 硬门** —— 按 gc #26 precedent
  采纳"corrected kernel"，用户确认 level-D 强度。
- **三 graft 落 `governance_core/` 包源**：
  - **G2**：`_v2_scaffold` 增 `## Current State (read, not assumed)` +
    `## Alternatives & Rationale` 两段（11 段）。
  - **G3**：`proposal_lib.reconcile()` + `_extract_scope_file_tokens` /
    `_loose_file_match` / `_commit_changed_files` + `reconcile` CLI 子命令（as-built
    覆盖差，advisory）；`commands/proposal.md` complete 加 step-0 reconcile。
  - **G1 level-D**：`current_state_adequacy()` form-only 谓词 → `transition --to
    approved` 硬 BLOCK + `--allow-empty-current-state` 豁免；`audit_proposals.py`
    **Check 13**（WARN-only）复用同一谓词，grandfather pre-cutover（2026-06-22）+
    archive/legacy/draft 豁免。
  - 研究范式 5 维（2 always-form + 3 conditional-substance）落
    `proposal-drafting-checklist.md`（`parse_checklist` 格式）。
- **关键决策**：form-vs-substance split —— 机器只验"有没有"（段在/非占位/≥1 file:line），
  人审"够不够"，拒了 LLM-judge 门。audit WARN 与 transition BLOCK 共用谓词永不打架。
- **测试**：新 `test_proposal_rigor.py` 17 项；全量 **91 pytest + 21 脚本式 = 0 失败**；
  CLI 烟测 reconcile + 门 BLOCK/override 通过；`audit_proposals` 0/43 failures 0 warnings
  （135 旧提案 0 new FAIL）；wheel 隔离 top-level 纯 `governance_core*`、无 maintainer 泄漏、
  新符号确实入包。dogfood：P-0108 本身以目标态起草（带两个新段）。

### 2026-06-18 — P-0106 实现：retire 死掉的 Hermes auto-refine 路径（gc #103，发布 0.34.0）

- **来源**：trade-agent consumer 以 plain issue **#103** 报 dead-code（P-0117）。
  批准前按要求做了全簇调用图核查：`record_step` 全仓库零 producer →
  `steps_taken` 恒空 → `diff_and_refine` 恒 None → wrap-up Step 4b `--auto-refine`
  恒 no-op（且 `--name/--steps` required，wrap-up 那条命令其实会 argparse 报错退出）。
  确认 hooks/tests/`__init__` 导出均无引用、`extract_skill` 等 live 路径独立。
- **关键决策**：用户问「是否该修使其生效而非删」。读下游后判定整链 naive（≥50%
  词袋判定、append-only 写、格式脆弱），即便接 producer 也会往 skill 文档写噪声。
  → 选 **retire 现有 naive 实现 + 另起 v2 设计 proposal P-0107**（LLM 反思 @
  wrap-up + `/update-skill` 门控），初衷被保留而非丢弃。
- **改动（6 文件）**：`discovery/extractor.py` 删 `diff_and_refine`/`refine_skill`/
  `_extract_workflow_steps`/`_find_novel_steps`/`--auto-refine` CLI；
  `discovery/tracker.py` 删 `record_step`/`steps_taken_this_session`/
  `record_refinement` + `steps_taken` 字段管线（含 `session_complexity` 恒 0 的项、
  get_stats 字段/print）；`commands/wrap-up.md` 删 Step 4b 并 renumber 4c→4b/4d→4c +
  清单去「Skill 已精炼」；`commands/extract-skill.md` 删 `refine_skill()` 指针；
  `commands/update-skill.md` 改 stale 理由（保留 learned/*.json 不触发规则）。
  保留 live：`extract_skill` + A/B/C 漏斗（`record_use/surfaced/triggered`）。
- **范围克制**：`weighted_scores` 的 `refinement_count` 项保留（live 评分，P-0107 Q5
  再议是否重接）；不碰 A/B/C 漏斗。
- **测试**：新增 `governance_core/tools/test_auto_refine_retired.py`（6 例:死符号
  消失/CLI 拒 --auto-refine/extract_skill 仍工作/complexity 恒等于 tasks+files//5+2
  无 steps 项/get_stats 无 steps_taken_today）；`test_skill_funnel` 12/12 回归绿。
- **验证**：0.33.0→**0.34.0**；pytest 66 passed（8 个既有源布局 false-fail 经 tools/
  确认 21 passed）；包源零残留引用 + 模块干净导入；upgrade+doctor exit 0（安装层
  wrap-up 无 auto-refine）；wheel 隔离（top-level 仅 `governance_core*`、maintainer
  未泄漏、改动文件齐全）。ledger 记 promoted（采纳 option a）。

### 2026-06-18 — P-0105 实现：Check 16 (16a) 豁免 slash command 覆盖 FAIL（gc #102，发布 0.33.0）

- **来源**：消费者 trade-agent 的 gc 能力 candidate，以 **plain issue #102**（无
  `candidate` label、无 envelope）提交 —— `candidate.py review` 扫不到（命中记忆
  candidate-review-misses-unlabeled-issues：查 `gh issue list` 捞 unlabeled）。
  经 `/curate-candidate` 评估为可促进通用精简，走 `/proposal`。follow-on of
  #101 / P-0104（同一 16a FAIL/WARN 面，additive）。
- **改动**：`audit_knowledge.py` `_audit_scenario_coverage` 加 `command_skills`
  集，16a 循环在 #101 non-hub/learned WARN 分支**之前** `continue` 跳过
  `source_type==command` —— 两 carve-out **可组合**（非替换）。理由：slash command
  始终在 harness Skill-tool 菜单按名可调，可发现性不依赖 SessionStart cluster
  surfacing（P-0113 缺口只针对 consult-only learned/guide）。guide/learned 仍受
  覆盖；16b phantom 不动。
- **范围决策**：**不**扩张到 Check 11（`_audit_skill_tiers`）—— 它有 `unclassified`
  兜底桶（11c 仅 WARN），command 可入桶不 FAIL；Check 16 无此兜底才过度 FAIL，
  故 candidate 精确只 scope 16，超范围会越出已批 proposal。
- **测试**：新增 `governance_core/tools/test_command_coverage_exempt.py`（4 例：
  command 豁免 / 非 hub learned 仍 WARN / guide 仍 FAIL / 16b phantom 不变）。
- **验证**：0.32.0→**0.33.0**；新+回归 13 passed（4 新 + 9 旧）；8 个源布局
  false-fail 经 `tools/` 路径确认通过（记忆 gc-test-suite-run-from-autonomy-layer）；
  upgrade + doctor exit 0；wheel 隔离（top-level 仅 `governance_core*` + dist-info、
  maintainer 未泄漏、新文件齐全）。
- **收尾**：commit `9875ebf`（Implements: P-0105 / Closes #102）；ledger 记 promoted
  （`maintainer/consumer_registry.json`，按记忆 curate-promote-clobbers... 用
  `registry.record_candidate` 直记而非 promote）；gc #102 已评论 + 关闭。

### 2026-06-17 — P-0104 实现：extract-skill business-path + audit Check 11/16 非 hub pending 容忍（gc #101，发布 0.32.0）

- **来源**：消费者 trade-agent 提的 gc 能力请求 issue #101（**非**结构化 candidate
  envelope，故 `candidate.py review` 扫不到 —— 走 /proposal 当能力新增，而非
  candidate promote）。follow-on of #100 / P-0103。
- **Part B（代码）**：`config.py` 加 hub 判定原语 —— `HUB_CONSUMER_ID` 常量 +
  `GovernanceConfig.consumer_id` 字段 + `is_hub` 属性 + `is_non_hub_clone()`
  （default-strict：config 缺失 / 无 consumer_id / hub 一律 strict，membership
  test 无 `.get` 兜底）。`audit_knowledge.py` Check 11a + 16a 对非 hub clone 的
  `source_type==learned` 且 registry-only skill 记 WARN（pending hub catalog）
  而非 FAIL；Check 11 registry 对齐 `project_root=root`（与 Check 16 一致、可隔离
  测试）。hub 行为不变。
- **Part A（skill）**：`commands/extract-skill.md` 加非 hub 分支（建 skill 文件 +
  入自有 `_scenario_clusters.json`，跳过 hub-owned 步骤 6/7/8；audit WARN 不回滚），
  hub 路径原样保留。
- **测试**：新增 `governance_core/tools/test_pending_catalog_tolerance.py`（6 例：
  hub / 非 hub / 缺 config / learned-only narrowness × Check 11a + 16a）。
- **验证**：版本 0.31.0→**0.32.0**；upgrade + doctor exit 0；全测 64 pytest + 21
  script = **85 passed**；wheel 隔离（top-level 仅 `governance_core*` + dist-info，
  maintainer 未泄漏，4 改动文件齐全）。
- **Non-goal**：hub-side cataloging sweep 归消费者 trade-agent **P-0114 WS-1**。
- 实现 commit：本阶段 feat（Implements: P-0104）；关 #101；complete + archive P-0104。

### 2026-06-16 — P-0103 Phase 5 发布 0.31.0（close learned-skill loop A/B/C/D 全数上线）

- **Phase 5**：bump 0.30.0 → **0.31.0**，发布 P-0103 全部四部分（A discover /
  B consult 第十五条 / C coverage gate / D funnel）到 PyPI；关 #100；
  complete + archive P-0103。
- 闭环回顾：A（`emit_bounded_injection` 有界注入）+ B（宪法第十五条 技能咨询
  纪律）+ C（audit Check 16 scenario coverage + extract-skill Step 6b）+ D
  （live `record_surfaced` + `--funnel`）。gc ship 机制（schema + reader + clause
  + gate），scenario 数据由各消费者自著（桥接设计）。
- 实现 commit：1045b6c（A+D）/ b9088f3（B 宪法）/ d5e8943（C gate）。

### 2026-06-16 — P-0103 Phase 4（C register-enforce）scenario coverage gate（未发布）

- **C（register-enforce）**：闭"作者忘了登记"的复发缺口。
  - `extract-skill.md` 加 **Step 6b "Surface the skill"**：tier 分类不够，skill
    只在进入 SessionStart surface 时才被咨询；须 universal tier 或某 scenario
    cluster 成员（引第十五条 + schema 文档）。Step 8 audit note 加 Check 16。
  - `audit_knowledge.py` 加 **Check 16 scenario-surface coverage**：每 md-skill
    必须 universal **或** ∈ ≥1 cluster，否则 FAIL（永不被 surface）；cluster
    phantom 成员 FAIL。**gate 在 `_scenario_clusters.json` 存在时**（opt-in：未采用
    scenario 的项目不受罚），与 Check 11 gating 同构。
- **修正**：`_audit_scenario_coverage` 用 `SkillRegistry(project_root=root)`
  （比 Check 11 的无-root 版更正确、且 `--root`/测试可隔离）。
- 涉及：`governance_core/tools/audit_knowledge.py`（Check 16 + 函数 + docstring）
  + `commands/extract-skill.md`（Step 6b + Step 8 note）+ 新
  `tools/test_scenario_coverage_audit.py`（3 例 fixture）。
- 验证：scenario 3/3 + pytest 58 + key script 6/6；upgrade manifest 152→154。
  **预存问题（非本改动）**：hub 全 `audit_knowledge.py` 在缺 `knowledge/INDEX.md`
  时崩（hub 的 knowledge/ 稀疏、不在常规测试套件里；待后续单独修）。未 bump 版本。
- **剩余 P-0103**：Phase 5（bump 0.31.0 + 发布 + 关 #100 + complete/archive）。

### 2026-06-16 — P-0103 Phase 3（B consult）新增宪法 第十五条 技能咨询纪律（未发布）

- **B（consult）**：经 `/iterate-constitution` 新增 **第十五条：技能咨询纪律** ——
  任务开始前必须先咨询 SessionStart 注入的 universal skills / scenario clusters，
  命中场景时**加载相关 skill/cluster 而非重新推导**。闭合 discover→**consult**→
  apply 的中段（A discover 已在 Phase 1 落地）。
- **载体**（用户选"走宪法"）：`constitution/total.md` 加第十五条（填 art_15 空槽，
  位于 14 wrap-up 与 16 memory 间）+ 新 clause 源
  `governance_core/clauses/art_15_skill_consultation_discipline.md`（**域中立**，
  下发所有消费者；未泄 gc 内部 proposal id）。
- 验证：regen CLAUDE.md 第十五条就位（247 行 / 13150 chars << 上限）；
  audit_sub_constitutions OK（无子宪法改动）；check_constitution_change clean；
  upgrade 渲染 `.governance/clauses` 10→11（art_15 生成）。classify gate 已记录
  （constitution/total.md 高敏路径，经 P-0103 治理）。
- **剩余 P-0103**：Phase 4（C extract-skill scenario 分类 + bijection gate）、
  Phase 5（dogfood + 发布 + 关 #100）。

### 2026-06-15 — P-0100 收编 candidate #96 proposal_suggest（泛化 kernel）+ 0.28.0

- **curate #96**（trade-agent `mechanism` 候选）→ 包源，泛化 kernel 收编：
  - 新 `governance_core/tools/proposal_suggest.py`：`/proposal classify` 只读建议
    助手，三路纯关键词召回（① 类似 proposal、② 起草检查项、③ likely scope）。
    **机制逐字保留**，仅 **瘦身 `_DOMAIN_ALIASES`**：删 trade 域词（信号/回测/
    交易/下单/风控…）只留域中立结构别名（宪法/契约/钩子/工具/审计/测试）。
  - 新 `governance_core/tools/test_proposal_suggest.py`：12 例；③ alias 用例改用
    保留别名（工具→tools）维持覆盖，fixture 去 trade 词中性化。
  - 新 `governance_core/knowledge_governance/proposal-drafting-checklist.md`：补
    candidate **缺失的 ② 数据源 seed**（`source_paths` 漏带、但其集成测试断言其
    存在）。通用治理起草经验 seed（4 条，域中立），消费者自维护其条目。
  - `governance_core/commands/proposal.md` classify 节加只读指针。
- **关键判断**：candidate 唯一实质缺陷是 ② 数据源文件没随载荷上传 → 补**通用
  seed** 同时满足"测试要求文件在"+"消费者自维护内容"，矛盾消解（非放宽测试）。
  `pyproject` glob 已覆盖二新文件，无需改 package-data。③ 在单 agent hub 退化为
  `（无）`（Art.12，非缺陷，对多 clone 消费者仍 live）。
- **记账**：`registry.record_candidate` 记 promoted（**不**用 `candidate.py promote`
  —— 会拿原始 payload 覆盖泛化改动，沿用 P-0098 教训）。
- 验证：pytest 44 green；proposal_suggest 12/12；proposal_classify×3 + import-audit
  全绿；upgrade + doctor exit 0；烟测三节渲染（① live / ② 命中 seed / ③ 无）；
  wheel 顶层仅 `governance_core*`、含 3 新文件、无 `maintainer/` 泄漏。版本
  0.27.0 → **0.28.0**。关 #96。
