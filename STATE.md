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

### 2026-06-12 — P-0099 修 consumer bug #90 sweep 重复 uplink + #91 sync_infra 删 tracked hook + 0.27.0

- **#90 `candidate.py sweep` 重复 uplink**（即 #87/#89 的成因）：
  - **RC1** `cmd_sweep` 抽出纯函数 `_dedup_pending_by_digest`，uplink 循环前按
    digest 去重 `pending`（pre-scan ledger 快照下两个同 digest envelope 都过
    `is_uplinked` → 都 uplink → 重复 issue）。
  - **RC2** `collect.py collect_netnew_skills`：已存在同 digest envelope 时跳过
    新建（`skill_digest` vs 现存 `payload_digest`；延迟 import ledger 避循环）。
    改后 collect 对未变 skill 幂等，变更 skill（新 digest）仍 stage 为 update。
- **#91 `sync_infra._remove_local_copy` 删 git-tracked 集中化 hook**：加
  `_is_git_tracked`（`git ls-files --error-unmatch`，任何失败 fail-safe→False）；
  tracked 的本地副本改为 `[KEEP]` 保留（settings 已指向 core 绝对路径、永不执行），
  只删 untracked orphan（迁移本意）。settings 引用重写半边不动。
- 测试：`test_candidate_sweep` +6（2 RC1 纯函数 + 4 RC2 collect 幂等/edited）；
  新 `test_sync_infra_remove_local_copy.py` 4 例（tracked keep / orphan del /
  dry-run / 非 repo fail-safe）。
- 验证：pytest 32（28+4）green；24 个脚本式测试全绿（command-guard 42/42 等
  无回归）；upgrade + doctor exit 0；wheel 顶层仅 `governance_core*`、含改动、
  无 `maintainer/` 泄漏。版本 0.26.0 → **0.27.0**。关 #90/#91。

### 2026-06-12 — P-0098 收编 gc #89 skill competing-design-proposals-with-deferred-adr（去域化）+ 0.26.0

- **curate #89**（trade-agent 候选 skill）→ 包源
  `governance_core/skills/competing-design-proposals-with-deferred-adr.md`：
  - frontmatter 重塑 learned→guide（`theme: universal` / `type: guide`；
    name/description/tags 保留；updated 06-12），H1 标题化 + 加 provenance 注。
  - **de-trade-ify**：唯一域泄漏 Note 行（"不可比红线/单流基线回归 delta=0"）
    泛化为通用基线回归守卫；机制/workflow 逐字保留。
- **#87 duplicate**：与 #89 payload 逐字相同（仅 candidate id 日期后缀 0611 vs
  0612 不同）。关 #87 指向 #89，**不**进 rejected_registry —— 内容实为 promoted，
  否则会给 trade-agent 发错 reject 信号。
- **关键坑**：hand-genericize 后**不能**用 `candidate.py promote`（它对 skill kind
  会把**原始** payload 拷回覆盖我去域化后的文件）；改直接调
  `registry.record_candidate` 记 promoted（同一库函数，Art.8 同路径）。
- **清理**：删 `.governance/candidate-outbox/` 两个死快照（command-guard
  `# P-0065 Phase 4 drift probe` 探针残留 + auth-guard pre-P-0082 旧快照；
  gitignored，live 自治层已无漂移、无需 promote）。
- 验证：28 pytest green；discovery 收录新 guide；upgrade + doctor exit 0；
  wheel 顶层仅 `governance_core*`、含新 skill、无 `maintainer/` 泄漏。
  版本 0.25.0 → **0.26.0**。
