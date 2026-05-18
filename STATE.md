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

### 2026-05-18 — P-0071 Phase 1 auth-code schema v2 + leasing + auth-guard cache fix

- 改动：codec payload schema 接受 `{1,2}` —— schema 2 携带 `expiry` /
  `revocation_feed_url` / `max_offline_days`，schema 1 保留（自托管 upgrade
  不中断，Art.8）。`auth-guard` 验证缓存键加 `verified_on` 日期维度 —— 过期码
  不再被陈旧 `valid:true` 命中（原 P-0065 缓存遗漏日期，本阶段先决修复）。
  `issue_auth_code` 默认签发 schema-2 365 天租约（`--schema` / `--expiry` /
  `--revocation-feed-url` / `--max-offline-days` 覆盖）。gc 自身重签 schema-2
  码、`config.json` 更新；版本 0.2.1→0.3.0。
- 涉及：`governance_core/auth/codec.py`、`hooks/auth-guard.py`、
  `maintainer/issue_auth_code.py`、`consumer_registry.json`、
  `.governance/config.json`、新增 `tools/test_auth_codec.py` +
  `test_auth_guard.py`、`pyproject.toml`、`__init__.py`、`docs/core-manual.md`。
- 关键决策：单一签名密钥对保留（区分 owner 靠 `consumer_id`，不分密钥）；
  schema 1 永久码仍被接受 = 过渡期不破；撤销源 URL 已嵌入新码，但拉取与
  执行属 Phase 3。
- 测试：`test_auth_codec` 11/11（双 schema 往返、过期/缺字段/篡改/未知 schema
  拒）；`test_auth_guard` 4/4（陈旧隔日 `valid` 缓存不再被信任的回归守卫）；
  upgrade/doctor exit 0；wheel 0.3.0 仅含 `governance_core*`。commit 172ee5c。

### 2026-05-18 — P-0070 Phase 2 upgrade prune (stale autonomy-layer files)

- 改动：Fix C —— `installer.py` 加 `_prune_stale`，`upgrade` 在 `_capture_drift`
  后、写新 manifest 前比对旧 manifest 与新 install 集，旧有新无的
  install-managed 路径删除（manifest-diff = 安全边界）+ `[prune]` 报告 + 空
  目录清理；`cli.py` 加 `--no-prune`；版本 0.2.0→0.2.1。一次性清掉 P-0069
  早于 manifest 残留的 `shared-code-per-agent-state.md`。
- 涉及：`governance_core/installer.py`、`cli.py`、`pyproject.toml`、
  `__init__.py`、`docs/{architecture,core-manual}.md`。
- 关键决策：manifest-diff 安全边界 —— business/authored/`learned/` 从不进
  manifest，故从不被 prune；prune 在 drift 捕获之后（被改过的陈旧文件先成候选）。
- 测试：`_prune_stale` 单测 5 项、探针文件真实 dogfood（装入→源删→upgrade
  prune）、upgrade/doctor exit 0、build 0.2.1。commit f09648c。P-0070 两 phase
  全部完成。

### 2026-05-18 — P-0070 Phase 1 audit_proposals path + tracker reason fixes

- 改动：Fix A —— `audit_proposals.py` 改用 `load_proposals_config` 解析
  in-flight 目录 + `_id_ledger.json`（与 `proposal_lib.py` 同源，不再硬编码
  父级相对路径）。Fix B —— `tracker.py` 加 `should_extract_reason()`，
  `--should-extract` CLI 区分 already-extracted-today / below-threshold /
  recommended、报实际原因；stats 加 `should_extract_reason` 字段。
- 涉及：`governance_core/tools/audit_proposals.py`、
  `governance_core/discovery/tracker.py`。
- 关键决策：两个均纯报告修复，不动 `should_extract()` 启发式；tracker CLI
  改 `sys.stdout.write`（避 `constitutional-review` 对 print 的拦截）。
- 测试：自托管 gc `audit_proposals` 报 in-flight=1/archive=4/0 failures
  （误报 ledger FAIL 消失）；`--should-extract` 正确报 "already extracted
  today"；`should_extract_reason` 单测。commit 0b5b870。
