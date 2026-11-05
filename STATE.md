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

### 2026-11-05 — 自动 merge 提交门禁 + 子宪法审计误报（0.48.3，未发布）

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

### 2026-11-05 — 发布 v0.48.2（deva-vani 升级反馈修复）

- owner 确认后推送 1 commit（8921f45），`gh release create v0.48.2`；workflow 42023042411：build / publish-pypi success。
- 核实：`gh release list` Latest = v0.48.2；PyPI 版本端点 `/pypi/governance-core/0.48.2/json` 含 wheel + sdist。
- 已通知 deva-vani：四个 clone 升 0.48.2 后各跑一次 doctor / check_agent_roles / audit_sub_constitutions；P-0129 验收第 1–3 项待 agent-platform 会话实测回报。

### 2026-11-05 — deva-vani 升级反馈修复（0.48.2）

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
