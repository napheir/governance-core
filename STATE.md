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

### 2026-07-01 — 发布 v0.38.7（候选 curation 批 + funnel WS-D）

- **发布**：`gh release create v0.38.7`（target master）→ CI release run `28493093455`
  → build + OIDC Trusted Publisher。跳过 0.38.5/0.38.6 中间版（未单独发），一次带上三个 patch。
- **核实（实际发布态，非 intent —— memory `release-verify-actual-published-state`）**：run
  jobs build + publish-pypi 均 success；PyPI JSON `info.version == 0.38.7`，含 wheel + sdist
  （`governance_core-0.38.7-py3-none-any.whl` + `.tar.gz`）。
- **覆盖**：0.38.5 CRLF parser fix + reject #120；0.38.6 promote #121 guide；0.38.7 funnel
  loaded-counter (#122)。push `04829e1..fb67a35`。

### 2026-07-01 — 完成 #122：skill-usage funnel loaded-counter（P-0115）

- **问题**：funnel `load` 列对 learned/guide 恒 0 —— 它们经 Read `.md` body 消费、不走
  Skill 工具（skill-usage-tracker 只听 Skill），path C 的 Read 半从未接线（P-0113 WS-D）。
- **改动（7 处，包源）**：`tracker.record_loaded`（per-day dedup、独立于 `record_use`）+
  `funnel_row` 扩 `loaded_count`/`last_loaded`；`registry._emit_funnel` load 列改
  `use_count + loaded_count`；新 hook `skill-read-tracker.py`（PostToolUse/Read →
  record_loaded）；`hooks_manifest.json` 注册；`runtime_import_audit.FAIL_OPEN_GC_IMPORTERS`
  登记（否则 doctor exit 9）；`runtime-import-discipline.md` 补行。
- **refinement（经用户确认）**：load = use_count + loaded_count，而非 issue 字面「仅
  loaded_count」—— guide 也能经 Skill 工具加载，只读 loaded_count 会静默丢该信号；两计数器
  事件源不相交，求和不重复计。
- **验证**：test_skill_funnel 23/23（+14 新）、candidate-recovery 16/16；hook 端到端
  subprocess（exit 0、同日 dedup=1、非 skill/非 Read 均 no-op）；upgrade `settings 20 hooks`、
  doctor exit 0（hooks=21 / registered=20）；wheel 隔离 OK（top-level 仅 `governance_core*`、
  含新 hook、`maintainer/` 无泄漏）。版本 0.38.6→0.38.7。
- **Non-Goals**：v1 不做意图分类；不碰 sync_infra CENTRAL_HOOKS（多-clone，hub N/A）。
- 涉及：`tracker.py`、`registry.py`、新 `skill-read-tracker.py`、`hooks_manifest.json`、
  `runtime_import_audit.py`、`runtime-import-discipline.md`、`test_skill_funnel.py`、版本×2。

### 2026-07-01 — 候选 curation：promote #121 triage-and-trim skill（P-0114）

- **#121 promote → guide**：`triage-and-trim-bloated-memory-index`（trade-agent）判为
  charter 内、通用、net-new（size 轴，补 `memory-staleness-policy` 的 time 轴）。经
  P-0114（classify→create→approve→implement→archive）。payload `type: learned→guide`、
  去 `layer`、补 house frontmatter，body 逐字保留。落 `governance_core/skills/`，tier-B
  SessionStart 注入（无需改 manifest）。
- **决策记录**：`registry.record_candidate` 记 `promoted`（非 `candidate.py promote`，
  避免 raw payload 覆盖手改 —— memory `curate-promote-clobbers-genericized-payload`）。
- **验证**：registry table 列出新 guide；upgrade `.claude/skills 18→19`、doctor green；
  wheel 隔离 OK（top-level 仅 `governance_core*`、含新 guide、`maintainer/` 无泄漏、
  skills .md 20）。版本 0.38.5→0.38.6。
- **cross-link #122**：本 guide 的 B1 毕业 gate（closure check 确认 surface 可达）是
  policy 半；#122 funnel loaded-counter 是 instrument 半（另案）。
- 涉及：新 `triage-and-trim-bloated-memory-index.md`、`consumer_registry.json`、版本×2。

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
