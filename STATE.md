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

### 2026-11-05 — P-0129 Phase B：混合条款从诞生起归项目所有（F2）

- **问题**：0.45.x 首次 install 把 7 条 `MIXED_CLAUSES` 登记进 `installed_files.json`；第二次 install 跳过已存在副本，
  `_prune_stale` 把它们当陈旧文件删除（deva-vani 四个 clone 全部缺失）。
- **修复**（`installer.py`）：`_render_clauses` 返回 `(managed, seeded)`，混合条款只在缺失时种子化、不进清单；
  新增 `_is_business_owned_clause`，`_prune_stale` 与 `_capture_drift` 对旧清单里已登记的混合条款跳过
  （一次性迁移，不删、不当 drift 上送）；被删掉的条款下次 install 自动重新种子化。
- **测试**：新增 `test_installer_mixed_clauses.py` 5 例（走真实 `install()`，只替身签名校验）；反向校准：HEAD 旧 installer
  连续 install 两次后 7/7 → 0/7。全量 pytest 276 passed；hub upgrade 后 18 条款完好，doctor OK。
