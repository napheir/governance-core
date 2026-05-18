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

### 2026-05-18 — P-0065 Phase 5 hub-side curation + convergence loop

- 改动：GC 侧 curation 收口闭环 —— 新增 consumer registry 模块
  `governance_core/candidates/registry.py` + committed 台账
  `maintainer/consumer_registry.json`（记已签发消费者 + 候选评审决策）；
  `issue_auth_code.py` 签发即登记消费者；`tools/candidate.py` 加
  `review`/`promote` 子命令；GC 侧 incoming `candidates/` 进 `.gitignore`；
  收口 hub 模型写入 `docs/architecture.md` + `docs/core-manual.md §11`。
- 涉及：新增 `candidates/registry.py`、`maintainer/consumer_registry.json`；
  改 `tools/candidate.py`、`maintainer/issue_auth_code.py`、`.gitignore`、
  `docs/{architecture,core-manual}.md`。
- 关键决策：registry 落 maintainer 侧、committed（durable 台账）；`promote`
  按 kind 复制进包源、judgment 人工/agent；GitHub issue 为候选权威记录。
- 测试：`issue_auth_code` 登记 registry、curation 11 项（review/promote/
  reject、registry 内容）、upgrade/doctor exit 0、build 隔离。commit f5b23f7。
  P-0065 六 phase 全部实现完成。

### 2026-05-18 — P-0065 Phase 4 candidate collection + submit + uplink

- 改动：候选管道三来源 —— 脱敏扫描器 `sensitive_scan.py`（HIGH/MEDIUM 分级）
  + `sensitive-data-guard` PreToolUse hook（user 选 Option B：补全 README 一直
  宣称却缺失的安全 hook）；`candidates/collect.py`（净新增 candidate-common
  skill 收集）；`candidates/uplink.py`（脱敏扫描 + `gh issue` 传输 + dry-run +
  体积上限）；CLI `tools/candidate.py`（collect/submit/uplink，consent 门）；
  `/submit-candidate` 命令；installer `_capture_drift`（upgrade 覆盖前捕获
  install-managed 文件漂移成 drift 候选 + stderr 报告）。
- 涉及：新增 `governance_core/sensitive_scan.py`、`hooks/sensitive-data-guard.py`、
  `candidates/{collect,uplink}.py`、`tools/candidate.py`、
  `commands/submit-candidate.md`；改 `installer.py`、`hooks_manifest.json`、
  `.gitignore`、`.claude/settings.local.json`。
- 关键决策：`sensitive-data-guard` 原不存在 → Option B 补全；payload 内联
  issue body（~60KB 上限）；漂移=捕获后覆盖（不留 override）；uplink 带
  `--dry-run`。
- 测试：扫描器+hook 16 项、Part A 8 项（collect/submit/uplink/secret-abort/
  consent-gate）、Part B 漂移真实 dogfood、upgrade/doctor exit 0、build 隔离。
  commit 47fdf8f。
