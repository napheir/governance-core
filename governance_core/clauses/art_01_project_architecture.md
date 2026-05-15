---
clause_id: art_01_project_architecture
clause_class: constitution-clause
extracted_from: agent-core CLAUDE.md (9f31024b)
source_constitution: constitution/total.md
generic_status: mixed
phase_2_action: needs-config-injection
---

## 第一条：项目架构

> **Example content note**: The specific agent names, directory paths, contract files, and pipeline references in tables below are drawn from the upstream project where governance-core was first developed. Downstream projects substitute their own domain via `.governance/config.json` and project-specific clause files. The principle (multi-agent topology, directory ownership, contract-based exchange) is generic.



采用多 Agent 并行开发模式（Boris Cherny 方法）：每个 Agent 拥有独立
git clone，在物理文件系统上完全隔离，通过 git 同步工作。

### Agent 体系

> Agent 列表由项目 `.governance/config.json` 的 `agents` 字段定义。下表展示
> "core + N 业务 agent" 拓扑的最小例子（精确名称、分支、职责由项目自定义）：

| Agent | 工作目录 | 分支 | 职责 |
|-------|---------|------|------|
| `core` | `agent-core/`（主仓库） | `master` | **治理、共享基础设施、契约管理、测试体系、安全审计** |
| `<business-agent-1>` | `agent-<business-1>/`（独立 clone） | `feature/<business-1>` | 业务领域 1 职责 |
| `<business-agent-2>` | `agent-<business-2>/`（独立 clone） | `feature/<business-2>` | 业务领域 2 职责 |
| ... | ... | ... | ... |

详细 scope 定义见 `AGENTS.md`（项目自维护）。

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
