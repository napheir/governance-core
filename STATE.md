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

### 2026-05-29 — fix #2 discovery GBK UnicodeDecodeError (Art.7.4)

- 改动：给 discovery 里读 git 输出的 `subprocess.run` 加
  `encoding="utf-8", errors="replace"`——`tracker.py`（`git diff/log` 算 session
  complexity 的两处）+ `discovery/__init__.py`（`resolve_project_root` 的
  `git rev-parse --show-toplevel`）。Windows 上 `text=True` 缺 encoding 时按
  GBK 解码 git 输出，遇非 ASCII 的 commit message / 文件名 / 仓库路径即
  `UnicodeDecodeError`，把该数据从复杂度计算里丢掉（issue #2 现象）。版本
  0.12.0 → 0.13.0。
- 涉及：`governance_core/discovery/tracker.py`、`governance_core/discovery/__init__.py`、
  `governance_core/__init__.py` + `pyproject.toml`（0.13.0）、`STATE.md`。
- 关键决策：`errors="replace"` 保证彻底无解码崩溃且**不丢文件**（直接回应 issue
  的 "offending file dropped from computation"）；修的是 tracker import 链的**整个
  bug 类**（tracker 两处 + resolve_project_root），不止 issue 点名的单行。
  `tools/test_command_guard.py` 有同款 `text=True` 无 encoding，但属测试文件、非
  runtime 路径，记下未动。NO_PROPOSAL（简单 bug fix）。原 issue 报 0.5.0，
  line 116 的 `.usage.json` 读早带 encoding；真 offending read 是 subprocess git
  解码。#3（auth-guard import 隔离）另议（security hook 重构、需 proposal）。
- 测试：全套 `tools/test_*.py` 17/17；`python -m governance_core.discovery.tracker
  --should-extract` 运行 clean；dogfood `governance-core upgrade` exit 0。

### 2026-05-29 — reject candidates #8 + #9（重投的 trade-coupled skills）

- 改动：用 `maintainer/reject_candidate.py --also-close` 拒 #8
  (cross-agent-gate-spec-mock) + #9 (p4-scenario-fixture-construction)。
  **关键**：两者都是**已拒 skill 的重投** —— `rejected_registry.json` 早有这
  两个 skill_name 条目（cross-agent-gate 曾为 #5/#7、p4-scenario 曾为 #4/#6，
  P-0076 backfill，`block_by_name: true`）。工具把 #8/#9 的 issue URL 追加进
  既有条目 + 发 advisory 评论 + 关 issue 为 not-planned。版本 0.11.0 → 0.12.0
  （shipped `rejected_registry.json` 内容变了，保版本↔内容洁净）。
- 涉及：`governance_core/candidates/rejected_registry.json`（追加 issue URL +
  时间戳）、`governance_core/__init__.py` + `pyproject.toml`（0.12.0）、`STATE.md`。
- 关键决策：两者均 trade-coupled（多 clone 拓扑在单 agent core 退化 + trade 域
  selection/risk/option/sector）；保留 `block_by_name: true`（pre-0.8.0 条目、
  按名硬拒）。**洞察**：trade-agent 会重传已拒 skill，极可能因其装的
  governance-core 版本早于 0.8.0+（未含 shipped rejected_registry），sweep 不知
  跳过 —— trade-agent 应 upgrade。无 proposal（curation bookkeeping、非能力变更）。
  通用内核欢迎作"去 trade 化的新 candidate / hub 自 authored 的 skill guide"
  （既有 advice 已载明：p4 的 schema-provenance 模式、cross-agent 的抽象 spec-mock
  模式由 hub 直接 author）。
- 测试：`test_rejected_registry` 21/21（含 shipped registry 含两 skill 的 smoke）；
  全套 `tools/test_*.py` 17/17；dogfood upgrade exit 0；wheel 0.12.0 build OK
  （top-level 仅 `governance_core` + dist-info、rejected_registry 在内、
  `maintainer/` 不泄漏）。

### 2026-05-29 — P-0079 promote /learn carrier-class gate (candidate #11), de-trade-ified

- 改动：curate trade-agent #11 入包源（P-0065 决策，优先级清单第 2 项）。在
  `governance_core/commands/learn.md` 的 `## 执行流程` 与 `### Step 1` 之间插入
  **Step 0：判定 carrier_class + 载体形式**（0.1 class 决策表 6 类 / 0.2 载体
  形式 MD vs HTML profile 表 / 0.3 声明输出格式 / 误用红线）—— 写 `knowledge/**`
  前强制声明 carrier_class（P-0053）+ 载体（P-0054）。引用的两 spec 都已在包源
  （`knowledge-carrier-classes.md` §2、`knowledge-html-profile.md` §1，后者刚被
  P-0078 扩）。版本 0.10.0 → 0.11.0（learn.md ship 进 wheel）。`candidate.py
  promote` 记 #11 `promoted`。
- 涉及：`governance_core/commands/learn.md`、`governance_core/__init__.py` +
  `pyproject.toml`（0.11.0）、`maintainer/consumer_registry.json`、`STATE.md`、
  `shared_state/proposals/core/p-0079-*.md`（提案档案）。
- 关键决策：**去 trade 化** —— trade-agent payload 示例带 trade 味
  （`knowledge/trading/trade-end-to-end-flow.html`、"写 trade 全流程"），下发
  全体 consumer 前改成领域中立（`knowledge/<domain>/<topic>-flow.html`、误用
  红线去 "trade"）；机制逐字保留、只改示例。**强制闸门**有意为之：把今天仅
  "文档化"的 P-0053/54 carrier 纪律变成 /learn 里的"闸门化"。验证：
  `git diff --ignore-cr-at-eol` 语义 diff = 2 hunk / 44 增 / 0 删（raw diff
  82 删 202 增的噪声纯属 CRLF↔LF + 尾换行；sha 差异同因，内容与 baseline 等价）。
  新增段 trade 泄漏检查通过（仅余通用英文词 "tradeoff"；既有 agent-role 枚举
  `{rules,trade,data,...}` 与本次无关）。
- 测试：全套 `tools/test_*.py` 17/17 PASS（skill 正文不单测，跑全套确认无连带
  破坏）；dogfood `governance-core upgrade --project-root .` exit 0，安装副本
  `.claude/commands/learn.md` 已带 Step 0；wheel 0.11.0 build OK（top-level 仅
  `governance_core` + dist-info，learn.md 在内、`maintainer/` 不泄漏）。

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
