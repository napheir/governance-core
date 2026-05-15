---
clause_id: art_02_directory_responsibilities
clause_class: constitution-clause
extracted_from: agent-core CLAUDE.md (9f31024b)
source_constitution: constitution/total.md
generic_status: mixed
phase_2_action: needs-config-injection
---

## 第二条：目录职责

> **Example content note**: The specific agent names, directory paths, contract files, and pipeline references in tables below are drawn from the upstream project where governance-core was first developed. Downstream projects substitute their own domain via `.governance/config.json` and project-specific clause files. The principle (multi-agent topology, directory ownership, contract-based exchange) is generic.



| 目录 | 职责 | 写权限 | 说明 |
|------|------|--------|------|
| `<business-dir-1>/` | 业务领域 1 代码（示例） | `<business-agent-1>` | 项目自定义 |
| `<business-dir-2>/` | 业务领域 2 代码（示例） | `<business-agent-2>` | 项目自定义 |
| `tests/` | **质量保证测试体系（P0-P4）** | **core** | 契约测试、集成测试、E2E 测试、每日回归测试 |
| `data/` | 数据采集、清洗、缓存 | `<data-agent>` | 通常 data agent 可写，其他只读 |
| `config/` | **所有配置文件（唯一来源）** | 按业务子目录细分 | 见第四条 |
| `contracts/` | 跨 agent 数据接口契约 | core（审核后合并） | 见第三条 |
| `proposals/` | 跨 agent 变更提案 | all | 见第五条 |
| `skills/` | 共享基础设施（指标、模型、数据） | core | rules/trade/data 只读消费 |
| `agents/` | Agent 框架代码 | core | |
| `common/` | 公共工具函数（外部 API 封装等示例） | core | |
| `audit/` | 审计日志基础设施 | core | |
| `knowledge/` | 项目知识库（模型演化、实验结论、领域知识、决策记录） | 各 agent 写各自归属子目录（见 AGENTS.md 知识库治理节） | 联邦模型，按概念组织 |
| `research/` | 工具调研、原型、评估报告 | research | sandbox/ 不进 Git |
| `artifacts/` | 输出产物（不进 Git） | 各 agent 写各自子目录 | |
| `tools/` | Scope 检查等治理工具 | core | |
| `agent_rules/` | Scope allow/deny 规则 | core | |
| `shared_state/`（位于 `<install-root>/` 根，非任何 clone 内） | 多 clone 共享运行时状态 | all 5 agents（按子目录分细，见第四条之一） | **不进 git**；单一物理副本；写入需 filelock + 原子写；详见第四条之一 |

**硬性约束**：
- 非写权限目录为**只读**，违规修改必须走提案流程（第五条）
- `data/` 仅 data agent 可写，其他 agent 只读
- 新文件必须放到对应职责目录，禁止在非职责目录创建文件

---
