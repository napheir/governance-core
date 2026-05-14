---
clause_id: art_12_scope_enforcement
clause_class: constitution-clause
extracted_from: agent-core CLAUDE.md (9f31024b)
source_constitution: constitution/total.md
generic_status: generic
phase_2_action: ready-to-use
---

## 第十二条：跨 Agent 协作与 Scope 执行


### 第1款 Agent Scope 定义

每个 agent 的可修改文件范围由 `agent_rules/{agent}.allow.txt` 定义。
Scope 外的文件对 agent 为**只读**（可通过 Read/Grep/Glob 访问，但不得通过 Write/Edit/Bash 修改）。

### 第2款 跨仓库写入禁止

当多个仓库作为 Claude Code 的 working directories 挂载时：
- **每个 agent 只能修改其启动仓库内的文件**
- 从 `agent-trade/` 启动的 agent 不得修改 `agent-core/`、`agent-rules/`、`agent-data/` 中的文件
- 从 `agent-rules/` 启动的 agent 不得修改 `agent-core/`、`agent-trade/`、`agent-data/` 中的文件
- 从 `agent-data/` 启动的 agent 不得修改 `agent-core/`、`agent-rules/`、`agent-trade/`、`agent-research/` 中的文件
- 从 `agent-research/` 启动的 agent 不得修改 `agent-core/`、`agent-rules/`、`agent-trade/`、`agent-data/` 中的文件
- 唯一例外：core agent 从 `agent-core/` 工作目录启动时，可按需修改所有仓库

### 第3款 技术执行机制（四层 + 一层）

防御分两层语义：

- **项目内 scope 防御**（4 层）保证 5 clone 互不串写：
  Layer 1 git pre-commit hook，Layer 2 Bash PreToolUse hook
  (`scope-guard.py`)，Layer 3 Edit/Write PreToolUse hook
  (`edit-write-guard.py`)，Layer 4 settings.local.json hook 注册。
- **会话边界防御**（1 层用户全局）保证任何 cwd 启动的 Claude session
  不能跨项目越界写：Layer 5 session-boundary-guard hook
  (`~/.claude/hooks/`)，default-deny 边界外路径，critical paths
  （`~/.ssh/`、`~/.aws/` 等）永不豁免。

两组互补——前者管 intra-project scope，后者管 extra-project boundary。

逐层 hook 文件路径 / 边界探测三规则 / override 通道
（`CLAUDE_BOUNDARY_OVERRIDE=1`）/ critical paths 清单 / bootstrap installer
执行约束详见 `knowledge/governance/scope-enforcement-mechanism.md`。

决策依据见 `proposals/project_boundary_guard_for_extra_project_writes.md`
（v2，approved 2026-05-01）+
`knowledge/decisions/adr-session-boundary-guard.md`。

### 第4款 不可豁免条款

以下规则即使在宪法修正案流程中也不得被豁免：
- **本条（第十二条）的修改**必须通过 `proposals/` 提案流程，经人工审批后由 core agent 执行
- **agent 不得自行扩大其 scope**（修改 `agent_rules/*.allow.txt` 中自身的条目）
- **技术执行机制（第3款）的移除或弱化**必须经人工审批

### 第5款 提案流程

任何需要跨 scope 修改的需求，必须：
1. 在发起仓库的 `proposals/` 目录创建提案文件（.md 格式）
2. 提案包含：问题描述、修改方案、影响分析、验证步骤
3. 等待人工审批
4. 由有权限的 agent（通常是 core agent）执行修改

---
