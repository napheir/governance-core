---
theme: core-only
owner: core
---

# /inventory - Harness 能力全景

实时扫描当前工程脚手架状态，展示所有能力清单。

## 工作流

1. 运行 `python tools/inventory.py`
2. 展示报告给用户（不做任何修改）

## 报告内容

- **Defense Hooks**: 活跃 / 孤儿（文件存在但未注册） / git hooks
- **Governance Tools**: 按类别分组（audit / testing / generation / dispatcher / analysis）
- **Slash Commands**: 所有可用命令
- **Agent Definitions**: 角色定义文件
- **Active Experiments**: 进行中的 A/B 实验
- **Component Lifecycle**: 架构性 vs 能力补偿组件，过期审查状态
- **Permissions**: allow 规则数量

## 可选参数

- `python tools/inventory.py --json` — 机器可读 JSON 输出（供未来前端消费）
