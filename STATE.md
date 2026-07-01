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

### 2026-07-01 — 发布 v0.38.7（候选 curation 批 + funnel WS-D）

- **发布**：`gh release create v0.38.7`（target master）→ CI release run `28493093455`
  → build + OIDC Trusted Publisher。跳过 0.38.5/0.38.6 中间版（未单独发），一次带上三个 patch。
- **核实（实际发布态，非 intent —— memory `release-verify-actual-published-state`）**：run
  jobs build + publish-pypi 均 success；PyPI JSON `info.version == 0.38.7`，含 wheel + sdist
  （`governance_core-0.38.7-py3-none-any.whl` + `.tar.gz`）。
- **覆盖**：0.38.5 CRLF parser fix + reject #120；0.38.6 promote #121 guide；0.38.7 funnel
  loaded-counter (#122)。push `04829e1..fb67a35`。

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
