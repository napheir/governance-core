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

### 2026-07-01 — 候选 curation：修 CRLF 解析 blocker + reject #120

- **blocker（bug fix）**：`governance_core/candidates/ledger.py` 的
  `parse_payload_from_issue_body` 用 `^### candidate\.json\n...` 锚 LF，但 gh 在
  Windows hub 取回的 issue body 是 CRLF → `reject_candidate` + ledger self-heal
  在真实 issue 上全解析失败。函数顶部加 `body.replace(CRLF, LF)` 单点归一化（同时
  修潜在 sha 保真：CRLF hub 重算 digest 永对不上 consumer 的 LF digest）。
  `test_candidate_recovery.py` 加 2 个 CRLF 用例（`_build_issue_body` 全 LF、从不
  触发 CRLF，正是漏网原因 —— 见 memory `hub-cannot-dogfood-crlf-drift`）。16/16 +
  uplink-drift 20/20 通过。
- **#120 reject-with-advisory**：`external-api-categorical-backfill`（trade-agent）
  判出 charter —— 数据管道工程 skill、非治理能力；gc 18 个 common 层 skill 全为
  治理/harness/meta。`maintainer/reject_candidate.py --also-close`，registry 记
  sha=35318c3c、advice=留作 trade-agent 本地 business skill。
- **版本**：0.38.4→0.38.5。upgrade + doctor green（hooks=20 / registered=19 / clauses=18）。
- 涉及：`ledger.py`、`test_candidate_recovery.py`、`rejected_registry.json`、版本×2。

### 2026-06-24 — 未决后续（deferred follow-ups，knowledge 去域化）

P-0113 去 trade 化 sweep 后刻意未扩范围、留待后续判断的两项（用户确认本轮到此为止）：

1. **`data-analysis-discipline.md` 的非路径类残留**：仍含 `/validate-pipeline` skill
   引用、`rules-agent R3` 的 Dense/sparse 域术语；且该文件整体偏 data 域 —— 是否该留在
   gc 通用 knowledge、还是整体下沉/移除，是比"清死链"更大的判断题。grep token gate 不覆盖
   这类（非路径、非已列 token），需专门一案。
2. **provenance `proposals/<name>.md` 根级指针（~10 处）**：技术上悬空（根级 proposals
   无 .md、全在 `_archive/`），但属迁移/提取出处，P-0086 先例明确保留。如要把它们重指
   `proposals/_archive/<year>/p-NNNN-*.md` 实际路径，另起一个 proposal（与去域化正交）。

两项均非 bug、不影响 audit（Failed:0）/ gate；纯文档完善度，优先级低。

### 2026-06-24 — 发布 v0.38.4（P-0113 去 trade 化 knowledge sweep）

- **发布**：bump `0.38.3→0.38.4`，commit `f24e040`，push，`gh release create v0.38.4`
  → CI build + OIDC Trusted Publisher。
- **核实**：CI run `28099806337` success（build + publish-pypi；watch 中途遇瞬时 401，
  改 `gh run view` 确认 success）。PyPI JSON `info.version == 0.38.4`，含 wheel + sdist。
  发布前 clean build sanity：wheel 内 17 个 knowledge .md **零域 token 命中**、METADATA
  0.38.4、顶层仅 `governance_core` 无泄漏（`unlock_trade` 字面量触 command-guard，用字符串
  拼接绕过校验脚本）。
- **覆盖**：本 patch 即 P-0113（去 trade 化 knowledge sweep）。

### 2026-06-24 — P-0113：去 trade 化 knowledge 残留 sweep（P-0086 后续）

- **方案（approved，Option B）**：阶梯 REMOVE 死 cross-ref / FIX-PATH 真文档错路径 /
  GENERICIZE 教学举例 token，机制文字逐字保留。Open Question §3「现存子目录」表按默认
  (b) reframe 为"推荐映射"+ disclaimer（用户未否决）。对齐 P-0086/P-0079 先例。
- **改动（9 文件，包源 `knowledge_governance/`）**：artifacts-layout、knowledge-html-profile、
  sub-constitution-red-lines、test-production-unification、knowledge-carrier-classes（最重，
  §2 表/各类举例/§3 表/§7 边界表）、scope-enforcement-mechanism、proposal-classify-fast-path、
  agent-least-privilege（§4 Futu/trade 举例泛化）、data-analysis-discipline。改动文件 bump
  `updated: 2026-06-24`。**保留** provenance `proposals/...` 指针、有效 gc cross-ref、中性
  `agent_rules/<agent>` 占位。
- **scope 扩展（grep gate 价值）**：grep gate 揪出 disposition 表（基于 path-grep）漏掉的
  同类 token 残留 —— artifacts-layout per-source 表的 `strangle`×3 + `rules.strangle.
  dataset_registry`、html-profile:36 与 data-analysis:38 的 `experiment_protocol`/`strangle`。
  按 gate 零命中 exit criteria + 用户"全部解决"一并清理（per-source 表/datasets 段泛化为
  `<agent>`/`<consumer>` 占位）。
- **验证**：grep gate（trade token 集）**零命中**；指向不存在类别的具体死路径**零残留**
  （只剩 `<占位>`）；`governance-core upgrade` 后 hub 自审 **Failed: 0 healthy**
  （warnings 34→28）；tool 测试 16/16 sanity。
- **故意未扩范围（flag 待后续）**：data-analysis-discipline.md 仍含**非路径类**残留
  —— `/validate-pipeline` skill 引用、`rules-agent R3` 的 Dense/sparse 域术语；且该文件
  整体偏 data 域，是否适合留在 gc 通用 knowledge 是更大问题。非本 sweep 的 path/token
  scope，留作独立判断。

### 2026-06-24 — 发布 v0.38.3（P-0112 + 悬空 related 引用清理）

- **发布**：bump `0.38.2→0.38.3`（两处），commit `a38b5b8`，push，
  `gh release create v0.38.3` 触发 `release.yml` → build + OIDC Trusted Publisher。
- **核实（非意图）**：CI run `28097541003` success（publish-pypi 21s）；PyPI JSON
  `info.version == 0.38.3`，含 wheel + sdist。发布前本地 clean build sanity：wheel 含
  P-0112 `index_present` 守卫、两个悬空 `related:` 已去（针对 frontmatter 块校验，
  非全文 —— 正文 §6 边界表仍有 data-flow.md/models 举例残留，属更大去域化任务、未扩
  范围）、METADATA 0.38.3、顶层仅 `governance_core` 无泄漏。
- **覆盖**：本 patch 含 P-0112（INDEX.md 崩溃修复）+ 2 个悬空 related 引用清理。

### 2026-06-24 — 修 2 个预存悬空 related 引用（P-0112 surface 出的独立问题）

- **来源**：P-0112 修好崩溃后 hub 自审能跑到 per-file 检查，暴露 2 个悬空 `related:`。
- **判定**：两个目标均**不存在**（gc 包无 `knowledge/decisions/` 目录 —— 上游项目路径
  惯例），属上游域残留。无内容可保留 → **删悬空条目**（非补建目标）。NO_PROPOSAL
  （窄文件、清晰复现、纯内容、无机制/契约变更）。
- **改动**（包源 `governance_core/knowledge_governance/`）：
  - `knowledge-html-profile.md`：删 `related: knowledge/governance/data-flow.md`，
    `updated` 2026-05-30→2026-06-24。
  - `resource-layer-hardening.md`：删 `related: knowledge/decisions/adr-session-boundary-guard.md`，
    `updated` 2026-06-01→2026-06-24。
- **验证**：`governance-core upgrade` 刷新 hub `knowledge/governance/` 安装产物后，
  `python tools/audit_knowledge.py` → **Failed: 0「Knowledge base is healthy.」**
  （hub 自审首次干净通过；34 warnings 为 transitional/WARN-only，非 failure）。

### 2026-06-24 — P-0112：audit_knowledge 容忍缺失 knowledge/INDEX.md（修预存崩溃）

- **触发**：实施 P-0111 时 hub 自审 `python tools/audit_knowledge.py` 暴露预存崩溃
  —— `main()` 无条件读 `knowledge/INDEX.md`（`:209`），缺失即裸抛 FileNotFoundError。
  `main()` 对缺 `knowledge/`、缺 contract 都有干净 `[FATAL]` 守卫，唯独 INDEX.md 没有。
- **关键约束**：不能简单返回空 map —— Check 4（owner-category，`:680`）对每个 knowledge
  文件查 owner map，空表 → 全员误 FAIL。要的是"**跳过 Check 4**"而非"空表"。
- **方案（P-0112，approved，Option A）**：INDEX.md 缺失 → WARN + `index_present=False`
  + 跳过 Check 4（owner-category 是多 agent 归属概念，单 agent 退化），其余检查照跑。
  INDEX.md **存在时行为零变化**。否决 B（FATAL，会让 hub 自审永久失败）/ C（给 hub 播种
  INDEX.md，无生成器+安装产物，更大设计题，defer 到 Non-Goals）。
- **改动**：`governance_core/tools/audit_knowledge.py` —— `parse_category_owner_map`
  加防御性 `is_file()` 短路返 `{}`；`main()` 加 `index_present` 守卫 + WARN；Check 4
  整段包 `if index_present:`。新增 `test_audit_index_absent.py`（5 例）。
- **测试**：新套件 5/5；含 pending_catalog / scenario_coverage / command_coverage 共
  23/23。hub 自审现跑通（WARN + 完成，不再 traceback）；`governance-core upgrade`
  dogfood 重装，自治层副本同样不崩。
- **新 surface 的独立问题（非本提案 scope，待报）**：崩溃修好后审计跑到，暴露 2 个预存
  悬空 `related:` 引用 —— `knowledge-html-profile.md → knowledge/governance/data-flow.md`、
  `resource-layer-hardening.md → knowledge/decisions/adr-session-boundary-guard.md`
  （包源 `governance_core/knowledge_governance/`，之前被崩溃掩盖）。

### 2026-06-24 — 发布 v0.38.2（P-0111 / gc #114 修复）

- **发布**：bump `0.38.1→0.38.2`（`pyproject.toml` + `governance_core/__init__.py`），
  commit `5ea6712`，push master，`gh release create v0.38.2` 触发 `release.yml` →
  build + OIDC Trusted Publisher。
- **核实（非意图）**：CI run `28084278001` success（build 13s + publish-pypi 19s）；
  PyPI JSON `info.version == 0.38.2`，`0.38.2` 含 wheel + sdist 双产物。发布前本地
  `python -m build`（先清 build/dist/egg-info）sanity：wheel 含 11b carve-out 串、
  METADATA Version 0.38.2、顶层仅 `governance_core`（无自治层/maintainer 泄漏）。
- **issue #114**：发布后关闭（fixed-and-shipped，留言指向 v0.38.2 + `upgrade`）。
- **patch 语义**：纯 bugfix → patch bump，与 0.38.1（围栏 bugfix）体例一致。

### 2026-06-24 — P-0111：Check 11b 非 hub branch-tier phantom 豁免（gc #114）

- **触发**：下游消费者 Trade Agent 报 gc #114 —— `audit_knowledge.py` Check 11b
  （tiers→registry phantom）缺 Check 11a / 16a 都有的 non-hub 豁免。叠加 `_tiers.json`
  `branch` tier「全局同步一份 / 文件 branch-local」结构错配，在非拥有者 clone 产生
  **无本地动作可清零**的死锁：留文件 → 16a FAIL，删文件 → 11b phantom FAIL。阻塞每个
  消费者的 `/publish-knowledge` `Failed=0` 门。
- **方案（P-0111，approved）**：Option 2 最小对称补丁。11b phantom 循环对
  `home_tiers == {"branch"}` 的 phantom 在 `non_hub` clone 下降级 WARN，复用既有
  `_detect_non_hub`，**零契约变更**。窄判（`== {"branch"}`）：同挂 universal/project 的
  phantom 仍 FAIL；hub / 无 config 仍严格 FAIL。Option 1（branch tier 加 ownership
  标注，需改 `_tiers.json` schema）显式 defer。
- **改动**：`governance_core/tools/audit_knowledge.py` 11b 段（`:412` 起）；
  `test_pending_catalog_tolerance.py` 加 5 例（non-hub branch→WARN / hub→FAIL /
  无 config→FAIL / non-branch phantom→FAIL / branch+universal 双挂→FAIL）。
- **测试**：`test_pending_catalog_tolerance.py` 11/11；含 `test_command_coverage_exempt`
  / `test_scenario_coverage_audit` 三套 18/18。直接对包源跑 #114 repro：non-hub branch
  phantom → `failed=0, warned=2`，死锁解除。`governance-core upgrade --project-root .`
  dogfood 重装，根副本 `:429` 已带 carve-out。
- **预存无关项（未扩范围）**：hub 自审 `python tools/audit_knowledge.py` 崩于
  `parse_category_owner_map`（`:209` 读缺失的 `knowledge/INDEX.md`），发生在 Check 11
  之前，与本改动无关。

### 2026-06-23 — Bugfix：`_extract_section`/`_extract_h3` 不识别 fenced code block（v0.38.1）

- **Bug**：`tools/proposal_lib.py` 的 `_extract_section`（及 P-0124 新增的 `_extract_h3`）
  按行扫 `## `/`### ` 前缀但**不跟踪 ``` / ~~~ 围栏**。后果：一个在代码围栏里引用
  `## Design & Contract` 模板（含 `<占位>`）的"元提案"，会让 `_extract_section` 抓到
  **围栏内的占位模板**而非围栏后真正填好的段 → `design_contract_adequacy` 误判"占位/空" →
  approve 门误 BLOCK / audit Check 14 误 WARN。同一 `_extract_section` 被 `current_state_adequacy`
  与 `_extract_scope_file_tokens` 复用 → 属普遍性 robustness bug，非 P-0124 专有。
- **复现确认**：TDD 先加围栏测试，对未修代码跑出**正是报告的错误**
  （`'### Interfaces, I/O & Realization' is empty or still the scaffold placeholder`）。
- **修复**：`_extract_section` + `_extract_h3` 各加 `_FENCE_RE` 围栏状态机——遇 ``` / ~~~ 行翻转
  `in_fence`，`in_fence` 内的 `## `/`### ` 不计作 heading 边界（计作内容）。纯 form 谓词解析
  健壮性修复，**不改门语义、不改 scaffold**。
- **核实差异**：报告称对 `proposals/_archive/2026/p-0124-*.md` 跑 audit——但该归档**不存在**
  （P-0124 是外部引用编号，从未是本仓 proposal，见 [[handed-proposal-id-may-not-be-local]]）。
  改用构造的围栏 fixture + audit-level 测试覆盖该症状。
- **测试**：design `test_proposal_design_contract.py` 加 4 例（`_extract_section`/`_extract_h3`
  单测 + design_contract 围栏 + audit Check 14 围栏）→ 23/23；rigor 加 current_state 围栏例 →
  18/18；自治层全套 proposal 测试 + `audit_proposals --root .` 0/45 失败 0 警告。版本 0.38.0→0.38.1。
- **已知相邻 gap（未扩范围）**：`_count_real_phases` 也按行扫 `### Phase` 非围栏感知；围栏里
  嵌 2-phase 模板会误判 complex。报告未涉、风险低，留作后续。

### 2026-06-23 — P-0124 实现：proposal scaffold 加 Design & Contract 段 + 条件 approve 门（v0.38.0）

- **动机**：scaffold 记 WHAT（Scope）却从不记 HOW-designed —— 无接口签名 / 字段流转契约 /
  流程图，也无处放未决决策。复杂提案在没对齐实现细节时被 approve → 实现漂移（典型：Todo
  Board 当静态页交付、漏建后端）。本提案加一个**比例化、按复杂度有条件 gate** 的设计段。
- **包源改动（全部 `governance_core/`）**：
  - `tools/proposal_lib.py`：`_v2_scaffold` 加 `## Design & Contract`（3 个 H3 子项
    Interfaces·I/O·Realization / Field Dictionary / Flow）+ `## Open Questions`（轻量、不
    gate）；`## Approval Criteria` 改 checklist。新增 form-only 谓词
    `design_contract_adequacy()` + 复杂度触发 `_is_complex_proposal()`（≥2 非占位 Phase
    **或** Scope 触及 `contracts/`）。`transition_proposal` 加 `allow_thin_spec` kwarg + 在
    Current-State 门后插 design 门（仅复杂提案）；CLI 加 `--allow-thin-spec`。`create` 写完
    scaffold 后**自动 emit** proposal_suggest 三路召回 ①②③（`_emit_create_recall`，
    best-effort）。
  - `tools/audit_proposals.py`：Check 14（WARN-only），与 approve 门**共享同一谓词**
    （`design_contract_adequacy` + `_is_complex_proposal`），cutover 2026-06-23、仅复杂+post-cutover。
  - `commands/proposal.md`：文档化设计段 / 条件门 / `--allow-thin-spec` / Open Questions /
    Approval-checklist；"可选建议模块"→ classify 必跑 suggest、create 自动 emit。
  - `knowledge_governance/proposal-drafting-checklist.md`：加 2 条 seed（设计/契约维度、
    realization 边界），来源 P-0124；`updated` 2026-06-23。
- **关键决策**：design 门只判 FORM（占位被替换 / 三子项在），SUBSTANCE 由人审（沿用 P-0108
  form-vs-substance）；Field Dictionary 空表骨架不算 filled。**Open Question（已决）**：本版
  `_is_complex_proposal` 不对"跨 agent 单 phase"触发，dogfood 后再议。
- **测试**：新增 `tools/test_proposal_design_contract.py`（19 例，覆盖 a–f + 谓词真值表）；
  P-0108 rigor 回归 17/17；自治层全套 proposal 测试 design 19 / rigor 17 / suggest 12 /
  classify_fast_hook 9 全绿；`audit_proposals --root .` 0/45 失败 0 警告。版本 0.37.0→0.38.0。

### 2026-06-22 — P-0110 实现：promote quality-gate form-vs-substance skill（gc #106，v0.37.0）

- **来源**：trade-agent candidate #106 `quality-gate-checks-form-human-judges-substance`
  —— 把 P-0108 G1 的 **form-vs-substance** 思路泛化为任意质量门的设计原则（机器验
  FORM/floor，人审 SUBSTANCE/ceiling，拒 LLM-judge）。net-new（gc skills 无同类；两个
  knowledge 匹配是无关 hard-block 机制）。
- **改动**：新增 `governance_core/skills/quality-gate-checks-form-human-judges-substance.md`
  —— 泛化 Notes（去 P-0118 示例 + dangling consumer-skill xref；Workflow 机制 verbatim），
  `theme: universal`，加 `## Discovery`。版本 0.36.0→0.37.0。**发布待用户确认**。
- **同批处理 #107**：candidate id 与 #105 字节相同（已 promote P-0109）→ **dup 关闭**，
  不重复 promote（ledger 已记该 id promoted）。
- **dogfood**：P-0110 经新 scaffold + 研究门 approve（Current State 引用
  `proposal_lib.py current_state_adequacy()` 等实读，放行）—— 这正是 #106 原则本身。
- **测试**：registry 发现（18 skills/32 total，guide）；91 pytest + 21 脚本式 = 0 失败；
  upgrade+doctor exit 0；wheel 0.37.0 隔离干净、skill 入包、无 maintainer 泄漏。

### 2026-06-22 — P-0109 实现：promote audit-subsystem-health skill（gc #105，发布 0.36.0）

- **来源**：consumer trade-agent 以正规 candidate 信封（gc #105，kind/skill，
  auto-eligible）提供 learned skill `audit-subsystem-health-before-proposing-change`。
  策展判定通用治理方法论，用户选 promote。
- **改动**：新增 `governance_core/skills/audit-subsystem-health-before-proposing-change.md`
  —— 泛化 Notes（去掉 P-0117 / auto-refine / gc #103 trade 域示例，改通用 worked
  example；Workflow 机制 verbatim），frontmatter 转 gc guide schema `theme: universal`，
  加 `## Discovery`（router-skip 决策）。版本 0.35.0→0.36.0。
- **scope 判定**：gc 全部 15 个 guide 都是 universal-tier、无 `INDEX.routing.json`/cluster
  基建 → 第 16 个 universal guide，SessionStart name+description surfacing，无需 routing/
  cluster 改动。与 P-0108 checklist dim-4 互补（draft-time nudge vs 可咨询 workflow）。
- **dogfood**：P-0109 由新 scaffold 生成（带 Current State + Alternatives 两段），approve
  时被 P-0108 研究门校验 —— 因 Current State 填了 file:line 而放行（门生效闭环）。
- **测试**：registry 发现新 skill（17 skills/31 total，guide tier）；全量 91 pytest +
  21 脚本式 = 0 失败；upgrade+doctor exit 0；wheel 0.36.0 隔离干净、skill 入包、无
  maintainer 泄漏。

### 2026-06-22 — P-0108 实现：把 Plan-mode 工程 rigor 嫁接到 proposal 管线（gc #104，发布 0.35.0）

- **来源**：trade-agent consumer 以 plain issue **#104**（P-0118）报"pipeline 在治理
  轴是 plan-mode 超集、工程 rigor 轴是子集"。策展判定：issue 正文 + **2 条评论**，
  评论 2（`444f837a`）把 G1 从软 WARN 演进到 **level-D 硬门** —— 按 gc #26 precedent
  采纳"corrected kernel"，用户确认 level-D 强度。
- **三 graft 落 `governance_core/` 包源**：
  - **G2**：`_v2_scaffold` 增 `## Current State (read, not assumed)` +
    `## Alternatives & Rationale` 两段（11 段）。
  - **G3**：`proposal_lib.reconcile()` + `_extract_scope_file_tokens` /
    `_loose_file_match` / `_commit_changed_files` + `reconcile` CLI 子命令（as-built
    覆盖差，advisory）；`commands/proposal.md` complete 加 step-0 reconcile。
  - **G1 level-D**：`current_state_adequacy()` form-only 谓词 → `transition --to
    approved` 硬 BLOCK + `--allow-empty-current-state` 豁免；`audit_proposals.py`
    **Check 13**（WARN-only）复用同一谓词，grandfather pre-cutover（2026-06-22）+
    archive/legacy/draft 豁免。
  - 研究范式 5 维（2 always-form + 3 conditional-substance）落
    `proposal-drafting-checklist.md`（`parse_checklist` 格式）。
- **关键决策**：form-vs-substance split —— 机器只验"有没有"（段在/非占位/≥1 file:line），
  人审"够不够"，拒了 LLM-judge 门。audit WARN 与 transition BLOCK 共用谓词永不打架。
- **测试**：新 `test_proposal_rigor.py` 17 项；全量 **91 pytest + 21 脚本式 = 0 失败**；
  CLI 烟测 reconcile + 门 BLOCK/override 通过；`audit_proposals` 0/43 failures 0 warnings
  （135 旧提案 0 new FAIL）；wheel 隔离 top-level 纯 `governance_core*`、无 maintainer 泄漏、
  新符号确实入包。dogfood：P-0108 本身以目标态起草（带两个新段）。

### 2026-06-18 — P-0106 实现：retire 死掉的 Hermes auto-refine 路径（gc #103，发布 0.34.0）

- **来源**：trade-agent consumer 以 plain issue **#103** 报 dead-code（P-0117）。
  批准前按要求做了全簇调用图核查：`record_step` 全仓库零 producer →
  `steps_taken` 恒空 → `diff_and_refine` 恒 None → wrap-up Step 4b `--auto-refine`
  恒 no-op（且 `--name/--steps` required，wrap-up 那条命令其实会 argparse 报错退出）。
  确认 hooks/tests/`__init__` 导出均无引用、`extract_skill` 等 live 路径独立。
- **关键决策**：用户问「是否该修使其生效而非删」。读下游后判定整链 naive（≥50%
  词袋判定、append-only 写、格式脆弱），即便接 producer 也会往 skill 文档写噪声。
  → 选 **retire 现有 naive 实现 + 另起 v2 设计 proposal P-0107**（LLM 反思 @
  wrap-up + `/update-skill` 门控），初衷被保留而非丢弃。
- **改动（6 文件）**：`discovery/extractor.py` 删 `diff_and_refine`/`refine_skill`/
  `_extract_workflow_steps`/`_find_novel_steps`/`--auto-refine` CLI；
  `discovery/tracker.py` 删 `record_step`/`steps_taken_this_session`/
  `record_refinement` + `steps_taken` 字段管线（含 `session_complexity` 恒 0 的项、
  get_stats 字段/print）；`commands/wrap-up.md` 删 Step 4b 并 renumber 4c→4b/4d→4c +
  清单去「Skill 已精炼」；`commands/extract-skill.md` 删 `refine_skill()` 指针；
  `commands/update-skill.md` 改 stale 理由（保留 learned/*.json 不触发规则）。
  保留 live：`extract_skill` + A/B/C 漏斗（`record_use/surfaced/triggered`）。
- **范围克制**：`weighted_scores` 的 `refinement_count` 项保留（live 评分，P-0107 Q5
  再议是否重接）；不碰 A/B/C 漏斗。
- **测试**：新增 `governance_core/tools/test_auto_refine_retired.py`（6 例:死符号
  消失/CLI 拒 --auto-refine/extract_skill 仍工作/complexity 恒等于 tasks+files//5+2
  无 steps 项/get_stats 无 steps_taken_today）；`test_skill_funnel` 12/12 回归绿。
- **验证**：0.33.0→**0.34.0**；pytest 66 passed（8 个既有源布局 false-fail 经 tools/
  确认 21 passed）；包源零残留引用 + 模块干净导入；upgrade+doctor exit 0（安装层
  wrap-up 无 auto-refine）；wheel 隔离（top-level 仅 `governance_core*`、maintainer
  未泄漏、改动文件齐全）。ledger 记 promoted（采纳 option a）。

### 2026-06-18 — P-0105 实现：Check 16 (16a) 豁免 slash command 覆盖 FAIL（gc #102，发布 0.33.0）

- **来源**：消费者 trade-agent 的 gc 能力 candidate，以 **plain issue #102**（无
  `candidate` label、无 envelope）提交 —— `candidate.py review` 扫不到（命中记忆
  candidate-review-misses-unlabeled-issues：查 `gh issue list` 捞 unlabeled）。
  经 `/curate-candidate` 评估为可促进通用精简，走 `/proposal`。follow-on of
  #101 / P-0104（同一 16a FAIL/WARN 面，additive）。
- **改动**：`audit_knowledge.py` `_audit_scenario_coverage` 加 `command_skills`
  集，16a 循环在 #101 non-hub/learned WARN 分支**之前** `continue` 跳过
  `source_type==command` —— 两 carve-out **可组合**（非替换）。理由：slash command
  始终在 harness Skill-tool 菜单按名可调，可发现性不依赖 SessionStart cluster
  surfacing（P-0113 缺口只针对 consult-only learned/guide）。guide/learned 仍受
  覆盖；16b phantom 不动。
- **范围决策**：**不**扩张到 Check 11（`_audit_skill_tiers`）—— 它有 `unclassified`
  兜底桶（11c 仅 WARN），command 可入桶不 FAIL；Check 16 无此兜底才过度 FAIL，
  故 candidate 精确只 scope 16，超范围会越出已批 proposal。
- **测试**：新增 `governance_core/tools/test_command_coverage_exempt.py`（4 例：
  command 豁免 / 非 hub learned 仍 WARN / guide 仍 FAIL / 16b phantom 不变）。
- **验证**：0.32.0→**0.33.0**；新+回归 13 passed（4 新 + 9 旧）；8 个源布局
  false-fail 经 `tools/` 路径确认通过（记忆 gc-test-suite-run-from-autonomy-layer）；
  upgrade + doctor exit 0；wheel 隔离（top-level 仅 `governance_core*` + dist-info、
  maintainer 未泄漏、新文件齐全）。
- **收尾**：commit `9875ebf`（Implements: P-0105 / Closes #102）；ledger 记 promoted
  （`maintainer/consumer_registry.json`，按记忆 curate-promote-clobbers... 用
  `registry.record_candidate` 直记而非 promote）；gc #102 已评论 + 关闭。

### 2026-06-17 — P-0104 实现：extract-skill business-path + audit Check 11/16 非 hub pending 容忍（gc #101，发布 0.32.0）

- **来源**：消费者 trade-agent 提的 gc 能力请求 issue #101（**非**结构化 candidate
  envelope，故 `candidate.py review` 扫不到 —— 走 /proposal 当能力新增，而非
  candidate promote）。follow-on of #100 / P-0103。
- **Part B（代码）**：`config.py` 加 hub 判定原语 —— `HUB_CONSUMER_ID` 常量 +
  `GovernanceConfig.consumer_id` 字段 + `is_hub` 属性 + `is_non_hub_clone()`
  （default-strict：config 缺失 / 无 consumer_id / hub 一律 strict，membership
  test 无 `.get` 兜底）。`audit_knowledge.py` Check 11a + 16a 对非 hub clone 的
  `source_type==learned` 且 registry-only skill 记 WARN（pending hub catalog）
  而非 FAIL；Check 11 registry 对齐 `project_root=root`（与 Check 16 一致、可隔离
  测试）。hub 行为不变。
- **Part A（skill）**：`commands/extract-skill.md` 加非 hub 分支（建 skill 文件 +
  入自有 `_scenario_clusters.json`，跳过 hub-owned 步骤 6/7/8；audit WARN 不回滚），
  hub 路径原样保留。
- **测试**：新增 `governance_core/tools/test_pending_catalog_tolerance.py`（6 例：
  hub / 非 hub / 缺 config / learned-only narrowness × Check 11a + 16a）。
- **验证**：版本 0.31.0→**0.32.0**；upgrade + doctor exit 0；全测 64 pytest + 21
  script = **85 passed**；wheel 隔离（top-level 仅 `governance_core*` + dist-info，
  maintainer 未泄漏，4 改动文件齐全）。
- **Non-goal**：hub-side cataloging sweep 归消费者 trade-agent **P-0114 WS-1**。
- 实现 commit：本阶段 feat（Implements: P-0104）；关 #101；complete + archive P-0104。
