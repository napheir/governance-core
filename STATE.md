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

### 2026-11-05 — 发布 v0.47.0（P-0129 Phase C/D/F）

- owner 确认后推送 master（5 commits）并 `gh release create v0.47.0`；release workflow 41995202256：build / publish-pypi success。
- 核实：`gh release list` Latest = v0.47.0；PyPI JSON latest = 0.47.0（wheel + sdist）。P-0129 的 F1–F10 至此全部发布。
- 已通知 deva-vani：`artifacts/deva-vani/2026-11-05-release-0.47.0.md` + 会话消息。
- 待办：P-0129 等 deva-vani 回报验收第 4 项实测后 complete + 归档；起草 P-0130（knowledge owner 枚举 / `audit_proposals` VALID_AGENTS /
  `check_agent_roles` / `audit_hooks` 写死上游角色，改为从 config 推导，涉及两份契约）；mab 侧问题与授权码进 git 另行处理。

### 2026-11-05 — P-0129 Phase F：提交前 scope 门禁（F9），版本 0.47.0（未发布）

- **问题**：install 不生成任何 `<agent>.allow.txt`、不装 pre-commit；`check_scope.py --agent core` 缺 `core.allow.txt` 即 FATAL ——
  第十二条的提交前防线在所有消费者里都不存在。
- **修复**：`check_scope.py` 不传 `--agent` 时按 config 判定身份，core 直接 PASS，跳过 `#` 注释行（与 edit-write-guard 一致）；
  installer 为每个非 core agent 生成带注释的空 allow.txt（deny-all，归项目所有，不进清单），在 git 根目录装
  `.git/hooks/pre-commit`（sh 存根，LF，调用 `check_scope.py --staged-only`）：带标记才刷新，别人的 hook 不覆盖，设了 `core.hooksPath` 不装。
  doctor 对空 allow list、缺失或外来的 pre-commit 告警。
- **偏差**：未接 `check_constitution_change.py` —— 它要读 pre-commit 时还不存在的提交信息、模板过时、输出 Unicode 符号，会拦住所有
  `CLAUDE.md` 提交；宪法源由 edit-write-guard L5 守护。另修 doctor 里 `hooks_dir` 变量被覆盖导致 OK 行 `hooks=0` 的回归（未发布前发现）。
- **dogfood**：hub upgrade 后装上 pre-commit，本提交即经过该门禁（core → PASS）。
- **测试**：新增 `test_installer_commit_gate.py` 9 例（含经真实 hook 的 `git commit`：业务越界被拒、加规则后通过、core 任意通过）。
  全量 pytest 307 passed，脚本风格全过；版本 0.46.0 → 0.47.0，wheel 含两个模板、无 `maintainer/`。**发布待 owner 确认**。

### 2026-11-05 — P-0129 Phase D：新项目生成总宪法初稿（F4）

- **问题**：新消费者的 `constitution/total.md` / `agent.md` 是 stub，regen 出的 `CLAUDE.md` 没有任何条款；Claude Code 只加载 `CLAUDE.md`，
  通用条款到不了上下文，启动即 STALE。
- **修复**：新模板 `governance_core/default_config/constitution_total.md.template`（现有 `default_config/*.template` glob 已覆盖打包，
  未按提案新建 `templates/`，记为偏差）：每条通用条款一节"精简陈述 + `.governance/clauses/` 指针"、agent 拓扑表、项目条款占位。
  `installer._seed_constitution`：`total.md` 缺失才生成，再用项目自己的 `tools/regen_constitution.py` 生成 `CLAUDE.md`；
  已有 `total.md` 不动，无 regen banner 的手写 `CLAUDE.md` 不覆盖。doctor 对不含任何条款指针的 `total.md` 告警。
- **限制**：mab 模板自带 stub `total.md`，所以 mab 新建的项目要等 mab 停发该 stub 后才受益（mab 侧，非本提案）。
- **测试**：新增 `test_installer_constitution_seed.py` 6 例（含模板对每个条款文件的指针完整性、装后 `regen --check` 为 OK）。
  全量 pytest 298 passed，脚本风格全过；hub upgrade 后宪法不变，doctor OK。
