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

### 2026-05-18 — P-0065 Phase 3 candidate envelope + layer tagging

- 改动：新增 `governance_core/candidates/`（envelope 模块：三 kind
  skill/hook/mechanism + drift 类；`build_envelope` / `validate_envelope` /
  `validate_metadata` / `make_candidate_id`）；新增 CLI
  `tools/validate_candidate.py`；`discovery/extractor.py` 加 `--layer` flag →
  写 learned skill `layer:` frontmatter；`extract-skill.md` 插入 layer 分类
  步骤；`lesson-classification.md` 加 generic-vs-project 轴。
- 涉及：`governance_core/candidates/{__init__,envelope}.py`、
  `governance_core/tools/validate_candidate.py`、`discovery/extractor.py`、
  `commands/extract-skill.md`、`skills/lesson-classification.md`。
- 关键决策：`layer ∈ {candidate-common, business}`，默认 candidate-common
  （过报便宜、漏报无声）；envelope 目录式（candidate.json + payload 子目录）。
- 测试：13 项单测、真实 extractor `--layer` 跑通、upgrade/doctor exit 0、
  build 隔离。commit 1d2a575。

### 2026-05-18 — P-0065 Phase 2 installed-files manifest + baseline hash

- 改动：`install`/`upgrade` 写 `.governance/installed_files.json`（128 文件，
  逐文件 path + baseline_sha256 + source_version + category）；新增查询工具
  `whichlayer.py`（路径 → install-managed / business）；manifest 进 `.gitignore`
  （纯派生物）。附带修 Phase 1 遗留：`verified_at` 码不变则保留，committed
  config.json 不再 churn。
- 涉及：`governance_core/installer.py`、新增 `governance_core/tools/whichlayer.py`、
  `.gitignore`、`docs/{architecture,core-manual}.md`。
- 关键决策：Phase 0 category 枚举执行修正（去 `config`、补 `knowledge`）；
  版本维持 0.2.0（P-0065 六 phase 整体一次发版）。
- 测试：gc dogfood upgrade（128 文件 manifest）、`whichlayer` 6 路抽检、
  `doctor` exit 0。commit ef791c1。
