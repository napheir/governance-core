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

### 2026-11-12 — P-0136 Phase 3：确保 owner 看到所有权通知（0.51.1，未发布）

- **info 通知**：`foreign-change-notice.py` 从 hook 输入里读取 `session_id`。
  - 每显示一次，就把这个 id 记进通知的 `shown`。
  - 等两个不同会话都显示过，才自动确认，`acked_by` 记为 `shown-2`。恢复或压缩会话时 id 不变，不会重复计数。
  - 拿不到 id 时，只显示，不计数。
  - alert 显示多少次都不会自动确认。
- **新增 `notices.py list --recent [--days N]`**：查看最近 N 天已确认的通知，默认 7 天。
- **新增 `notice-gate.py`（UserPromptSubmit）**：
  - 只要还有未确认的 alert，每个会话的第一条输入会被拦一次，并附上 alert 摘要。
  - 拦过的会话 id 记在 `.governance/notice_gate_seen.json`，这个文件是 clone 本地的，已加进受管的 `.gitignore`。
  - 单 agent 项目只读一下配置就退出；自身出错时放行。
  - 被拦的原因会不会显示给用户，文档里没有写，留到 Phase 4 由 deva-vani 的 owner 现场确认。
- **文档**：core-manual §15，以及 `/proposal` 里说明 body Edit 会被记入日志。
- **测试**：
  - `test_ownership_delivery.py` 新增 9 个，其中 8 个在 Phase 2 的代码上会失败；剩下那个检查无 alert 时放行，新旧代码上都通过。
  - 已有测试改为：info 不再在第一次显示时确认。
  - 全部 541 个测试通过，command-guard 42/42，doctor 正常（注册了 24 个 hook）。
- **下一步**：Phase 4，请 owner 确认发布 0.51.1（含 6a6ae5b），然后 deva-vani 按顺序现场验证。

### 2026-11-12 — P-0136 Phase 2：把 Edit/Write 记入写日志，按路径链解释变更（0.51.1，未发布）

- **新增两个 hook**，都是出错就放行，已登记在 `FAIL_OPEN_GC_IMPORTERS` 里：
  - `own-write-capture.py`（PreToolUse）：写入前把目标文件的 sha 记到 `.governance/pending_writes/<key>.json`。这个目录是 clone 本地的，已加进受管的 `.gitignore`。
  - `own-write-journal.py`（PostToolUse）：写入后调用 `record_write(op="edit:<Tool>", via="edit")` 记一行日志。没有待记录的写入时，它不加载 gc 包就直接退出。
- **`ownership.py` 的改动**：
  - `_chain`：同一路径的日志行必须从上次看到的 sha 一路接到当前 sha。
  - `scan` 改用这条规则判断变更能不能解释。
  - `record_write` 增加 `via` 参数。agent 写自己的文件之前，先检查上次看到的 sha 能否接到 `sha_before`；接不上就先发 alert，然后才更新清单。
  - 严重级别：只有 core 通过库写入才是 info；core 直接 Edit 别人的分区是 alert。
  - `journal_records(rotated=True)` 也读已轮转出去的日志文件。
- **`edit-write-guard`**：匹配范围扩到 `Edit|Write|MultiEdit|NotebookEdit`。NotebookEdit 读取 `notebook_path`，内容扫描也覆盖 MultiEdit 和 NotebookEdit。
- **`tool_use_id`**：hook 文档里没有写这个字段，但 Claude Code 更新日志里有："Added `tool_use_id` field to `PreToolUseHookInput` and `PostToolUseHookInput` types"。另外做了 `session_id` 加路径哈希的备用键。
- **测试**：
  - `test_ownership_own_edits.py` 新增 13 个，`test_shared_state_partitions.py` 新增 1 个。
  - 在 0.51.0 的代码上，13 个会失败；跨轮转日志那一个是防回归用的，新旧代码上都通过。
  - 全部 532 个测试通过，command-guard 42/42，doctor 正常（注册了 23 个 hook）。
- **单 agent 项目**（包括本 hub）：新逻辑全部不起作用，没有行为变化。

### 2026-11-12 — P-0136 Phase 1：所有权契约 1.1.0（0.51.1，未发布）

- **P-0136 已批准**：owner 说"批准P-0136"，按决策卡上的默认值执行，进入 in-progress。它是 P-0135 的后续，草稿留在 `shared_state/`，修复发布前不归档。
- **契约 `shared_state_ownership.md` 升到 1.1.0**：
  - **Edit/Write 也记入写日志。** 由两个出错时放行的 hook 负责：写入前记下原 sha，写入后记一行，`via` 为 `edit`，`op` 为 `edit:<Tool>`。覆盖所有改文件的工具。
  - **怎样算"能解释的变更"。** 同一路径的日志行要从上次看到的 sha 一路接到当前 sha；只有一行恰好以当前 sha 结尾，不算。自己写入前也要先做这项检查，然后才更新清单。
  - **core 直接 Edit 别人的分区**，算 alert。
  - **info 通知**在两个不同会话里显示过才自动确认（`shown`、`shown-2`）。
  - **有未确认的 alert 时**，每个会话的第一条输入被拦一次。
  - **新增** `notices.py list --recent`，可以事后查看已确认的通知。
- **下一步**：Phase 2 实现 Edit/Write 写日志和链式检查，Phase 3 实现通知送达。
- **另外两个已获批的方向**：
  - **sync_infra**：查 clone 路径的逻辑和 hook 接线方式要一起改，待起草提案。
  - **决策台账、每周回顾、owner 底线**：做成一个 gc 提案。每周回顾要在打开会话时检查本周做了没有，没做就补上。owner 待办台（中央 todo board）另行讨论。
- **测试**：所有权相关测试 85 个全部通过，知识库检查通过。

### 2026-11-10 — rotate_state 每次轮转都提示暂存 STATE_ARCHIVE.md（0.51.1，未发布）

- **问题**（deva-vani 反馈）：忙的时候，每天最多保留 3 条的上限会把当天较早的条目轮转进已跟踪的 `STATE_ARCHIVE.md`，而输出里没有任何提示。
  agent 只暂存了 STATE.md，被轮转的条目就从 git 里丢了。他们 content e71465c 和 core 646f7cf 各出过一次，都已补提交，内容没有丢。本仓库的 1aee998 也出过同样的事。
- **修复**：以前只在新建归档文件时警告，现在每次真正轮转都打印 `[WARN] <path> changed (N entries moved in): stage it together with STATE.md`。
  新建归档时打印的是 `created ... (untracked, ...)`。dry-run，或没有条目可轮转时，不打印。
- **不改** `/wrap-up`：第 2 步从 0.48.4 起已经写明要一起暂存。
- **未处理**：条目轮转出去后，里面的待办就不会再出现在 SessionStart 摘要里。deva-vani 目前手工把待办挪进最新条目。是否在上游解决，等 owner 决定。
- **涉及文件**：`governance_core/tools/rotate_state.py`、`test_rotate_state_archive.py`。新增 2 个测试，新测试在 HEAD 版本上失败、在新版本上通过。版本升到 0.51.1。
- **测试**：tools 513 个加 maintainer 5 个，共 518 个通过；command-guard 42/42；doctor OK。
- **待 owner 批准**：P-0135 info 通知的确认方式修改。批准后也放进 0.51.1。

### 2026-11-06 — 发布 v0.51.0（含 0.50.0：P-0134 + P-0135）

- owner「现在发布」。推送 eb7edf8..152f8a1，GitHub Release v0.51.0，release CI run 42196326998 success，
  PyPI 0.51.0 可见（wheel + sdist）。发布前构建的 wheel 已确认包含 ownership.py、foreign-change-notice.py、notices.py 和契约，没有混入 `maintainer/`。
- 发布说明只写新增的保护机制和多 agent 项目的升级顺序，不写漏洞利用细节。
  升级顺序：先把平铺的集合改成按 agent 分区，再 `pip -U`，紧接着在每个 clone 跑 upgrade，最后在 core 跑一次 `/audit`。
- 已通知 deva-vani 按这个顺序升级，并请他们把 core 的分支审计结果和他们手工审计的结果对照后回报。这是 P-0135 结案条件之一。
- 仍在进行：
  - P-0135：还差 owner 在界面上确认看到了通知，以及 deva-vani 的对照结果；提案留在 `shared_state/`，暂不归档。
  - P-0132：trade 和 auto-tax 等他们有空时再升级。
  - P-0133：还差 owner 验证两种启动方式。
  - P-0134：已实施，等 owner 决定是否归档。
- 全局 Python 仍是 0.49.1，各消费者用 `/upgrade` 自行升级。

### 2026-11-06 — P-0135 Phase 3：把别人改了你的内容告诉你和你的 owner（0.51.0，未发布）

- 新增 `governance_core/ownership.py`，提供三类存储和一个公共接口：
  - **写日志**：`_journal.jsonl` 只追加、带哈希链，超过 5 MB 轮转，链跨文件延续。
  - **通知**：`notices/<agent>/<id>.json`，分 info 和 alert；确认后移到 `acked/`。
  - **已见清单**：`.governance/state_seen.json`，存在各 clone 本地。
  - **公共接口** `record_write(project_root, op, rel_path, sha_before, sha_after)`：
    写入方是路径的属主时只更新它自己的清单；写入方不是属主时给属主发通知，core 发 info，其他人发 alert。
- `scan()` 在会话启动时运行：属于本 agent 的分区里，凡是不是它自己改的变化都先存成通知，再更新清单。
  能在日志里找到写入方就记名，找不到就标"来源不明"。第一次运行只建基线，不产生通知。单 agent 项目什么都不做。
- 新 SessionStart hook `foreign-change-notice.py`：
  - 内容同时发给 owner 界面（`systemMessage`）和 agent（`additionalContext`，要求它先向 owner 报告）。
  - 每个 clone 都会显示全项目还没确认的通知数量，日志链断了会报警。
  - info 显示一次后自动确认。
  - 已登记到 `FAIL_OPEN_GC_IMPORTERS` 和 hooks_manifest。
- `tools/notices.py list/ack`：agent 只能确认自己的通知，core 可以确认任何通知；alert 只有 owner 发话才确认。
  proposal_lib 的 create / transition / link / handoff / orchestrate / archive 都会写日志；日志写失败只警告，这次改动会在属主那边显示为"来源不明"。
- `check_scope --notify` 给被审计的 agent 和每个文件属主各发一条 scope-violation alert；`/sync-repos` 和 `/audit` 改为带 `--notify`。
- `.gitignore` 受管块里加上 `state_seen.json`；`_journal*`（含锁文件）列为只能经库写入。core-manual 新增 §15。
- 测试：新增 `test_shared_state_notice.py`（14 个）、分支审计 `--notify` 用例（1 个）。HEAD 上收集阶段就失败（还没有 ownership 模块）。
  全量（venv）pytest 516 passed，含 `__main__` 的 28 个全过；upgrade 无 drift；doctor exit 0；wheel 含新文件，`maintainer/` 未混入。

### 2026-11-06 — P-0135 Phase 2：shared_state 按 agent 分区（0.51.0，未发布）

- `_guard_common`：新增 `shared_state_root()`，从 config `shared_state_root` 读取，不再写死 `<clone>/../shared_state`；
  还新增了 `native_path()`（把 Git Bash 的 `/c/...` 写法转成 Windows 路径）、`partition_patterns()`、`shared_state_access()`。
  后者把一个写入目标判为 `outside` / `own` / `lib-only` / `foreign` / `other` 之一，在 Windows 上不区分大小写。
- edit-write-guard：原先 shared_state 下一律放行，现改为 `_check_shared_state()`，只放行写入自己的分区。
- scope-guard：新增 Layer 4，拆解 shell 命令（shlex，识别引号、分隔符和 `cd`），找出重定向、`cp`、`mv`、`rm`、`touch`、`mkdir`、`ln`、`tee`、`sed -i`、`dd of=` 的写入目标，
  目标不是自己的分区就拦截。读文件、写自己的分区、`python tools/...` 不受影响。
- proposal_lib：
  - transition / link / set_handoff_to / set_orchestration 必须由属主或 core 发起（`_require_owner_or_core`）。
  - archive 的 `--force-agent` 只有 core 能用；`create --agent` 填别的 agent 时只有 core 可以。
  - State Log 每行末尾加 `by <actor>`。
- 文档：`/proposal`（三处强制说明、反模式）、art_04b（写权限的执行方式），说法都改为与实现一致。
- 测试：新增 `test_shared_state_partitions.py`，45 个，guard 以子进程运行，覆盖分区判定、Git Bash 路径和大小写、Edit/Write、shell 写法、proposal_lib 属主检查。
  反向校准（HEAD）：新加的拦截全部 FAIL 或 ERROR；放行的用例（自己的分区、读文件、core）在 HEAD 上同样 PASS，说明没有误拦。
  全量（venv）pytest 501 passed，含 `__main__` 的 28 个全过；upgrade 无 drift，doctor exit 0。
- 注意：在包源目录 `governance_core/tools/` 下直接跑 proposal 测试会因为找不到 config 而失败；要在自治层 `tools/` 下跑（memory 已记）。

### 2026-11-05 — 发布 v0.49.0（P-0131 + P-0132 A/B）

- owner「发布，然后休息，明天再继续其他工作」：推送 4 commits（e69569f..7739fe3），`gh release create v0.49.0`；workflow 42046609426
  build / publish-pypi success；`gh release list` Latest = v0.49.0；PyPI 版本端点含 wheel + sdist。0.48.5 未单独发布（并入 0.49.0）。
- **发布通知未送达**：deva-vani 会话已关闭（SendMessage: not reachable）；通知稿存
  `artifacts/deva-vani/2026-11-05-release-0.49.0.md`，明天对方会话起来后发送。他们已撤回换码请求（owner 决定旧码继续有效）；计划：四个 clone 升级 → core `--remove-config-auth-code` 并提交 →
  /sync-repos → 删其 Art.4 例外。明天继续，升级前由其 owner 看预览确认。
- **明天待办**：P-0132 Phase C（hub 重签码用 `--out`、删 config 旧码、按指纹吊销 `99411b5a` 并推 feed，每步 owner 确认）；
  editable 安装隔离（owner 决定）；edit-write-guard `shared_state/` 放行他 agent 提案目录（安全，勿公开，建议单独提案）；
  scope-guard `python -c` 内 `.replace(` 误报（低）；旧遗留：mab 问题、条款残留、hook 接线冲突。

### 2026-11-05 — 实施 P-0132 Phase A+B：码移出 git、按码吊销、停用 schema 1（0.49.0）

- **A 存储**：新增 `auth/store.py`（`.governance/auth_code` 单行、原子写；随 auth 包 vendored 进 `_gc_auth`）。installer 取码顺序
  `--auth-code` → 码文件 → config 旧码（仅迁移来源）；config 只写 `consumer_id` / `verified_at`，旧码保留到
  `--remove-config-auth-code`（install / upgrade 新参数）；gitignore 受管块加 `/.governance/auth_code`（单独常量，不进"仍被跟踪的运行时
  文件"提示）；doctor 读码文件、config 残留旧码时警告（并报 config 是否被 git 跟踪）、码文件被跟踪时提示保持私有。auth-guard 只读码文件
  （不再读 config.json），candidate.py 同。
- **B 吊销**：`codec.SUPPORTED_SCHEMAS = (2,)`，新增 `code_fingerprint()`；feed 条目可带 `code_sha256`（必须同时带 consumer_id），
  `is_revoked(feed, cid, code_sha256=None)`，`remove_revocation` 只撤整 consumer 条目，新增 `remove_code_revocation`；auth-guard 带指纹
  检查、schema 非 2 一律拦截；install 时尽力拉一次 feed，按码被吊销 → exit 7；`revoke_consumer.py --code-file/--code-sha256/
  --unrevoke-code`；`issue_auth_code.py` 去掉 schema 1、新增 `--out PATH`（码写文件不打印，避免进会话记录）。
- 新契约 `contracts/authorization_schema.md` 1.0.0；README / core-manual §9 更新。hub 已 dogfood：upgrade 把码迁到码文件，doctor 警告 config
  残留（Phase C 再删）。
- **测试**：新增 `test_auth_code_storage.py`（8，真实 install + 测试密钥签名的码与 feed）；`test_revocation.py` +6、`test_auth_guard.py` +4、
  `test_auth_codec.py` +2（pytest 风格，一次性测试密钥：fixture 改写 vendored `_gc_auth/pubkey.json`）；旧脚本用例改为码文件存储、schema 1
  改为拒收；旧客户端兼容用冻结的 0.48.4 `validate_feed` / `is_revoked` 快照（shipped 测试拿不到 hub 历史）。对 0.48.5 反向校准：11 FAIL +
  1 ERROR（新模块缺失），兼容用例（整 consumer 吊销仍拦所有码）两版都过。全量 pytest 377 passed，脚本风格全过；wheel 含 store.py 与新契约。
- **偏离**：A、B 共用 installer / auth-guard 同一批函数，合为一个提交（提案写的是各一个）。
- deva-vani：业务方决定码文件保持 gitignored；请求在其四个 clone 升到 0.49.0、删掉 config 旧码后，由维护者重签其码并按码吊销旧码
  （待 owner 决定）。另报：本机 editable 安装让未发布代码在 deva-vani 会话里实时生效（其 doctor 现 exit 7，属预期）；scope-guard 对
  `python -c` 里的 `.replace(` 误报（低优先级）。

### 2026-11-05 — 实施 P-0131：merge 导入按来源提交归属（0.48.5，未发布）

- owner「OK，实施P-0131。批准P-0132，同意你的建议。完成131后可以你直接做132」：P-0132 pending → approved（Open Questions 按倾向）；
  P-0131 → in-progress。
- `check_scope.py`：`load_core_refs()` 从 config 取 `upstream_branch`（优先）+ `core_branches`，只留能解析的；`same_as_master` →
  `same_as_core(path, staged, core_ref)`；`foreign_import_commits()` 用 `git log --cc --name-only MERGE_HEAD ^HEAD ^<core refs>`
  列出非 core 历史的导入提交（含 merge 提交里的冲突解决 / 夹带）；merge 过滤：与 core 引用相同，或与 MERGE_HEAD 相同且无非 core 提交
  触及，才放行，否则 `IMPORTED_OUT_OF_SCOPE: <hash> <subject>` 并提示 fetch；pre-merge-commit 的 DEFER 也改比 core 引用；
  去掉 `"core"` / `"master"` 字面量。`config.py`：`upstream_branch: str | None`，去掉 `.get` 默认值。
- 踩坑：`str.splitlines()` 也会在 `\x1e` 处断行，把 git log 的记录分隔符吃掉，导致归属为空（门禁放行）；改 `split("\n")`。
- 测试：0.48.3 的自动 merge fixture 改为"core-next 属 core 历史、origin/master 指向更新的 core-tip"；+7（upstream 领先陈旧 master 时
  自动 merge 直接提交、从 upstream 同步通过、合并其他 agent 分支的越界提交被拒、对方 merge 提交夹带越界被拒、pull 自己的分支通过、
  deva-vani 的 STATE.md 冲突场景通过、硬编码检查 ×2）。对 0.48.4 反向校准：5 例 FAIL，放行类 6 例两版都过。
  全量 pytest 357 passed，脚本风格 28 个全过。版本 0.48.4 → 0.48.5。**发布待 owner 确认**。
- 文档：`/sync-repos`、core-manual、skill `verify-guard-fires-in-its-target-context` 各补一段。
- deva-vani 回报 P-0129 验收第 1–3 项全部 BLOCKED（第 4 项早已通过）→ P-0129 可结案；另报 edit-write-guard 对 `shared_state/`
  一律放行（可写他 agent 的提案目录），请勿公开，待处理。
