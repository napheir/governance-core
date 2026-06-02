---
clause_id: art_03_contracts
clause_class: constitution-clause
extracted_from: agent-core CLAUDE.md (9f31024b)
source_constitution: constitution/total.md
generic_status: generic
phase_2_action: ready-to-use
---

## 第三条：契约机制

> **Example content note**: The specific agent names, directory paths, contract files, and pipeline references in tables below are drawn from the upstream project where governance-core was first developed. Downstream projects substitute their own domain via `.governance/config.json` and project-specific clause files. The principle (multi-agent topology, directory ownership, contract-based exchange) is generic.



### 3.1 契约目录

`contracts/` 存放所有跨 agent 的稳定数据接口定义。Agent 之间**不得**通过直接 import 对方代码来交互，只能通过契约定义的文件格式交换数据。

| 契约文件 | 用途 | 生产者 | 消费者 |
|----------|------|--------|--------|
| `<your-feature-schema>.json` | 项目特征/数据列定义（示例） | `<producer-agent>` | `<consumer-agent-1>, <consumer-agent-2>` |
| `<your-signal-contract>.md` | 项目信号/事件格式（示例） | `<producer-agent>` | `<consumer-agent>` |
| `knowledge_frontmatter_schema.md` | `knowledge/**/*.md` frontmatter 必填字段与枚举（含 owner） | core | all agents（写/读 knowledge 的都受约束） |
| `knowledge_index_schema.md` | `knowledge/**/INDEX.md` 结构 | core | 项目 knowledge renderer（如 `build_knowledge_dashboard.py`，business-owned，gc #24）, `tools/audit_knowledge.py`, all agents |

### 3.2 契约变更流程

1. 生产者 agent 在 `proposals/` 创建变更提案（描述原因、格式变更、兼容性影响）
2. Core agent 审查并合并到 `contracts/`
3. 消费者 agent 从 `contracts/` 读取，**不得**直接修改

### 3.3 信号交互路径

| 方向 | 路径 | 格式定义 |
|------|------|---------|
| `<producer> → <consumer>` | `artifacts/<your-pipeline>/signals/{YYYYMMDD}/signals.jsonl` | `contracts/<your-signal-contract>.md` |
| `<producer> → <simu/test-agent>` | `artifacts/<your-pipeline>/` | `contracts/<your-signal-contract>.md` |

---
