---
theme: core-only
---

# Skill 模板

创建新 Skill 文件时参考此模板。

## 文件位置

- **用户可调用的 slash command**: `.claude/commands/<name>.md`
  - 用户通过 `/<name>` 触发
  - 适用于标准化工作流（审计、测试、部署等）

- **非用户调用的辅助 skill**: `.claude/skills/<name>.md`
  - Agent 内部自动引用
  - 适用于前置检查、模板、策略等

## 模板结构

```markdown
# /<command-name> - 简短描述

说明此 Skill 的用途（1-2 句话）。

## 前置检查
1. 检查项 1
2. 检查项 2

## 工作流
1. 步骤 1: 具体操作
   - 命令: `python -m module.name`
   - 预期输出: ...
2. 步骤 2: ...

## 产出
- 输出文件路径
- 日志检查要点

## 注意事项
- 引用宪法相关条款
- 错误处理方式
```

## 命名规范

| 类型 | 命名 | 示例 |
|------|------|------|
| 审计类 | `audit-*` | `/audit`, `/audit-scope` |
| 测试类 | `*-test` | `/daily-test` |
| 操作类 | 动词-名词 | `/wrap-up`, `/futu-check` |
| 数据类 | `collect-*`, `check-*` | `/collect-data` |
| 训练类 | `train-*` | `/train-strangle` |

## 注意事项

- frontmatter 不是必需的，Claude Code commands 直接识别 `.md` 文件名作为命令名
- 文件内容即为 Agent 执行时的指令提示
- 引用的路径和命令必须真实存在
- 跨 Agent 共享的 skill 放在 agent-core，各 Agent 通过 git pull 同步
