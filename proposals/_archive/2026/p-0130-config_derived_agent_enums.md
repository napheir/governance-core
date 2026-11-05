---
id: P-0130
agent: core
status: implemented
created: 2026-11-05
approved_at: 2026-11-05
started_at: 2026-11-05
implemented_in: 69772dc
implemented_at: 2026-11-05
owner: core
---

# Proposal P-0130: Derive agent enums and clone lists from config (contracts + validators)

## Trigger

deva-vani core（第二个多 clone 消费者，agent = core / platform / experience / content）在 0.46.0 之后又报了两处与 P-0129 F1
同族的问题：knowledge 契约的 `owner` 枚举、`tools/check_agent_roles.py` 的 `AGENT_DEFS` 都写死了上游角色。本仓库按角色名
token 全量扫描（P-0129 的门禁按 `feature/...` 分支扫，扫不到角色名），又找到 `audit_proposals.VALID_AGENTS`、提案契约
`agent` 枚举、`audit_hooks.py` 写死的上游 clone 列表，以及 0.47.0 与一份 shipped skill 之间的规范冲突。

涉及两份契约（`contracts/`）与多个校验器，属治理变更 → PROPOSAL_REQUIRED。P-0129 已批准范围不含这些，故单开。

## Current State (read, not assumed)

**G1 提案 `agent` 枚举（影响最直接）**
- `governance_core/contracts/proposal_frontmatter_schema.md:81`（v1.5.0）：`agent` 为 enum "One of `core`, `rules`, `trade`, `data`, `research`"。
- `governance_core/tools/audit_proposals.py:85` `VALID_AGENTS = {"core", "rules", "trade", "data", "research"}`，`:214` 不在其中即 FAIL。
- 对照：`proposal_lib._agents()` 已从 config 推导（`governance_core/config.py:169` `"agents": [a.name for a in cfg.agents]`），
  所以 deva-vani 的业务 agent 能 `create` 提案，却过不了 `audit_proposals`。`audit_proposals.py:367` 已 import
  `governance_core.config.load_proposals_config`，数据源现成。
- hub 归档 61 份提案全是 `agent: core`（`grep -h "^agent:" proposals/_archive/*/*.md`）。

**G2 knowledge `owner` 枚举**
- `governance_core/contracts/knowledge_frontmatter_schema.md`（v1.2.0）§3.2 表格列 rules/trade/data/research/core，`:88` 起
  "Unknown values are a hard audit failure"。
- `governance_core/tools/audit_knowledge.py:501` `owner_enum = parse_enum(contract_fm, "### 3.2 \`owner\`")`（契约驱动，
  从表格解析）；`:580` 不在其中即 FAIL。
- `governance_core/tools/migrate_knowledge_frontmatter.py:38` `VALID_OWNERS` 同样写死。
- shipped knowledge 文档 17 份全是 `owner: core`（`governance_core/knowledge_governance`）。

**G3 `check_agent_roles.py`**
- `governance_core/tools/check_agent_roles.py:26-47` `AGENT_DEFS` 写死 rules/trade/data/research 的 clone 目录、角色前缀词表
  （如 `["trade", "execution", "risk", "order"]`）和核心角色文件名；`:127` 不在其中即 "Unknown agent"。
- 规则本体在条款 `governance_core/clauses/art_01_project_architecture.md:46`："每个 agent 至少有一个与 agent 同名的核心角色定义
  （如 `data-specialist.md`）"，`:49` 禁止跨 scope 角色定义。hub `.claude/agents/` = `core-auditor.md` + 共享角色
  `design-system-owner.md`。

**G4 `audit_hooks.py` 整体陈旧**
- `governance_core/tools/audit_hooks.py:33-39` 写死 core/trade/rules/data/research 五个 clone；`:44-50` 期望的
  `sensi-guard.py`、`pipeline-check.py` 在包里不存在（现为 `sensitive-data-guard.py` 等，权威清单是
  `governance_core/hooks/hooks_manifest.json`）。对任何消费者都只能报假问题。
- 被 `governance_core/commands/audit.md:29` 与 skill `settings-json-merge-semantics.md:25,29,42` 引用；
  其 `_check_legacy_settings_json`（`:224-260`）只对 settings.json 里的 `hooks` / `enabledPlugins` 报警，这部分仍有价值。

**G5 规范冲突（0.47.0 引入）**
- `governance_core/skills/settings-json-merge-semantics.md` 规范第 3 条："新 clone bootstrapping 时只生成 `settings.local.json`，
  不要创建 `settings.json`"。而 `tools/sync_infra.py:167-173` 把 `.claude/settings.json`（`projectRoot` 边界锚）列为每个 clone 必有，
  0.47.0 的 `installer._ensure_boundary_anchor` 也写它。第 3 条写得过宽：它要防的是 `hooks` / `enabledPlugins` 落在 settings.json
  （第 2 条已覆盖），不是边界锚。

**G6 文档示例**
- `governance_core/knowledge_governance/skill-scenario-clusters.md:58` 用 `trade` 举例 per-agent theme。

## Scope

- `governance_core/contracts/proposal_frontmatter_schema.md`：`agent` 改为"∈ 本项目 config `agents[].name`"，版本 1.5.0 → 1.6.0。
- `governance_core/contracts/knowledge_frontmatter_schema.md`：§3.2 `owner` 改为"∈ config `agents[].name`，`core` 恒为 core agent 别名"，1.2.0 → 1.3.0。
- `governance_core/tools/audit_proposals.py`、`audit_knowledge.py`、`migrate_knowledge_frontmatter.py`：枚举改从 config 推导。
- `governance_core/tools/check_agent_roles.py`、`audit_hooks.py`：v2，agent / clone / hook 清单全部从 config 与 `hooks_manifest.json` 推导。
- `governance_core/skills/settings-json-merge-semantics.md`（G5）、`governance_core/knowledge_governance/skill-scenario-clusters.md`（G6）。
- 新测试：`governance_core/tools/test_config_derived_enums.py`、`test_check_agent_roles.py`、`test_audit_hooks.py`。
- `docs/core-manual.md` 同步；版本 0.47.0 → 0.48.0。

## Design & Contract

### Interfaces, I/O & Realization

- **共用数据源**：`governance_core.config.load_config(repo_root)`（tools 可 import 包；不涉及 hook，无 runtime-import 约束）。
  读 `agents[].{name, clone_dir}` 与 `core_agent_name`。不再新增第二份实现：tools 已在用这个模块。
- **G1 `audit_proposals`**：`VALID_AGENTS` 常量删除，改为 `_valid_agents(repo_root) -> set[str]`。
  - in-flight 区：`agent ∉ config agents` → FAIL（与今天的硬失败语义相同，只是枚举来源换成 config）。
  - archive / legacy 区：`agent` 须匹配 `^[a-z][a-z0-9_-]*$`（形式校验）；不在当前 config 中 → WARN（下线 agent 的历史提案仍合法）。
  - 执行者：`python tools/audit_proposals.py` CLI（`/wrap-up` 2c、`/proposal` 流程调用）。
- **G2 `audit_knowledge` / `migrate_knowledge_frontmatter`**：`owner_enum = {a.name for a in cfg.agents} | {"core"}`。
  契约 §3.2 不再列表格值，改写规则；`parse_enum(..."### 3.2 owner")` 调用删除（契约驱动的含义变为"契约指定枚举来源"）。
  执行者：`python tools/audit_knowledge.py`（`/learn`、`/wrap-up` 调用）、`migrate_knowledge_frontmatter.py` CLI。
- **G3 `check_agent_roles` v2**：对 config 每个 agent：clone 根 = 单 agent 时为本仓库，多 agent 时为 `<本 clone 父目录>/<clone_dir>`；
  Check 1：`.claude/agents/` 至少一个 `<agent>-*.md`；Check 2：文件名前缀等于**另一个** agent 名 → 跨 scope（共享角色如
  `design-system-owner.md` 不受影响）；Check 3 frontmatter 不变。`--agent X` 不在 config → 列出 config 中的 agent。执行者：CLI。
- **G4 `audit_hooks` v2**：repo 清单同 G3；期望 hook = `hooks_manifest.json` 中每个 hook 文件；检查：文件存在、在
  `settings.local.json` 注册、与 core clone 副本 checksum 一致（多 clone 时）、`_check_legacy_settings_json` 与 stale ref 检查保留。
  删除 `REQUIRED_HOOKS` / `SYNCED_HOOKS` / `CORE_ONLY_HOOKS` 常量。`--fix` 保留（从 core 复制缺失 hook）。执行者：CLI / `/audit`。
- **G5**：skill 第 3 条改为"新 clone 不要在 `settings.json` 放 `hooks` / `enabledPlugins`；`settings.json` 只承载需要跨 clone 共享、
  经 git 同步的声明（如 `projectRoot` 边界锚，由 installer 维护）"。
- **G6**：示例改为 `<agent>`（如 `platform`）。

### Field Dictionary

| field | type | meaning | producer | consumer | constraints / allowed values |
|-------|------|---------|----------|----------|------------------------------|
| proposal `agent` | str | 提案所属 agent | `/proposal create`（`proposal_lib`）| `audit_proposals`、session-context | `contracts/proposal_frontmatter_schema.md` §2（v1.6.0）：in-flight ∈ config `agents[].name`；归档仅形式校验 |
| knowledge `owner` | str | 知识条目的维护 agent | `/learn` 等写入方 | `audit_knowledge`、scope guards | `contracts/knowledge_frontmatter_schema.md` §3.2（v1.3.0）：∈ config `agents[].name` ∪ {`core`} |
| config `agents[].name` / `clone_dir` / `core_agent_name` | str | 拓扑 | owner / installer | 上述全部校验器 | N/A contracts/ —— config schema 尚无契约（P-0129 Q4 已 defer）|

### Flow

```
.governance/config.json (agents, core_agent_name)
   -> governance_core.config.load_config
   -> audit_proposals  (in-flight agent ∈ agents -> FAIL else; archive form-only + WARN)
   -> audit_knowledge / migrate_knowledge_frontmatter  (owner ∈ agents ∪ {core})
   -> check_agent_roles / audit_hooks  (clone roots from clone_dir; hooks from hooks_manifest.json)
```

## Non-Goals

- **条款正文里的上游业务残留**：`art_02b`（P4 响应 "S3/S5 → rules, S6/S9 → trade"）、`art_07`（`legacy/`、`common/`）、`art_08`
  （paper/live 措辞）、`art_10`（rules/trade 输出表）、`art_04`（`config/` 目录约定）。属条款去业务化，另开提案（按
  detrade 的 token grep 门禁做）。
- **knowledge 分类目录的写死映射**：`audit_knowledge.py` / `infer_carrier_class.py` 里的 `research`、`models` 是 knowledge
  **目录类别**，不是 agent 角色；同属去业务化，随上一条处理。
- 为 config 立契约（P-0129 Q4 defer 项）。
- mab 侧问题与授权码进 git（另行处理）。

## Open Questions

- Q1 归档提案的 agent 不在当前 config：**倾向 WARN 而非 FAIL**（agent 下线后历史记录仍应合法；in-flight 才需要在册）。
- Q2 knowledge `owner` 是否接受字面 `core` 作为 core agent 别名（当 `core_agent_name` 不叫 `core` 时）：**倾向接受**——shipped 的
  17 份文档都写 `owner: core`，与 guard 的 `CORE_ROLE` token 一致。
- Q3 `audit_hooks` 修 v2 还是退役（`doctor` 已按 `hooks_manifest.json` 检查单 clone 注册）：**倾向 v2**——跨 clone 副本一致性
  与 settings.json 漂移检查是 doctor 没有的；v2 的数据源全部现成。
- Q4 发布：本提案 3 个 phase 合为一次发布 0.48.0。**倾向一次发**（彼此独立、风险低）。

## Alternatives & Rationale

- **枚举来源**：(a) 在契约表格里追加 deva-vani 的角色 —— 每个新消费者都要改上游契约，不可行；(b) 每个项目覆写契约文件 ——
  契约是 install-managed，会被 upgrade 覆盖或当 drift 上送；(c) **契约写规则、值取自 config（选用）**：与 P-0129 的身份来源一致，
  单一数据源。
- **归档提案**：硬失败会让任何下线过 agent 的项目永远审计不过；完全不校验会放过拼写错误。形式校验 + WARN 取中。
- **`audit_hooks`**：退役最省事，但丢掉跨 clone 一致性检查（多 clone 项目恰好最需要）；v2 只是把数据源换成 config +
  manifest，改动面小于重写。

## Guardrails

- 只改 `governance_core/` 包源；每个 phase 后 `governance-core upgrade --project-root .` 并在 hub dogfood（hub 单 agent `core`）。
- 校验器改动按 `contract-driven-validator` guide：校验规则来源写在契约里，validator 只实现契约说的来源。
- 多 clone 行为用 deva-vani 形状的 fixture 测（`verify-guard-fires-in-its-target-context` guide 的 topology fixture 要求），并对
  0.47.0 旧代码反向校准（旧代码对 `agent: platform` 报 FAIL、对 `owner: platform` 报 FAIL、`check_agent_roles --agent platform` 报 Unknown）。

## Phases

### Phase 0: Governance bootstrap

- N/A —— 不改宪法；两份契约是包源契约文件，随 Phase A / B 在本提案内修改。

### Phase A: 提案 `agent` 枚举（G1）

- Deliverables：契约 v1.6.0；`audit_proposals` 改用 config；`test_config_derived_enums.py` 的提案部分。
- Validation：多 agent fixture 中 `agent: platform` 的 in-flight 提案 PASS；`agent: ghost` 的 in-flight 提案 FAIL；归档中的
  `agent: retired` WARN 不 FAIL；hub `audit_proposals` 仍 0 failures。
- Exit criteria：Approval Criteria 1、2。

### Phase B: knowledge `owner` 枚举（G2）

- Deliverables：契约 v1.3.0；`audit_knowledge`、`migrate_knowledge_frontmatter` 改用 config；测试的 knowledge 部分。
- Validation：`owner: platform` PASS（多 agent fixture）；`owner: ghost` FAIL；`owner: core` 在 `core_agent_name: lead` 时 PASS；
  hub `audit_knowledge` 仍通过。
- Exit criteria：Approval Criteria 3。

### Phase C: `check_agent_roles` / `audit_hooks` v2 + 文档（G3–G6）

- Deliverables：两个工具 v2；`test_check_agent_roles.py`、`test_audit_hooks.py`；skill G5 修正、G6 示例；core-manual。
- Validation：4 clone fixture：缺 `<agent>-*.md` → HIGH；`platform` clone 里放 `content-writer.md` → 跨 scope HIGH；共享角色不报；
  audit_hooks 对 manifest 中缺失 / 未注册 / checksum 不一致的 hook 报告，对只含 `projectRoot` 的 settings.json 不报。
- Exit criteria：Approval Criteria 4–6。→ **发布 0.48.0**（需人工确认，core-A3）。

## Approval Criteria

> Each item pairs a plain-language acceptance with ONE discriminating check token
> (`cmd: <exit 0 = pass>` / `agent-rubric: <ref>` / `human-verify: <sentence>`; see
> contracts/proposal_gate_schema.md). An item with no check token is prose, not an
> acceptance signal.

- [ ] Every Field Dictionary entry names its governing `contracts/` file (or is N/A) — human-verify: proposal agent → proposal_frontmatter_schema §2, knowledge owner → knowledge_frontmatter_schema §3.2, config fields N/A with reason
- [ ] Every user-facing capability / mutation has a named realizer — human-verify: each validator change names its CLI and calling skill
- [ ] All Open Questions are resolved or explicitly deferred — human-verify: owner rules on Q1–Q4
- [ ] 1. 提案枚举取自 config（in-flight 硬校验、归档形式校验）— cmd: python -m pytest tools/test_config_derived_enums.py -q -k proposal
- [ ] 2. hub 自身提案审计不回退 — cmd: python tools/audit_proposals.py
- [ ] 3. knowledge owner 取自 config，`core` 别名有效 — cmd: python -m pytest tools/test_config_derived_enums.py -q -k knowledge
- [ ] 4. check_agent_roles v2 在 4 clone fixture 上按 config 判定 — cmd: python -m pytest tools/test_check_agent_roles.py -q
- [ ] 5. audit_hooks v2 以 hooks_manifest.json 为准、不误报边界锚 — cmd: python -m pytest tools/test_audit_hooks.py -q
- [ ] 6. 包源不再含写死的上游角色名（knowledge 目录类别与一次性迁移工具除外）— cmd: bash -c "! git grep -nE \"[\\\"'\\\`](rules|trade|simu)[\\\"'\\\`]\" -- governance_core ':!governance_core/tools/test_*' ':!governance_core/tools/migrate_proposals_to_shared_state.py'"

## Validation Plan

- 每个 phase：改包源 → `governance-core upgrade --project-root .` → 新测试 + 全量（pytest 风格 + 脚本风格分别跑）→ `audit_proposals` /
  `audit_knowledge` 在 hub 上结果不变。
- 反向校准：把 0.47.0 的 `audit_proposals.py` / `audit_knowledge.py` / `check_agent_roles.py` 放进同一 fixture，确认上述 PASS 用例在旧代码上 FAIL。
- 发布前 wheel 检查（只含 `governance_core*`，无 `maintainer/`）。发布后请 deva-vani 在业务 clone 跑 `audit_proposals` /
  `check_agent_roles` 回报。

## Rollback / Recovery

- 各 phase 独立：回退单个 commit 即恢复旧枚举；契约版本号随之回退。
- 校验器只放宽"枚举来源"、不放宽形式检查，回退无数据风险。

## Risks

- **config 缺失或损坏时校验器无法运行**（低）：`load_config` 缺 config 即抛错（Art.4），这本身就是坏安装；hub 与消费者都有 config。
- **已有消费者的 knowledge 条目用了上游角色名**（低）：上游项目的 `owner: trade` 等条目在其自身 config 里本就有该 agent；
  不在 config 的才会 FAIL，属于真实错误。
- **audit_hooks v2 首次运行报出大量真实问题**（中）：旧版从未正确运行过，消费者可能第一次看到真实漂移；作为报告工具，不阻断。

## State Log

- 2026-11-05: draft created by core agent (P-0130)
- 2026-11-05: draft → pending (submit for review)
- 2026-11-05: pending → approved (owner: 批准 P-0130 (2026-11-05). Open Questions by stated defaults: Q1 archive agent not in config -> WARN; Q2 accept literal core as alias; Q3 audit_hooks v2 not retire; Q4 single release 0.48.0)
- 2026-11-05: approved → in-progress
- 2026-11-05: in-progress → implemented (Phases A fc91f6d, B ca218bb, C 69772dc. Criteria 1-6 pass (criterion 6's documented cmd had broken quoting; the same gate run directly exits 1 = clean). As-built deviations: knowledge carrier_class cutover renumbered v1.3.0->v1.4.0 across learn.md, knowledge-html-profile.md, audit_knowledge.py, infer_carrier_class.py; check_scope.py comment genericized; audit_hooks dropped _check_stale_local_refs (sync_infra central model, misfires on installer wiring).)
