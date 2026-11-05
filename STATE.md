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

### 2026-11-05 — 起草 P-0131 + rotate_state 归档标题修复（0.48.4，未发布）

- **P-0131 已起草并提交评审（pending）**：merge 导入按来源提交归属。现状：`check_scope.py:279-290` 对与 MERGE_HEAD 相同的越界文件
  整体放行、不看来源；core 分支写死为本地 `master`，而 config 已有 `core_branches` / `upstream_branch`（`config.py:103` 对后者用了
  `.get` 默认值）。方案：从 config 推导 core 引用；只放行来自 core 历史的导入，非 core 提交（含 merge 提交的冲突解决 / 夹带改动，
  `--diff-merges=dense-combined` 实测可列出）触及的越界文件判 `IMPORTED_OUT_OF_SCOPE` 并点名提交。三个 phase。
  验收命令逐条预跑：`-k foreign` 会命中已有的 `test_foreign_pre_commit_left_alone`，改为 `-k foreign_agent_branch`。
- **deva-vani 0.48.3 实测**：四个 clone 都有 pre-commit + pre-merge-commit，doctor / check_agent_roles / audit_sub_constitutions 全过；
  `--no-ff --no-commit` + `git commit` 的 sync 通过；DEFER 路径尚未在真实 sync 中触发。
- **rotate_state 首次归档写入上游标题**（deva-vani 报）：`ARCHIVE_HEADER` 写死 "# Trade Agent 项目状态文档 — Archive"，hub 自己的
  STATE_ARCHIVE.md 也是这个标题。改为取 STATE.md 的 H1 加 " -- archive"（无 H1 时 "# STATE archive"）；已有归档保留原标题。
  首次新建归档时 stats 带 `archive_created` 并 WARN 提示与 STATE.md 一起暂存；`/wrap-up` Step 2 写明 rotation 改动或新建
  STATE_ARCHIVE.md 时必须一起 add。hub 归档标题已改。
- **测试**：+3（`test_rotate_state_archive.py`），对旧版反向校准 3 例全 FAIL。全量 pytest 350 passed，脚本风格全过。
  版本 0.48.3 → 0.48.4。**发布待 owner 确认**。

### 2026-11-05 — 发布 v0.48.3（自动 merge 提交门禁 + 子宪法审计）

- owner 确认后推送 1 commit（e5e3dfb），`gh release create v0.48.3`；workflow 42028597542：build / publish-pypi success。
- 核实：`gh release list` Latest = v0.48.3；PyPI 版本端点 `/pypi/governance-core/0.48.3/json` 含 wheel + sdist。
- 已通知 deva-vani（他们等 owner 看过 `/upgrade` 预览再升级；本机 governance-core 为 editable 安装，指向本仓库工作区）。

### 2026-11-05 — 自动 merge 提交门禁 + 子宪法审计误报（0.48.3）

- **背景**：deva-vani 四个 clone 已升到 0.48.2，三项修复全部确认；`/sync-repos` 不加 `--no-verify` 实测通过（`--no-ff --no-commit` 后 `git commit`）。
  另报两个问题。
- **自动 merge 不经门禁**（P-0129 F9 覆盖缺口）：无冲突的 `git merge` 自动提交，运行的是 pre-merge-commit 而非 pre-commit。
  探测（`artifacts/p0129/probe_pre_merge_commit.py`）：pre-merge-commit 运行时 MERGE_HEAD / MERGE_MSG 都还没写，只有 `GIT_REFLOG_ACTION`；
  hook 失败后 git 才写 MERGE_HEAD 并保留暂存的 merge。→ 新增 `check_scope.py --merge-commit`：与 master 相同的文件放行，
  其余越界文件 `[DEFER]` exit 1，由 `git commit` 经 MERGE_HEAD 感知的 pre-commit 收尾。installer 用 `COMMIT_GATES` 表装两个 stub
  （新模板 `default_config/pre-merge-commit.template`），doctor 两个都查。
- **audit_sub_constitutions 误报**：`git log --all --grep=docs(constitution)` 把 merge 进来的 core 总宪法提交也算上，并对整份 CLAUDE.md
  跑正则（附录反放宽文字命中 `豁免.*红线`）。改为：只扫 regen 实际使用的子宪法文件（`agent.<name>.md`，缺则 legacy `agent.md`），
  HEAD 上的路径限定历史（默认历史简化排除未改变本分支该文件的 core 提交），只对新增行跑正则。旧版连业务 agent 自己的放宽也漏报。
- **文档**：`/sync-repos` Step 2 改 `git merge --no-ff --no-commit`，说明普通 merge 的 DEFER 行为、MERGE_HEAD 不存在时跳过 Step 4；
  core-manual 补 0.48.3 说明；skill `verify-guard-fires-in-its-target-context` 补第三种提交上下文。
- **测试**：+7（pre-merge-commit 安装、自动 merge DEFER 后 commit 收尾、自动 merge 夹带越界三方合并结果被拒、master 最新时自动提交、
  core 自动 merge、merge 进来的 core 宪法提交不报、业务 agent 放宽自身子宪法被报）；对 0.48.2 反向校准 5 例 FAIL，
  另 2 例两版都过（防过度拦截）。全量 pytest 347 passed，脚本风格 28 个全过；wheel 含新模板。版本 0.48.2 → 0.48.3。**发布待 owner 确认**。
- **未处理、待 owner 定**：merge 导入豁免不看来源——任何分支 merge 进来、与 MERGE_HEAD 相同的文件都放行（含其他业务 agent 的分支）。
