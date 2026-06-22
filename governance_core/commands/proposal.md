---
theme: universal
owner: core
---

# /proposal - Proposal 状态机操作 v2

封装 proposal 生命周期：起草 / 审批 / 实施 / 归档。**所有原子操作通过
`tools/proposal_lib.py` CLI 完成**（filelock + 原子写 + 自动 State Log + audit
ledger snapshot）。Agent 不直接 Edit frontmatter / 不直接动 body 之外的字段。

存储与状态机契约：
- `contracts/proposal_frontmatter_schema.md` v1.1.0（id / agent / status / 三方一致 / mutex）
- 物理位置：`shared_state/proposals/<agent>/p-NNNN-<slug>.md`（in-flight，不进 git）
- 归档位置：`proposals/_archive/<YYYY>/p-NNNN-<slug>.md`（terminal 后进 git）
- 配置：`config/proposals_config.json`（路径 / lock / agents 枚举）

---

## 子命令一览

| 命令 | 作用 | 状态转移 |
|------|------|---------|
| `/proposal classify <description>` | 三值 gate：决定是否需要 proposal | （只读） |
| `/proposal create --slug X --title "Y" [--agent Z]` | 起草新 proposal，自动分配 P-NNNN | (新文件) → draft |
| `/proposal submit <id>` | 请 user 评审 | draft → pending |
| `/proposal approve <id>` | user 已明确批准（P-0108 研究门：Current State 须达标，否则 BLOCK） | pending → approved |
| `/proposal start <id>` | 实施开始（可选；短任务可跳过） | approved → in-progress |
| `/proposal complete <id> [--commit <hash>]` | reconcile + 实施完成 + 自动归档 | (approved\|in-progress) → implemented → archive |
| `proposal_lib.py reconcile --id X --commit H` | as-built 覆盖差（advisory，complete step-0） | （只读） |
| `/proposal reject <id> --reason "..."` | user 明确否决 | pending → rejected |
| `/proposal supersede <id> --by <new-path>` | 被新方案替代 | (任意) → superseded |
| `/proposal list [--include-terminal]` | 列出 in-flight + (可选) archive | （只读） |
| `/proposal show <id>` | 显示 frontmatter + body 预览 | （只读） |
| `/proposal path <id>` | 解析 id 到当前文件路径 | （只读） |

`<id>` 始终是 `P-NNNN` 形式（大写 P，四位数）。

---

## `classify` — 入口三值 gate（codex-inspired）

任何非平凡 Edit/Write 之前，先做分类。**返回三值之一**：

| 输出 | 含义 | 下一步 |
|------|------|--------|
| `NO_PROPOSAL` | 任务清晰、单 scope、低风险 | 直接 commit / Plan mode |
| `PROPOSAL_REQUIRED` | 跨 scope / 跨 clone / 治理 / 多 phase / 需审 | 调 `/proposal create` |
| `NEEDS_CLARIFICATION` | scope 模糊，能影响实施方式 | 找 user 问最小必要问题 |

### 必判 PROPOSAL_REQUIRED 的条件

- 改全局治理：`CLAUDE.md` / `contracts/` / `agent_rules/` / hook 源 / skill 体系 / scope 规则
- 多 phase / 跨仓库 / 跨目录 / 架构级 / security-sensitive / 需 rollback
- 安装依赖 / 改 secrets handling / 改自动化策略 / 改 generated state
- User 明确要求 proposal / plan approval / staged execution

### 可判 NO_PROPOSAL 的条件

- 单 agent scope 内、本 session 可执行完毕的局部修改
- 简单 bug fix（窄文件 + 清晰复现）
- 纯解释 / 翻译 / 总结 / 只读检查
- User 明确要求"立即查 X"类命令

### 输出格式

```
[classify] PROPOSAL_REQUIRED
reason: 触及 `agent_rules/` 写权限规则，是跨 agent 治理变更
evidence: 已读 `agent_rules/rules.allow.txt:1-20`、`hooks/edit-write-guard.py:40`
scope (建议): 加 rules.allow.txt 一行 + Phase 0 走 /iterate-constitution
```

`evidence:` 行记录"判定前实读了哪些源"（file:line / 度量），是 P-0108 研究范式
的 point-of-change 维度在 classify 出口的落点；空着 = 凭印象判定，应补读。

判 `NEEDS_CLARIFICATION` 时附最小必要问题（1–2 条）。

---

## 执行流程

### `classify <description>`

1. 读 `.claude/skills/proposal-vs-plan-mode-vs-commit.md` decision flow（指导 NO_PROPOSAL 判定）
2. 应用上述"必判 / 可判"条件表
3. 不动文件，输出三值 + reason + 建议 scope（如 PROPOSAL_REQUIRED）或最小问题（如 NEEDS_CLARIFICATION）

> **可选建议模块**（只读、不阻断）：起草前可跑
> `python tools/proposal_suggest.py "<description>"` surface 三路机械召回 ——
> ① 类似 / 相关 proposal、② 起草检查项 / 历史经验、③ likely scope owner
> （按 `agent_rules/*.allow.txt`）。输出仅供参考、决策权在起草 agent；每节空集
> 显式渲染 `（无）`。② 数据源为 `knowledge/governance/proposal-drafting-checklist.md`
> （通用 seed，消费者自维护其条目）。

### `create --slug X --title "Y" [--agent Z]`

调 `python tools/proposal_lib.py create --slug X --title "Y" [--agent Z]`：

1. lib 内部 filelock 内扫所有 in-flight + archive + legacy 文件，求 max NNNN + 1
2. 写 11 段 v2 scaffold 到 `shared_state/proposals/<agent>/p-NNNN-<slug>.md`
3. frontmatter: `id` / `agent` / `status: draft` / `created` / `owner`
4. body 11 段：Trigger / **Current State (read, not assumed)** / Scope / Non-Goals /
   **Alternatives & Rationale** / Guardrails / Phases（含 Phase 0 governance bootstrap
   slot）/ Approval Criteria / Validation Plan / Rollback / Risks / State Log
5. State Log 已有一行 `YYYY-MM-DD: draft created by <agent> agent (P-NNNN)`

`--agent` 缺省时由 git 分支自动检测（master → core，feature/rules-* → rules，...）。

Agent 收到 scaffold 路径后，**填充各段内容**（直接 Edit 文件 body 部分，不动 frontmatter）。

> **P-0108 两个新段（研究 rigor）**：
> - `## Current State (read, not assumed)` —— 实读 point-of-change 现状并 cite ≥1
>   `file:line`；**approve 时硬门校验**（form：段在、非占位、有具体引用），不达标
>   `approve` 被 lib BLOCK，须补研究或 `--allow-empty-current-state` 豁免。
> - `## Alternatives & Rationale` —— proportionate：单一显然解写"单一显然解 + 理由"；
>   设计抉择权衡 ≥2 方案 + 取舍。

### `submit <id>`

调 `python tools/proposal_lib.py transition --id P-NNNN --to pending --note "submit for review"`。

语义：**draft → pending = "请 user 看"**。此后 proposal 进入 session-context.py 的 pending 列表，user 会在 SessionStart 时看见。

### `approve <id>`

**安全约束**：本 turn 用户消息必须含明确批准信号（`approved` / `通过` / `批准` / `ok 实施` / `可以实施` / `同意` / `同意该 proposal`）。否则拒绝并提示。

调 `python tools/proposal_lib.py transition --id P-NNNN --to approved --note "<approval signal excerpt>"`。

### `start <id>`（可选）

调 `python tools/proposal_lib.py transition --id P-NNNN --to in-progress`。

短任务可跳过直接 `complete`。

### `complete <id> [--commit <hash>]`

**三步操作**：先 as-built reconcile，再 transition 到 implemented，再询问 user 是否归档。

0. **as-built reconcile**（P-0108 G3）：调
   `python tools/proposal_lib.py reconcile --id P-NNNN --commit <hash>`
   打印 `[in scope, NOT touched]` / `[touched, NOT in scope]` 两份覆盖差。
   advisory（loose token match）：agent 审两份清单，把实质偏离（漏改的 scope 文件、
   越界改的文件）记进 `## State Log`，再继续。
1. 调 `python tools/proposal_lib.py transition --id P-NNNN --to implemented [--commit <hash>]`
   - `--commit` 缺省 → 用 `git log -1 --format=%h` 拿 HEAD short hash
   - lib 内 `git rev-parse --verify` 校验 hash 解析得通
2. 询问 user："是否立即归档到 `proposals/_archive/<YYYY>/`？"
   - User 同意 → 调 `python tools/proposal_lib.py archive --id P-NNNN`（git mv 到 archive 路径，删 shared_state 副本）
   - User 推迟 → 保留在 shared_state，可后续手动调 archive；audit_proposals.py Check 9 会监测同 id 互斥

### `reject <id> --reason "..."`

**安全约束**：与 approve 同样要求用户明确否决信号（`rejected` / `否决` / `不通过`）。

调 `python tools/proposal_lib.py transition --id P-NNNN --to rejected --reason "..."`。

完成后询问 user 是否归档（同 complete 第 2 步）。

### `supersede <id> --by <new-path>`

调 `python tools/proposal_lib.py transition --id P-NNNN --to superseded --superseded-by <new-path>`。

**双向一致性**（audit Check 6）：lib 不自动写新 proposal 的 `supersedes` 反向字段（避免误改无关 proposal）；agent **必须**手动在新 proposal frontmatter 加 `supersedes: [proposals/<old-rel>]`，然后审计会校验互引。

### `list [--include-terminal]`

调 `python tools/proposal_lib.py list [--include-terminal]`：

- 默认：列 in-flight 区（`shared_state/proposals/<agent>/`），按 agent 分组
- `--include-terminal` 时追加 archive 区
- 输出表：ID / Agent / Status / Region (in-flight | archive) / Filename

### `show <id>`

调 `python tools/proposal_lib.py show --id P-NNNN`：

- 显示文件路径
- frontmatter dict（JSON 形式）
- body 头 30 行

### `path <id>`

调 `python tools/proposal_lib.py path --id P-NNNN`：仅打印绝对路径（脚本管线友好）。

---

## 安全约束

- **Agent 不能自批 approve / reject**：必须 user 明确信号；signal 摘录写进 `--note` 字段
- **commit hash 强校验**：`complete` 时 hash 必须 `git rev-parse --verify` 通过；lib 已强制
- **filelock 保证原子性**：id 分配、状态转移、归档都在 lock 内（lock_path 由 config 指定）
- **不绕过 lib 直接 Edit 文件**：lib 维护 State Log + snapshot ledger + 字段一致性；绕过会破坏 audit trail
- **shared_state 跨 clone 可见**：非 core agent 只能写自己 `shared_state/proposals/<self>/`，由 `agent_rules/<self>.allow.txt` + edit-write-guard 强制

---

## 验收清单（每次执行后输出）

```
/proposal 报告:
- [x] 子命令: <classify | create | submit | approve | start | complete | reject | supersede | list | show | path>
- [x] 目标: <P-NNNN | description for classify>
- [x] 状态转移: <prev> → <new> (transition 子命令才有)
- [x] 写入字段: <list of frontmatter fields modified>
- [x] 安全检查: <user 批准信号原文 / SKIP>
- [x] commit hash 校验: <git rev-parse 输出 / SKIP>
- [x] 文件路径: <shared_state/... 或 proposals/_archive/...>
- [x] Audit snapshot: <audit/proposal_snapshots/P-NNNN/<status>.md / SKIP>
```

---

## 集成

### `/wrap-up` Step 2c（半自动）

Commit message 含 `Implements: P-NNNN` 或 `Per proposal P-NNNN` 时，wrap-up 建议
调 `/proposal complete P-NNNN`；agent 主动建议，待 user 确认或显式声明后执行。

### `/iterate-constitution`

改宪法的 proposal 一定有 Phase 0 governance bootstrap 段（v2 scaffold 已预留）。

### Backfill（Phase 4 范畴）

历史 76 legacy proposals 通过 `tools/migrate_proposals_to_shared_state.py`
（P-0001 Phase 3 创建）一次性 dry-run 审 + execute 迁移，不属本 skill 范畴。

---

## 反模式

- ❌ 直接 Edit shared_state/proposals/ 文件的 frontmatter
- ❌ 直接 Edit 文件的 `## State Log` 段（破坏 audit trail）
- ❌ Agent 自批 approve / reject（违反安全约束）
- ❌ `complete` 时不传 hash 也不在能解析的 HEAD 状态（lib 会拒）
- ❌ 把 supersede 当 reject 用（supersede = 被新方案替代，reject = 被否决）
- ❌ 跨 agent 写他人 `shared_state/proposals/<X>/`（hook 阻断）
- ❌ classify 直接跳过、agent 自行判断是否要 proposal（人脑判断 ≠ skill 一致性）

---

## 与现有 skill 协作

| Skill | 关系 |
|-------|------|
| `/wrap-up` Step 2c | commit message 命中时半自动调本 skill |
| `/iterate-constitution` | 改宪法的 proposal 必经；Phase 0 必走该 skill |
| `proposal-vs-plan-mode-vs-commit` (guide) | classify 子命令的判据依据 |
| `/publish-knowledge` | 不涉及（proposal 不进 knowledge/） |
