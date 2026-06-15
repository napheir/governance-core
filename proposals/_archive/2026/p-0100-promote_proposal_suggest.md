---
id: P-0100
agent: core
status: implemented
created: 2026-06-15
approved_at: 2026-06-15
implemented_in: 757d04f
implemented_at: 2026-06-15
owner: core
---

# Proposal P-0100: 收编 candidate #96: proposal_suggest classify 建议助手 (泛化 kernel)

## Trigger

User 审查 candidate #96（`mechanism` from trade-agent，`/curate-candidate`
layer-2），决定**收编泛化 kernel**。提供物 `proposal_suggest.py` 是 `/proposal
classify` 阶段的只读建议助手（三路纯关键词召回：① 类似 proposal、② 起草检查项、
③ likely scope owner），不阻断、不改文件、空集显式渲染 `（无）`。

按 classify gate（L2 §1）：新增治理 tool + seed knowledge 随包下发消费者 + 编辑
`commands/proposal.md`（skill 体系）+ 多 phase → **PROPOSAL_REQUIRED**
（quick classify 已记 log，2026-06-15）。

## Scope

收编 candidate 的**泛化 kernel**（机制逐字保留，仅去域泄漏 + 补缺失数据源）：

1. **新增** `governance_core/tools/proposal_suggest.py` —— payload 机制逐字保留，
   仅 **瘦身 `_DOMAIN_ALIASES`**：删除 trade-agent 域词（信号/回测/仿真/交易/下单/
   风控/采集/清洗/挖掘/训练/模型/分析 → trade/simu/rules/data/analysis），只留
   域中立的治理/基础设施结构别名（宪法→constitution、契约→contracts、钩子/hook/
   技能/slash→.claude、工具→tools、审计→audit、测试→tests），并注释说明消费者按
   自身域扩展。
2. **新增** `governance_core/tools/test_proposal_suggest.py` —— payload 测试，
   将 ③ alias 用例改用保留别名（工具→tools）以维持覆盖，去除 fixture 里残留的
   trade 词汇（中性化）。
3. **新增** `governance_core/knowledge_governance/proposal-drafting-checklist.md`
   —— 补 candidate **缺失的 ② 数据源 seed**（candidate 的 `source_paths` 未带、
   但其集成测试断言其存在）。内容为**通用治理起草经验** seed（域中立，源自 gc
   自身真实经验），消费者后续自维护其条目。
4. **编辑** `governance_core/commands/proposal.md` —— 在 `classify` 执行流程加
   一行**指针**：起草前可选跑 `python tools/proposal_suggest.py "<description>"`
   surface 三路召回，作为参考、不阻断。

发布：版本 0.27.0 → 0.28.0；curation 决策直接 `registry.record_candidate` 记账
（**不**用 `candidate.py promote` —— 会拿原始 payload 覆盖泛化改动）；close #96。

## Non-Goals

- **不引入相似度排序 / embeddings** —— 保持 payload 契约的纯关键词召回（candidate
  Non-Goals）。
- **不为消费者预置域条目** —— ② seed 只放域中立通用经验；trade 等域内容由消费者
  自维护。
- **不改 ③ 在单 agent hub 的退化事实** —— 本 hub 只有 `shared.*`、无 per-agent
  `*.allow.txt`，③ 永远 `（无）`（符合 Art.12 退化）；机制对多 clone 消费者仍 live。
- **不把 helper 做成阻断 gate** —— 永远只读、永远 surface、决策权在起草 agent。
- **不动 pyproject package-data** —— `tools/*.py` 与 `knowledge_governance/*.md`
  glob 已覆盖二新文件（仍在 Phase 2 wheel 校验复核）。

## Guardrails

- **edit-write-guard / proposal-classify-fast** —— 编辑 `commands/proposal.md`
  （harness）+ 新增治理 tool 命中 classify gate；已先跑 quick classify 清账。
- **constitutional-review** —— `proposal_suggest.py` 无 `.get(k, default)` 兜底、
  用 `out()` 代 print、Windows UTF-8 重配，符合 Art.4/7（payload 已自带）。
- **Art.11.2** —— 只改 `governance_core/` 包源，**不**碰根级自治层副本；改完
  `upgrade --project-root .` 重装再跑测试（Art.11.3 dogfood）。
- **Art.11.4** —— wheel 顶层须仍只 `governance_core*`，二新文件在 wheel 内、
  `maintainer/` 不泄漏。

## Phases

### Phase 0: Governance bootstrap

- Deliverables: 本 proposal（P-0100）approved；quick classify log 已记。
- Validation: `/proposal show P-0100` 状态 approved。
- Exit criteria: user 明确批准信号。

### Phase 1: 泛化 kernel 落地到包源

- Deliverables: 上述 Scope 1–4 四处文件改动（均在 `governance_core/`）。
- Validation: 文件就位；`proposal_suggest.py` 机制逐字、仅 aliases 瘦身；seed
  checklist 含 frontmatter（6 必填 + `carrier_class: reference`）+ ≥1 个
  `### / 触发/教训/怎么做/来源` 条目。
- Exit criteria: 四处改动完成、自审无域泄漏残留。

### Phase 2: dogfood 重装 + 验证 + wheel 隔离

- Deliverables: 版本 0.28.0；upgrade 重装；测试通过；wheel 校验。
- Validation:
  - `governance-core upgrade --project-root .` → `governance-core doctor` exit 0。
  - 从 repo-root 跑 `python tools/test_proposal_suggest.py`（autonomy 层，
    per gc-test-suite layout）全绿 + `python tools/audit_knowledge.py` 通过 seed。
  - 烟测 `python tools/proposal_suggest.py "<desc>"` 三节都渲染（① live、② 命中
    seed、③ `（无）`）。
  - `python -m build --wheel` 后断言 wheel 顶层仅 `governance_core*`、二新文件在内、
    `maintainer/` 未泄漏。
- Exit criteria: 全部 validation 通过。

### Phase 3: curation 记账 + 归档 + close

- Deliverables: `registry.record_candidate` 记 promoted 决策；commit
  （`Implements: P-0100`）；`/proposal complete` 归档；issue #96 close + 致谢评论。
- Validation: registry 写入；#96 状态 CLOSED 含 outcome 评论。
- Exit criteria: candidate pipeline 闭环。

## Approval Criteria

- Scope 四处改动 + 泛化策略（机制逐字、仅去域泄漏、补 ② seed）合理。
- 版本 0.28.0、记账方式（`record_candidate` 而非 `promote`）、close #96 流程认可。
- 接受 ③ 在本 hub 退化为 `（无）`（单 agent 拓扑事实，非缺陷）。

## Validation Plan

见 Phase 2 Validation。核心闸门：测试全绿 + doctor exit 0 + wheel 隔离三断言通过
+ 烟测三节渲染正确。

## Rollback / Recovery

- Phase 1 未提交前：`git checkout -- governance_core/` 丢弃。
- Phase 2 重装后发现问题：还原包源四文件 + 回退版本号，再 `upgrade` 重装。
- Phase 3 记账后：candidate 决策 ledger 可改记 / issue 可重开 —— 但 promote 是
  capability add，回退需新 proposal（与本条声明一致）。
- 单点开关：helper 是独立 script，未被任何 hook 调用 —— 删 `tools/proposal_suggest.py`
  + 撤 proposal.md 指针即完全移除，无残留依赖。

## Risks

- **[低] ② seed 域中立但可能过窄** —— 起步只放少量通用经验；消费者/本 hub 后续
  按真实教训追加（这正是 seed 的设计意图）。
- **[低] 测试在 package-source 布局 false-fail** —— 已知坑（hook-path / import
  布局）；按纪律从 repo-root autonomy 层跑，不在 `governance_core/tools/` 跑。
- **[极低] 新数据文件漏出 wheel** —— glob 已覆盖；Phase 2 wheel 断言兜底。
- **[低] aliases 瘦身改动测试** —— ③ 用例改用保留别名维持覆盖，机制本身零改动。

## State Log

- 2026-06-15: draft created by core agent (P-0100)
- 2026-06-15: draft → pending (submit for review: promote candidate #96 proposal_suggest (genericized kernel))
- 2026-06-15: pending → approved (user approval: 批准)
- 2026-06-15: approved → implemented
