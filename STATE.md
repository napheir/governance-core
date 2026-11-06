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

### 2026-11-06 — 发布 v0.49.1；editable 安装隔离（B 方案第 1–3 步）；起草 P-0133

- 发布：owner 选「三项一起发」，即发布确认（core-A3）。推送 1bd6a1e..e1ed6f4，GitHub Release v0.49.1，release CI run 42168442113 success；
  PyPI 0.49.1 可见（wheel + sdist）。发布前本地构建 wheel 检查：顶层只有 `governance_core*`，新文件都在，`maintainer/` 没有混入。
  已通知 deva-vani：72 个隔离的 drift 候选在各 clone 升级到 0.49.1 后可以删除。
- B 方案第 2 步：在 hub 建 `.venv`（已在 gitignore 中），`pip install -e ".[dev]" build`；venv python 导入 `<repo>/governance_core`，版本 0.49.1。
- B 方案第 3 步：全局 Python 3.11 执行 `pip install governance-core==0.49.1`，卸掉了 editable 0.9.0（pip show 的版本号一直停在 0.9.0）。
  此后 deva-vani、auto-tax 和 multi-agent-bootstrap（依赖 gc）用的都是 PyPI 上的正式版。用 `python -P` 核实过：全局 python 导入 site-packages。
- 新发现：在仓库根目录用 `python -c` 或 `python -m pytest`，当前目录在 sys.path 里，所以不管哪个解释器都会导入仓库源码。
  而用脚本方式跑的测试、hook 和 `governance-core` 命令会用全局的正式版。忘记激活 venv 时不会报错，两套代码混着用。memory 已更新。
- 第 6 步（防忘检查）：脚本 `maintainer/hub_python_check.py` 已写好但未提交。它在全局 python 下输出 SessionStart JSON 警告，
  在 venv 下不输出。注册它要新建 `.claude/settings.json`，classify-fast gate 判为 PROPOSAL_REQUIRED，所以起草了 **P-0133**（pending，待 owner 批准）。
  安装器只对多 clone 布局写 `settings.json`（installer.py:747-797），所以 hub 加在这里的 hook 不会在 upgrade 时被覆盖。
- 待 owner 做：在 `~/.bashrc` 加 `alias gchub='cd ~/workshop-claude/governance-core && source .venv/Scripts/activate && claude'`，以后用它启动 hub。
  第 5 步（新会话里核实导入来源并跑全量测试）要在用 gchub 开的新会话里做。

### 2026-11-06 — 子宪法审计命中改为告警；改 layer 即撤回已收集的候选（并入 0.49.1）

- deva-vani 又报两件事，owner 选「三项一起发」，与 drift 修复一起进 0.49.1。classify：NO_PROPOSAL（两处窄改动，复现清楚，契约不变）。
- `audit_sub_constitutions`：`可.*<关键词>` 会把「不可修改宪法」判成放宽，content 起草的收紧条文「允许和禁止的表述由法务界定，写进
  brand_voice 契约的红线」也被记为 HIGH、exit 1，只能改写措辞过审计。现在正则命中只记 WARN（报告列出命中的新增行，供人工复核，
  不影响 exit code），只有提交声明 `Violates-Core: YES` 才记 HIGH、exit 1。这与文档里第 4 层「告警」的定位一致，阻断仍由 pre-commit 负责。
  没有采用「识别收紧句式」的方案：用正则补正则，只会越补越多。`check_constitution_change.py` 不是安装进去的 hook，没有改。
- `candidate.py sweep`：outbox 里的候选只要不在台账里就上传，不看源 skill 当前的 layer，所以 owner 把 skill 改成 `business` 也撤不回。
  新增 `collect.collected_skill_source()` / `is_withdrawn()`：由 collect 打包的 skill 候选（rationale 与 payload 形状可辨认），
  如果对应的 learned skill 已不是 `candidate-common`（改了 layer 或删掉了），sweep 跳过并报 `withdrawn`。
  drift / submit 候选不受影响，撤回方法是从 outbox 删除。rationale 字符串提取为常量 `COLLECT_RATIONALE`。
- 文档：constitution-protection-mechanism（第 4 层说明）、iterate-constitution 验收项（加 WARN）、wrap-up 4c（撤回）、core-manual §11。
- 测试：新增 `test_candidate_sweep_withdrawn.py`（5 个，不需要签名密钥，只 stub uplink 和 hub 查询）；
  `test_audit_sub_constitutions_layout.py` 把原「放宽即 exit 1」改为告警，另加收紧措辞和声明 YES 两个用例。
  反向校准（HEAD）：审计 3 FAIL / 2 PASS，sweep 2 FAIL（改 layer、删除）/ 3 PASS（对照）。
  全量 pytest 389 passed，含 `__main__` 的 28 个测试文件全过；upgrade 无 drift，doctor exit 0。
- 未处理：deva-vani 报的第 4 件事（业务 clone 会把 merge 进来的 core learned skill 当作自己的候选收集），不在本次批准范围，另行报告。

### 2026-11-06 — 修 drift 误报：从 core merge 进来的文件不算本地改动（0.49.1，未发布）

- deva-vani 回报：业务 clone merge 了 core 提交的 gc-managed 文件，但其 manifest（untracked）还停在旧 baseline，于是 upgrade 把
  每个 merge 进来的文件都打包成 `candidate-common` 的 drift 候选。0.48.2 起，3 个业务 clone 共积了 72 个，sweep 一跑就会变成 hub
  的公开 issue。对方已全部隔离，一个都没发出。classify：NO_PROPOSAL（改动集中在一个函数，复现清楚，契约不变）。
  owner「按你的建议a的计划修bug」。
- `installer._capture_drift(project_root, consumer_id, config, dry_run)`：文件不等于 baseline，但等于本次要写入的版本
  （`_incoming_sha256`），也不算 drift。条款按渲染后的内容比较：新增 `_rendered_clause()`，供 `_render_clauses` 和 drift 判断共用；
  新增 `_lf_sha256()`，`_content_sha256` 改为调用它。
- 顺带修了 `_pkg_source_path`：`.claude/hooks/_gc_auth/*`（vendored 的 `auth/`）原先被映射到不存在的 `hooks/_gc_auth/`，
  导致这 6 个文件即使修了 (a) 仍判为 drift，`upgrade --dry-run` 的 diff 也显示「source not located」。现改为最长前缀优先匹配。
- 没有采用 (b)（与 upstream 分支内容一致就跳过）：在 core clone 里，core 自己提交过的手改会被跳过，然后被 upgrade 静默覆盖。
  (a) 要求 core 和业务 clone 用同一个包版本升级。本机的 editable 安装恰好会破坏这个前提，所以隔离 editable 安装也有助于补上这个缺口。
- 文档：`/sync-repos`「同步后：对齐 gc-managed 层 manifest」不再写"只是噪音"，改为说明 0.49.1 的判断规则、旧版 clone 的处理办法，
  以及同一包版本的前提；wrap-up 5b 的提示同步修改。
- 测试：新增 `test_installer_drift_merged_upstream.py`（5 个，走真实 `install()`，manifest 改为旧版 baseline）。反向校准（HEAD）：
  4 FAIL（merge 进来的文件、渲染后的条款、merge 文件中混有一个本地改动、vendored 路径映射），
  1 PASS（baseline 最新时本地改动仍被捕获，两版都过）。`_capture_drift` 签名改了，现有调用点相应更新：drift_eol ×4、mixed_clauses ×1。
  全量 pytest 382 passed，脚本风格 28 个全过；hub upgrade 无 drift，doctor exit 0。**发布待 owner 确认。**

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
