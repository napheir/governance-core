---
id: P-0070
agent: core
status: implemented
created: 2026-05-18
approved_at: 2026-05-18
started_at: 2026-05-18
implemented_in: f09648c
implemented_at: 2026-05-18
owner: core
---

# Proposal P-0070: Governance tooling fixes -- 3 reconciliation gaps surfaced by P-0065 dogfood

## Trigger

Executing P-0065 (governance convergence hub) over six phases, each phase's
`/wrap-up` audit surfaced three pre-existing governance-tooling defects.
None was in P-0065's scope; all were recorded in the P-0065 archive State
Log as "out-of-scope, deferred". User directed filing them as their own
proposal (2026-05-18).

All three are **reconciliation gaps** -- a tool that did not fully catch up
with an earlier structural change (P-0066 self-hosting, P-0069 discovery
packaging), latent until P-0065's dogfood exercised it.

**A. `audit_proposals.py` resolves the wrong shared_state.**
It looks for in-flight proposals and `_id_ledger.json` under
`<install_root>/shared_state/` (the parent workshop directory) instead of
the self-hosted repo's own `shared_state/`. Result: `audit_proposals.py`
reports `in-flight=0` when P-0065 was in-flight, and `FAIL [ledger]:
_id_ledger.json does not exist`. `proposal_lib.py` resolves the same path
**correctly** (it found P-0065 under the repo's own `shared_state/`), so the
two tools disagree. A P-0066-era (self-hosting) gap.

**B. `tracker --should-extract` reports a false reason.**
`should_extract()` returns False for two distinct reasons -- (1) session
complexity below threshold, or (2) an extraction already happened today.
The CLI unconditionally prints `[NO] Not enough complexity for extraction
yet` with `Complexity: N (threshold: 5)`, even when `N >> 5` and the real
reason is (2). Observed every P-0065 wrap-up (complexity 24..30, all >= 5,
all mislabeled "not enough complexity") -- because P-0065 Phase 3 ran one
`/extract-skill`, every later `should_extract()` that day hit branch (2).
`should_extract()`'s logic is correct; only the CLI's reason-reporting is
wrong. A P-0069-era gap (the tracker was packaged in P-0069).

**C. `upgrade` never prunes stale autonomy-layer files.**
`governance-core install/upgrade` is copy-based and purely additive: it
overwrites and adds, never removes. A file deleted from the package source
(e.g. P-0069 deleted the `shared-code-per-agent-state` skill guide) leaves a
stale copy in the consumer's autonomy layer, which the skill registry still
discovers and lists. A P-0066/P-0069-era gap.

Why PROPOSAL_REQUIRED: changes governance infrastructure (`audit_proposals.py`,
`discovery/tracker.py`, `installer.py`); fix C is security-sensitive (it
deletes files from the autonomy layer). Multi-fix.

## Scope

### In-Scope

1. **Fix A** -- `tools/audit_proposals.py` reads `shared_state_root` from
   `.governance/config.json` (the source `proposal_lib.py` already uses)
   instead of computing an install-root-relative path.
2. **Fix B** -- `discovery/tracker.py` CLI: when `should_extract()` is False,
   report the actual reason -- "already extracted today" vs "complexity
   below threshold" -- instead of always claiming insufficient complexity.
3. **Fix C** -- `installer.py` `upgrade` prunes stale autonomy-layer files:
   after computing the new install set, any path in the **previous**
   `installed_files.json` manifest that is absent from the new set is
   removed. Prune runs **after** P-0065's `_capture_drift` (a locally-edited
   stale file is first captured as a drift candidate, then pruned -- no
   silent loss). Reported like drift, on stderr.

### Out-of-Scope (Non-Goals)

- **Not** changing `should_extract()`'s extraction heuristic or threshold --
  Fix B is purely the CLI's reason message.
- **Not** pruning business / authored files -- only paths recorded as
  install-managed in the prior manifest are prunable; files absent from the
  manifest (business files, the `.claude/skills/learned/` carve-out) are
  never touched.
- **Not** a redesign of the copy-based installer -- prune is an additive
  reconciliation step, not a switch to a different sync model.
- **Not** addressing the CI Node.js 20 deprecation (separate hygiene item).

## Non-Goals

参见 Scope.Out-of-Scope。本节保留位仅供归档审查工具识别。

## Guardrails

| Guard | 适用阶段 | 关注点 |
|-------|---------|--------|
| `edit-write-guard` | Phase 1/2 | `audit_proposals.py` / `tracker.py` / `installer.py` 是 install-managed -- 改 `governance_core/` 包源、不碰自治层副本（宪法第十一条） |
| 文件删除安全 | Phase 2 | prune 删自治层文件 -- 只删旧 manifest 内记录的 install-managed 路径；business / authored / `learned/` 永不删；prune 在 `_capture_drift` 之后 |
| `command-guard` | Phase 2 | `governance-core upgrade` dogfood 调用前明示 |
| `boundary-guard` | 全期 | 在 governance-core 自身 session（self-hosted）执行 -- 改包源 in-boundary |

## Phases

### Phase 1: 报告修正（Fix A + Fix B）

两个小的"工具报告了错误信息"修复，合并一个 phase、一个 commit。

- Deliverables:
  - `tools/audit_proposals.py`：从 `.governance/config.json` 的
    `shared_state_root` 解析 in-flight 目录与 `_id_ledger.json`，与
    `proposal_lib.py` 一致。
  - `discovery/tracker.py` CLI（`--should-extract`）：`should_extract()` 为
    False 时区分原因 -- "今日已提取" / "复杂度不足"，打印对应文案；JSON
    输出（`stats`）可附 `should_extract_reason` 字段。
  - gc 版本 bump + 文档（如需）。
- Validation: 自托管 gc 跑 `audit_proposals.py` -- 正确报告 in-flight 计数、
  不再误报 ledger 缺失；构造"今日已提取"与"复杂度不足"两态，验 CLI 文案各自
  正确。
- Exit criteria: 两个工具对自托管布局报告准确。

### Phase 2: upgrade 自治层 prune（Fix C）

- Deliverables:
  - `installer.py`：`upgrade` 在 `_capture_drift` 之后、写新 manifest 之前，
    比对旧 `installed_files.json` 与新 install 集；旧有新无的 install-managed
    路径 -> 删除（prune）。空目录顺带清理。
  - prune 报告（stderr，与 drift 报告并列）：N 个陈旧文件已 prune。
  - 安全边界：只 prune 旧 manifest 内的路径；首次 install 无旧 manifest ->
    不 prune；缺失文件 -> 跳过不报错。`--no-prune` 逃生口（可选）。
  - gc 版本 bump + 文档。
- Validation: 在 manifest 有记录后，删一个包源文件 + `upgrade` -> 验对应
  自治层副本被 prune、business/authored 文件未动、`learned/` 未动；验
  P-0069 残留的 `shared-code-per-agent-state` 旧 guide 被清除。
- Exit criteria: 包源删除的文件不再在消费者自治层残留；registry 不再发现
  陈旧 guide。

## Approval Criteria

User 在批准前应能确认：

1. 三个 fix 都是 reconciliation 缺口的修复，非新功能；P-0065 dogfood 已暴露、
   已记入 P-0065 归档提案 State Log。
2. Fix B 只改 CLI 文案，不动 `should_extract()` 的提取启发式。
3. Fix C 的 prune **只删** 旧 manifest 内的 install-managed 路径，business /
   authored / `learned/` 永不删；且 prune 在 drift 捕获之后（陈旧但被本地改过
   的文件先成候选、不丢失）。
4. 2 phase，每 phase 独立可交付、可单独 revert。

## Validation Plan

- Phase 1：自托管 gc 跑 `python tools/audit_proposals.py` 验 in-flight /
  ledger 报告正确；构造 tracker 两态验 `--should-extract` 文案。
- Phase 2：人为删一个包源文件 -> `governance-core upgrade` -> 验自治层副本
  被 prune、非 install-managed 文件未动；专门验 `shared-code-per-agent-state`
  旧 guide 清除、registry 不再列它。
- 全程：gc 自身 self-hosted 实例 dogfood。

## Rollback / Recovery

- **Phase 1**：`audit_proposals.py` / `tracker.py` 改动 `git revert`；纯报告
  逻辑，revert 即回旧行为。
- **Phase 2**：`installer.py` prune 逻辑 revert -> 回到纯 additive upgrade；
  prune 是删除动作，但删的是包源已移除的文件 -- revert 后这些文件单纯重新
  残留，无数据丢失风险（被本地改过的已由 drift 捕获）。`--no-prune` 亦可
  运行时关闭。
- 总体：每 phase 独立 commit，可逐 phase revert。

## Risks

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| prune 误删 business / authored 文件 | 低 | 高 | 只 prune 旧 manifest 内路径；manifest 仅含 install-managed；`learned/` 等 carve-out 不在 manifest -> 天然安全；Phase 2 显式验证非 install-managed 文件未动 |
| prune 删掉被本地改过的陈旧文件 -> 改动丢失 | 低 | 中 | prune 在 P-0065 `_capture_drift` 之后 -- 漂移先被捕获成候选，再 prune |
| `audit_proposals.py` 仍有其他自托管路径假设 | 中 | 低 | Phase 1 验证以实际自托管 gc 跑通为准；如发现更多就地修 |
| tracker JSON 输出新增字段破坏下游 | 低 | 低 | 新增 `should_extract_reason` 为附加字段，旧消费者忽略即可 |

## State Log

- 2026-05-18: draft created by core agent (P-0070)
- 2026-05-18: draft → in-progress（user approve P-0070）。
- 2026-05-18: Phase 1 提交（commit 0b5b870）—— Fix A：`audit_proposals.py` 改用
  `load_proposals_config` 解析 in-flight 目录 + ledger（与 `proposal_lib.py`
  一致）；Fix B：`tracker.py` 加 `should_extract_reason()`，CLI 区分
  "already-extracted-today" / "below-threshold" / "recommended"，stats 加
  `should_extract_reason` 字段。验证：自托管 gc `audit_proposals` 报
  in-flight=1/archive=4/0 failures（ledger FAIL 消失）；`--should-extract`
  正确报"already extracted today"；`should_extract_reason` 单测 2 态。
- 2026-05-18: Phase 2 提交（commit f09648c）—— Fix C：`installer.py` 加 `_prune_stale`，
  `upgrade` 在 `_capture_drift` 之后、写新 manifest 之前比对旧 manifest 与新
  install 集，旧有新无的 install-managed 路径删除（manifest-diff = 安全边界，
  business/authored/`learned/` 从不进 manifest 故从不被删），`[prune]` 报告 +
  空目录清理；`cli.py` 加 `--no-prune`；版本 0.2.0→0.2.1；docs。验证：
  `_prune_stale` 单测 5 项（删陈旧/留在用/不碰非 manifest business 文件/无
  manifest no-op/缺失路径跳过）；探针文件真实 dogfood（装入→源删→upgrade
  prune→`[prune]` 报告→自治层副本消失）；upgrade/doctor exit 0；build 0.2.1。
  说明：prune 是 manifest-diff，只清 manifest 出现（P-0065 Phase 2）之后变
  陈旧的文件；P-0069 早于 manifest 删的 `shared-code-per-agent-state.md` 不在
  任何 manifest、由本 phase 一次性手动清理（registry 已不再列它）。
- (原 draft 撰写记录) 提案撰写完成 —— 3 个 P-0065 dogfood 暴露的治理工具缺口
  （audit_proposals 自托管路径 / tracker CLI 误报原因 / upgrade 不 prune），
  组织为 2 phase（报告修正 / upgrade prune）。待 user 审阅。
- 2026-05-18: draft → pending (user approved)
- 2026-05-18: pending → approved (user approved)
- 2026-05-18: approved → in-progress (Phase 1 started)
- 2026-05-18: in-progress → implemented (P-0070 both phases implemented (0b5b870, f09648c))
