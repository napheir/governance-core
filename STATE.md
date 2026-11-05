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

### 2026-11-05 — P-0129 Phase E：STATE 解析 + .gitignore 受管块，版本 0.46.0（未发布）

- **F6**：session-context 条目改用 `^### \d{4}-\d{2}-\d{2}`（与 `rotate_state._ENTRY_RE` 一致），STATE 模板注释不再被当成条目；
  hub SessionStart 实测已不再列出 `### YYYY-MM-DD`。
- **F10**：installer 在 `.gitignore` 维护起止标记之间的运行时块（cache / usage.json / direction_check_ts / settings.local.json /
  audit / installed_files.json / candidate-outbox）；保留原换行风格、块外逐字节不变、标记损坏则不动。doctor 对"已被跟踪的运行时文件"
  给 note（非告警）——hub 自身会提示 `.claude/settings.local.json`（历史上一直跟踪，属预期）。hub `.gitignore` 已由 upgrade 写入该块。
- **F5**：`.role` 在 Phase A 已停止读取；hub 的 `.role` 文件与宪法第二条表格条目留待 /iterate-constitution。
- **版本**：0.45.1 → 0.46.0（Phase A+B+E）。wheel 检查：顶层仅 `governance_core*`，无 `maintainer/`。
- **测试**：新增 `test_installer_gitignore_block.py` 8 例、`test_session_context_state.py` 2 例；全量 pytest 286 passed，
  脚本风格全部通过；upgrade + doctor OK。**发布待 owner 确认**（core-A3）。
