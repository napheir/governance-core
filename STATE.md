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

### 2026-07-08 — 发布 v0.39.0（P-0118：_tiers.json 退休 / theme 派生）

- **bump**：0.38.9 → 0.39.0（`pyproject.toml:7` + `governance_core/__init__.py:6`）。minor
  —— P-0118 退休整个中心化 `_tiers.json` 子系统、injection/index/audit 改从 per-skill
  `theme` 派生，属消费者可见行为变更。
- **发布**：`gh release create v0.39.0`（target master）→ CI `release.yml` build + OIDC
  Trusted Publisher（P-0064）。
- **消费者影响**：升级后其 `_tiers.json` 被忽略（injection 改读 `theme:universal` + learned）；
  audit Check 11/16 改 theme 版；`build_skill_index`/`skill_catalog` 输出改 theme 分组。过时
  的 `test_pending_catalog_tolerance.py` 被正常 prune（非 ownership transfer，无需 EXEMPT）。
- **核实**：actual published state 见本 turn 报告（`gh run` + PyPI `/0.39.0/json`，
  memory `release-verify-actual-published-state`：按版本端点为准，勿信 aggregate 缓存）。

### 2026-07-08 — P-0118 Phase 2-3：_tiers.json 全面退休，builder/auditor/writer 收敛到 theme

- **Phase 2（builder 去域化）**：`build_skill_index.py` / `skill_catalog.py` 重写为从
  `theme` 派生分组（universal / core-only / `<agent>` / learned），**删硬编码 "Trade Agent"
  + universal/project/branch TIER_ORDER** 域泄漏；不再需 `_tiers.json` 即可运行；render 去
  时间戳变确定性；顺带清 skill_catalog 一处 Art.7 `⚠` Unicode 违规。
- **Phase 3（auditor + writer 收敛）**：
  - `audit_knowledge` Check 11 `_audit_skill_tiers`（bijection + non-hub carve-out）→
    `_audit_skill_themes`（theme 存在 + INDEX 新鲜度）；Check 16 universal 改从 `theme:universal`
    派生、learned 恒 surfaced。**删 `_detect_non_hub` 及整套 non-hub carve-out**（per-file
    theme 无中心漂移，carve-out 存在理由消失，见记忆 `nonhub-audit-carveouts-are-a-family`）。
  - `extract-skill.md` writer：删 hub/non-hub 的 `_tiers.json` 编目步（6/6b/7/8/6N/7N/8N）→
    learned 恒 auto-surfaced，极简为"可选 cluster + 可选 rebuild index"。
  - 事实指针同步：`session-context.py` docstring、`art_15` 条款、`skill-scenario-clusters.md`
    的 "universal 集来自 _tiers.json" → 改 `theme`。
  - **candidate.py 无需改**（collect 用 `layer: candidate-common` envelope 轴，不碰 _tiers）。
- **测试**：删 `test_pending_catalog_tolerance.py`（整文件测已移除的 non-hub carve-out）→ 新增
  `test_skill_theme_audit.py`；重写 `test_scenario_coverage_audit.py` / `test_command_coverage_exempt.py`
  为 theme 版。4 个 skill 测试 23/23 绿；全 tools 套件无新增回归（8 仍为包源布局伪失败）。
- **dogfood**：upgrade 后 hub `build_skill_index` 生成 INDEX.md（33 skills / Universal+Core-only），
  `--check` 幂等，`audit` Check 11 [OK] + 整体 healthy，`skill_catalog` [Universal](28)/[Core-only](5)。
- **发现待办（正交）**：`rotate_state.py:31` ARCHIVE_HEADER 硬编码 "Trade Agent" —— 另一处域泄漏，
  属 STATE archive 非 skill-tier，留后续。
- **P-0118 全 4 phase 完成** → /proposal complete。

### 2026-07-08 — P-0118 Phase 0-1：skill 复用分类统一到既有 theme（注入解耦）

- **背景**：trade-agent handoff `skill-reuse-layer-unification.md` 提议给 skill 加
  per-skill `reuse` frontmatter、退休中心化 `_tiers.json`。核对现状发现诊断**被低估**：
  gc 包源已 ship 整套 `_tiers.json` 子系统（reader + 2 builder + writer + auditor），
  且 `build_skill_index.py:41` / `skill_catalog.py:36` **硬编码 "Trade Agent"** 域泄漏。
- **关键转向**：实施中发现 gc **已有** per-skill 广度字段 `theme:`（universal/core-only/
  `<agent>`，sync_infra 强制、决定跨 clone 分发；`sync_infra.py:231-251`）—— 即文档称
  "不存在"的那个字段。故**不新增 `reuse`**（会成第 5 条重叠轴），维护者批 Option 1：
  injection/index 直接派生自 `theme`、退休 `_tiers.json`。零新字段 / 零 backfill。
- **P-0118**（pending→approved→in-progress）：完整统一，4 phase；本次交付 Phase 0-1。
- **Phase 0（doc）**：`knowledge_governance/skill-scenario-clusters.md` 记录 theme 作为
  广度字段 + 注入派生规则 + 退休 `_tiers.json`（title/tags/updated 同步）。
- **Phase 1（注入）**：`registry.py` 加 `SkillEntry.theme` + `_extract_metadata` 解析
  theme；`emit_bounded_injection` 注入池 = 所有 learned + `theme:universal` guide，
  **停读 `_tiers.json`**。重写 `test_skill_injection_bounded.py`（9 cases 含 `_tiers.json`
  忽略回归守卫）全绿；auditor 18/18 不回归。hub dogfood：SessionStart 从 counts-only
  升级为 theme 派生的 bounded 菜单（18 universal guide，capped 10 + "+8 more"）。
- **待续**：Phase 2（builder/catalog 派生 theme + 清 "Trade Agent"）、Phase 3（auditor
  Check 11/16 + extract-skill writer + candidate collect + 退休 `_tiers.json` 物理文件）。
- **改动**：`governance_core/{knowledge_governance/skill-scenario-clusters.md,
  discovery/registry.py, tools/test_skill_injection_bounded.py}`。

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

### 2026-07-01 — 发布 v0.38.9（#123 boundary-guard + #119 intentional-drift）

- **发布**：`gh release create v0.38.9`（target master）→ CI release run `28497552876`
  → build + OIDC Trusted Publisher。跳过 0.38.8 中间版（未单独发）。
- **核实（实际发布态）**：run jobs build + publish-pypi 均 success；PyPI 按版本端点
  `/0.38.9/json` version==0.38.9，含 wheel + sdist。注意 aggregate `/json` 一度因 Fastly
  缓存滞后仍显 0.38.7 —— 按版本端点为准（memory `release-verify-actual-published-state`）。
- **覆盖**：0.38.8 #123 boundary-guard UTF-8 + fail-closed；0.38.9 #119 intentional-drift。
  push `c6ae193..d79fb7b`。

### 2026-07-01 — 修 #119：消费者声明 intentional-drift → layer:business（P-0117）

- **问题**：`installer._capture_drift` 把每个 drift 文件都打 `candidate-common`，消费者
  sweep 每次 upgrade 重复 uplink 同一**有意** drift（digest 台账因日期戳 re-mint 挡不住；
  rejected_registry 被动 + 名全局，语义也不对）。
- **改动（ADR option 1，用户定）**：加 `installer._load_intentional_drift()` 读消费者自有
  `.governance/intentional_drift.json`（`{"schema":1,"drift_targets":[...]}`，fail-safe、
  Art.4 无 get-default、路径 `/` 归一）；`_capture_drift` 对声明路径传 `layer="business"`
  （sweep 只吃 candidate-common → 天然跳过），其余不变，**仍捕获**（保 capture 安全网）。
- **跨仓库对齐**：文件名 + schema 锁定 trade-agent P-0125 已发 interim → 消费者剪枝可零改造退役。
- **验证**：pytest 11/11（+5 新：parser 4 + business/candidate-common 分层 1）；upgrade +
  doctor exit 0；wheel 隔离 OK（consumer `intentional_drift.json` 不入 wheel/manifest）。
  版本 0.38.8→0.38.9。schema 归 parser 所有（同 P-0115 `.usage.json` 先例，非 contracts/）。
- 涉及：`installer.py`（常量 + helper + layer 选择）、`test_installer_drift_eol.py`、版本×2。

### 2026-07-01 — 修 #123：session-boundary-guard UTF-8 字节读 + fail-closed（P-0116）

- **bug**：`governance_core/tools/session-boundary-guard.py` 的 `main()` 用文本模式
  `json.load(sys.stdin)`（随 GBK/cp936 locale 误解 CJK 路径）且 `except: exit(0)` fail-open。
  它是**唯一**还这样的 hook —— 其余 20 个 hook 全用 `sys.stdin.buffer.read().decode("utf-8")`。
- **改动（用户定 fail-closed）**：`main()` 改 UTF-8 字节读（对齐全家，T-0015）；parse/decode
  失败 → stderr BLOCKED + `exit 2`（fail-closed，boundary-guard 专属加固，siblings 保持
  fail-open）。边界判定逻辑不动。
- **回归测试（+2 → 27）**：CJK 路径在 `PYTHONIOENCODING=ascii` 下仍 BLOCK（旧码会
  UnicodeDecodeError → fail-open exit 0，测试证伪）；malformed payload → BLOCK（fail-closed）。
- **无自锁**：项目 upgrade 只装项目 `tools/`，不碰 `~/.claude/hooks/` 活动守卫。
- **验证**：test_session_boundary_guard 27/27；upgrade + doctor exit 0；wheel 隔离 OK。
  版本 0.38.7→0.38.8。先例 P-0101（同款 UTF-8 修 classify-fast）/ P-0087。
- 涉及：`session-boundary-guard.py`、`test_session_boundary_guard.py`、版本×2。
