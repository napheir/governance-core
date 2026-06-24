---
id: P-0112
agent: core
status: implemented
created: 2026-06-24
approved_at: 2026-06-24
implemented_in: 69e7d7b
implemented_at: 2026-06-24
owner: core
---

# Proposal P-0112: audit_knowledge: degrade gracefully when knowledge/INDEX.md absent (skip Check 4, no crash)

## Trigger

实施 P-0111 时跑 hub 自审 `python tools/audit_knowledge.py` 暴露一个**预存、与
P-0111 无关**的崩溃：`main()` 无条件读 `knowledge/INDEX.md`，文件缺失即裸抛
`FileNotFoundError` traceback，整个审计无法运行。单 agent hub 的 `knowledge/` 是
gitignored 安装产物、本就无顶层 INDEX.md。改 audit gate 的降级行为（缺失时 Check 4
怎么办）触 audit 治理基建，与 P-0104/0105/0111 同族，按先例走 proposal。

## Current State (read, not assumed)

读自 0.38.2 包源：

- `audit_knowledge.py:208-209` —— `parse_category_owner_map` 无条件
  `index_md.read_text(encoding="utf-8")`，`index_md = knowledge_root / "INDEX.md"`。
  文件缺失 → `FileNotFoundError`，无 try / 无存在判断。
- `audit_knowledge.py:616` —— `main()` 调 `category_owners = parse_category_owner_map(knowledge_dir)`，
  无保护；崩在此处之前于任何 per-file 检查。
- `audit_knowledge.py:596-604` —— `main()` 对缺失的 `knowledge/` 目录、缺失的
  `contracts/knowledge_frontmatter_schema.md` **都有干净的 `[FATAL]` + `return 1`
  守卫**；唯独 INDEX.md 无对等守卫（不一致）。
- `audit_knowledge.py:677-686` —— Check 4「owner matches category」对**每个** knowledge
  文件查 `category_owners.get(category)`；`allowed is None` 即
  `fail(... "category %r not found in top INDEX.md owner map")`。故空 map → **每个文件
  全员 FAIL**（把崩溃换成误 FAIL 洪水，非可接受降级）。
- hub `knowledge/` 实测仅 `design/` + `governance/` 两子目录，**无顶层 `INDEX.md`**；
  installer（`installer.py:96` 仅映射 `knowledge_governance → knowledge/governance`）
  不安装顶层 INDEX.md。
- `contracts/knowledge_index_schema.md` §1 —— 顶层 `knowledge/INDEX.md` 是 **core
  手写**的权威 subdirectory→owner 表，**无生成器**；消费者为
  `build_knowledge_dashboard.py`（业务自有，gc #24）与 `audit_knowledge.py`。
- 该崩溃此前未被自动套件捕获：`python tools/audit_knowledge.py`（main）不在 pytest /
  脚本式套件内，仅单元函数被测 —— 故 hub 上裸跑才暴露。

## Scope

`governance_core/tools/audit_knowledge.py` 的 `main()`：在调用
`parse_category_owner_map` 前判 `knowledge/INDEX.md` 是否存在 —— 缺失则 WARN（不
FATAL、不 traceback）、`category_owners = {}`、置 `index_present = False`，并据此
**跳过 Check 4**（owner-category，多 agent 归属检查，单 agent / 未建 index 时退化）；
其余所有检查照跑。`parse_category_owner_map` 自身加一层防御性存在判断。新增 main-level
回归测试。**无契约变更**（`knowledge_index_schema.md` 不变）。

## Design & Contract

> Proportionate. Trivial change: one line "implementation self-evident; no interface
> or data-flow change." Otherwise fill all three sub-parts; use "N/A — <reason>" for
> any that genuinely doesn't apply — never leave a placeholder.

### Interfaces, I/O & Realization

两个既有边界，签名不变：

- `parse_category_owner_map(knowledge_root: Path) -> dict[str, list[str]]`
  （`:206`）：开头加 `if not (knowledge_root / "INDEX.md").is_file(): return {}`
  防御层 —— 直接调用者不再 traceback。INPUT：`knowledge_root`；OUTPUT：map（缺失→空）。
- `main(root) -> int`（`:592`）：在 `:616` 处改为先判存在：
  ```python
  index_md = knowledge_dir / "INDEX.md"
  index_present = index_md.is_file()
  if index_present:
      category_owners = parse_category_owner_map(knowledge_dir)
  else:
      logger.warning("[WARN] knowledge/INDEX.md absent — owner/category "
                     "check (Check 4) skipped (single-agent or pre-index project)")
      category_owners = {}
  ```
  Check 4（`:677-686`）整段包进 `if index_present:`，缺失时直接落到 Check 5，不 fail。

realizer：`audit_knowledge.py` 的 `main()` CLI（`python tools/audit_knowledge.py` /
`/publish-knowledge` 间接）即 end-to-end 执行者，无新执行组件。

### Field Dictionary

无跨边界持久化 / 跨 agent 新字段。`index_present` 是 `main()` 内 in-memory 局部 bool。
N/A — 不涉持久字段；治理 INDEX.md 结构的 `contracts/knowledge_index_schema.md` 不变。

| field | type | meaning | producer | consumer | constraints / allowed values |
|-------|------|---------|----------|----------|------------------------------|
| index_present | bool (local) | INDEX.md 是否存在 | main() | Check 4 gate | True/False |

### Flow

`knowledge/INDEX.md`（core 手写，可缺）→ `main()` `is_file()` 判存在 →
present: `parse_category_owner_map` 产 owner map，Check 4 逐文件校验 owner∈allowed；
absent: WARN + 跳过 Check 4 → 其余检查（frontmatter / enum / 日期 / carrier_class /
skill tiers / scenario coverage）照跑 → 退出码。

## Non-Goals

- **不给 hub 播种 / 生成 `knowledge/INDEX.md`**：INDEX.md 是 core 手写、无生成器、
  hub knowledge/ 又是 gitignored 安装产物 —— 是否该为自托管 hub 建一份 INDEX.md 是
  独立、更大的设计题（installer 播种 vs 提交 vs 生成器），本提案 defer。
- **不改 `knowledge_index_schema.md` 契约**：INDEX.md 结构不变。
- **不动 `build_knowledge_dashboard.py`**：dashboard 渲染器对缺失 INDEX.md 的行为
  另属业务自有（gc #24），不在本 audit 修复范围。
- **INDEX.md 存在时行为零变化**：present 路径完全照旧（Check 4 全跑），本提案只新增
  absent 分支。

## Open Questions

None.（"hub 是否该有 INDEX.md" 已显式 defer 至 Non-Goals。）

## Alternatives & Rationale

权衡三方案：

- **A. WARN + 跳过 Check 4（本提案选）**：与 `main()` 既有「缺 knowledge/ / 缺 contract
  → 干净处理」一致的失败软化；owner-category 是多 agent 归属概念，单 agent / 未建
  index 时本就 N/A。修崩溃 + 正确降级，零契约面。
- **B. 缺失即 `[FATAL]` + return 1**（对齐另两个守卫）：但这会让单 agent hub 的自审
  **永久失败** —— hub 合法地无 INDEX.md，FATAL 是误伤。否决。
- **C. 给 hub 播种 INDEX.md**：根因之一，但 INDEX.md 无生成器、hub knowledge/ 是安装
  产物，播种/提交/生成器是更大设计题。否决（defer 到 Non-Goals），不阻塞崩溃修复。

选 A：最小、与既有降级哲学一致、不永久失败、不扩面。

## Guardrails

- `edit-write-guard`：改 `governance_core/tools/audit_knowledge.py`（包源，符合
  第十一条），不触宪法三文件，不被阻断。
- 无 command-guard / sensitive-data-guard / boundary-guard 相关动作。

## Phases

### Phase 0: Governance bootstrap

N/A — 非宪法 / 契约变更。

### Phase 1: INDEX.md 缺失守卫 + Check 4 gate + 回归测试

- Deliverables:
  - `parse_category_owner_map`（`:206`）加防御性 `is_file()` 短路返回 `{}`。
  - `main()`（`:616`）加 `index_present` 判存在 + WARN + `category_owners = {}`。
  - Check 4（`:677-686`）整段包进 `if index_present:`。
  - 回归测试：main-level 用例覆盖 absent→不崩 + Check 4 跳过（不污染 failed）；
    present→Check 4 仍校验 owner-category（含一例 owner 不匹配仍 FAIL）。
  - 改完包源 `governance-core upgrade --project-root .` 重装。
- Validation:
  - `python tools/audit_knowledge.py`（hub 自审）现可跑完，不再 traceback。
  - 新增回归用例 + 既有审计套件无回归。
- Exit criteria: hub 自审跑通、新用例绿、既有测试不回归、commit 引 `Implements: P-0112`。

## Approval Criteria

- [x] Field Dictionary：唯一字段 `index_present` 为 in-memory 局部 bool（N/A 持久化，已标注）
- [x] realizer 是既有 `main()` / `parse_category_owner_map`（无 implied-but-unbuilt）
- [x] Open Questions 已 resolve / defer（None）
- [ ] INDEX.md present 路径行为零变化（Check 4 全跑）
- [ ] INDEX.md absent → 不 traceback、不 FATAL、WARN + 跳过 Check 4、其余检查照跑
- [ ] absent 时 Check 4 不污染 failed 计数（不出现 "category not found" 误 FAIL 洪水）
- [ ] 回归用例覆盖 absent-no-crash / absent-skip-check4 / present-still-validates

## Validation Plan

1. `python tools/audit_knowledge.py`（升级后的自治层副本）—— 在 hub（无 INDEX.md）
   跑完返回非 traceback；INDEX.md 相关仅 1 条 WARN。
2. 直接对包源构造 fixture：absent INDEX.md → `main()` 不抛、Check 4 计数为 0 贡献；
   present + owner 不匹配 → Check 4 仍 FAIL（present 路径未退化）。
3. 既有 `test_pending_catalog_tolerance.py` / `test_scenario_coverage_audit.py` /
   `test_command_coverage_exempt.py` 全绿（确认未碰其他 check）。
4. `governance-core upgrade --project-root .` 后自治层副本带新行为。

## Rollback / Recovery

单文件单段改动 + 测试；`git revert <commit>` 整体回退，`upgrade` 还原自治层。
无状态迁移、无数据格式变更，回退无残留（回退后崩溃复现，但属已知预存态）。

## Risks

- **静默放过多 agent 真缺失**（低概率 / 低影响）：多 agent 消费者本该有 INDEX.md，
  若缺则 Check 4 被跳过。缓解：absent 必出 WARN（可见、可行动），非静默；present
  路径零变化故已建 index 的消费者不受影响。
- **过度跳过其他检查**（低概率 / 中影响）：缓解：gate **仅**包住 Check 4 这一段，
  其余检查（frontmatter/enum/日期/carrier_class/tiers/coverage）显式照跑 + 回归用例
  钉死 present 路径仍校验。
- **掩盖 hub 应建 INDEX.md 的根因**（已知 / 低影响）：Non-Goals 显式 defer 并记录，
  WARN 持续提示，不假装根因已解。

## State Log

- 2026-06-24: draft created by core agent (P-0112)
- 2026-06-24: draft → pending (submit for review: audit_knowledge graceful-degrade on absent knowledge/INDEX.md (skip Check 4, no crash))
- 2026-06-24: pending → approved (user approval signal: '批准' (audit_knowledge graceful-degrade on absent knowledge/INDEX.md))
- 2026-06-24: approved → implemented (as-built reconcile: knowledge/INDEX.md + knowledge_index_schema.md intentionally untouched (Non-Goals: no seed, no contract change); STATE.md per phase discipline; test_audit_index_absent.py is the planned regression test. No substantive deviation.)
