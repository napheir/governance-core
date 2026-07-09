---
title: Constitution Protection Mechanism (Constitution Article 13 detail)
status: active
created: 2026-05-07
updated: 2026-05-07
owner: core
carrier_class: reference
tags: [governance, constitution, protection, art13, hierarchy, audit]
---

# Constitution Protection Mechanism — Operational Detail

Originally Constitution Article 13 §3 修改权限 + §4 监督机制. Migrated here
on 2026-05-07 per `proposals/prefix_cost_optimization.md` Phase C1
(extraction commit: see git log). The constitution keeps:

- §1 宪法层级 single sentence
- §2 违宪警告 single sentence
- §3 强制工作流 paragraph (the rule is "must use /iterate-constitution")
- §4 监督机制 5-layer count + 不可豁免条款
- pointer to this file for detailed total/sub-constitution rules + commit
  template + per-layer defense detail

This file contains:
- §1 — 总宪法 (master constitution) modification rules
- §2 — 子宪法 (per-agent sub-constitution) modification rules
- §3 — Decision criteria (which file to modify)
- §4 — Mandatory commit message template for sub-constitution edits
- §5 — Five-layer defense detail (table + pre-commit hook block rules)

These remain CONSTITUTIONAL constraints — the inline residue declares the
invariants; this file enumerates the cases.

---

## 1. 总宪法（master constitution）

Files: `agent-core/CLAUDE.md`、`agent-core/AGENTS.md`

Rules:
- 只能在总 agent 工作目录（`agent-core/`）下修改
- 变更后通过 git pull 同步到各 agent clone
- 定义跨 agent 共同准则（目录职责、配置管理、Git 纪律、跨 agent 协作等）
- 修改流程：提案 → 人工审批 → core agent 通过 `/iterate-constitution` 执行

## 2. 子宪法（per-agent sub-constitution）

Files: `agent-data/CLAUDE.md`, `agent-rules/CLAUDE.md`,
`agent-trade/CLAUDE.md`, `agent-research/CLAUDE.md`

Rules:
- **可在本 agent 工作目录自主修改**（仍须经 `/iterate-constitution` skill）
- 修改后必须 git commit，commit message 需符合强制模板（见 §4）
- 定期通过 git pull 同步总宪法的更新
- **硬性约束**：子宪法不得放宽总宪法的约束（只能更严格或补充细节）
- 冲突时以总宪法为准

## 3. Decision criteria

Where does the change belong?

- 影响多个 agent 的规则 → 提案修改总宪法
- 仅影响本 agent 的实施细节 → 直接修改子宪法
- 历史教训 / 决策上下文 → `knowledge/decisions/adr-*.md`，宪法只放指针
- 操作步骤 / checklist → `.claude/commands/<name>.md` skill，宪法只放指针

## 4. 子宪法修改的 Commit Message 强制模板

未含 `[CONSTITUTION_CHANGE]` tag 的 agent.md 修改会被 pre-commit 拦截。

```
docs(constitution): <one-line summary>

[CONSTITUTION_CHANGE]
- Article: 第X条
- Scope: agent-only
- Type: add-detail | clarify | restrict-further
- Violates-Core: NO

<详细说明>
- 修改原因: ...
- 影响范围: 仅本 agent

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```

字段语义：

| 字段 | 取值 | 说明 |
|------|------|------|
| Article | `第X条` | 必须是已存在的条款编号；新增条款不允许（要走总宪法提案）|
| Scope | `agent-only` | 强制；`cross-agent` 会被 pre-commit 阻止 |
| Type | `add-detail` / `clarify` / `restrict-further` | 描述变更性质 |
| Violates-Core | `NO` | `YES` 会被 pre-commit 阻止 |

## 5. 监督机制（五层防御）

| 层级 | 机制 | 触发时机 | 强度 |
|------|------|---------|------|
| 1 | Pre-commit hook 检测 | 子 agent commit 子宪法前 | 阻断 |
| 2 | 总宪法核心条款清单（见附录 → `sub-constitution-red-lines.md`） | 开发时参考 | 文档 |
| 3 | Commit message 强制模板（见 §4） | 子 agent commit 子宪法前 | 阻断 |
| 4 | Core agent 自动审计（`tools/audit_sub_constitutions.py`） | Core agent 启动时 | 告警 |
| 5 | 人工定期审查 | 每月 | 最终裁决 |

### Pre-commit hook 阻止规则

- ❌ 修改总宪法定义的核心条款（见附录红线清单 → `sub-constitution-red-lines.md`）→ 阻止，提示走提案
- ❌ `Scope: cross-agent` → 阻止，提示走提案
- ❌ `Violates-Core: YES` → 阻止
- ❌ Commit message 缺少 `[CONSTITUTION_CHANGE]` 标签 → 阻止
- ✅ 仅修改子宪法特有条款 + 格式正确 → 放行

## 6. Cross-references

- Constitution 第十三条 (slim residue + pointer to this file)
- Constitution 附录 (red-line table → `sub-constitution-red-lines.md`)
- `tools/audit_sub_constitutions.py` (Layer 4 implementation; CORE_KEYWORDS dict is authoritative)
- `tools/check_constitution_change.py` (pre-commit hook implementation)
- `.claude/commands/iterate-constitution.md` (mandatory entry-point skill)
- `proposals/prefix_cost_optimization.md` §4.2 / audit §2.3 (extraction rationale)
