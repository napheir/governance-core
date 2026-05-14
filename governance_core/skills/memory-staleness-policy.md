---
theme: universal
---

# 记忆过期策略

Agent 在使用 auto-memory 记忆文件时，应根据记忆类型检查时效性。

## 过期阈值

| 记忆类型 | 过期阈值 | 使用前动作 |
|---------|---------|-----------|
| `project` | 7 天 | 验证是否仍然有效（读取相关文件/git log 确认） |
| `reference` | 30 天 | 检查外部链接/资源是否仍可达 |
| `user` | 无过期 | 通常长期有效，无需检查 |
| `feedback` | 无过期 | 通常长期有效，无需检查 |

## 实施方式

1. 记忆文件的 frontmatter 中建议包含 `updated: YYYY-MM-DD` 字段
2. Agent 在引用 project/reference 类型记忆时，检查 `updated` 日期
3. 超过阈值的记忆，在使用前通过 Read/Grep/Bash 验证当前状态
4. 验证后发现已过时的记忆，应更新或删除

## 示例

```markdown
---
name: crypto-core-status
description: crypto-options 项目当前进展
type: project
updated: 2026-03-11
---
```

若当前日期超过 2026-03-18（7 天），Agent 应在引用此记忆前确认项目状态是否有变化。
