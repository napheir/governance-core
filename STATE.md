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

### 2026-11-05 — P-0129 Phase C：多 clone 自动生成会话边界锚（F3）

- **问题**：新装多 clone 消费者没有 `.claude/settings.json` 的 `projectRoot: "../"`，会话边界只到 clone，`../shared_state/` 提案写不了；
  补这个文件又被 classify 闸门拦，只能 `CLAUDE_BOUNDARY_OVERRIDE` 解开。
- **修复**（`installer.py`）：`_ensure_boundary_anchor` 在 agents > 1 且 `shared_state_root` 与 clone 同在项目目录下时，幂等加入该键；
  保留其他键，已有不同值不动（告警），JSON 无法解析不改写。单 agent（hub）与非标准布局不写。doctor 对缺锚的多 clone 告警（不影响退出码）。
  安全前提是 Phase A 的按 config 判定身份。core-manual 同步。
- **测试**：新增 `test_installer_topology_anchor.py` 6 例（真实 `install()`；含端到端：装完后 `derive_session_boundary` 解析到项目目录）。
  全量 pytest 292 passed，脚本风格全过；hub upgrade 后无 settings.json（单 agent），doctor OK。

### 2026-11-05 — 发布 v0.46.0（P-0129 Phase A/B/E）

- owner 确认后推送 master（8 commits）并 `gh release create v0.46.0`；release workflow 41991242166：build / publish-pypi success。
- 核实已发布状态：`gh release list` Latest = v0.46.0；PyPI JSON latest = 0.46.0（wheel + sdist）。
- 已通知 deva-vani：`artifacts/deva-vani/2026-11-05-release-0.46.0.md` + 会话消息（升级前先写业务 agent allow.txt、核对 clone_dir；
  升级后实测 3 个场景回报 = P-0129 验收第 4 项）。
- 下一步：P-0129 Phase C/D/F → 0.47.0；P-0129 保持 in-progress。
