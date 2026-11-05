# STATE — governance-core

Session-bridge log. `/wrap-up` Step 1 prepends a dated entry under
"Updates in This Session"; `tools/rotate_state.py` archives entries older
than 7 days to `STATE_ARCHIVE.md`; `session-context.py` surfaces recent
entries at SessionStart.

This file is committed (authored governance record). Adopted by P-0068
Phase 3c — single-agent governance-core still needs a session-state bridge,
so the STATE.md capability is provided by the package (the installer seeds
an initial copy; `rotate_state.py` ships in `tools/`).

## 1. Updates in This Session

<!-- Newest entry on top. Format:
### YYYY-MM-DD — <short title>
- 改动摘要 / 涉及文件 / 关键决策 / 测试结果
-->

### 2026-11-05 — deva-vani 升级反馈修复（0.48.2，未发布）

- **背景**：deva-vani 四个 clone 已升级到 0.48.1，doctor 全 OK；P-0129 验收第 4 项实测通过（越界 commit 被 pre-commit 拒，exit=1），
  第 1–3 项待 owner 开 agent-platform 会话。同时报 3 个问题 + 1 处文档矛盾。
- **check_agent_roles 误报**（P-0130 引入）：installer 给每个 clone 装 `core-auditor.md`、master 跟踪的 core 角色随 merge 进业务 clone，
  被 Check 2 判跨 scope。改为只把**其他业务 agent** 名作前缀视为跨 scope，core 角色在各 clone 合法。
- **audit_sub_constitutions 找不到业务 clone**（F7 同族）：按 `install_root/agent-<name>` 拼路径；改为本 clone 父目录 + config `clone_dir`。
- **`detect_role('.')` 返回 `<unresolved>`**：`_root()` 只 normpath，`basename('.')` 为空；改为 abspath（fail-closed 方向不变）。
- **`/sync-repos` Step 4 的 `commit --no-verify`**：0.48.1 起门禁在结束 merge 的 commit 时用 MERGE_HEAD 识别导入，去掉 `--no-verify`，被拒即停报；
  补充"master 停止跟踪的文件会被 merge 删除、upgrade 前该 clone 无 hook 注册"；更正"config.json 是 gitignored"的不实描述。
- **测试**：+3（core 角色在业务 clone 不报、相对路径身份解析、嵌套布局找到兄弟 clone）；对 HEAD 旧代码反向校准 3 例全 FAIL。
  全量 pytest 340 passed，脚本风格全过。版本 0.48.1 → 0.48.2。**发布待 owner 确认**。

### 2026-11-05 — 发布 v0.48.1（提交门禁修复）

- owner 确认后推送 2 commits，`gh release create v0.48.1`；workflow 42008760054：build / publish-pypi success。
- 核实：`gh release list` Latest = v0.48.1；PyPI 项目级 JSON 一度仍显示 0.48.0（CDN 缓存），版本端点 `/pypi/governance-core/0.48.1/json`
  与 simple 索引均已含 wheel + sdist —— 以版本端点 / simple 索引为准。
- 已通知 deva-vani：业务 clone 直接升到 0.48.1，P-0129 验收第 4 项在 0.48.1 上做。

### 2026-11-05 — P-0129 F9 实施缺陷修复：提交门禁的合并与暂存比较（0.48.1，未发布）

- **发现**：deva-vani 报升级顺序后，本仓库先探测 0.47.0 门禁在业务 clone 的 `/sync-repos` 合并上的行为（`artifacts/p0129/probe_merge_gate.py`）：
  合并未自动提交（冲突 / `--no-commit`）时，pre-commit 把从 master 合入的 core 文件判 OUT_OF_SCOPE —— `check_scope.same_as_master`
  比的是 `master..HEAD`，而 pre-commit 时 HEAD 还是合并前。写测试时又暴露同根漏洞：`agent_rules/*` 等特殊文件"与 master 相同即放行"
  比的也是 HEAD 而非暂存区，`--staged-only` 下业务 agent 可在本次提交里改写自己的 `allow.txt`（扩权）。
- **修复**（`check_scope.py`）：`same_as_master(path, staged)`：staged 模式比暂存区 vs master；新增 `in_merge()`（rev-parse，兼容 worktree）
  与 `same_as_merge_head()`（暂存区 vs MERGE_HEAD），合并过滤改用二者；均设 `cwd=ROOT`。属 P-0129 F9 范围内修复（P-0129 仍 in-progress）。
- **测试**：`test_installer_commit_gate.py` +3（合并导入通过、合并中夹带越界改动被拒、改写自身 allow.txt 被拒，均经真实 hook）；
  反向校准：0.48.0 的 check_scope 上 3 例全 FAIL。全量 pytest 337 passed，脚本风格全过。版本 0.48.0 → 0.48.1。**发布待 owner 确认**。
