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

### 2026-07-09 — 发布 v0.40.1（P-0120：publish-knowledge Step 4 方向门修复 / #132）

- **bump**：0.40.0 → 0.40.1（`pyproject.toml:7` + `governance_core/__init__.py:6`）。patch ——
  P-0120 bugfix：`diff_classify` 派生 `direction`（additive）+ `/publish-knowledge` Step 4.2/4.3
  按 `direction != behind` gate `M-fm-only` collect。
- **发布**：`gh release create v0.40.1`（target master）→ CI `release.yml` build + OIDC Trusted
  Publisher（P-0064）。
- **消费者影响**：升级后 `/publish-knowledge` Step 4 不再把落后 clone 的 `M-fm-only`（`direction:
  behind`）checkout 回 master —— 修复 hub frontmatter 静默回滚（issue #132）。纯修复 + 新工具字段，
  无破坏性。
- **核实**：actual published state 见本 turn 报告（`gh release list` + PyPI `/0.40.1/json`）。

### 2026-07-09 — 处置 report：dup candidate 止回流 + publish-knowledge Step 4 方向门（P-0120 / #132）

- **candidates #129/#131**：`triage-and-trim-bloated-memory-index` 已 promote（P-0114/`fd5939e`/
  v0.38.6），consumer sweep 第 5 次重复提交（#124/#125/#127→#129/#131）。close(not planned) +
  dup 评论；`reject_candidate.py --legacy-rstrip` 登进 `rejected_registry.json`（`block_by_name`，
  含两 issue url）—— 唯一能触达 consumer sweep 的 hub 杠杆，止住回流（手工 close 评论到不了 sweep）。
- **bug #132（P-0120）**：`/publish-knowledge` Step 4 对 `M-fm-only` 无条件 collect +
  `git checkout FETCH_HEAD`；clone 落后 hub 时（`added_in_fm==0`）静默回滚 hub 刚 backfill 的
  frontmatter 字段。修：`diff_classify.py` 派生 `direction`（ahead/behind/mixed/na）；Step 4.2 表 +
  4.3 改为 `direction != behind` 才收；mixed→收（approver 定案）。
- **涉及文件**：`governance_core/tools/diff_classify.py`、`commands/publish-knowledge.md`、
  新 `tools/test_diff_classify.py`（该工具原 **0 测试覆盖**）、`candidates/rejected_registry.json`。
- **测试**：13/13 direction + 38/38 script-style + 147 pytest；`upgrade`+`doctor` exit 0。additive、
  可整体 revert，不碰 contracts/。
- **未发布**：source-only 落地；release（版本 bump + `gh release`）留人工确认（core-A3）。

### 2026-07-08 — 发布 v0.40.0（P-0119：签字验收门 + execution-class 校准轨）

- **bump**：0.39.0 → 0.40.0（`pyproject.toml:7` + `governance_core/__init__.py:6`）。minor ——
  P-0119 additive 加第三/四道 approve form-gate + `/proposal run` runner。
- **发布**：`gh release create v0.40.0`（target master）→ CI `release.yml` build + OIDC Trusted
  Publisher（P-0064）。
- **消费者影响**：升级后 approve 多两道 form 门：③签字验收（每个 `## Approval Criteria` 项须带
  check token `cmd:`/`agent-rubric:`/`human-verify:`，**迁移期 WARN**，cutover 2026-07-08
  grandfather）；④execution-class 校准门（仅 frontmatter 带 `execution:` 的提案，BLOCK）。新
  `/proposal run` 子命令（dry-run 默认）。均 additive，普通提案只多一个 WARN。
- **核实**：actual published state 见本 turn 报告（`gh run` + PyPI `/0.40.0/json`，按版本端点为准）。

### 2026-07-08 — P-0119 Phase 2：execution-class 校准硬门 + /proposal run runner

- **校准门**：`gate_calibration_adequacy(body)`（FORM：execution-class 提案每个真 phase 须有
  `gate: <check-token>` + `calibration: neg→FAIL; golden→PASS`）；approve 对 `execution:` 提案
  硬 BLOCK + `--allow-uncalibrated-gate`；audit Check 16（WARN，共享谓词，cutover grandfather，
  非-execution 免检）。
- **runner `/proposal run <id> [--execute]`**：跑 approved/in-progress 的 execution-class 提案
  per-phase `gate:`。**默认 dry-run**（只列不跑）；`--execute` 才跑 `cmd:` gate。非 approved /
  非 execution-class → 拒绝。安全：cmd 任意、repo root 同步执行、approve=授权、dry-run-default。
- **文档**：`commands/proposal.md` 补 approve 四门说明 + `run` 章节 + 子命令表行。
- **测试**：`test_proposal_gates.py` +8（校准门 / phase 提取 / gate token），共 18；既有 gate
  测试 68 无回归；audit 0/0。
- **P-0119 全 phase（0-2）完成**；Phase 3（签字门 WARN→BLOCK）留待一个 rotation 后翻转。
- **改动**：`governance_core/{tools/proposal_lib.py, tools/audit_proposals.py,
  tools/test_proposal_gates.py, commands/proposal.md}`。

### 2026-07-08 — P-0119 Phase 0-1：签字验收门（第三道 approve form-gate）

- **背景**：trade-agent handoff `proposal-signed-acceptance-gates.md` —— 在现有两门
  （Current State/Design）上加第三道签字门 + execution-class 校准轨。§1 引用核对对齐 main
  （唯一漂移：Design gate 在 `proposal_lib.py:829` 非 brief 说的 `:486`）；§5 todo 桥本仓无
  （不引入）；§7 命名定 `execution: gates` + `/proposal run`。P-0119 approved（全 4 phase）。
- **Phase 0（契约）**：新 `contracts/proposal_gate_schema.md`（check/gate/calibration grammar）；
  `proposal_frontmatter_schema.md` 加 optional `execution` 字段 → v1.2.0。
- **Phase 1（通用签字门）**：`proposal_lib.approval_criteria_adequacy(body)`（FORM：每个 Approval
  Criteria 项须带一个 check token `cmd:`/`agent-rubric:`/`human-verify:`）；`_v2_scaffold` 项模板
  token 化；approve 路径追加**迁移期 WARN**（stderr，非 BLOCK，Phase 3 再翻）+
  `--allow-unsigned-criteria`；`audit_proposals` Check 15（WARN，共享谓词，cutover 2026-07-08
  grandfather）。
- **dogfood**：Check 15 立刻 WARN 了 P-0119 自身 3 个未签通用项 → 补 token 后 audit 0/0；本提案
  Approval Criteria 全按签字格式（自证）。
- **测试**：`test_proposal_gates.py` 10 例全过；既有 gate 测试（design_contract/rigor/classify）
  60 例无回归。
- **待续**：Phase 2（execution-class 校准硬门 + `/proposal run` runner，含 arbitrary-cmd 安全面）、
  Phase 3（签字门 WARN→BLOCK，rotation 后）。
- **改动**：`governance_core/{contracts/proposal_gate_schema.md(新), contracts/proposal_frontmatter_schema.md,
  tools/proposal_lib.py, tools/audit_proposals.py, tools/test_proposal_gates.py(新)}`。

### 2026-07-07 — Candidate curation：4 open issue 清空（3 dup + 1 拒）

- **审查**：`/curate-candidate`。open candidate = #124/#125/#127
  `triage-and-trim-bloated-memory-index` + #126 `headless-browser-visual-verify`。
- **#124/#125/#127（关 dup）**：三者 payload body 与包源
  `governance_core/skills/triage-and-trim-bloated-memory-index.md` **逐字相同**
  —— 该 skill 已于 2026-07-01 经 **P-0114**（commit `fd5939e`, v0.38.6）promote 入源。
  属"已 promote candidate 被 consumer sweep 重复 re-file"，`gh issue close --reason
  "not planned"` + dup 评论（根因：consumer 侧仍挂 `layer: candidate-common`，建议 retag）。
- **#126（拒 + advisory）**：headless-Chrome 截图验证 SVG/HTML = 通用渲染/工程技巧，
  非 governance/meta，超出 charter（同 2026-07-01 #120 判例）。
  `maintainer/reject_candidate.py --issue 126 --also-close`，advice：retag `layer:business`
  本地保留。`block_by_name=false`（只按 payload sha 拦，泛化重写版仍可再邀）。
- **改动**：`governance_core/candidates/rejected_registry.json` +1 条（committed ledger）。
  无能力新增 → 无 /proposal、无版本 bump。candidate 队列现为空。
