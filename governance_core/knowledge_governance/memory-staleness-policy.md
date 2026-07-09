---
title: Memory Staleness Policy (Constitution Article 16 detail)
status: active
created: 2026-05-07
updated: 2026-05-07
owner: core
carrier_class: reference
tags: [governance, memory, auto-memory, staleness, art16]
---

# Memory Staleness Policy — Operational Detail

Originally Constitution Article 16 §16.2 + §16.3 + §16.4 + §16.5. Migrated
here on 2026-05-07 per `proposals/prefix_cost_optimization.md` Phase C1
(extraction commit: see git log). The constitution keeps:

- §16.1 expiry-threshold table (4-row, foundational invariant — stays inline)
- §16.4-§16.5 红线 single-line summaries (must verify before reference;
  banned states)
- pointer to this file for index format + file structure + implementation
  rules + ban list

This file contains:
- §1 — MEMORY.md index format (按 type 分区 layout)
- §2 — Memory file structural requirements (frontmatter, size, hook quality)
- §3 — Implementation rules (4 numbered must-do)
- §4 — Banned states (4 numbered禁止)
- §5 — Relationship with `.claude/skills/memory-staleness-policy.md` guide

These remain CONSTITUTIONAL constraints. Sub-constitutions cannot relax
them per Constitution 附录 红线 row "第十六条".

---

## 1. MEMORY.md 索引规范

所有 agent 的 MEMORY.md **必须**采用按 type 分区的索引格式：

```markdown
# Memory Index

## Context
- Agent 基本信息（scope、分支、操作手册路径等）

## Feedback
- [文件名.md](文件名.md) — 一句话钩子（< 100 字符）

## Project
- [文件名.md](文件名.md) — 一句话钩子

## Reference
- [文件名.md](文件名.md) — 一句话钩子
```

### 规则

- MEMORY.md 是纯索引，**不**内嵌记忆内容（内容放独立 `.md` 文件）
- 每个索引条目一行，< 100 字符，整体 < 50 行
- Context 区可直接写入（不超过 5 行基本信息），无需独立文件

## 2. Memory 文件规范

| 要求 | 说明 |
|------|------|
| Frontmatter 必填 | `name`, `description`, `type`, `updated` 四个字段 |
| 单文件行数限制 | ≤ 100 行（超出则拆分为多个文件） |
| 一句话钩子 | MEMORY.md 中的索引行必须让 agent 一眼判断是否需要深入读取 |
| 内容聚焦 | 不存代码模式、git 历史、调试方案等可从代码推导的信息 |

## 3. Implementation rules

1. 记忆文件的 frontmatter 中**必须**包含 `updated: YYYY-MM-DD` 字段
2. Agent 在引用 `project` / `reference` 类型记忆时，**必须**检查 `updated`
   日期是否超过阈值（Art.16 §16.1 表）
3. 超过阈值的记忆，在使用前通过 Read/Grep/Bash **验证当前状态**后方可引用
4. 验证后发现已过时的记忆，**必须**更新或删除，不得继续引用过时内容

## 4. Banned states

- **禁止**基于超过阈值且未验证的记忆做出代码修改决策
- **禁止**创建不含 `updated` 字段的新记忆文件
- **禁止**在记忆过时后仅添加注释而不更新内容
- **禁止**在 MEMORY.md 中内嵌记忆内容（必须拆为独立文件 + 索引条目）

## 5. Relationship with `.claude/skills/memory-staleness-policy.md` guide

`.claude/skills/memory-staleness-policy.md` 是 **how-to 教程 + 示例**
（user-facing usage walkthrough），不是宪法权威源。两者角色分工：

| 文件 | 角色 | 优先级 |
|------|------|------|
| Constitution Art.16 §16.1 (inline) + this governance file | **宪法权威**（detail of `必须` / `禁止`） | 最高 |
| `.claude/skills/memory-staleness-policy.md` guide | how-to + 示例 | 教程性 |

**已知冲突**（截至 2026-05-07）：

- guide 中 `project` 阈值 = 7 天
- 宪法 §16.1 中 `project` 阈值 = 14 天
- guide 用"建议 / 应"，宪法用"必须 / 禁止"

冲突时**以宪法为准**。guide 应在后续单独 commit 内对齐，但本次 C1 step 5
不动 guide（保留分工，避免 scope 蔓延）。

## 6. Cross-references

- Constitution 第十六条 §16.1 (slim residue inline + pointer to this file)
- Constitution 附录 红线 row "第十六条" (sub-constitutions cannot relax)
- `.claude/skills/memory-staleness-policy.md` (how-to guide; conflicts noted in §5)
- `proposals/prefix_cost_optimization.md` §4.4 / audit §2.4 (extraction rationale; Art.16 was conditional, executed because guide is not a 1:1 match)
