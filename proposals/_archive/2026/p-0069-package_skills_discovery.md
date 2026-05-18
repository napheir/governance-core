---
id: P-0069
agent: core
status: implemented
created: 2026-05-18
approved_at: 2026-05-18
started_at: 2026-05-18
implemented_in: 44c8183
implemented_at: 2026-05-18
owner: core
---

# Proposal P-0069: Package skills.discovery (skill-learning machinery) into governance-core

## Trigger

Spun out of P-0068 Phase 3b. P-0068 (config-aware skills) found that the
skill-learning machinery behind `/extract-skill` and `/wrap-up` Steps 4a-4c —
`skills.discovery` (`tracker.py` / `extractor.py` / `registry.py` /
`__init__.py`, ~1439 lines) — was **never extracted into the governance-core
package** by P-0059. It still lives only in agent-core
(`agent-core/skills/discovery/`). Consequently `/extract-skill` and the
`/wrap-up` skill-learning steps reference a hardcoded `../agent-core` sibling
clone and cannot run in any governance-core consumer that is not agent-core.

P-0068 measured the machinery (4 files, 1439 lines, deeply coupled to
agent-core via the `shared-code-per-agent-state` pattern: `CODE_ROOT` is
derived to always point at agent-core, `resolve_project_root()` splits
code-location from per-agent state-location). That is a proposal-sized
extraction in its own right, so P-0068 spun it out here: P-0068 Phase 3b put
a **capability gate** on `/extract-skill` + `/wrap-up` Step 4 (skip cleanly
with `[capability pending P-0069]` when `skills.discovery` is not importable),
and this proposal carries the actual packaging.

Why PROPOSAL_REQUIRED: governance infrastructure (skill-learning loop) +
multi-phase + cross-repo extraction + affects every consumer + same
packaging-extraction class as P-0059 / P-0066 P1 / P-0068.

## Scope

### In-Scope

1. **Extract** `skills/discovery/` (tracker / extractor / registry /
   `__init__`) from agent-core into the governance-core package.
2. **De-couple from agent-core**: the `CODE_ROOT`-points-at-agent-core and
   `resolve_project_root()` per-agent-state model assumes code lives in one
   canonical sibling clone and runs from others. When the code lives **inside
   the installed package**, code-location is the package and state-location
   is the consuming project. Rework `__init__.py`'s resolver accordingly.
3. **Package layout + import path**: decide and lock — `governance_core/skills/
   discovery/` as `governance_core.skills.discovery`, vs a top-level
   `skills.discovery`. Wire `pyproject.toml` (`packages.find`, package-data)
   so the machinery ships in the wheel.
4. **Finalize skill wiring**: rewrite `/extract-skill` + `/wrap-up` Steps
   4a-4c to invoke the packaged machinery directly (no `PYTHONPATH`, no
   `../agent-core`); remove the P-0068 interim capability gate once the
   capability is present.
5. **State location**: learned-skill state (`.usage.json`, learned skill
   files) stays in the consuming project (`.claude/skills/learned/`), durable
   per P-0068 3a.

### Out-of-Scope (Non-Goals)

- Not P-0068's other buckets (already done) or P-0065 / P-0067.
- Not redesigning the skill-learning *algorithm* — extraction + de-coupling +
  packaging only.
- Not the candidate-promotion pipeline (P-0065).

## Non-Goals

参见 Scope.Out-of-Scope。本节保留位仅供归档审查工具识别。

## Guardrails

| Guard | 适用阶段 | 关注点 |
|-------|---------|--------|
| `edit-write-guard` | 全期 | 改 `governance_core/` 包源是公共层变更——改源、`upgrade` 回流 |
| `command-guard` | 全期 | `governance-core` CLI、`git push`、发版前明示 |
| `boundary-guard` | Phase 1 | 从 agent-core 取源是跨 boundary 读 |

## Phases

### Phase 0: 设计锁定

- Deliverables: 锁定包内布局 + import 路径（`governance_core.skills.discovery`
  vs `skills.discovery`）；锁定 code-location vs state-location 的新解析模型
- Validation: 设计经 user review
- Exit criteria: 布局 / import / 解析模型定案

### Phase 1: 抽取 + 去 agent-core 耦合

- Deliverables: 把 4 个文件抽进 `governance_core/`；重写 `__init__.py` 解析器
  （code = 包，state = 消费项目）；`pyproject.toml` 打包配置
- Validation: `python -m build` 产物含 machinery；无 `../agent-core` 依赖
- Exit criteria: machinery 随包发布、可导入

### Phase 2: 接线 + 去 P-0068 interim gate

- Deliverables: `/extract-skill` + `/wrap-up` 4a-4c 改用打包后的 machinery；
  移除 P-0068 的 `[capability pending P-0069]` 门控
- Validation: 自托管 gc 跑 `/extract-skill` → 产出 learned skill；`/wrap-up`
  4a-4c 跑通
- Exit criteria: skill-learning 在任何消费者可用,无 agent-core 依赖

### Phase 3: 验证 + 文档 + 发版

- Deliverables: doctor / build 验证；architecture.md 记 machinery 已打包；
  gc patch bump + GitHub Release
- Validation: doctor 通过；dogfood `/extract-skill` 在 gc 跑通
- Exit criteria: 发布,消费者 `upgrade` 即得 skill-learning

## Approval Criteria

User 在批准前应能确认：

1. `skills.discovery` 是 P-0059 抽包漏项，本 proposal 补完（同 P-0066 P1 类）
2. 抽取 + 去 agent-core 耦合（code=包 / state=消费项目）+ 打包 + 接线
3. P-0068 已留 interim 门控,本 proposal 完成后移除门控
4. learned skill state 仍留消费项目,不进包

## Validation Plan

- Phase 1：`python -m build` 产物含 `skills.discovery`；grep 无 `../agent-core`
- Phase 2：自托管 gc dogfood `/extract-skill` + `/wrap-up` 4a-4c
- Phase 3：doctor + 文档

## Rollback / Recovery

- 每 phase 是 gc repo 独立 commit,可逐 phase `git revert`
- 抽取的 machinery 是新增 `governance_core/` 子树,删之即回；P-0068 的
  interim 门控在门控移除前一直是安全网

## Risks

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 去 agent-core 耦合改坏 code/state 分离 → state 写错位置 | 中 | 高 | Phase 0 锁解析模型；Phase 2 dogfood 验证 state 落点 |
| import 路径选择影响既有 agent-core 调用 | 中 | 中 | Phase 0 评估；agent-core 回归（其自身 session）|
| 1439 行抽取带入 agent-core 专属假设 | 中 | 中 | Phase 1 逐文件审；grep 兜底 |

## State Log

- 2026-05-18: draft created by core agent (P-0069) - spun out of P-0068 Phase 3b
- 2026-05-18: draft → pending (ready)
- 2026-05-18: pending → approved (user directed: continue P-0069)
- 2026-05-18: approved → in-progress (begin Phase 0)
- 2026-05-18: in-progress → implemented (P-0069 complete - 4 phases)
