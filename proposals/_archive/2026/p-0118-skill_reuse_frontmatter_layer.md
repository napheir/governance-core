---
id: P-0118
agent: core
status: implemented
created: 2026-07-08
approved_at: 2026-07-08
started_at: 2026-07-08
implemented_in: fa608cc
implemented_at: 2026-07-08
owner: core
---

# Proposal P-0118: Unify per-skill reuse classification into frontmatter layer; retire central _tiers.json authoring

## Trigger

trade-agent（core role）递交 handoff 设计简报 `skill-reuse-layer-unification.md`，
指出 gc 的复用/层级分类分散在三条重叠轴上、且无 per-skill 复用字段，导致每个多
agent 消费者各自在中心化 `_tiers.json` 里重造一套 tier taxonomy，gc 的通用机制
（`emit_bounded_injection`）再按约定耦合到消费者命名的 `universal` key。

维护者核对现状（见下）后确认诊断成立且**被低估**：gc 包源已 ship 整套围绕
`_tiers.json` 的子系统（reader + 2 builder + writer + auditor），并把 trade-agent
的域名词硬编码进包源。

治理适用性：本改动触及 skill 分类体系、`knowledge_governance/` 语义契约、核心注入
机制（registry）、auditor 与打包 —— 多 phase、架构级、改治理体系，命中第三/十一/
十三条与 `/proposal classify` 的多条必判条件，故走 proposal 分阶段实施。

维护者已定两项决策：**(1) 完整统一**（per-skill frontmatter 为单源，退休中心化
`_tiers.json` 授权）；**(2) 3 级 enum `universal/project/business`**（保留 gc 现有
表达力，仅 `branch→business` 对齐 envelope，消灭第 4 术语）。

> **设计修订（本 session，维护者已批 Option 1「派生自 theme」）**：实施中发现 gc
> **已有**一个 gc-native、per-skill、frontmatter 的广度字段 `theme:`（`universal |
> core-only | <agent>`，由 `sync_infra` 强制、决定跨 clone 分发；`sync_infra.py:231-251`）
> —— 即 handoff 文档声称"不存在"的那个 per-skill 复用字段。故**不新增 `reuse` 字段**
> （那会成为第 5 条重叠轴，正是本提案要消灭的），改为**让 injection/index 直接派生自
> 既有 `theme`**、退休中心化 `_tiers.json`。**下文凡写 `reuse` 处一律读作 `theme`**；
> 随之取消：新字段 / 新枚举 / 新契约 / 35-skill backfill / reuse↔_tiers 不变式（`theme`
> 早已在全部 shared skill 上，零 backfill）。learned skill 无 theme → 注入时恒视为本
> agent 的 universal。原决策 (2) 的 enum 命名问题一并作废（沿用 theme 的既有枚举）。

## Current State (read, not assumed)

gc 包源围绕中心化 `knowledge/skills/_tiers.json` 已成型一套子系统，全部 ship 给消费者：

- **Reader/注入**：`governance_core/discovery/registry.py:449-471` `emit_bounded_injection`
  读 `_tiers.json → tiers.universal.skills`，作为 SessionStart 热集，capped by
  `_UNIVERSAL_INJECTION_LIMIT=10`（registry.py:427）。`SkillEntry` dataclass
  （registry.py:49-63）目前只有 name/description/source_type/tags，**无 reuse 字段**；
  `_extract_metadata`（registry.py:306-334）只解析 description + tags。
- **Builder ×2（含域泄漏）**：`governance_core/tools/build_skill_index.py:38,41` 与
  `governance_core/tools/skill_catalog.py:33,36` **都硬编码**
  `TIER_ORDER=["universal","project","branch","unclassified"]` 和字面
  `"Tier 2 — Project-Universal (Trade Agent)"`。
- **Writer**：`governance_core/commands/extract-skill.md:61-64` step 6 用 "no Trade Agent
  coupling / depends on Trade Agent infra" 描述 universal/project/branch，写入 `_tiers.json`。
- **Auditor**：`governance_core/tools/audit_knowledge.py` Check 11a/b/c
  （`_audit_skill_tiers`，:333-490）强制 registry↔`_tiers.json` bijection + INDEX.md
  freshness；Check 16（`_audit_scenario_coverage`，:494-596）要求每个 md-skill 进
  universal tier 或 scenario cluster 才算 surfaced。
- **Schema 缺口**：`_scenario_clusters.json` 有独立 schema doc
  （`knowledge_governance/skill-scenario-clusters.md`），但 `_tiers.json` 的
  universal/project/branch taxonomy 仅在该文件 :19 一句带过（"P-0043 reuse-tier"），
  **无独立契约**。`governance_core/contracts/` 只有 proposal / knowledge_frontmatter /
  knowledge_index 三个 schema，**无 skill-frontmatter 契约**（故文档建议的"加到
  knowledge_frontmatter_schema.md"有误：skill ∉ knowledge/）。
- **envelope 轴**：`governance_core/candidates/envelope.py:38`
  `LAYERS=("candidate-common","business")`；installer p-0117（4d6f87a）用 `layer:business`
  标 intentional drift。
- **规模**：gc 自身 ship 15 commands + 20 guides = 35 个 md-skill 需 backfill reuse。
- **hub 现状**：本 repo（单 agent）无 `_tiers.json`（`0 learned + 19 guides`），该子系统
  纯为下发给多 agent 消费者服务 —— 泄漏修复无法 dogfood 复现，靠单元/fixture 测试。

## Scope

把"某 skill 是否通用/项目内/业务专属"从中心化 `_tiers.json` 迁到 per-skill frontmatter
的 `reuse` 字段（enum `universal | project | business`），gc 机制一律从 frontmatter 派生。

改动文件（包源 `governance_core/`）：
- `discovery/registry.py` — `SkillEntry` 加 `reuse`；`_extract_metadata` 解析 `reuse`；
  `emit_bounded_injection` 改从 `reuse:universal` 派生注入池（`_tiers.json` fallback）。
- `commands/extract-skill.md` — writer 改为在 skill frontmatter 写 `reuse:`，退休"改
  `_tiers.json`"步骤；去除 "Trade Agent" 措辞。
- `tools/build_skill_index.py`、`tools/skill_catalog.py` — 从 frontmatter 派生 tier 分组；
  删硬编码 `"Trade Agent"` TIER_TITLES 与 `TIER_ORDER`；`_tiers.json` 若留则降级为派生缓存。
- `tools/audit_knowledge.py` — Check 11/16 改校验 frontmatter `reuse` 枚举 +（若保留
  `_tiers.json`）校验其为 frontmatter 的幂等再生。
- `knowledge_governance/skill-scenario-clusters.md`（或新契约，见 Open Questions）— 记录
  `reuse` 字段 spec + enum 语义，reconcile `business` 一词跨 envelope/whichlayer/drift 的重叠。
- `pyproject.toml` — 若新增 schema 文件，确认 package-data 覆盖（召回③提醒）。

de-domain：清除包源里 `"Trade Agent"` 字面泄漏（build_skill_index / skill_catalog /
extract-skill）。gc 自身 35 个 shipped skill 一并 backfill `reuse`。

## Design & Contract

> Proportionate. Trivial change: one line "implementation self-evident; no interface
> or data-flow change." Otherwise fill all three sub-parts; use "N/A — <reason>" for
> any that genuinely doesn't apply — never leave a placeholder.

### Interfaces, I/O & Realization
- **`reuse` frontmatter field** on `.claude/{commands,skills,skills/learned}/*.md`：
  YAML 标量 `reuse: universal|project|business`。producer：skill 作者 / `/extract-skill`
  writer。consumer：registry、2 builder、auditor、candidate collect。realizer：skill 文件本身
  （static-file，被下列组件读取）。
- **`SkillRegistry._extract_metadata`**（registry.py）— INPUT：skill .md 全文 frontmatter；
  OUTPUT：现有 `(description, tags)` 扩为 `(description, tags, reuse)`；`SkillEntry` 加
  `reuse: str = ""`（缺省空 = 未声明）。realizer：registry（进程内 import / `python -m` CLI）。
- **`emit_bounded_injection`**（registry.py）— INPUT：`manifest_for_injection(["learned","guide"])`
  各 entry 的 `reuse`；选 `reuse == "universal"` 组注入池，按 `(score desc, name)` 排序、
  cap `_UNIVERSAL_INJECTION_LIMIT`。fallback：当**无任一 skill 声明 reuse** 时回退读
  `_tiers.json.tiers.universal.skills`（迁移期零回归）。realizer：`session-context.py`
  SessionStart hook（进程内调 registry）。
- **`build_skill_index.py` / `skill_catalog.py`**（CLI）— INPUT：registry manifest 的
  `reuse`（不再读消费者 `_tiers.json` 的 taxonomy）；OUTPUT：按 universal/project/business
  分组的 `knowledge/skills/INDEX.md` / 终端视图。TIER_TITLES 去域化（无 "Trade Agent"）。
- **`audit_knowledge.py` Check 11/16**（CLI）— INPUT：registry `reuse` + 可选 `_tiers.json`；
  校验 enum 合法 + 每 md-skill 有 reuse +（若 `_tiers.json` 存在）它是 frontmatter 的幂等再生。
- **`extract-skill.md` writer**（`/extract-skill` command + agent）— 产出 skill frontmatter 含
  `reuse:`；非 hub 路径同样在自己 skill 文件写 `reuse`，不再依赖 hub 编辑 `_tiers.json`。

### Field Dictionary

| field | type | meaning | producer | consumer | constraints / allowed values |
|-------|------|---------|----------|----------|------------------------------|
| `reuse` | enum str | skill 复用广度 | skill 作者 / `/extract-skill` | registry / 2 builder / auditor / candidate collect | `universal\|project\|business`；缺省空 = 迁移期未声明；治理源：`knowledge_governance/skill-scenario-clusters.md`（或新 `contracts/skill_frontmatter_schema.md`，见 Open Q） |
| `_tiers.json.tiers.universal.skills` | list[str] | (迁移期) 旧中心化注入池 | 消费者手工 / builder 派生 | `emit_bounded_injection` fallback、Check 11 | backfill 后降级为可选派生缓存；治理源同上 |

### Flow
```
skill 作者 / /extract-skill
   └─写→ skill .md frontmatter `reuse:`
            └─scan→ SkillRegistry._extract_metadata → SkillEntry.reuse
                       ├─→ emit_bounded_injection (reuse==universal, cap 10) → SessionStart 注入
                       ├─→ build_skill_index / skill_catalog → INDEX.md / 终端视图（派生）
                       ├─→ audit_knowledge Check 11/16 → enum + 幂等再生校验
                       └─→ candidate collect → uplink 选集
   (中心化 _tiers.json：迁移期仅当无任一 reuse 声明时作 fallback；backfill 后降级派生缓存)
```

## Non-Goals

- 不动 A/B/C **injection tier**（source_type-keyed，`skill-injection-tiers.md`）—— 正交。
- 不动 **whichlayer** install-managed/business 归属轴 —— 正交（仅 reconcile "business"
  一词的措辞，见 Design）。
- 不动 **carrier_class**（内容性质轴，`knowledge/**`）—— 正交。
- 不动 `_scenario_clusters.json` scenario 轴 —— 保留为按需 on-demand 通道。
- 不 backfill 消费者自己的 skill（各消费者自迁；gc 只 backfill 自身 35 个 shipped skill）。
- 不在本提案强制删 `_tiers.json` 物理文件 —— 先降级为 fallback/派生缓存，彻底退休另评。
- 不新建"给所有 skill frontmatter 立契约"的大工程（除非维护者在 Open Q 选新契约路径）。

## Open Questions

> Known-undecided design points to resolve (or explicitly defer) BEFORE approval.
> Lightweight — NOT gated; the approver decides each. Write "None" rather than leaving
> the placeholder.

> 原 Open Questions（reuse/layer 命名、schema 家、business 跨轴 reconcile）已被上方"设计
> 修订：theme pivot"**作废**（不新增字段 → 无命名/契约问题）。剩余已决点：

- **learned skill 注入规则** — 已决：learned 无 theme，注入时恒入 universal 池（本 agent
  自有提炼，Art.15 应每 session 可召回）。
- **`_tiers.json` 终局** — 已决：injection（Phase 1）即停读；builder/auditor（Phase 2/3）
  改派生自 theme 后，`_tiers.json` 物理文件退休（连同 audit Check 11 的 `_tiers.json` 分支）。
- **注入语义位移** — `theme:universal` 池（gc 自身 ~18 guide）> 旧手工 curated 列表；靠
  cap 10 + `(score,name)` 排序 + "+N more" 溢出行收敛，超量走 scenario cluster。已在
  `test_skill_injection_bounded.py` 覆盖（capping / 排除 core-only / 忽略 `_tiers.json`）。

## Alternatives & Rationale

设计抉择，权衡 ≥2：

1. **enum 基数（维护者已定 3 级）**：3 级 `universal/project/business` vs 2 级复用 envelope
   `candidate-common/business`。选 3 级：gc shipped 工具（builder/audit/writer）已依赖 3 级
   表达力，折成 2 级会把 project 折进 business，对多 agent 消费者是表达力回退。仅
   `branch→business` 改名对齐 envelope 的 `business` + p-0117 `layer:business`，消灭第 4 术语。
2. **per-skill frontmatter vs 保留中心化 `_tiers.json`**：选 frontmatter 单源。中心 JSON 与它
   描述的 skill 文件天然漂移，且 bijection 检查本身要消费者自著；frontmatter 让 per-file 成
   唯一真源，中心-vs-perfile 漂移结构性消失。
3. **增量只清泄漏 vs 完整统一（维护者已定完整统一）**：只清 "Trade Agent" 字面泄漏见效快，
   但中心-vs-perfile drift 与"消费者重造 taxonomy、gc 按约定耦合"的根因仍在 —— 故取完整统一。

## Guardrails

- `edit-write-guard`：改包源 `governance_core/**`（非宪法三文件）—— 允许，不触
  `/iterate-constitution` 门（本提案不改 total.md/agent.core.md/CLAUDE.md，故 Phase 0
  非 governance bootstrap 而是 docs-only 契约）。
- `constitutional-review` hook：改 registry / audit 代码须守 Art.4 零 `.get(k,default)` 兜底
  （沿用 `emit_bounded_injection` 现有 `_field` 成员测试模式）、Art.7 无 print / 无 Unicode 符号。
- `runtime_import_audit`：不新增 hook 的 `import governance_core`（本提案不动 hook import 面）。
- 打包隔离（第十一条 11.4）：若新增 schema 文件须进 `pyproject.toml` package-data，wheel 只含
  `governance_core*`。
- dogfood（11.3）：改完包源须 `governance-core upgrade --project-root .` 重装本 hub session。

## Phases

### Phase 0: 语义契约（docs-only，先行、低风险）— DONE

- Deliverables: 在 `knowledge_governance/skill-scenario-clusters.md` 记录 `theme` 作为
  per-skill 广度字段 + injection 派生规则 + 退休 `_tiers.json` 说明（非新字段）。
- Validation: `audit_knowledge` 不受影响（未引用新字段）。
- Exit criteria: theme pivot 方向已由维护者确认。

### Phase 1: 注入解耦核心 — DONE

- Deliverables: `SkillEntry.theme` + `_extract_metadata` 解析 `theme`；`emit_bounded_injection`
  注入池 = 所有 learned + `theme:universal` guide，**不再读 `_tiers.json`**。**无 backfill**
  （`theme` 早已在全部 shared skill 上）。
- Validation: 重写 `test_skill_injection_bounded.py`（9 cases：learned 恒入池 / theme:universal
  入池 / core-only 排除 / `_tiers.json` 被忽略回归守卫 / capping / cluster / surfaced）全绿；
  auditor 测试（18）不回归。
- Exit criteria: 注入从 theme 派生；hub dogfood 菜单正常。

### Phase 2: builder/catalog 派生自 theme + 去域化

- Deliverables: `build_skill_index.py` / `skill_catalog.py` 从 `theme` 派生分组（universal /
  core-only / <agent>）；删硬编码 `"Trade Agent"` TIER_TITLES 与 `TIER_ORDER`；停读 `_tiers.json`。
- Validation: INDEX.md 幂等再生；grep token-gate 确认包源无 "Trade Agent" skill-tier 残留。
- Exit criteria: builder 从 theme 派生；域泄漏清零。

### Phase 3: auditor + writer + candidate 收敛 + 退休 _tiers.json

- Deliverables: `audit_knowledge` Check 11/16 改校验 `theme`（替代 `_tiers.json` bijection）；
  `extract-skill.md` writer 退休"改 `_tiers.json`"步、去 "Trade Agent" 措辞（skill 创建即带 theme）；
  candidate collect 用 theme；删 `_tiers.json` 相关死码。
- Validation: 全 gc 测试套件（两种风格）；`/audit` 绿；dogfood `upgrade` 后 SessionStart 注入正常。
- Exit criteria: 单轴单字段（theme）；inject / index / audit / collect 四路都读 theme。

## Approval Criteria

> Concrete checks to tick before approval — derive from the spec above, don't restate
> goals. For a complex proposal include, as applicable:

- [ ] Every Field Dictionary entry names its governing `contracts/` file (or is N/A)
- [ ] Every user-facing capability / mutation has a named realizer (nothing implied-but-unbuilt)
- [ ] All Open Questions are resolved or explicitly deferred
- [ ] injection / index / audit / collect 统一派生自既有 `theme`，无新增 `reuse` 字段/枚举/契约
- [ ] `emit_bounded_injection` 停读 `_tiers.json`（回归守卫测试在）
- [ ] 包源 grep token-gate 无 "Trade Agent" skill-tier 残留（非仅路径表）
- [ ] `_tiers.json` 物理文件与 audit Check 11 的相关分支已退休（Phase 3）

## Validation Plan

- 单元：注入不变式 fixture（`reuse:universal` ↔ `_tiers.json.universal` 字节一致）、enum
  校验、INDEX.md 幂等再生、candidate collect 选集一致。
- 套件：从 repo 根跑 `tools/test_*.py`（pytest 风格 + script 风格**分别**跑，见记忆
  `gc-test-suite-two-styles`）；`python tools/audit_knowledge.py` 绿。
- de-domain 退出判据：`grep -ri "trade agent" governance_core/` 应只余合法多 agent enum，
  无 skill-tier 域泄漏（token grep-gate，非路径表，见记忆 `detrade-sweep-use-token-grep-gate`）。
- dogfood：`governance-core upgrade --project-root .` 后新 session SessionStart 注入行为正常
  （本 hub 无 `_tiers.json`，走 fallback/counts-only，不应崩）。
- 打包：`rm -r build; python -m build` 后核 wheel 含新 schema 文件（记忆
  `wheel-package-data-nonpy` / `stale-build-lib-cache-masks-file-removal`）。

## Rollback / Recovery

- 每 phase 独立 commit，可 `git revert`。
- Phase 1 注入改动带 `_tiers.json` fallback，最坏回退到旧中心化路径无需改消费者。
- `reuse` 字段迁移期为 optional（缺省空），未 backfill 的 skill 不 FAIL，可随时停在 additive 阶段。
- Phase 0 schema 为 docs-only，无运行时副作用，可单独 revert。

## Risks

- **注入语义位移**（中）：`reuse:universal` 池 > 旧 curated 列表 → 可能注入更多。缓解：cap 10 +
  score 排序 + fixture 不变式测试；文档显式说明位移。
- **消费者迁移期双读**（中）：frontmatter 与 `_tiers.json` 并存期语义要一致。缓解：fallback 仅在
  "无任一 reuse 声明"时触发，避免半迁移状态歧义；auditor 校验幂等再生。
- **打包漏出**（低）：新 schema 文件漏进 package-data → 消费者拿不到（记忆
  `wheel-package-data-nonpy`）。缓解：Phase 0 即加 package-data + wheel 内验证。
- **stale build/lib 掩盖删除**（低）：删硬编码后旧 wheel 残留。缓解：build 前 `rm -r build`。
- **dogfood 盲区**（低）：hub 无 `_tiers.json`，泄漏修复靠单元/fixture 而非症状复现（同记忆
  `hub-cannot-dogfood-crlf-drift` 之理）。缓解：fixture 测试覆盖多 agent 路径。

## State Log

- 2026-07-08: draft created by core agent (P-0118)
- 2026-07-08: draft → pending (submit for review: skill reuse frontmatter unification, decisions (full unify + 3-level universal/project/business) pre-decided by maintainer)
- 2026-07-08: pending → approved (user approval: 认可，批准; OQ leanings accepted (field=reuse, schema home=skill-scenario-clusters.md))
- 2026-07-08: approved → in-progress
- 2026-07-08: in-progress → implemented (spans bc95eee (Phase 0-1 registry/injection) + fa608cc (Phase 2-3). Reconcile deviations all benign: registry.py in the earlier commit; _tiers.json not touched (hub has no such file - retirement is code stop-reading; consumers delete theirs); pyproject.toml not touched (theme pivot added no new schema file). Extra touched: art_15 clause + session-context docstring (stale _tiers.json->theme pointer syncs) + test files (theme rewrites). candidate.py untouched by design.)
