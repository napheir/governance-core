---
clause_id: art_16_memory_staleness
clause_class: constitution-clause
extracted_from: agent-core CLAUDE.md (9f31024b)
source_constitution: constitution/total.md
generic_status: generic
phase_2_action: ready-to-use
---

## 第十六条：记忆过期策略


Agent 使用 auto-memory 系统时，必须根据记忆类型评估时效性，避免基于过时信息做出决策。

### 16.1 过期阈值

| 记忆类型 | 过期阈值 | 使用前动作 |
|---------|---------|-----------|
| `project` | 14 天 | 验证是否仍然有效（读取相关文件或 `git log` 确认） |
| `reference` | 30 天 | 检查外部链接/资源是否仍可达 |
| `user` | 无过期 | 通常长期有效，无需检查 |
| `feedback` | 无过期 | 通常长期有效，无需检查 |

### 16.2 详细规范（外移）

MEMORY.md 按 type 分区索引格式、Memory 文件结构规范（frontmatter / size /
hook / 内容聚焦）、实施规则细则、完整禁止清单详见
`knowledge/governance/memory-staleness-policy.md`。

### 16.3 红线（必须 inline 的核心约束）

- **必须**：记忆文件 frontmatter 含 `updated: YYYY-MM-DD`；引用
  `project` / `reference` 记忆前检查日期是否超过 §16.1 阈值；超阈值前
  Read/Grep 验证后方可引用；过时即更新或删除
- **禁止**：基于超阈值未验证记忆做代码决策；创建无 `updated` 字段的新记忆；
  仅加注释不更新内容；MEMORY.md 内嵌记忆内容（须拆独立文件 + 索引条目）

注：`.claude/skills/memory-staleness-policy.md` 是 how-to 教程，与本条
约束有已知数值差异（见 governance file §5）；冲突时以宪法为准。

---
