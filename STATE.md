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

### 2026-07-15 — P-0123：`upstreamed` 终态（issue #136，consumer proposal 上送到 hub）

- **问题**（issue #136）：candidate/uplink 管线把 consumer proposal 的能力上送到 hub 后，
  该 proposal 真正终结、但替代方案落在**另一仓库**，schema 无终态可表达 ——
  `superseded_by` 强制本地相对路径 + 必须存在 + 反向引用（`audit_proposals.py` Check 6），
  跨仓库引用只会永久 audit FAIL。选 issue 的 **shape B**（一等终态）而非 shape A（复用
  `superseded_by`）。
- **改动**（全在包源 `governance_core/`）：
  - 契约 `contracts/proposal_frontmatter_schema.md` → v1.3.0：§3.1 加终态 `upstreamed`；
    §4.4a 要求 `upstreamed_to` + `upstreamed_at`；§5.6 外部引用 format 规则；§7 不变式。
  - `tools/proposal_lib.py`：`VALID_STATUS` / `TERMINAL_STATUS` 加 `upstreamed`；`*→upstreamed`
    从任意态（比照 supersede）；transition 分支 + CLI `--upstreamed-to`；archive date-map；
    新增**共享谓词** `validate_upstreamed_ref`（writer + validator 同一函数）。
  - `tools/audit_proposals.py`：enum / `REQUIRED_BY_STATUS` / Check 17（format-only，**不解析**
    跨仓库引用）/ `upstreamed_at` 日期集。
  - `hooks/session-context.py`：pending banner 用 allowlist，`upstreamed` 自动隐藏（仅补注释）。
  - `commands/proposal.md`：`upstream` 子命令 + 反模式（区分 supersede）。
  - 新增 `tools/test_upstreamed_status.py`（13 例，覆盖 issue 三条验收 + 谓词 + enum 一致性）。
- **关键决策**（用户）：语法可严，但**写入时即 fail-fast**（`transition` 拒坏 ref，报含示例的
  同一条消息），owner 一次改对、不必反复撞 audit —— 故 writer 与 validator 共用谓词与消息。
- **测试**：新 13/13；rigor 18/18、design-contract 23/23、gates 全绿；audit 全库 0/58。
  **dogfood**：`upgrade` 重装后，安装层 CLI 实测 —— 坏 ref 被拒（exit 1，P-0123 未动）、
  好 ref `draft→upstreamed` 三字段齐全（throwaway P-0124 已完整清理，台账回 59）。

### 2026-07-10 — 发布 v0.41.1（P-0122：quote-aware redirect 消除引号内 `>` 误报）

- **bump**：0.41.0 → 0.41.1（`pyproject.toml:7` + `governance_core/__init__.py:6`）。patch ——
  纯误报收窄（引号内 `>` 不再当重定向），不破坏、不开真实写路径。
- **发布**：`gh release create v0.41.1`（target master）→ CI `release.yml` + OIDC Trusted Publisher。
- **消费者影响**：升级后 boundary-guard 不再把 commit message / 内联脚本里引号内的 `>` 误判为跨界
  写而 block 命令；真实未引号重定向照旧 block；引号不平衡 fail-safe。
- **核实**：actual published state 见本 turn 报告（`gh release list` + PyPI `/0.41.1/json`）。

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
