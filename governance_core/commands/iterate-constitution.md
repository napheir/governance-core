---
theme: universal
owner: core
---

# /iterate-constitution - 宪法迭代工作流

封装宪法变更的标准操作：决定改哪、插哪、怎么验、怎么同步。**任何对
`constitution/total.md` / `constitution/agent.md` / `CLAUDE.md` 的修改
必须经此 skill** —— `edit-write-guard.py` Layer 5 阻断式强制（除 core
在 master 直接 Edit 也照走，因 R5 已证 core 同样会犯放错位置的错）。

## 触发时机

- **显式 slash**：用户输 `/iterate-constitution` 或要求"改宪法 / 加红线 / 加 Article"
- **Edit/Write 拦截后引导**：Agent 直 Edit `constitution/*.md` 被 L5 block，提示走 skill
- **Router 关键词触发**：prompt 含 `改宪法` / `iterate constitution` / `add article` 等 → router 注入本 skill 概要

## 执行流程

### Step 0：明确意图

用户给出（或 Agent 整理）：
- 要 add / modify / deprecate 的内容
- 影响范围：仅本 agent / 多 agent / 全项目
- 触发原因：新需求 / 教训沉淀 / 工具变更 / 红线补强

### Step 1：决策落点（决策树，必经）

```
Q1: 影响多个 agent 吗？
  ┌─ Yes → Q2
  └─ No  → constitution/agent.md（仅本 clone）+ R-rule 编号约定
            (rules R1- / data D1- / trade T1- / research RES1- ...)

Q2: 是 hook / pre-commit / 跨 agent 协作依赖的红线吗？
  ┌─ Yes → constitution/total.md 主条款
  └─ No  → Q3

Q3: 是历史教训 / 决策上下文 / 实验结论吗？
  ┌─ Yes → knowledge/decisions/adr-*.md（不进宪法）
  │       + 在宪法红线条款下挂 "see ADR" 指针（如该红线确实因此 ADR 而立）
  └─ No  → Q4

Q4: 是操作步骤 / checklist / 命令序列吗？
  ┌─ Yes → .claude/commands/<name>.md（skill 文件）
  │       + 宪法只放"调用此 skill 是阻塞规则"指针
  │       (跨条款原则：Skill 单一权威源，见总宪法 第十三条 附录)
  └─ No  → 重新归类（不应进宪法）
```

**禁止**：直接编辑 `CLAUDE.md`（生成产物，pre-commit 会拦）。所有变更走
`constitution/total.md` 或 `constitution/agent.md` source 文件。

### Step 2：决策插入位置（仅 total.md / agent.md）

| 类型 | 操作 |
|------|------|
| 加新条款 | append 在最后一条之后，编号顺延；如该条款进入红线，**必须**同步更新总宪法 第十三条 附录 红线清单 |
| 加细则 | append 到现有条款的子节（X.Y） |
| 修订现有 | Edit 现有文本；commit message 必须解释 backward compat 影响 |
| 删除现有 | **不允许直接删**；必须走完整 `proposals/` 流程，加 deprecated tag 过渡，最终 archive |

### Step 3：应用变更

用 Edit / Write tool 修改 source 文件。**不直接改 CLAUDE.md**。

如果新增条款引用了 skill / guide / ADR：先确保被引用对象存在，避免创建悬空指针。

### Step 4：自动验证（必跑）

```bash
# 4a. 重生 CLAUDE.md
python tools/regen_constitution.py

# 4b. 子宪法红线审计（仅当改 agent.md 时）
python tools/audit_sub_constitutions.py

# 4c. knowledge audit（仅当新建 ADR 时）
python tools/audit_knowledge.py

# 4d. routing 校验（仅当改 router）
python tools/validate_routing.py

# 4e. CLAUDE.md budget 检查
wc -l CLAUDE.md
# 软上限 30000 chars / 1000 lines；超出则警告"考虑搬细节到 governance/"
```

### Step 5：同步与传播

| 改动类型 | 同步方式 |
|---------|---------|
| `constitution/total.md` | `tools/sync_infra.py --execute` 推到全 clone（total.md 在 ALWAYS_COPY_FILES）|
| `constitution/agent.md` | **仅本 clone**（per-clone owned，不跨 sync）|
| `.claude/commands/*.md` 新 skill | sync_infra（SKILL_DIRS 路由）|
| `.claude/hooks/*.py` 新 hook | sync_infra（per-clone copy 必须）|
| `knowledge/INDEX.routing.json` 新 trigger | sync_infra（ALWAYS_COPY_FILES）|
| `knowledge/decisions/*.md` 新 ADR | `/publish-knowledge`（federated）|

### Step 6：Commit-ready summary

输出推荐的 commit message + 受影响 clone 列表 + 下一步建议。

#### 改 `total.md` 的 commit message 模板

```
docs(constitution): <one-line summary>

Article: 第X条
Type: add-clause | clarify | restrict-further | add-detail
Audience: all agents

<详细说明>
- 修改原因: ...
- 影响 article 表 / 红线清单: yes/no
- 后续: sync_infra 已跑 / 待 sync-repos 推到 4 clone
```

#### 改 `agent.md` 的 commit message 模板（**强制**）

```
docs(constitution): <one-line summary>

[CONSTITUTION_CHANGE]
- Article: 第X条
- Scope: agent-only
- Type: add-detail | clarify | restrict-further
- Violates-Core: NO

<详细说明>
- 修改原因: ...
- 影响范围: 仅本 agent
```

未含 `[CONSTITUTION_CHANGE]` tag 的 agent.md 修改会被 pre-commit 拦截。

## 验收清单（必须输出）

```
/iterate-constitution 报告:
- [x] Step 1 决策落点: <total | agent | ADR | skill>，理由: <一句话>
- [x] Step 2 插入位置: <Article X.Y / 新增 第N条 / Edit 现有>
- [x] Step 3 已应用: <文件路径>
- [x] Step 4 验证:
       - regen: OK / FAIL
       - audit_sub_constitutions: OK / SKIP / FAIL
       - audit_knowledge: OK / SKIP / FAIL
       - validate_routing: OK / SKIP
       - CLAUDE.md budget: <chars>/30000
- [x] Step 5 同步: <sync_infra 已跑 / 仅本 clone / publish-knowledge 已跑>
- [x] Step 6 Commit message: <粘贴上方模板填好的内容>
```

未输出 = skill 未完成 = 禁止 commit。

## 反模式

- ❌ 直接 Edit `CLAUDE.md`（pre-commit + L5 会拦）
- ❌ 把详细命令 / checklist 项数 / bash 片段塞进宪法（违反 第十三条 附录"Skill 单一权威源"原则）
- ❌ 在宪法里枚举 "skill X 当前有 N 项 checklist"（skill 改了就 drift）
- ❌ 把 agent-specific 规则塞进 total.md（污染所有 agent 的 CLAUDE.md）
- ❌ 把跨 agent 红线塞进单个 agent.md（其他 agent 看不到，治理失效）
- ❌ 未走 skill 直 Edit constitution/*（L5 block，提示重做）

## 与现有工具的协作

- 复用 `tools/regen_constitution.py`（Step 4a）
- 复用 `tools/audit_sub_constitutions.py`（Step 4b，已存在）
- 复用 `tools/audit_knowledge.py`（Step 4c）
- 复用 `tools/validate_routing.py`（Step 4d，R8 引入）
- 复用 `tools/check_constitution_change.py`（pre-commit 已用，本 skill 提前调一次给即时反馈）
- 复用 `tools/sync_infra.py --execute`（Step 5）
