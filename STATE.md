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

### 2026-07-10 — P-0122：session-boundary-guard quote-aware redirect（消除引号内 `>` 误报）

- **残留（#134/P-0121 记在案）**：redirect 正则把任意 `>` 当重定向符，引号内的 `>`（commit
  message `-m "x > /path"`、内联脚本 `python -c "a >> b"`）被误当写目标 → 误 block。本 session
  每个带 `>` 的 commit 都得绕 `-F` 文件。
- **修（P-0122，approved）**：新增 `_quoted_char_mask` 纯helper（左到右追踪单/双引号态），
  `extract_bash_paths` 仅对 `redirect` label 跳过"`>` 操作符落在**平衡引号**内"的匹配。引号不平衡
  → 不信 mask、按重定向处理（fail-safe 过度 block，不 under-block）。verb 类 pattern（cp/mv/
  Remove-Item…）不受影响（需真 verb，不会对任意引号内 `>` 误报）。
- **权衡（已在 ADR 记录）**：引号内 subshell 重定向（`bash -c 'echo > /out'`）不再被抓——但那是
  subprocess 内写，**本就是 guard 的 documented non-goal**（#135 Gap B），不失任何已保证的覆盖。
- **验证**：boundary-guard 51/51（新增 47 引号内 commit-msg `>` 放行、48 内联 `>>` 放行、49 真实
  未引号重定向照旧 block、50 引号 TARGET 照旧 block、51 引号不平衡 fail-safe）+ peer 全过。
- **live 自证**：本条 commit 的 message 内联含 `>` 且未用 `-F` —— 部署后的 quote-aware enforcing
  copy 放行了它（若旧版会 block）。
- **涉及**：`governance_core/tools/{session-boundary-guard.py, test_session_boundary_guard.py}`。

### 2026-07-10 — 测试卫生：pytest 不再爬 gitignore 的 artifacts/

- **问题**：`pytest`（repo root）会收集 gitignore 的 `artifacts/candidate-review/**` 里的废弃
  candidate payload（各自带 `test_*.py`）→ 14 个假失败 + 与源码测试的 basename 碰撞。
- **修**：`pyproject.toml` 加 `[tool.pytest.ini_options] norecursedirs`（含 `artifacts` + 复原
  pytest 默认排除项）。纯 dev 配置，不影响 wheel/消费者，无版本 bump。
- **验证**：artifacts 假失败清零（15→8 failed）。剩余 8 个是**既有**包源布局假失败（hook/config
  测试在 `governance_core/tools/` 布局下 config 解析失败；经 autonomy 层 `tools/` 跑 21/21 全过）——
  排除 artifacts 移除了 basename 碰撞、把这批一直存在的布局假失败暴露出来，非本次引入。
- **遗留（未纳入本次）**：`pytest`-from-package-source 对 hook/config 测试的布局假失败是更深的
  "规范测试入口"问题（见 memory gc-test-suite-run-from-autonomy-layer），单列。
- **涉及**：`pyproject.toml`。

### 2026-07-10 — 发布 v0.41.0（P-0121 / #135：boundary-guard 覆盖全部写工具）

- **bump**：0.40.3 → 0.41.0（`pyproject.toml:7` + `governance_core/__init__.py:6`）。**minor** ——
  收紧 enforcement（block 更多），对消费者是行为破坏（gate-all vs 旧三名单）。
- **发布**：`gh release create v0.41.0`（target master）→ CI `release.yml` build + OIDC Trusted
  Publisher（P-0064）。
- **消费者影响**：升级后 `session-boundary-guard` 用 shape-based 路由 gate 全部写工具（PowerShell/
  NotebookEdit/Monitor/未来 shell/command 形 MCP）；经这些工具的合法跨界写须走
  `CLAUDE_BOUNDARY_OVERRIDE=1`。Read/Glob/Grep 跨界读不受影响。
- **核实**：actual published state 见本 turn 报告（`gh release list` + PyPI `/0.41.0/json`）。

### 2026-07-10 — P-0121 / #135：session-boundary-guard 覆盖全部写工具（shape-based）

- **gap #135**：`session-boundary-guard` 只 gate `{Bash, Edit, Write}` 三个工具名，matcher=`""`
  对所有工具触发但对其余工具名 fast-exit —— PowerShell 工具 / NotebookEdit / Monitor 全部
  绕过边界检查、无 enforcement。
- **修（P-0121，approved）**：`main()` 由 tool-NAME allowlist 改为 **shape-based 路由**：①有
  `command` 字段 → command-scan（Bash/PowerShell/Monitor/未来 shell/command 形 MCP，无名单）；
  ②`WRITE_PATH_TOOLS={Edit,Write,NotebookEdit,MultiEdit}` 显式集 → path-check。**路径工具刻意
  不按 field-shape 判**——`file_path`/`path` 被 READ 工具（Read/Glob/Grep）共用，shape-only 会
  误 block 跨界**读**。新增 PowerShell 写 cmdlet（Remove-Item/New-Item/Copy-Item/Move-Item/
  Add-Content）+ `$null` device sink。
- **收紧权衡**：经 PowerShell 工具静默成功的合法跨界写现在须走 `CLAUDE_BOUNDARY_OVERRIDE=1`
  （audited；critical 永不豁免）——explicit+logged 的更好姿态。
- **非目标（ADR 边界）**：subprocess/脚本内写（需 OS 级 sandbox，resource-layer 轨）；path 形
  MCP 写工具（field-shape 无法与读工具区分，defer）。
- **验证**：boundary-guard 46/46（新增 32-46：PowerShell block/allow + `$null`/NUL sink +
  NotebookEdit + **Read/Glob/Grep 跨界读照旧 allow** 回归门）+ peer 全过。
- **部署注意**：enforcing copy 是 user-global `~/.claude/hooks/`，`upgrade --project-root .` 不碰
  它（见 [[session-boundary-guard-enforced-from-user-global]]）——本 session 生效需另行重装 user
  层 hook（跨项目、待 user 确认）。
- **涉及**：`governance_core/tools/{session-boundary-guard.py, test_session_boundary_guard.py}`。

### 2026-07-10 — 发布 v0.40.3（#134：session-boundary-guard device-sink 放行）

- **bump**：0.40.2 → 0.40.3（`pyproject.toml:7` + `governance_core/__init__.py:6`）。patch ——
  纯 hook 误报修复，无行为破坏、无新字段。
- **发布**：`gh release create v0.40.3`（target master）→ CI `release.yml`（`release: published`
  触发）build + OIDC Trusted Publisher（P-0064）。
- **消费者影响**：升级后 `session-boundary-guard` 不再把 `2>/dev/null` / `>/dev/null` / `2>NUL`
  这类 stderr/stdout 丢弃重定向误判为跨界写而 block 整条命令；真实越界重定向目标照旧 block。
- **核实**：actual published state 见本 turn 报告（`gh release list` + PyPI `/0.40.3/json`）。

### 2026-07-10 — 修复 #134：session-boundary-guard 放行 device-sink 丢弃重定向

- **bug #134**：`session-boundary-guard.py` 的 redirect 提取器把 `2>/dev/null` / `>/dev/null` /
  `2>NUL` 里的 sink 当写目标。Windows 上 `normalize_path_for_match("/dev/null")` 相对当前盘符
  解析成 `C:/dev/null`（越界）→ **整条 Bash 命令被 block**。高频误报：任何 `grep ... 2>/dev/null`、
  `cmd >/dev/null 2>&1` 都被拒。（`2>&1` fd-dup 早已被 capture class 的 `&` 排除，此次只补 device-sink。）
- **修**：新增 `DEVICE_SINKS` 集合（`/dev/null` `/dev/stdout` `/dev/stderr` `/dev/zero` `/dev/tty` `nul`），
  在 `extract_bash_paths` 里对**未经路径解析的 RAW token**大小写不敏感匹配后 skip。只收窄误报，
  不开任何真实写路径：sink 不在 `CRITICAL_PATH_PATTERNS`、真实越界重定向目标（`cmd > /outside`、
  `> ~/.ssh/...`）照旧 block。
- **单一权威源收敛**：user 已手动热修 enforcing copy `~/.claude/hooks/session-boundary-guard.py`
  解自己燃眉之急并提 #134 让我落到包源；我把包源对齐到 #134 提案原文，改后包源 ≡ user-global
  enforcing copy ≡ repo autonomy `tools/`（`governance-core upgrade --project-root .` 重装两次）。
- **classify**：NO_PROPOSAL（单 agent scope 内、非宪法/契约的窄误报修复；issue 即设计+审查记录）。
- **验证**：boundary-guard 31/31（新增 28-31 device-sink 放行 + 22/23 真实越界照旧 block）+ peer
  derive_session_boundary 全通过。
- **涉及**：`governance_core/tools/session-boundary-guard.py`、`governance_core/tools/test_session_boundary_guard.py`。

### 2026-07-09 — 发布 v0.40.2（#133：shipped governance 文档 carrier_class 合规）

- **bump**：0.40.1 → 0.40.2（`pyproject.toml:7` + `governance_core/__init__.py:6`）。patch ——
  纯 knowledge frontmatter 合规修复（11 个 shipped governance 文档 backfill `carrier_class: reference`）。
- **发布**：`gh release create v0.40.2`（target master）→ CI `release.yml` build + OIDC Trusted
  Publisher（P-0064）。
- **消费者影响**：升级后 `audit_knowledge.py` 不再对 gc-shipped `knowledge/governance/*.md` 报
  carrier_class transitional WARN —— 消费者 knowledge audit 干净通过，无需碰 install-managed 文件（#133）。
- **核实**：actual published state 见本 turn 报告（`gh release list` + PyPI `/0.40.2/json`）。

### 2026-07-09 — 修复 #133：backfill carrier_class 到 gc-shipped governance 文档

- **bug #133**：gc 随包发的 `knowledge_governance/*.md` 缺 `carrier_class`，而同包发的
  `contracts/knowledge_frontmatter_schema.md` 声明其 transitional-required（v1.2.0 warn，v1.3.0
  hard-fail）→ 消费者 `audit_knowledge.py` Check 12 对 gc 自有文件常驻 WARN 且**改不掉**
  （install-managed，本地加 = drift 被 `upgrade` 覆盖）。"hub 不合自己发的 schema"。
- **修**：11 个缺失文件 backfill `carrier_class: reference`（`knowledge/governance/` → `reference`，
  由 taxonomy §3 + schema §3.4 + 5 个现存文件三重锁定）；`README.md` 无 frontmatter 豁免；插入在
  `owner:` 行后。幂等脚本 byte-preserving（每文件恰 +1 行）。
- **classify**：NO_PROPOSAL（机械 backfill 现有 required 字段、audit oracle 验证、无
  rule/contract/skill/逻辑改动）。
- **验证**：upgrade 后 audit_knowledge 的 11 个 governance carrier_class WARN 全清（仅剩 2 个
  `knowledge/design/*` hub 本地 business 文件，非 gc-shipped，超范围）；38/38 script + 147 pytest；
  `upgrade`+`doctor` exit 0。
- **未做（建议）**：无回归门防新 governance 文档再漏必填字段（审包源合规需 source↔installed 布局
  映射）—— 留作后续 follow-up。
- **涉及**：`governance_core/knowledge_governance/{testing-pyramid, constitution-protection-mechanism,
  memory-staleness-policy, resource-layer-hardening, sub-constitution-red-lines,
  test-production-unification, scope-enforcement-mechanism, agent-least-privilege,
  data-analysis-discipline, artifacts-layout, skill-scenario-clusters}.md`。

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
