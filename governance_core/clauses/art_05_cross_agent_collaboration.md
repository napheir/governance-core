---
clause_id: art_05_cross_agent_collaboration
clause_class: constitution-clause
extracted_from: agent-core CLAUDE.md (9f31024b)
source_constitution: constitution/total.md
generic_status: generic
phase_2_action: ready-to-use
---

## 第五条：跨 Agent 协作


### 5.1 Scope Governance

每个 agent 的写权限由 `agent_rules/<agent>.allow.txt` 定义。
共享禁写路径由 `agent_rules/shared.deny.txt` 定义。

**合规门禁**：提交前必须通过 `python tools/check_scope.py --agent <name>`

**Proposals 协同**：in-flight proposals 的物理唯一副本位于
`shared_state/proposals/<agent>/`（按 agent 分桶，单副本对全 5 clone 直接
可见，消除 git 异步同步窗口期内的双份起草）。状态进入 terminal
（`implemented` / `rejected` / `superseded`）后由 proposal 的 owner agent
（frontmatter `agent` 字段）通过 `/proposal complete` 或 `/proposal reject`
自行归档到 `proposals/_archive/<YYYY>/` 进 git 保留 audit trail；
`proposal_lib archive` 子命令强制校验 frontmatter `agent` 字段 = 当前
branch 检测到的 agent，跨 owner 归档被拒。Core agent 负责跨 5 clone
audit archive 完整性（同 id 重复 / 多分支冲突 / agent ↔ commit author
不符等），不再垄断归档写入。同一 proposal id 不得同时存在于 in-flight
路径与 archive 路径。Frontmatter 字段（id / agent / status / 终态字段）
契约见 `contracts/proposal_frontmatter_schema.md`；状态转移由 `/proposal`
skill 封装，禁止直接 Edit frontmatter 绕过 skill。ID 分配跨 5 clone 通过
`shared_state/proposals/_id_ledger.json`（A2 SoT，filelock 内 RMW）单调
递增分配，跨分支不重复。

### 5.2 跨 Scope 修改流程

当 agent 需要修改非职责目录时：
1. 在 `proposals/` 创建提案（说明原因、影响、兼容性）
2. Core agent 审查并执行变更
3. 变更合并到 master 后，各 agent clone 通过 git pull 同步

### 5.3 禁止事项

- **禁止** agent 直接修改非职责目录的代码（即使用户指示，也应先警告）
- **禁止** 在 agent 子 clone 中修改 `contracts/`、`agent_rules/`、宪法文件
- **禁止** 绕过 scope gate 提交

### 5.4 Proposal Classify Gate（入口强制）

任何 agent 在会话内**首次执行非平凡 Edit/Write 之前**，必须调
`/proposal classify <description>` 跑入口三值 gate（具体子命令语义与
判定条件见 `.claude/commands/proposal.md` skill 文件，Skill 单一权威源）。

**"非平凡" 触发条件**（命中任一即必须先 classify）：

- 多 phase（≥ 2 个 deliverables 阶段）
- 架构级（schema 迁移 / API 形状变化 / 替换主管线 / 重新设计）
- 跨仓库 / 跨 clone / 治理变更 / 需 rollback / security-sensitive
- 安装依赖 / 改自动化策略 / 改 generated state / 改 secrets handling

**禁止**：以 "全部在 own scope 内"、"不跨 agent" 为唯一理由跳过 classify。
Scope 是 PROPOSAL_REQUIRED 的*充分*条件之一，**不是*必要*条件**——
multi-phase / 架构级 / schema 迁移即使全在 own scope 内也必须 classify。

**classify 输出处理**：

- `NO_PROPOSAL` → 方可直接动手
- `PROPOSAL_REQUIRED` → 必须先 `/proposal create` 起 draft 再实施
- `NEEDS_CLARIFICATION` → 先 ask user 最小必要问题

**违反判定**：commit message 含 retroactive proposal / 一次性 46 秒内回填
所有 state snapshot / proposal body 自承 "implementation already at commit X"
等任一证据，**视为本款违反**（参考 P-0056 dogfood 案例，2026-05-14）。

**不可豁免**：本款修改必须走 `/iterate-constitution` + `proposals/` 流程。

---
