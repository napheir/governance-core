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

### 2026-05-29 — P-0085 promote #18: knowledge-html-profile §2.5 业务优先节

- 改动：策展通用层候选 **issue #18**（mechanism / drift, trade-agent）—— 把 net-new
  规范节 **§2.5「信息构建原则（业务优先）」**（~100 行）promote 进
  `governance_core/knowledge_governance/knowledge-html-profile.md`，profile
  v1.0.0 → 1.1.0。§2.5 规定 HTML 的**叙事语域**（§2.1–§2.4 管结构）：主叙事用业务
  语言、机器细节下沉 `<details>`、表格列优先业务语义、whole-document 应用范围。
- baseline drift（候选 baseline `432b40…` ≠ 当前源 `1ddbf8…`）→ **不信旧行号**，
  按上下文锚点手工应用（§2.4 末插 §2.5；§2.1 summary / §6 行 / §8 / §9 同步改）。
- **de-trade-ify**（skill step 3）：机制文字逐字保留，仅把消费者域示例换成 gc 自身域 ——
  §2.5.3 正/反例 trade 期权 pipeline（`option_selector` / strangle）→ **gc upgrade/install
  pipeline**（原子覆盖安装 / 改动文件转存 candidate-outbox）；§2.5.6 反模式去掉 `P-0081`
  与 trade section 名（signal_reader / scheduler / 面板）；provenance 改记 P-0085。
- **audit 工具与机器契约不动**：§2.5 是 voice/framing，机器无法判定 → 明确为
  human-review 层（§2.5.5 + §8）；`audit_html_profile.py` 只校验结构、**不随 profile
  v1.1.0 bump**。
- 涉及：`governance_core/knowledge_governance/knowledge-html-profile.md`、
  `pyproject.toml` + `governance_core/__init__.py`（0.18.0 → 0.19.0）、`STATE.md`、
  `shared_state/proposals/core/p-0085-*.md`。
- 关键决策：改包源（Art.11.2），不碰自治副本；独立 proposal/commit（与 #19 分开）。
  **发现既有 de-trade 缺口**：profile §3.3.1（`signal_reader/dedup` Mermaid 例）+ §4.1
  （`artifacts/strangle50/...` autogen 例）是 P-0078 cluster 遗留的 trade 残留，**不在
  P-0085 scope**（Non-Goals 不动 §3/§4）—— 已向 user 提示为后续候选。
- 测试：全套 `tools/test_*.py` **21/21**；`audit_html_profile.py` exit 0（无 HTML 文件、
  工具未改）；de-trade grep 闸门确认 §2.5（168–227 行）零 trade token；dogfood `upgrade`
  → autonomy profile 刷新到 v1.1.0；`governance-core doctor` exit 0。

### 2026-05-29 — P-0084 promote #19: narrow classify-paths governance glob

- 改动：策展通用层候选 **issue #19**（mechanism, trade-agent）—— bug fix。
  `governance_core/tools/proposal-classify-paths.json` v1.0.0 → 1.1.0：governance
  类的 catch-all `.governance/**/*` 收窄为权威子路径
  `.governance/clauses/**/* + core_keywords.json + config.json`。
- 根因：catch-all 命中**瞬态 gitignored** `.governance/candidate-outbox/`
  （collect.py `OUTBOX_REL`），导致 `/submit-candidate` / `/upgrade` drift-uplink
  每次写 envelope 都被 classify-fast PreToolUse hook 误判 `PROPOSAL_REQUIRED`
  硬阻。**gc 自身（self-host 消费者）现也中招** —— 强 dogfood 信号。matcher
  `_classify_match.py` 无 negation operator，故用显式枚举而非 exclude。同时
  剔除派生物 `.governance/installed_files.json`。
- 涉及：`governance_core/tools/proposal-classify-paths.json`、
  `governance_core/tools/test_proposal_classify_paths.py`（加 P-0084 回归断言 +
  docstring 17→19 globs）、`pyproject.toml` + `governance_core/__init__.py`
  （0.17.0 → 0.18.0）、`shared_state/proposals/core/p-0084-*.md`。
- 关键决策：改**包源**（Art.11.2），不碰自治副本；走独立 proposal（与 #18 分开，
  各自 commit/rollback）；保留所有真实治理源覆盖（实测前后对照：candidate-outbox
  / installed_files True→False，clauses/core_keywords/config/CLAUDE.md 仍 True）。
- 测试：`test_proposal_classify_paths.py`（19 globs、回归断言）+
  `test_proposal_classify.py` 9/9 + `test_proposal_classify_fast_hook.py` 7/7
  （自治层）全绿；dogfood `upgrade` → autonomy 副本刷新到 v1.1.0；
  `governance-core doctor` exit 0。

### 2026-05-29 — P-0083 add /curate-candidate command skill

- 改动：新增 `governance_core/commands/curate-candidate.md` —— hub 侧候选策展的
  编排 skill（`/submit-candidate` 的对偶），从本会话 6 轮策展提炼。**指针式
  checklist**（Art.99：只指向权威工具/文档、不复述）：review → classify（通用 vs
  域特定 / net-new / 完整性）→ verify（drift sha 比对 + `git apply --recount` /
  `--ignore-cr-at-eol` 去 CRLF 噪声;去 trade 化）→ 改包源（Art.11.2）→ wire（hook
  manifest + runtime-import-discipline;新数据文件进 package-data）→ validate（bump
  + 测试 + dogfood + doctor + wheel 隔离）→ record（promote/reject）→ `/proposal`
  + 关 issue。版本 0.16.0 → 0.17.0。
- 涉及：`governance_core/commands/curate-candidate.md`（新）、`governance_core/__init__.py`
  + `pyproject.toml`（0.17.0）、`STATE.md` / `STATE_ARCHIVE.md`（rotate）、
  `shared_state/proposals/core/p-0083-*.md`。
- 关键决策：**packaged command skill**（不是 gitignored `.claude/skills/learned/`
  —— 那会被 upgrade 清掉,自托管 hub 的正确归宿是包源 command）；指针式（Art.99
  单一源、零复述 → 不漂移）；把 6 轮踩过的坑编进去（缺件 / CRLF / 去 trade 化 /
  package-data / 自托管 nuance）。本会话 should-extract 一直 YES,此 skill 是其落点。
- 测试：全套 `tools/test_*.py` **21/21**；dogfood `upgrade` → 已装 + registry 发现
  （available-skills 列出 `/curate-candidate`）；`governance-core doctor` exit 0；
  wheel 0.17.0 build OK（top-level 仅 `governance_core` + dist-info、skill 在内、
  `maintainer/` 不泄漏）。

### 2026-05-27 — P-0077 uplink drift diff + --body-file (issue #15)

- 改动：`candidates/uplink.py` 大改 —— `build_issue` 加 drift 分支：
  当 envelope 有 `drift_target` + `baseline_sha256` 且
  `installer._pkg_source_path` 解析得到 baseline 时，body 渲染
  unified diff（against baseline）+ `payload_form: diff` +
  `payload_sha256:` 行（按 ledger._hash_payload 同算法）；无法解析
  baseline 时 fallback legacy full-payload。net-new envelope 路径不
  变（P-0076 ledger rehash 仍依赖 full payload fence）。`gh_command`
  argv 从 `--body body` 改 `--body-file <tempfile>`：用
  `NamedTemporaryFile(delete=False)` 写 body，pass file path 到 gh，
  finally `unlink(missing_ok=True)`。这绕过 Windows
  CreateProcessW ~32K UNICODE_STRING cmdline 限制（Python 把这个
  surface 为 FileNotFoundError，旧版本误归类为"gh missing"）。
  `UplinkError` 在 stderr 含 "label not found" pattern 时附 hint
  打印 `gh label create candidate / kind/skill / kind/hook /
  kind/mechanism` 4 行。`candidates/ledger.py`
  `parse_payload_from_issue_body` 加 drift body 短路：识别
  `payload_form: diff` 后从 body 读 `payload_sha256:` 返回，跳过
  rehash；`discover_uplinked_from_hub` drift body 直接用
  meta["payload_sha256"]。`maintainer/reject_candidate.py` 同样
  drift 路径不 rehash + 不走 pre-0.8.0 heuristic。版本 0.8.0 →
  0.9.0。docs/core-manual.md §11 加 P-0077 drift-as-diff 子节 + hub
  labels setup 子节。
- 涉及：`governance_core/candidates/uplink.py`、
  `governance_core/candidates/ledger.py`、
  `maintainer/reject_candidate.py`、
  `governance_core/tools/test_uplink_drift_diff.py`（新，20 用例）、
  `governance_core/__init__.py` + `pyproject.toml`（0.9.0）、
  `docs/core-manual.md`、`STATE.md`、
  `shared_state/proposals/core/p-0077-*.md`。
- 关键决策：`payload_form: diff` 显式 metadata（不靠"猜身体形状"）；
  drift fallback 到 legacy full-payload 让 uplink 永不因 baseline
  miss 阻塞；P-0076 net-new rehash 路径完全保留（向后兼容）；
  `--body-file` Linux/macOS 也用（统一行为、no-op for them）；
  Windows newline 提醒在测试用 `write_bytes` 控制 bytes。
- 测试：`test_uplink_drift_diff` 20/20（build_issue 9 + parser 5 +
  discover_recovery 3 + gh_command 3）；全套回归 revocation 24 +
  renewal 13 + candidate-attribution 9 + candidate-reminder 7 +
  update-reminder 9 + auth-guard 9 + auth-codec 11 + upgrade-dry-run
  14 + candidate-recovery 14 + rejected-registry 21 +
  uplink-drift-diff 20 = 151/151 全绿。wheel 0.9.0 含 uplink/ledger/
  test_uplink_drift_diff；dogfood upgrade OK；doctor exit 0、hooks
  19/registered 18。

### 2026-05-26 — P-0076 Phase 2 reject feedback registry

- 改动：新建包源 `candidates/rejected_registry.json`（schema 1，含两条
  backfill 条目对应 #4/#6 + #5/#7、`block_by_name: true` 标记 pre-0.8.0
  sha 不可还原场景）。新建包源模块 `candidates/rejected.py`
  （`load_rejected_registry` / `is_rejected` / `should_block` /
  `format_advisory` 四个 API）。`cmd_sweep` 接 `is_rejected` 检查：
  exact → 阻断 + stdout 打印结构化 SKIPPED advisory；name +
  `block_by_name: true` → 阻断；name + `block_by_name: false` → stderr
  warn + 仍 uplink（允许 hub 重评 rewrite）。`candidate-reminder.py`
  hook 扩展：SessionStart 时 cross-check pending 与 registry，被拒
  skill 在 banner 出 WARNING 行。新建 hub 工具
  `maintainer/reject_candidate.py`（`--issue N --reason X --advice Y
  [--also-close] [--dry-run]`），抓 issue body、复用 Phase 1 共享 parser
  解析 payload、自动判 pre-0.8.0 rstrip 场景 → 写 registry +（可选）
  关闭 issue 加 advisory comment。`pyproject.toml` package-data 加
  `candidates/*.json` 让 registry 进 wheel。版本 0.7.0 → 0.8.0（按
  P-0074/P-0075 模式一次性 bump 跨两 phase）。
- 涉及：`governance_core/candidates/rejected.py`（新）+
  `rejected_registry.json`（新）、`maintainer/reject_candidate.py`（新）、
  `governance_core/tools/test_rejected_registry.py`（新，21 用例）、
  `governance_core/tools/candidate.py`（接 `is_rejected`）、
  `governance_core/hooks/candidate-reminder.py`（SessionStart 增 WARNING）、
  `governance_core/__init__.py` + `pyproject.toml`（0.8.0、package-data
  加 `candidates/*.json`）、`docs/core-manual.md`（§11 加 self-heal +
  reject feedback 两段、新 §13 maintainer reject workflow）、`STATE.md`、
  `shared_state/proposals/core/p-0076-*.md`。
- 关键决策：registry schema 加 `block_by_name: bool` 字段（默认 false、
  pre-0.8.0 backfill 设 true）让 maintainer 显式覆盖 name match 的"宽松"
  默认；不引入"unreject"工作流（rewrite 用新名字、强制语义表态）；不自动
  修改 consumer skill frontmatter（守 autonomy carve-out 不变量）；wheel
  shipped registry，不走另立签名 feed（advisory 非 security critical、
  wheel 签名已证来源）。
- 测试：`test_rejected_registry` 21/21（is_rejected 6 + should_block 4 +
  format_advisory 5 + malformed registry 2 + shipped registry smoke 4）；
  全套回归 revocation 24 + renewal 13 + candidate-attribution 9 +
  candidate-reminder 7 + update-reminder 9 + auth-guard 9 + auth-codec 11
  + upgrade-dry-run 14 + candidate-recovery 14 + rejected-registry 21 =
  131/131 全绿。wheel 0.8.0 build OK（`rejected.py` /
  `rejected_registry.json` 进 wheel、`maintainer/` 不漏）。dogfood
  `governance-core upgrade --project-root .` OK，hooks 19/18 registered、
  doctor exit 0。`reject_candidate.py --dry-run --issue 4` 演练成功，
  自动识别 pre-0.8.0、设 block_by_name=true、sha=null。P-0076 两 phase
  全部实现完成。

### 2026-05-26 — P-0076 Phase 1 sweep ledger 自愈

- 改动：`governance_core/candidates/ledger.py` 加
  `parse_payload_from_issue_body(body) -> (meta, {name: bytes})`（共享
  parser，Phase 2 maintainer 工具也用）+ `discover_uplinked_from_hub(
  origin, repo)`（`gh issue list --state all --search "[candidate]
  (from <origin>)"`、逐 issue 解析 fenced block、rehash、返回
  `[{digest, candidate_id, issue_url}]`、`gh`/网络/解析失败均 best-effort
  退回空）。`uplink.py` 修 payload 段 **不 rstrip**（保留原文 bytes、让
  hash round-trip 正确）。`candidate.py` `cmd_sweep` 在 collect 之后、
  pending 选择之前接 recovery：ledger 空 + outbox 非空 + `gh` 可用即调，
  把 recovery 结果写入 `_uplinked.json`。
- 涉及：`governance_core/candidates/ledger.py`、
  `governance_core/candidates/uplink.py`、
  `governance_core/tools/candidate.py`、
  `governance_core/tools/test_candidate_recovery.py`（新，14 用例）、
  `STATE.md`、`shared_state/proposals/core/p-0076-*.md`。
- 关键决策：保持 `payload_digest` 行为不变（按 `read_bytes()` 哈希）、
  改 `build_issue` 让 issue body 不 rstrip → round-trip 一致；recovery
  全程 fail-safe（FileNotFoundError / CalledProcessError /
  JSONDecodeError 均 logger.info 后返空）；recovery 只在 ledger 真的
  empty 时触发，正常 consumer 不付网络代价。
- 修环境：发现 `pip show` 显示 0.7.0 但 Editable project location 丢失
  ([[editable-install-clobber]] 信号)，`pip install -e .` 重装恢复。
- 测试：`test_candidate_recovery` 14/14（parser 5 + discover 8 +
  end-to-end round-trip 1）；回归 revocation 24 + renewal 13 +
  candidate-attribution 9 + candidate-reminder 7 + update-reminder 9 +
  auth-guard 9 + auth-codec 11 + upgrade-dry-run 14 = 96/96 全绿。
  无版本 bump（按提案 Phase 1+2 单次 bump pattern，待 Phase 2 一起
  0.7.0 → 0.8.0）。
