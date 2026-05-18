---
theme: core-only
owner: core
---

# /sync-repos - 跨仓库 Git 同步

将 master 最新变更同步到所有 agent clone 仓库。
**Core agent 专属命令**：只有 core agent 有权执行跨仓库 merge（宪法第十二条第2款）。

> **Topology gate (P-0068)** — multi-agent command. First read
> `.governance/config.json`; if `agents` has length 1 (single-agent
> topology), print `[N/A — single-agent topology — skipped]` and stop —
> there are no other clones to sync. Otherwise proceed: the full
> capability below is retained for multi-agent consumers.

## 前置条件

1. Core 的所有变更已 commit 并 push 到 origin/master
2. 如果刚执行了 `/wrap-up`（含 push），应立即运行本命令完成闭环

## 工作流

对每个 agent clone（rules, trade, data, research）按顺序执行：

### Step 1: Stash 本地变更

```bash
cd <clone_dir>
git stash
```

记录是否有 stash（用于最后恢复）。

### Step 2: Fetch + Merge

```bash
git fetch origin master
git merge origin/master --no-edit
```

### Step 3: 自动解决冲突

如果 merge 产生冲突，自动处理：

**STATE.md / STATE_ARCHIVE.md 冲突**（最常见）：
- 保留双方内容（去除冲突标记），两边的条目都保留
- 这些是追加式文件，双方内容不互斥

**`CLAUDE.md` 冲突**（per-clone regenerated artifact）：
- 取本 clone 版本（`--ours`），因为每 clone 的 CLAUDE.md 是从该 clone 的
  `agent.<role>.md`（per-role 文件，详见 proposal `per_role_agent_md_files.md`）
  本地 regen 出来的；master 的 CLAUDE.md 仅对 core agent 正确
- 安全网：merge 后跑 `python tools/regen_constitution.py` 重生一次确保和当前
  `agent.<role>.md` 一致

**其他文件冲突**：
- 取 master 版本（`--theirs`），因为 master 是 core 管理的基础设施
- 例外：如果冲突文件在 agent 的 allow list 中，报告冲突等待用户决定

```python
# STATE.md / STATE_ARCHIVE.md 自动去标记
content = content.replace('<<<<<<< HEAD\n', '')
content = content.replace('=======\n', '')
content = content.replace('>>>>>>> origin/master\n', '')

# CLAUDE.md → --ours
git checkout --ours -- CLAUDE.md && git add CLAUDE.md
```

### Step 4: Commit merge

```bash
git add -u
git commit --no-verify --no-edit
```

**必须 `--no-verify`**：merge 引入的 scope 外文件会触发 pre-commit hook。
这是合法操作 — `check_scope.py` 的 MERGE_HEAD 检测在 `git merge` 阶段生效，
但 commit 阶段 MERGE_HEAD 已消费，需要 `--no-verify` 补偿。

### Step 5: 恢复本地变更

```bash
git stash pop  # 仅在 Step 1 有 stash 时执行
```

### Step 6: 验证

对每个 clone 检查关键基础设施文件是否到位：
- `tools/check_scope.py` 中包含 `MERGE_HEAD`（merge bypass fix）
- `governance_core/discovery/tracker.py` 中包含 `populate_from_git`（tracker fix）
- `.claude/settings.local.json` 中包含 `session-context` 和 `constitution-reminder`（hooks）

## 输出格式

```
=== Repo Sync Results ===
[OK]   agent-rules: merged N commits, 0 conflicts
[OK]   agent-trade: merged N commits, 1 conflict (STATE.md auto-resolved)
[OK]   agent-data: already up to date
[FAIL] agent-research: unresolved conflict in <file> — needs manual intervention

Verification:
  rules:    check_scope=OK tracker=OK hooks=OK
  trade:    check_scope=OK tracker=OK hooks=OK
  data:     check_scope=OK tracker=OK hooks=OK
  research: check_scope=OK tracker=OK hooks=OK
```

## 何时运行

1. `/wrap-up` 完成后（如果本阶段修改了共享基础设施并 push）
2. 用户明确要求同步
3. 发现 agent 报告基础设施问题时（先 push fix，再 sync）

## 标准闭环流程

```
[完成任务] → /wrap-up → git push → /sync-repos → 各 agent 获得最新基础设施
```
