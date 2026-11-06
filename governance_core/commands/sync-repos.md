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
git merge --no-ff --no-commit origin/master
```

`--no-commit` 让每次 merge 都在 Step 4 经 pre-commit 门禁提交。若用普通
`git merge`：无冲突时 git 会自动提交，此时运行的是 pre-merge-commit 而不是
pre-commit（governance-core 0.48.3+ 两者都装）。pre-merge-commit 运行时
MERGE_HEAD 尚未写入，它只能认出与 core 引用相同的文件；其余越界文件会让
这次自动提交 `[DEFER]`（exit 1）。merge 仍保持暂存状态，照常进入 Step 4 即可。

core 引用来自 config（governance-core 0.48.5+）：`upstream_branch`（如
`origin/master`，Step 2 刚 fetch 过）优先，其次 `core_branches`。门禁只放行来自
core 历史的导入；若 merge 带进了不在 core 历史里的提交（例如另一个业务 agent 的
分支），这些提交触及的越界文件会被判 `IMPORTED_OUT_OF_SCOPE` 并点名提交。
跨 agent 的改动应先进 master，再由本命令同步。

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
git commit --no-edit
```

若 `git rev-parse -q --verify MERGE_HEAD` 失败（已是最新；或用了普通 `git merge`，已 fast-forward / 自动提交），跳过本步。

**不要用 `--no-verify`**（governance-core 0.48.1+）：结束 merge 的这次 commit 时 MERGE_HEAD
仍存在，pre-commit 的 `check_scope.py --staged-only` 把"暂存内容与 MERGE_HEAD 完全一致"的
文件识别为 merge 导入、放行。若 pre-commit 仍拒绝，说明有文件既不等于 master 版本也不等于
本 clone 的允许范围——即冲突解决时夹带了越界改动：停下来报告，不要绕过。（0.47.0 / 0.48.0
的门禁比较的是 `master..HEAD`，会误拦 merge 导入；遇到时先 `git merge --abort`，升级后重来。）

### Step 5: 恢复本地变更

```bash
git stash pop  # 仅在 Step 1 有 stash 时执行
```

### Step 6: 验证

对每个 clone 检查关键基础设施文件是否到位：
- `tools/check_scope.py` 中包含 `MERGE_HEAD`（merge bypass fix）
- `governance_core/discovery/tracker.py` 中包含 `populate_from_git`（tracker fix）
- `.claude/settings.local.json` 中包含 `session-context` 和 `constitution-reminder`（hooks）

## 同步后：对齐 gc-managed 层 manifest（gc #26 / P-0095）

`/sync-repos` 用 **git merge** 同步内容。对 **gc-managed 自治层**（`governance-core
upgrade` 安装的 hook / gc tool / gc command / clause 源 + `.governance/installed_files.json`
manifest）存在一个边界，须在 merge 后处理：

- **文件内容：git merge 能正确携带。** 这些文件在多 clone 消费者里是 git-tracked 的，
  merge 把 master 的新版本内容并入各 clone。`check_scope.py` 的 `MERGE_HEAD` 豁免
  正是为此设计——所以 git merge 是 gc-managed 文件内容到达
  clone 的**合法且正确**通道（不会"销毁本地 drift"：merge 走的是三方合并/冲突，不是
  无声覆盖）。
- **manifest 不随 git 走。** `installed_files.json`（0.46.0 起在 `.gitignore` 受管运行时块里）
  只由 `governance-core upgrade` 写。merge 后 clone 的文件已是新版，但 manifest 仍停在旧
  baseline / 旧 version。（`.governance/config.json` 目前仍是 git-tracked 的。）
- **master 停止跟踪的文件会被 merge 删除。** 例如在 master 上 `git rm --cached
  .claude/settings.local.json` 后，各 clone merge 时该文件被删，直到下一次 upgrade 重新生成前
  **该 clone 没有任何 hook 注册**。所以这类 merge 之后要立即对该 clone 跑下面的 upgrade。

**后果与对策**：这不影响 clone 的功能，hook 跑的是新文件，包也是新版本。若本次 merge 携带了
gc-managed 文件，对每个受影响 clone 补跑一次

```bash
governance-core upgrade --project-root <clone>
```

对齐 manifest，同时捕获真正的 drift。

**0.49.1 起**：upgrade 不再把 merge 进来的文件判为 drift。判断依据是：文件内容已经等于本次 upgrade
要写入的版本，就不算 drift，对 clause 按渲染后的内容比较。只有既不等于旧 baseline、也不等于新版本
的文件，才算本地改动。

更早的版本会把每个 merge 进来的文件都打包成 `layer: candidate-common` 的 drift 候选。下一次
`/wrap-up` 的 `candidate.py sweep` 会把它们作为公开 issue 发到 hub。旧版 clone 在 upgrade 后要检查
`.governance/candidate-outbox/`，内容与 master 相同的 drift 候选直接删掉。

这一判断要求 core 与业务 clone 用**同一个包版本**升级。若业务 clone 装的包比 core 提交时新，
merge 进来的文件既不等于旧 baseline，也不等于新版本，仍会被判为 drift。

纯 business 层（STATE / `knowledge/**` / 业务代码 / 配置）没有这个问题，它们没有 manifest。

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
