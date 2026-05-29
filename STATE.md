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

### 2026-05-29 — P-0082 self-contain auth-guard（vendor auth 子包，关 #3）

- 改动：**Phase A** —— `governance_core/auth/` 内部绝对导入改**相对**
  （`__init__`/`codec`/`revocation`：`from . import _ed25519/codec/sign/verify`
  + 替换 `auth.sign`/`auth.verify` 调用点），使 auth 子包**可重定位**（同一份源
  既作 `governance_core.auth` 包用、又能作独立包 import），逻辑零改。**Phase B**
  —— installer 加 `COPY_CATEGORIES ("auth" → .claude/hooks/_gc_auth)` +
  `CATEGORY_OF["auth"]` + `_copy_tree` 跳 `__pycache__`/`.pyc`；`auth-guard.py`
  顶部加 `_HOOK_DIR` + `sys.path.insert`，5 处 import 从 `governance_core.auth`
  改 `_gc_auth`（**自包含、无 `import governance_core`**）；`runtime_import_audit`
  的 `GC_IMPORT_EXEMPT` **清空**（P-0081 grandfather 自衰减）；
  `runtime-import-discipline.md` §3/§4 更新；`test_auth_guard` 在临时 repo vendor
  `_gc_auth`、`test_runtime_import_audit` 改空-exempt 断言。版本 0.15.0 → 0.16.0。
  **关 #3**。
- 涉及：`governance_core/auth/{__init__,codec,revocation}.py`、
  `governance_core/hooks/auth-guard.py`、`governance_core/installer.py`、
  `governance_core/runtime_import_audit.py`、
  `governance_core/knowledge_governance/runtime-import-discipline.md`、
  `governance_core/tools/{test_auth_guard,test_runtime_import_audit}.py`、
  `governance_core/__init__.py` + `pyproject.toml`（0.16.0）、`STATE.md`、
  `shared_state/proposals/core/p-0082-*.md`。
- 关键决策：**单一源** `governance_core/auth/`，`_gc_auth/` 是 install 产物
  （Art.8 同代码路径、Art.11.4 不进 wheel —— wheel 仍只 `governance_core*`，
  auth/ 作为包发布、`_gc_auth` 不在内）。**相对导入使 vendoring 无需源变换**
  （faithful copy，installer 直接 rglob 拷贝）。prune 是 **manifest-diff** 式 →
  `_gc_auth` 进 install set（category auth）即永不误删（**双 upgrade 验证存活**）。
  **fail-closed 语义不变**（坏 auth → exit 2），但 freeze 风险消除：hook + 其依赖
  现在是一个 install 单元（不再依赖 governance_core 可 pip-import）。dogfood
  `upgrade` 不热替换当前 session 的 live hook（启动时加载）→ 零冻结风险。
- 测试：**Phase A** 可重定位 round-trip（独立 `_gc_auth` import + sign/verify）
  + `test_auth_codec`/`test_revocation`/`test_auth_guard` green。**Phase B** 全套
  `tools/test_*.py` **21/21**（`test_auth_guard` 用 vendored 布局、
  `test_runtime_import_audit` 空 exempt）；`hook_imports_gc(auth-guard)=False`；
  `governance-core doctor` exit 0 **无 tracked-exception 行**（exempt 空、全面强制）；
  直调安装版 auth-guard 对真实 config **exit 0 授权**；**双 upgrade `_gc_auth` 5
  文件存活**；wheel 0.16.0 build OK（top-level 仅 `governance_core` + dist-info、
  auth/ 5 文件+pubkey 在内、`_gc_auth` 不进 wheel、`maintainer/` 不泄漏）。

### 2026-05-29 — P-0081 立 runtime-import-discipline 不变式 + doctor 检查（#3 根治）

- 改动：查 issue #3 发现前提已过时（当前 6 hook + 8 tool 都 import governance_core，
  非"唯一"），但内核成立。**锐化不变式**：import governance_core 的 hook 必须守护
  import 且 fail-open；必须 fail-CLOSED 的安全门则必须自包含——证据是除 auth-guard
  外所有 importer 都守护 + fail-open（sensitive-data-guard 注释明写"auth-guard
  already fails closed"）。auth-guard 是唯一违反者（PreToolUse `*` + fail-closed →
  governance_core 不可导入即冻结每次工具调用）。新增治理文档
  `knowledge_governance/runtime-import-discipline.md` + 新模块
  `runtime_import_audit.py`（`FAIL_OPEN_GC_IMPORTERS`/`GC_IMPORT_EXEMPT`/
  `check_runtime_import_discipline`）+ doctor 检查（unclassified gc-importer →
  exit 9；auth-guard 以文档化临时例外 grandfather，doctor 保持 exit 0、对新 hook
  强制）。**不动 auth-guard 代码**（636 行 crypto vendor 留 P-0082）。版本 0.14.0
  → 0.15.0。
- 涉及：`governance_core/runtime_import_audit.py`（新）、`installer.py`（doctor 加
  P-0081 检查，新退出码 9）、`knowledge_governance/runtime-import-discipline.md`（新）、
  `tools/test_runtime_import_audit.py`（新，13 用例）、`__init__.py` + `pyproject.toml`
  （0.15.0）、`STATE.md`、`shared_state/proposals/core/p-0081-*.md`。
- 关键决策：**不进宪法**（治理文档 + doctor 检查，免 /iterate-constitution 重流程；
  要 entrench 可后续加一行 Art.11 引用）；grandfather auth-guard（仿 P-0075
  prune-exempt：向前强制、P-0082 落地后自衰减）；检查作用域限 shipped hooks（manifest
  名单），不误伤消费者自有 hook；不变式从"per-call guard 自包含"锐化为"fail-open-guarded
  或自包含、安全门自包含"。**#3 保持 OPEN**，P-0082 vendor auth-guard 后才关。
- 测试：`test_runtime_import_audit` 13/13（hook_imports_gc 4 + 合成 dir 5 + 真实
  shipped hooks 4：无 unclassified 违规 / auth-guard 是 tracked 例外 / 5 个 fail-open
  importer 都在且确 import gc / exempt 恰为 {auth-guard.py}）；全套 `tools/test_*.py`
  **21/21**；`governance-core doctor` exit 0 并打印 "runtime-import-discipline:
  1 tracked exception(s) ... ['auth-guard.py']"；dogfood upgrade exit 0；wheel
  0.15.0 build OK（top-level 仅 `governance_core` + dist-info、新模块/doc/测试在内、
  `maintainer/` 不泄漏）。

### 2026-05-29 — P-0080 promote classify fast-path hard-block cluster (#17 + #13)

- 改动：curate trade-agent 的 classify fast-path 集群入包源（P-0065 决策，原
  #12/#13/#14 阻塞件经索要后由 #17 完整重投）。落 **8 个 net-new**：
  `hooks/proposal-classify-fast.py`（L5 PreToolUse 硬阻断 hook：触及高敏路径且本
  session 未 classify 即 exit 2）、`tools/_classify_match.py`（gitignore-glob
  matcher）、`tools/proposal-classify-paths.json`（高敏路径 allowlist：governance/
  harness/routing/infra/settings 五类）、`tools/proposal-classify-keywords.json`
  （结构变更关键词）、3 个测试、`knowledge_governance/proposal-classify-fast-path.md`
  （reference doc）。**合并 #13** 的 `_cmd_classify`/`_classify_quick` + argparse
  入 `tools/proposal_lib.py`（`git apply --recount`，3 hunk/158 增/0 删纯增）。
  `hooks_manifest.json` 注册新 hook（PreToolUse, Edit|Write|MultiEdit|NotebookEdit）。
  版本 0.13.0 → 0.14.0。
- 涉及：`governance_core/hooks/proposal-classify-fast.py` + `hooks_manifest.json`、
  `governance_core/tools/{_classify_match.py, proposal-classify-paths.json,
  proposal-classify-keywords.json, test_proposal_classify*.py(×3), proposal_lib.py}`、
  `governance_core/knowledge_governance/proposal-classify-fast-path.md`、
  `governance_core/__init__.py` + `pyproject.toml`（0.14.0 + package-data 加
  `tools/*.json`）、`maintainer/consumer_registry.json`、`STATE.md`、
  `shared_state/proposals/core/p-0080-*.md`。
- 关键决策：**抓到打包 bug** —— 首次 wheel build 缺两个 `tools/*.json`（默认不打包
  data 文件；editable 安装掩盖了），会下发"找不到配置的坏 hook"给消费者 →
  `pyproject.toml` package-data 补 `tools/*.json`，重建后 8 文件全入 wheel。这正是
  dogfood + wheel 隔离纪律存在的意义。hook **不 import governance_core**（守 copy-based
  不变式，恰是 #3 auth-guard 违反的）；配置 **无 trade 泄漏**（globs 是 gc 自身结构）。
  **自托管 nuance**：globs 是自治层相对路径、不含 `governance_core/**`，故 hub 的包源
  开发不被 gate；被 gate 的是 root/自治层治理文件。#14 sync_infra 多 clone 接线按
  trade-agent scope note + 单 agent 拓扑排除。
- 测试：全套自治层 `tools/test_*.py` **20/20**（17 + 3 新 classify）；**硬阻断 hook
  直调验 6 态**：BLOCK(新 session+治理/harness 路径 exit 2)、ALLOW(非 allowlist)、
  逃生门 `CLAUDE_CLASSIFY_FAST_DISABLE=1`、fail-open(坏 JSON)、自托管 nuance
  (`governance_core/**` 不 gate)、有 classify entry 放行。dogfood upgrade exit 0
  (hook 注册进 settings.local.json)、doctor exit 0。wheel 0.14.0 build OK（top-level
  仅 `governance_core` + dist-info、8 文件全在、`maintainer/` 不泄漏）。

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
