---
clause_id: art_01_project_architecture
clause_class: constitution-clause
extracted_from: agent-core CLAUDE.md (9f31024b)
source_constitution: constitution/total.md
generic_status: mixed
phase_2_action: needs-config-injection
---

## 第一条：项目架构

> **Example content note**: The specific agent names, directory paths, contract files, and pipeline references in tables below come from the Trade Agent project (where governance-core was first developed). Downstream projects substitute their own domain via `.governance/config.json` and project-specific clause files. The principle (multi-agent topology, directory ownership, contract-based exchange) is generic.



基于 Futu OpenAPI 的算法交易系统，采用多 Agent 并行开发模式（Boris Cherny 方法）：
每个 Agent 拥有独立 git clone，在物理文件系统上完全隔离，通过 git 同步工作。

### Agent 体系

| Agent | 工作目录 | 分支 | 职责 |
|-------|---------|------|------|
| core | agent-core/（主仓库） | master | **治理、共享基础设施、契约管理、测试体系、安全审计** |
| rules | agent-rules/（独立 clone） | feature/rules-algorithm | 规则挖掘、模型训练、信号生成 |
| trade | agent-trade/（独立 clone） | feature/trade-strategy | 交易策略、执行、风控 |
| data | agent-data/（独立 clone） | feature/data-analysis | 数据采集、清洗、分析、质量监控 |
| research | agent-research/（独立 clone） | feature/research | 工具调研、可行性评估、原型验证 |

详细 scope 定义见 `AGENTS.md`。

### 角色定义规范

每个 Agent 必须在 `.claude/agents/` 目录下为其承担的角色创建独立定义文件（Claude Code 原生 agent 格式）。

**关注点分离原则**：

| 内容 | 存放位置 | 示例 |
|------|---------|------|
| 角色身份、职责、工具、工作流 | `.claude/agents/<role>.md` | "你是数据基础设施专家" |
| 治理约束、禁止事项、审查标准 | `CLAUDE.md`（子宪法） | "禁止硬编码" |
| 跨 agent 架构、scope 定义 | `AGENTS.md` | agent 所有权列表 |

**硬性约束**：
1. 每个 agent **至少**有一个与 agent 同名的核心角色定义（如 `data-specialist.md`）
2. 新增子角色时**必须**创建对应的 `.claude/agents/<role>.md` 文件
3. **禁止**在 `CLAUDE.md` 中定义角色身份和工作流（属于角色定义文件的职责）
4. 角色定义文件**只能**定义本 agent 职责范围内的角色（禁止跨 scope 角色定义）
5. 角色定义文件的创建/修改**不需要**宪法修改模板（不是宪法变更）

详细模板和命名规范见 `AGENTS.md` 的"角色定义文件标准"节。

---
