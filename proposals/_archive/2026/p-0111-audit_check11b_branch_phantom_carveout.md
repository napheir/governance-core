---
id: P-0111
agent: core
status: implemented
created: 2026-06-24
approved_at: 2026-06-24
implemented_in: 6107ce2
implemented_at: 2026-06-24
owner: core
---

# Proposal P-0111: Check 11b: non-hub branch-tier phantom WARN carve-out (symmetry with 11a/16a)

## Trigger

下游消费者 Trade Agent 报 gc #114（`trade`/`core` clone 联合诊断）：
`audit_knowledge.py` Check 11b（tiers→registry phantom）缺少 Check 11a / Check 16
都有的 non-hub 豁免，与 `_tiers.json` `branch` tier 的"全局同步一份 / 文件 branch-local"
结构错配叠加后，在非拥有者 clone 里产生**无任何本地动作可清零**的 phantom FAIL，
阻塞每个消费者的 `/publish-knowledge` `Failed=0` 门。改治理 FAIL 门行为 = 治理体系
变更，按宪法第十三条走 proposal。

## Current State (read, not assumed)

读自 gc 0.38.1（`governance-core version` 确认）：

- `governance_core/tools/audit_knowledge.py:412-422` —— Check 11b phantom 循环对
  `phantoms = all_tier_entries - md_skills` 中**每一项无条件 `failed += 1`**，零豁免。
- `audit_knowledge.py:387-403` —— Check 11a（registry→tiers）**有** non-hub-learned
  豁免（`:390` `if non_hub and name in learned_skills:` → WARN，gc #101/P-0104）。
- `audit_knowledge.py:534-557` —— Check 16 16a（coverage）**有两个**豁免：`:536`
  `command` 豁免（gc #102/P-0105）、`:544` non-hub-learned → WARN（gc #101/P-0104）。
- `audit_knowledge.py:309-321` —— `_detect_non_hub(root)` 已存在（default-strict，
  仅 config 正向识别 consumer_id 才 True），11b 已可直接复用（`:372` 已取 `non_hub`）。
- `build_skill_index.py:38` / `skill_catalog.py:33` —— `TIER_ORDER` 含 `branch`；
  `branch` tier body 是无 per-skill ownership 标注的扁平 `skills: []` 列表
  （`audit_knowledge.py:374-376` 同样读法），故"哪个 branch 拥有此条目"无数据可查。
- `governance_core/tools/test_pending_catalog_tolerance.py` —— 现成的 11a/16a 豁免
  回归测试，已有 `_tiers` / `_config` / `_guide_skill` helper，可直接扩 11b 用例。

**死锁**：`branch`-tier skill 文件 branch-local，`_tiers.json` 全局同步一份。非拥有者
clone 里：留文件 → 16a FAIL（既非 universal 又无法跨 ownership 入 cluster）；删文件
→ 11b phantom FAIL（同步来的列表仍列着）。两条路皆 FAIL，无本地可同时清零的动作。

## Scope

`governance_core/tools/audit_knowledge.py` 的 `_audit_skill_tiers` Check 11b 段
（`:412-422`）：对**仅**归属 `branch` tier 的 phantom，在 `non_hub` clone 下降级为
WARN（镜像 11a/16a 既有 `_detect_non_hub` 豁免）。新增回归测试到
`governance_core/tools/test_pending_catalog_tolerance.py`。**无契约文件变更**
（`_tiers.json` schema 不变）。

## Design & Contract

> Proportionate. Trivial change: one line "implementation self-evident; no interface
> or data-flow change." Otherwise fill all three sub-parts; use "N/A — <reason>" for
> any that genuinely doesn't apply — never leave a placeholder.

### Interfaces, I/O & Realization

唯一改的边界是既有内部函数 `_audit_skill_tiers(root: Path, tiers_path: Path)
-> tuple[int, int]`（签名不变）。Check 11b phantom 循环改为先算每个 phantom 的
归属 tier 集，再分支判定：

- INPUT：`tier_to_skills`（已构建，`:374-376`）、`md_skills`（已构建，`:362-365`）、
  `non_hub`（已取，`:372`）。无新读取源。
- OUTPUT：`(failed, warned)` 计数 —— 对 `non_hub and home_tiers == {"branch"}` 的
  phantom，由 `failed += 1` 改为 `warned += 1` + WARN 日志；其余 phantom 不变。

realizer：`audit_knowledge.py` 这一个 CLI/库函数即 end-to-end 执行者（消费者经
`python tools/audit_knowledge.py` 或 `/publish-knowledge` 间接调用），无新执行组件。

伪代码：
```python
branch_only = lambda n: {t for t, names in tier_to_skills.items() if n in names} == {"branch"}
for name in sorted(phantoms):
    if non_hub and branch_only(name):
        logger.warning("  WARN: branch-tier entry %r absent in this clone ...", name)
        warned += 1
    else:
        logger.warning("  FAIL: _tiers.json entry %r ... (phantom)", name)
        failed += 1
```
取 `home_tiers == {"branch"}`（仅 branch 为唯一 home）而非 `name in branch_entries`：
避免同时挂在 universal/project 的 phantom 被错误降级（那仍是真 FAIL）。

### Field Dictionary

无跨边界持久化 / 跨 agent 新字段；仅复用既有 in-memory 结构。N/A — 治理它们的
`contracts/proposal_frontmatter_schema.md` 等不涉及；`_tiers.json` schema 不变。

| field | type | meaning | producer | consumer | constraints / allowed values |
|-------|------|---------|----------|----------|------------------------------|
| (无新增) | — | — | — | — | — |

### Flow

`_tiers.json` (branch tier, 全局同步) → `_audit_skill_tiers` 算 phantom →
`_detect_non_hub(root)` 判 clone 身份 → branch-only phantom 在 non-hub 下计 WARN
（否则 FAIL）→ `(failed, warned)` 汇总进 `main()` 的退出码 / `/publish-knowledge` 门。

## Non-Goals

- **不改 `_tiers.json` schema**：不给 branch tier 加 per-skill ownership 标注
  （那是 issue option 1，需契约变更，本提案 defer）。
- **不动 Check 16 16a**：删文件即解死锁（16a 因文件已删而 OK，11b 降 WARN），故 16a
  的对称 branch 豁免非破死锁所必需。若后续消费者刻意保留外 branch 文件而撞 16a，
  另案处理。
- **不放宽 hub / 无 config 行为**：hub 自身与任何 config 缺失/不可读的 clone 仍严格
  FAIL（`_detect_non_hub` default-strict 已保证）。
- **不放宽非 branch tier 的 phantom**：universal / project / unclassified 的 phantom
  即便在 non-hub clone 仍 FAIL（这些应全局存在，缺失是真问题）。

## Open Questions

None.（option 1 已显式 defer 至 Non-Goals；16a 对称豁免同上。）

## Alternatives & Rationale

权衡两方案（即 issue 给的两选项）：

- **Option 1（clone-aware branch 解析）**：理论更优雅，但需知"每个 branch 条目归属
  哪个 branch"，而当前 `branch` tier 是无 ownership 标注的扁平列表（Current State 已
  核），实现等于改 `_tiers.json` schema = 契约变更，lift 大、面广。
- **Option 2（最小对称补丁，本提案选）**：仅复用既有 `_detect_non_hub`，对 branch-only
  phantom 在 non-hub 下降 WARN，零契约变更，完全镜像 11a/16a 的既有范式。branch-local
  skill 在非拥有者 clone 的**自然状态就是"文件缺失"→ 命中 11b phantom**，故单修 11b
  即让"删文件"成为可行路径（11b→WARN、16 因文件已删 OK），死锁即解。

选 Option 2：最小、对称、无契约面、与 P-0104/P-0105 范式一致。

## Guardrails

- `edit-write-guard`：本提案改 `governance_core/tools/audit_knowledge.py`（包源，
  非自治层副本，符合第十一条），不触宪法三文件，不被阻断。
- 无 command-guard / sensitive-data-guard / boundary-guard 相关动作（纯本仓库内
  包源编辑 + 测试）。

## Phases

### Phase 0: Governance bootstrap

N/A — 非宪法 / 契约变更，无 governance bootstrap。

### Phase 1: 11b branch-tier 豁免 + 回归测试

- Deliverables:
  - `audit_knowledge.py:412-422` 11b 循环改为 `home_tiers == {"branch"}` + `non_hub`
    → WARN，其余 phantom 仍 FAIL（实现见 Design）。
  - `test_pending_catalog_tolerance.py` 新增 Check 11b 用例：non-hub branch phantom
    → WARN（failed==0）、hub → FAIL、无 config → FAIL、non-hub 但 universal phantom
    → 仍 FAIL（豁免窄）。
  - 改完包源后 `governance-core upgrade --project-root .` 重装（第十一条 dogfood）。
- Validation:
  - `python -m pytest governance_core/tools/test_pending_catalog_tolerance.py -q` 全绿。
  - 既有审计套件无回归（见 Validation Plan）。
- Exit criteria: 新用例绿、既有测试不回归、commit 引 `Implements: P-0111` + `gc #114`。

## Approval Criteria

- [x] Field Dictionary 无新跨边界字段（N/A，标注已写）
- [x] 唯一 realizer 是既有 `_audit_skill_tiers`（无 implied-but-unbuilt 能力）
- [x] Open Questions 已全部 resolve / defer（None）
- [ ] 豁免仅命中 `home_tiers == {"branch"}` 的 phantom（universal/project phantom 仍 FAIL）
- [ ] hub / 无 config clone 行为不变（仍严格 FAIL）
- [ ] 新增 11b 回归用例覆盖 non-hub→WARN / hub→FAIL / 无config→FAIL / non-branch→FAIL

## Validation Plan

1. `python -m pytest governance_core/tools/test_pending_catalog_tolerance.py -q`
   —— 含新 11b 用例。
2. `python tools/audit_knowledge.py`（本 hub 自审）—— 无 `_tiers.json` 时 11b 不触发，
   应仍 healthy；确认本仓库不回归。
3. 复现 issue repro：临时构造 non-hub config + branch-tier phantom fixture，确认
   `_audit_skill_tiers` 返回 `failed==0, warned>=1`。
4. `governance-core upgrade --project-root .` 后自治层副本带新行为。

## Rollback / Recovery

单文件单段改动 + 测试；`git revert <commit>` 即整体回退，重装 `upgrade` 还原自治层。
无状态迁移、无数据格式变更，回退无残留。

## Risks

- **过度豁免**（低概率 / 中影响）：若把 `name in branch_entries` 写成宽匹配，会掩盖
  同挂 universal 的真 phantom。缓解：用 `home_tiers == {"branch"}` 严格判定 + 专门
  的 non-branch-phantom-still-fails 回归用例。
- **hub 被误放宽**（低概率 / 高影响）：缓解：`_detect_non_hub` default-strict，hub /
  无 config 用例钉死 FAIL。
- **掩盖真实 branch 配置错误**（低概率 / 低影响）：WARN 仍可见，不静默；消费者拿到的是
  可解释的告警而非死锁。

## State Log

- 2026-06-24: draft created by core agent (P-0111)
- 2026-06-24: draft → pending (submit for review: Check 11b non-hub branch-tier phantom WARN carve-out, gc #114)
- 2026-06-24: pending → approved (user approval signal: '批准' (gc #114 Check 11b branch-tier carve-out))
- 2026-06-24: approved → implemented (as-built reconcile: _tiers.json intentionally untouched (Option 2 = no schema change, per Non-Goals); STATE.md per phase-commit discipline. No substantive deviation.)
