---
id: P-0113
agent: core
status: implemented
created: 2026-06-24
approved_at: 2026-06-24
implemented_in: e25932d
implemented_at: 2026-06-24
owner: core
---

# Proposal P-0113: De-trade upstream domain residue in governance knowledge bodies (P-0086 follow-up sweep)

## Trigger

修 P-0112 的悬空 `related:` 引用时，用户要求"另起一个 cleanup，全部解决掉这些问题"
—— 即 gc 包 governance knowledge 正文里残留的、指向**不存在目标**的上游（trade）域
引用。改的是发给所有消费者的包源 knowledge（Art.11.1 单一权威源），跨 8 文件、且
"保留教学举例 vs 删除死链"是政策抉择 → 走 proposal。本提案是 **P-0086/P-0079
去 trade 化先例的后续 sweep**（同族）。

## Current State (read, not assumed)

机械全量 grep（`knowledge/[a-z_-]+/...\.(md|py|html)`）+ 子 agent 逐处取上下文，
对照 gc 包真实结构核实：

- gc 包真实 knowledge 结构：`knowledge/governance/`（17 文件）、`knowledge/design/`
  （仅 component-catalog / design-principles）、`knowledge/methodology` 与
  `knowledge/operations` **空**；**不存在** `knowledge/{models,decisions,domain,
  datasets,research}/`（`installer.py:96-98` 只映射 governance/methodology/operations）。
  core 操作手册在 `docs/core-manual.md`（**不**在 `knowledge/operations/`）。
- 死引用（指向不存在目标）实测 ~17 处跨 8 文件，分两类：
  - **死 cross-ref / 边界表行**（断言某 gc 文档存在但其实没有）：
    `data-flow.md`（artifacts-layout.md:64、knowledge-html-profile.md:412、
    knowledge-carrier-classes.md:76、data-analysis-discipline.md:63）、
    `_constitution_inline_audit_2026-05-07.md`（sub-constitution-red-lines.md:122、
    test-production-unification.md:82）、`decisions/adr-session-boundary-guard.md`
    （scope-enforcement-mechanism.md:145）、`decisions/adr-classify-fast-path.md`
    （proposal-classify-fast-path.md:187）。
  - **教学举例 token**（用 trade 域文件名举例某 carrier-class / 机制）：
    `knowledge-carrier-classes.md` §2/§3/§7 + :62/:76/:77/:88/:93/:102/:126/:225
    （s30/s50_current、strangle_mechanics、dense_o2、evaluation_metrics、
    experiment_protocol、trade ADR 名等）、`knowledge-html-profile.md`:413/:421
    （models/build_dashboard.py owner=rules、domain/harness_defense.html）、
    `sub-constitution-red-lines.md`:97（operations/data-manual.md，在 ```markdown 围栏
    合规示例内）、`agent-least-privilege.md`:74/77（`trade`/`unlock_trade` 角色举例）。
- **先例 P-0086/P-0079**（已读归档）确立政策：**泛化举例（不删），机制/契约逐字保留，
  删死 cross-ref，patch 级、仅改源、保留 provenance**。P-0086 明确**保留**了真实 gc
  内容（harness_defense 概念、owner=core）与 §9 candidate-origin 的 "trade-agent"
  出处归属（那是准确 provenance，非域举例）。
- `core-manual` 是**真实 gc 文档但路径错**（carrier-classes.md:88 写
  `knowledge/operations/core-manual.md`，实际 `docs/core-manual.md`）→ FIX-PATH 而非删。
- provenance 类 `proposals/<name>.md` 根级指针（~10 处）技术上也悬空（根级 proposals
  无 .md、全在 `_archive/`），但属**迁移/提取出处**，先例明确保留 → 本 sweep **不碰**。

## Scope

仅 `governance_core/knowledge_governance/` 下 8 个 .md（包源），按下方 disposition 表
逐处 REMOVE / FIX-PATH / GENERICIZE；**机制/契约/规则文字逐字保留**，只改死链与举例
token。涉及文件：`artifacts-layout.md`、`knowledge-html-profile.md`、
`sub-constitution-red-lines.md`、`test-production-unification.md`、
`knowledge-carrier-classes.md`（最重）、`scope-enforcement-mechanism.md`、
`proposal-classify-fast-path.md`、`agent-least-privilege.md`。改动文件 bump `updated`。
**无契约变更、无机制变更、无代码变更**；不碰 provenance `proposals/...` 指针。

## Design & Contract

> Proportionate. Trivial change: one line "implementation self-evident; no interface
> or data-flow change." Otherwise fill all three sub-parts; use "N/A — <reason>" for
> any that genuinely doesn't apply — never leave a placeholder.

### Interfaces, I/O & Realization

无接口 / I/O / 代码变更 —— 纯 knowledge 正文内容编辑（static markdown）。realizer：
人工 Edit 包源 .md + `governance-core upgrade` 把改后内容刷到自治层 `knowledge/`。
disposition 表（每行一处死引用）：

| # | 文件:行 → 目标 | role | disposition | 改法 |
|---|---|---|---|---|
| 1 | artifacts-layout.md:64 → data-flow.md | 死 cross-ref | REMOVE | 删该 "See also" bullet |
| 2 | knowledge-html-profile.md:412 → data-flow.md | 边界表行 | REMOVE | 删表行 |
| 3 | knowledge-html-profile.md:413 → models/build_dashboard.py(rules) | 举例 | GENERICIZE | 去路径+`rules`，改"某 consumer 的 generated dashboard 脚本" |
| 4 | knowledge-html-profile.md:421 → domain/harness_defense.html | 举例(owner=core,先例保留概念) | FIX-PATH | `domain/` 不存在 → 重指 `knowledge/governance/harness_defense.html`，保留 reference/Mermaid/owner=core |
| 5 | sub-constitution-red-lines.md:97 → operations/data-manual.md | 围栏内合规示例 | GENERICIZE | 改 `docs/core-manual.md` + `governance-core upgrade`；"data-agent"→"某 consumer agent" |
| 6 | sub-constitution-red-lines.md:122 → _constitution_inline_audit_*.md | 死 cross-ref | REMOVE | 删 bullet |
| 7 | test-production-unification.md:82 → _constitution_inline_audit_*.md | 死 cross-ref | REMOVE | 删 bullet（:82-83） |
| 8 | knowledge-carrier-classes.md:62 → decisions/adr-001-w120-window.md 等 | 举例(decision-record 类) | GENERICIZE | 换中性/gc ADR 名 |
| 9 | carrier-classes.md:76 → domain/strangle_mechanics.md | 举例(reference 类) | GENERICIZE | 换真实 gc reference 文档名 |
| 10 | carrier-classes.md:76 → governance/data-flow.md | 举例 | GENERICIZE | 换真实 gc reference 文档名 |
| 11 | carrier-classes.md:77 → methodology/evaluation_metrics.md | 举例 | GENERICIZE | 换中性占位或删第三例 |
| 12 | carrier-classes.md:88 → operations/core-manual.md | 真文档错路径 | FIX-PATH | `docs/core-manual.md`；旁 trade manual 名泛化 |
| 13 | carrier-classes.md:93 → methodology/experiment_protocol.md | 举例 | GENERICIZE | 去括号路径，留概念 |
| 14 | carrier-classes.md:102 → datasets/dense_o2_*.md | 举例 | GENERICIZE | `<dataset>_<date>.md` 占位 |
| 15 | carrier-classes.md:126 → models/s30_current/s50_current.md | 举例(current-state 类) | GENERICIZE | `<model>_current.md` 占位 |
| 16 | carrier-classes.md §2/§3/§7 taxonomy 表 (E1/E2/E3/E8) | spec 路径列/目录归属表 | GENERICIZE | 见 Open Questions（§3「现存」表需 approver 裁定） |
| 17 | scope-enforcement-mechanism.md:145 → decisions/adr-session-boundary-guard.md | 死 cross-ref | REMOVE | 删 bullet |
| 18 | proposal-classify-fast-path.md:187 → decisions/adr-classify-fast-path.md | 计划态死路径 | GENERICIZE | "写 retro"去 `decisions/` 路径 |
| 19 | agent-least-privilege.md:74/77 → `trade`/`unlock_trade` 举例 | 多 agent 举例 | GENERICIZE | 换中性 `<role>` + 通用 denied token |

### Field Dictionary

N/A — 纯 static markdown 内容编辑，无跨边界字段、无持久化新字段。治理 knowledge
结构的 `contracts/knowledge_frontmatter_schema.md`、`knowledge_index_schema.md` **不变**。

| field | type | meaning | producer | consumer | constraints / allowed values |
|-------|------|---------|----------|----------|------------------------------|
| (无) | — | — | — | — | — |

### Flow

包源 `knowledge_governance/*.md`（去 trade 化编辑）→ `governance-core upgrade` →
自治层 `knowledge/governance/` 安装产物 → `audit_knowledge.py` 自审（related 仍 0 失败）
+ grep gate 零命中 trade token → 随 patch 发布给消费者。

## Non-Goals

- **不改机制 / 契约 / 代码**：carrier-class 定义、规则、syntax 逐字保留；只改死链 +
  举例 token（P-0086/P-0079 同款边界）。
- **不碰 provenance `proposals/<name>.md` 指针**（~10 处）：属迁移/提取出处，先例明确
  保留；如要重指 `_archive/` 路径，另起 proposal。
- **不动正文里已是中性占位的 `agent_rules/<agent>.allow.txt`** 等（E6）：已通用，非残留。
- **不扩到非 knowledge 残留**（如 `tools/scan_classify_log.py` 等 "待开发" 工具路径）：
  非本 knowledge sweep 范畴。
- **不删 §3 目录表整体**：见 Open Questions —— 该 spec 表有教学价值，倾向 reframe 而非删。

## Open Questions

- **carrier-classes.md §3「现存子目录归属」表（E2）怎么处理？** 该表列了一堆 gc 不存在
  的上游子树（models/decisions/domain/datasets/...）并称"现存"。两选：
  (a) 裁剪到 gc-real 行（governance/ + design/）+ 一句"消费者可加自己的域子树"；
  (b) **改表头为"推荐/示例 carrier-class 子树映射"+ disclaimer**（保留教学 taxonomy，
  不再断言这些子树在本仓"现存"）。
  **倾向 (b)**（保留 spec 的教学价值，符合 P-0079 disclaimer 范式）；approver 未否决
  即按 (b) 实施。§2 路径列（E1/E8）同样按 (b) 泛化为占位。

## Alternatives & Rationale

- **A. 全删所有死/举例引用**：最省事，但会毁掉 carrier-classes 这个 **spec 文档**的
  教学价值（它靠跨类举例讲分类法）——违背 P-0079「泛化举例、保留机制」先例。否决。
- **B. 阶梯式 REMOVE/FIX-PATH/GENERICIZE（本提案选）**：死 cross-ref 删、真文档错路径
  修、教学举例泛化为中性占位、机制逐字留。与 P-0086/P-0079 完全一致。
- **C. 全留不动**：消费者继续收到指向幽灵文件的死链、上游 trade 术语，文档可信度受损。
  否决（用户已明确要求清理）。

选 B：与既有去 trade 化先例对齐、保留 spec 教学价值、消除死链与域泄漏。

## Guardrails

- `edit-write-guard`：改 `governance_core/knowledge_governance/*.md`（包源 knowledge，
  符合 Art.11.2），不触宪法三文件、不触自治层副本，不被阻断。
- 无 command-guard / sensitive-data-guard / boundary-guard 相关动作（纯本仓库内容编辑）。

## Phases

### Phase 0: Governance bootstrap

N/A — 非宪法 / 契约变更。

### Phase 1: 去 trade 化 sweep + 验证

- Deliverables:
  - 按 disposition 表逐处 REMOVE / FIX-PATH / GENERICIZE（8 文件），机制文字逐字保留。
  - §3 目录表按 Open Questions 决议处理（默认 (b) reframe + disclaimer）。
  - 改动文件 bump `updated: 2026-06-24`。
  - `governance-core upgrade --project-root .` 重装。
- Validation:
  - grep gate：trade token 集（`strangle|s30_current|s50_current|dense_o2|
    evaluation_metrics|experiment_protocol|data-manual|trade-manual|unlock_trade|
    _constitution_inline_audit|data-flow\.md|adr-001-w120`）在 knowledge_governance
    下零命中（provenance `proposals/` 行除外）。
  - `python tools/audit_knowledge.py` → Failed: 0（related 仍 0 失败）。
  - `python -m pytest governance_core/tools/test_*.py` 无回归。
- Exit criteria: grep gate 零命中、hub 自审 Failed:0、测试不回归、commit 引 `Implements: P-0113`。

## Approval Criteria

- [x] Field Dictionary N/A（纯 static markdown，无字段，已标注）
- [x] realizer 明确（人工 Edit 包源 + `governance-core upgrade`）
- [ ] Open Questions（§3 目录表 a/b）已由 approver 裁定（默认 (b)）
- [ ] 机制 / 契约 / 规则文字逐字保留（仅死链 + 举例 token 变）
- [ ] provenance `proposals/...` 指针未被碰
- [ ] 真文档错路径已 FIX-PATH（core-manual → docs/core-manual.md），未误删
- [ ] grep gate trade token 零命中；hub 自审 Failed:0；测试不回归

## Validation Plan

1. grep gate（见 Phase 1 Validation 的 token 集）零命中。
2. `python tools/audit_knowledge.py`（upgrade 后自治层）→ Failed: 0。
3. `python -m pytest governance_core/tools/test_*.py -q` 全绿（确认未碰代码路径）。
4. 人工抽查 carrier-classes.md：carrier-class 定义 / 规则文字与改前逐字一致（diff 只含
   举例 token 与表头）。

## Rollback / Recovery

纯内容编辑，无状态 / 格式 / 代码变更；`git revert <commit>` 整体回退，`upgrade` 还原
自治层。回退后死链与 trade 术语复现（已知态）。

## Risks

- **误删教学价值**（中概率 / 中影响）：缓解：阶梯优先 GENERICIZE 而非 REMOVE；机制文字
  逐字保留 + 人工 diff 抽查（Validation 4）；§3 表 reframe 不删。
- **误碰真实 gc 内容**（低概率 / 中影响）：缓解：disposition 表逐处标 role；真文档错路径
  走 FIX-PATH；provenance 与已有效 cross-ref（memory-staleness / sub-constitution）
  显式 KEEP。
- **泛化占位再引入新死链**（低概率 / 低影响）：缓解：占位用 `<model>`/`<domain>` 角括号
  显式非路径形态 + audit related 校验 + grep gate。

## State Log

- 2026-06-24: draft created by core agent (P-0113)
- 2026-06-24: draft → pending (submit for review: de-trade knowledge residue sweep (P-0086 follow-up, 8 files, disposition table))
- 2026-06-24: pending → approved (user approval signal: '批准'; Open Question §3 dir table -> default (b) reframe+disclaimer (no objection raised))
- 2026-06-24: approved → implemented (as-built: all 8 scope files done. Deviation (justified): data-analysis-discipline.md touched (named in Current State as a data-flow.md site but omitted from the Scope 8-file list); plus grep-gate surfaced same-token residue beyond the disposition table (artifacts-layout per-source table strangle x3, html-profile:36 experiment_protocol) -- cleaned to honor the zero-hit gate exit criteria. STATE.md per phase discipline. Non-path residue in data-analysis-discipline (validate-pipeline, rules-agent R3) deliberately left as out-of-scope, flagged in STATE.)
