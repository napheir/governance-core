---
theme: core-only
owner: core
---

# /update-skill - Authored skill 变更闭环

**Core agent 专属命令**。每次修改 authored skill 文件后调用，确保变更完整传播、宪法无残留 drift。

## 触发条件

本阶段修改过以下任一路径下的文件时**必须**调用：

- `.claude/commands/*.md`（斜杠命令，如 `/wrap-up`、`/audit`）
- `.claude/agents/*.md`（子 agent 角色定义）
- `.claude/hooks/*.py`（harness hook 脚本）
- `tools/sync_infra.py` 的 `COPY_COMMANDS` / `COPY_AGENTS` / `CENTRAL_HOOKS` 清单

**不触发**：`.claude/skills/learned/*.json`（per-agent runtime tracker state，由 SkillTracker 运行时维护，不与宪法耦合）。

## Step 1：识别本阶段改过的 skill 文件

```bash
git diff --name-only HEAD~1 2>/dev/null | grep -E '^\.claude/(commands|agents|hooks)/|^tools/sync_infra\.py$'
# 或针对未提交的：
git status --short | grep -E '\.claude/(commands|agents|hooks)/|tools/sync_infra\.py'
```

列出命中文件。若为空，本 skill 跳过，在阶段总结声明"本阶段未改动 authored skill"。

## Step 2：宪法引用审计

对每个命中文件 `<skill>`，grep 总宪法看是否有条款引用：

```bash
grep -n "$(basename <skill> .md)\|<skill 关键词>" CLAUDE.md
```

### 判定规则（附录"跨条款原则：Skill 单一权威源"）

- ✅ 宪法仅以 pointer 形式引用（`以 .claude/commands/X.md 为单一权威源`）→ 无需改宪法
- ❌ 宪法枚举了 skill 的 step / 命令 / checklist 项数 → **必须**同步重构宪法为 pointer（或确认 skill 文件"子集"和宪法"全集"是否仍对齐，若偏移则以 skill 为准）
- ❌ 宪法声明了 skill 文件不再支持的行为 → 必须删除或改写

重构样板（参考 Art.14 / Art.15.1）：

```markdown
`/<skill>` skill（`.claude/commands/<skill>.md`）是<操作名称>的**唯一权威操作清单**；
skill 步骤随工程实践演化，本宪法不复述其内容。
```

## Step 3：传播到各 clone

> **Topology gate (P-0068)** — Steps 3-4 are multi-agent. If
> `.governance/config.json` has a single agent (`agents` length 1), print
> `[N/A — single-agent topology — skipped]` and skip Steps 3 and 4 — there
> are no other clones to propagate to or drift-check. Resume at Step 5.
> Otherwise proceed.

```bash
python tools/sync_infra.py            # dry-run 预览
python tools/sync_infra.py --execute  # 有 [COPY] 项则执行
```

仅当 skill 在 `sync_infra.py` 的 `COPY_COMMANDS` / `COPY_AGENTS` 清单内才会传播。
若新增的 skill 需要跨 clone 共享，必须先把文件加入这两个清单再跑 sync_infra。

Hooks 不需要复制（`CENTRAL_HOOKS` 走中央引用，clones 自动看到新版）。

## Step 4：drift 零残留校验

每个 clone 运行一次 SessionStart drift 检测，确认无 `[SKILL DRIFT]`：

```bash
for clone in agent-rules agent-trade agent-data agent-research; do
  echo "=== $clone ==="
  cd ../$clone && echo '{}' | python "$CLAUDE_PROJECT_DIR/.claude/hooks/session-context.py" 2>&1 | grep -E "SKILL DRIFT" || echo "(clean)"
  cd "$CLAUDE_PROJECT_DIR"
done
```

期望：全部输出 `(clean)`。若有 `[SKILL DRIFT]`，回到 Step 3 重跑 sync_infra。

## Step 5：STATE.md 登记

在 `STATE.md` 追加一条：

```markdown
### YYYY-MM-DD — Skill update: <skill-name>
- 改动：<一句话描述>
- 宪法同步：Art.X 重构为 pointer / 无宪法引用
- 传播：sync_infra --execute 覆盖 N 个 clone / 仅 core 本地
- Drift 校验：clean
```

## Step 6：Checklist 收尾

```
Skill update 闭环:
- [x] Step 1: 识别到 <N> 个改动文件: <list>
- [x] Step 2: 宪法引用审计 (重构 Art.X / 无命中)
- [x] Step 3: sync_infra --execute (传播 M 个文件 / 无需传播)
- [x] Step 4: 4 clone drift 校验 clean
- [x] Step 5: STATE.md 已登记
```

## 禁止事项

- ❌ 本命令与 `/wrap-up` 是**不同**的闭环。本命令覆盖 authored skill 的"代码侧"变更，`/wrap-up` 覆盖"阶段总结侧"。两者可同阶段各执行一次。
- ❌ 修改了 authored skill 但未运行本命令就 commit → 视为违反宪法附录"Skill 单一权威源"原则（drift 风险累积）
- ❌ 用本命令覆盖 `.claude/skills/learned/*.json` 或 MEMORY 文件变更（走各自对应工具）
