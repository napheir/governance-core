---
id: P-0068
agent: core
status: implemented
created: 2026-05-18
approved_at: 2026-05-18
started_at: 2026-05-18
implemented_in: 40ac2f3
implemented_at: 2026-05-18
owner: core
---

# Proposal P-0068: Config-aware skills - single-agent degradation + de-hardcode + capability completeness

## Trigger

P-0066 made governance-core self-hosted under a **single core-agent** topology
and degraded the constitution *clauses* accordingly — Art.5 (cross-agent) and
Art.12 (scope) are explicitly marked "继承条款，单 agent 下退化". But the
*skills* the package ships (`governance_core/commands/*.md`,
`governance_core/skills/`) were left as the original **multi-agent** versions.

P-0066's own closing review exposed it. Reading `/wrap-up` (the skill Art.14
*mandates*) against self-hosted single-agent gc: of its 9 sub-steps, only 2
apply cleanly (git commit, output checklist); the rest are broken or wrong.

Since Art.99 makes the skill the authoritative procedure ("Skill 单一权威源")
and Art.14 makes `/wrap-up` mandatory, **a skill that cannot run = broken
governance**. P-0066 degraded the clauses; it did not touch the skills, so the
project has a constitution and a wrap-up clause it cannot actually execute.

### Guiding principle — install-and-get-everything (安装完即所得)

The package always ships the **complete** capability set, multi-agent
capabilities included. A consumer's topology changes only **which steps run**,
never **which capabilities are present**. Single-agent consumers degrade
multi-agent steps to *not run*; they never *lack* the capability. No topology
gets a stripped-down package; no consumer hand-rolls a missing capability.

### Tri-bucket model (locked in Phase 0)

Every skill step audited falls into exactly one bucket:

- **Bucket A — broken paths.** Hardcoded cross-repo references
  (`../agent-core/...`, `PYTHONPATH=../agent-core`, `skills.discovery` imports,
  absolute `~/workshop-claude/agent-core/...`) — P-0059 extraction leftovers.
  Bugs in **any** topology. Fix: de-hardcode.
- **Bucket B — genuinely multi-agent steps.** Cross-clone merge, cross-agent
  knowledge publish, cross-clone infra sync. The **package keeps the full
  multi-agent capability**; under single-agent topology the step **degrades to
  not-run** (explicit skip). Compatibility, not exclusion.
- **Bucket C — runs for single-agent too, but is broken/incomplete.** Lesson
  classification & archival, skill extraction & refinement, STATE.md upkeep.
  A single agent genuinely performs these — they are **not** degraded to skip;
  they are **fixed so they actually run** for single-agent gc.

Why PROPOSAL_REQUIRED: governance infrastructure (skills are the authoritative
procedures, Art.99) + multi-phase + affects every consumer + same
packaging-extraction defect class as P-0059/P-0066.

## Scope

### In-Scope

1. **Skill audit + tri-bucket classification** of every package-shipped skill
   (`governance_core/commands/*.md`, `governance_core/skills/**`). Done in
   Phase 0 — see "Phase 0 — Locked decisions" below.
2. **Bucket A — de-hardcode**: remove every hardcoded cross-repo reference;
   paths resolve within the consuming project or the installed package. Fixes
   apply to all topologies.
3. **Bucket B — degrade to not-run, keep capability**: genuinely multi-agent
   steps read `.governance/config.json`; under single-agent topology
   (`len(agents)==1`) they emit an explicit "N/A — single-agent topology —
   skipped" and do nothing. The multi-agent capability stays fully shipped and
   fully functional for multi-agent consumers.
4. **Bucket C — fix so it runs for single-agent**. Hard rule: **reuse, never
   fork** — re-provision adapts only a skill's topology-dependent *edges*
   (paths, destinations, git treatment), reusing the existing unified decision
   logic verbatim; never a parallel gc-specific copy (Art.99 单一权威源).
   - **4a. Lesson classification & archival.** The classification *decision
     logic* is the existing `lesson-classification` skill and stays the single
     unified authority — P-0068 builds no gc-specific classifier. The archival
     **destinations stay byte-identical** to the multi-agent ones
     (`.claude/skills/`, `.claude/skills/learned/`, `knowledge/`, etc.) — the
     routing config is **not** diverged. The only real difference between
     topologies is git durability: gc gitignores its autonomy layer, so a
     lesson written to an authored-content destination there would be lost on
     reclone. Solution: gc's `.gitignore` carves out the **authored-content
     destination subpaths** as committed `!` exceptions (e.g.
     `!/.claude/skills/learned/`, the authored-knowledge subpath). Identical
     destinations; the topology difference is confined to `.gitignore`, which
     is inherently a per-project file.
   - **4b. Skill extraction & refinement.** The `skills.discovery` machinery
     (tracker / extractor / registry behind `/extract-skill` + auto-refine) is
     **not in the governance-core package** — agent-core infrastructure P-0059
     never extracted. **Locked decision: package it** into `governance_core/`
     as a real importable subpackage so `/extract-skill` + auto-refine work for
     every consumer (install-and-get-everything). If the machinery proves
     large, it MAY spin out as its own proposal — P-0068 keeps the decision +
     the `/wrap-up` wiring, the spun-out proposal carries the code.
   - **4c. STATE.md upkeep.** `/wrap-up` Step 1 maintains a `STATE.md`
     session-bridge; `session-context.py` reads it; `rotate_state.py` archives
     stale entries. **Locked decision: the STATE.md capability lives in the
     package** — `rotate_state.py` is already package-resident; `/wrap-up`
     Step 1 must target the **local installed** `tools/rotate_state.py` (a
     bucket-A fix, not `../agent-core/`); the installer seeds an initial
     `STATE.md` so a fresh consumer has one without hand-rolling it. gc adopts
     a committed `STATE.md`.
5. **`/wrap-up` first and end-to-end**: it is the skill Art.14 mandates — all
   9 sub-steps must apply, skip cleanly (B), or run (C), with no broken step.

### Out-of-Scope (Non-Goals)

- Not rewriting skill intent/logic — path sanitization, topology gating, git
  treatment only.
- Not P-0067 (installer emits settings.local.json) or P-0065 (candidate
  pipeline).
- Not changing multi-agent behavior for multi-agent consumers — A fixes apply
  to all; B/C adaptations trigger only on single-agent topology.

## Non-Goals

参见 Scope.Out-of-Scope。本节保留位仅供归档审查工具识别。

## Guardrails

| Guard | 适用阶段 | 关注点 |
|-------|---------|--------|
| `edit-write-guard` | 全期 | 改 `governance_core/commands` `governance_core/skills` 是公共层变更——改包源、`upgrade` 回流 |
| `command-guard` | 全期 | `governance-core` CLI、`git push`、发版前明示 |
| `constitutional-review` | 全期 | skill 是治理文档；改动须符合 Art.99（指针+阻塞规则，不复述步骤） |

## Phase 0 — Locked decisions (2026-05-18, user-reviewed)

**Audit (12 commands).** Bucket-tagged: `wrap-up` (A: rotation path /
PYTHONPATH; B: 2b/5/5b; C: lesson, skill-extract, STATE.md), `extract-skill`
(A: PYTHONPATH×4; C: skills.discovery unpackaged), `sync-repos` (A: STATE.md
refs; B: whole skill = cross-clone merge), `sync-infra` (B: deploy-to-clones),
`publish-knowledge` (B: `git fetch ../agent-<name>`), `update-skill` (A:
absolute `~/workshop-claude/agent-core`, `cd ../$clone`; B: cross-clone),
`dashboard` (B: cross-agent), `proposal` / `iterate-constitution` (minor
multi-agent prose; `proposal_lib` already fixed in P-0066 P1), `audit` /
`inventory` / `learn` (≈clean). The 16 `skills/*.md` are mostly *guide*
documents (not step-procedures); fixes there are text-accuracy
(`cross-clone-base-promotion`, `shared-code-per-agent-state` = multi-agent
guides — label scope; `lesson-classification`, `_template` = de-hardcode the
agent-core prose).

**Decision 1 — lesson archival destinations stay identical.** No remap. The
`lesson-classification` routing config is byte-identical across topologies.
gc durability is handled by `.gitignore` `!` carve-outs on the
authored-content destination subpaths — confined to `.gitignore`.

**Decision 2 — package `skills.discovery`** (option a). Spin-out allowed if
large.

**Decision 3 — infra = compatibility, degrade to not-run.** `sync_infra` /
`/sync-repos` keep their full multi-agent capability in the package; under
single-agent topology they degrade to not-run. No "degrade into an
upgrade-check". (The `governance-core upgrade` dogfood loop is a separate,
pre-existing mechanism — constitution 11.3 / core-manual — not a `/wrap-up`
step.) **Infra is bucket B**, not C.

**Decision 4 — STATE.md capability in the package.** gc adopts a committed
`STATE.md`; `rotate_state.py` stays package-resident; `/wrap-up` Step 1 targets
the local `tools/` copy; the installer seeds an initial `STATE.md`.

## Phases

### Phase 0: 全量审计 + 三桶分类 + 决策锁定 — DONE

Audit + tri-bucket classification + 4 decisions locked (see above), user-reviewed
2026-05-18.

### Phase 1: 桶 A — 去硬编码

- Deliverables:
  - 移除全部硬编码跨 repo 引用：`wrap-up` Step 1 rotation 改指本地
    `tools/rotate_state.py`；`extract-skill` 的 `PYTHONPATH=../agent-core` ×4；
    `update-skill` 的绝对路径 `~/workshop-claude/agent-core` + `cd ../$clone`；
    `lesson-classification` / `_template` 的 agent-core 文案
  - gc patch bump
- Validation: 无 `../agent-core` 兄弟 clone 的环境跑受影响命令无 ENOENT；
  grep `\.\./agent-` / `agent-core` / `skills\.discovery` 仅剩合理残留（如
  guide 文档对多 agent 的描述性提及），无可执行硬编码
- Exit criteria: skill 不再有可执行的硬编码跨 repo 引用

### Phase 2: 桶 B — 多 agent 步骤降级为不跑（能力保留在包）

- Deliverables:
  - `publish-knowledge` / `sync-repos` / `sync-infra` / `dashboard` 跨 agent 步
    骤、`wrap-up` 2b/5/5b 加 config 门控：单 agent 拓扑显式 "N/A —
    single-agent — skipped" 不动作；多 agent 能力完整保留
  - skill 文本同步降级条件标注（遵 Art.99，指针式）
- Validation: 单 agent config 跑 → 干净 skip 带原因；多 agent config 跑 → 行为不变
- Exit criteria: B 类步骤单 agent 不跑、不报错；多 agent 全功能

### Phase 3: 桶 C — 修到单 agent 能跑（解法 + 验证）

- Deliverables:
  - **3a 教训分类归档**：分类判定逻辑复用 `lesson-classification` skill 原样不
    动；归档落点跨拓扑一致；gc `.gitignore` 给授权写入子路径开 `!` 例外，使
    落点 committed；`/wrap-up` Step 4.0 在单 agent gc 走通分类→归档
  - **3b skill 提取与精炼**：把 `skills.discovery`（tracker/extractor/registry）
    打包进 `governance_core/` 成可导入子包；`/extract-skill` + auto-refine 在
    任何消费者可用
  - **3c STATE.md**：gc 建 committed `STATE.md`；installer 播初始 `STATE.md`
    模板；`/wrap-up` Step 1 指本地 `tools/rotate_state.py`
- Validation:
  - 3a：跑一次 lesson-classification → 落点 `git status` 可见为 tracked-able
  - 3b：自托管 gc 跑 `/extract-skill` → learned skill 落 committed 位置、
    registry 可发现；auto-refine 按实际步骤更新
  - 3c：全新装一个消费项目 → 即有 `STATE.md`；`/wrap-up` Step 1 rotation 跑通
- Exit criteria: C 类三项在单 agent gc 实际可跑,均通过验证

### Phase 4: `/wrap-up` 端到端 dogfood

- Deliverables:
  - `/wrap-up` 在自托管单 agent gc 端到端跑通：9 子步骤全部 apply / 干净
    skip(B) / 实际执行(C),无 broken step
  - gc 自身 `governance-core upgrade` 回流,用新 skill
- Validation: gc 自身 session 跑 `/wrap-up`,输出完整检查清单、无 broken/ENOENT
- Exit criteria: Art.14 在 gc 可被实际、完整执行——宪法与技能闭合

### Phase 5: 文档 + 发版

- Deliverables:
  - architecture.md / core-manual.md 记三桶模型 + "安装完即所得"原则
  - gc patch bump + GitHub Release（人工确认后）
- Validation: doctor 通过；文档准确
- Exit criteria: 配置感知的 skill 发布,消费者 `upgrade` 即得

## Approval Criteria

User 在批准前应能确认：

1. 问题定性：P-0066 降级了宪法条款但漏了 skill；`/wrap-up` 对单 agent gc 半残
2. **安装完即所得**：包永远带完整能力（含多 agent）；拓扑只决定哪些步骤*跑*，
   不决定哪些能力*在*
3. 三桶：A 去硬编码（全拓扑）/ B 多 agent 步骤单 agent 降级为不跑、能力留包 /
   C 单 agent 照样跑、修到能跑
4. C 类**复用不 fork**：只动拓扑边缘（路径/落点/git 处置），判定逻辑沿用现有
   统一 skill；4a 落点跨拓扑一致，差异只落在 `.gitignore`
5. 本 proposal 是公共层变更，按 P-0063 在 gc repo 改、消费者 `upgrade` 回流

## Validation Plan

- Phase 1：受影响命令在无 `../agent-core` 环境跑通；可执行硬编码 grep 零命中
- Phase 2：单/多 agent 双 config 验 B 类步骤行为
- Phase 3（逐项）：3a 落点 committed / 3b `/extract-skill`+auto-refine 可用 /
  3c 新装项目即有 STATE.md 且 rotation 跑通
- Phase 4：gc 自身 `/wrap-up` 端到端，输出完整检查清单、无 broken step
- Phase 5：doctor + 文档核对

## Rollback / Recovery

- **Phase 0**：纯设计（已完成，决策锁定）
- **Phase 1/2/3**：`governance_core/commands` `governance_core/skills`
  （及 3b 的 `governance_core/skills/discovery`、installer 的 STATE.md seed）
  改动 `git revert`
- **Phase 4**：dogfood / `STATE.md` 改动 revert
- **Phase 5**：文档 + 发版；发版不可撤,skill 行为可由 revert + republish 修正
- 总体：每 phase gc repo 独立 commit,可逐 phase revert

## Risks

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 把 C 类误当 B 类 skip 掉 → 静默丢失治理能力 | 中 | 高 | 三桶分类已 user-review 锁定；C 类每项必须有解法+验证才算 Exit |
| C 类再供给时为单 agent 另造并行判定逻辑 → 分叉 | 中 | 高 | Scope 硬规则"复用不 fork"；4a 落点跨拓扑一致、不 remap；review 查无新增分类器 |
| 打包 `skills.discovery` 体量过大撑大 P-0068 | 中 | 中 | 过大则机制部分 spin out 独立 proposal，P-0068 留决策+wiring |
| 降级门控误判拓扑 → 多 agent 项目步骤被误 skip | 中 | 高 | 判据单一（`len(agents)`）；Phase 2 双 config 验证 |
| `.gitignore` carve-out 漏某授权写入子路径 → 仍丢失 | 中 | 中 | 3a 验证显式查 `git status` tracked-able |
| skill 文本改动违 Art.99（复述步骤）| 中 | 中 | 改动走 review；只加降级/边缘条件标注 |

## State Log

- 2026-05-18: draft created by core agent (P-0068)
- 2026-05-18: body authored - follow-up surfaced by P-0066 closing review
- 2026-05-18: revised after user review - tri-bucket model (A/B/C)
- 2026-05-18: revised after 2nd user review - "reuse, never fork" hard rule
- 2026-05-18: draft -> pending -> approved -> in-progress
- 2026-05-18: Phase 0 done - audit + 4 decisions locked after user review:
  (1) lesson archival destinations stay identical, gc durability via
  .gitignore carve-out (no remap); (2) package skills.discovery; (3) infra is
  bucket B - degrade to not-run, capability stays in package, no
  "upgrade-check" re-shape; (4) STATE.md capability lives in the package, gc
  adopts a committed STATE.md. Guiding principle locked: install-and-get-
  everything. Infra moved C->B; bucket C is now lesson / skill-extraction /
  STATE.md.
- 2026-05-18: in-progress → implemented (P-0068 complete - 6 phases, all committed)
