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

### 2026-11-06 — P-0135 Phase 1：由 core 运行的分支范围审计（0.51.0，未发布）

- `check_scope.py --audit-branch --agent X [--repo <clone>] [--ref R] [--json]`：
  - **审计对象**：在 core 仓库里把该 clone 当前检出的提交拉取到 `refs/gc-audit/<agent>`，审计它与 core ref 的 merge-base 以来的净改动（含 merge 时的冲突解决）。
  - **规则来源**：`git show <core ref>:agent_rules/<agent>.allow.txt`，不读分支或工作区里的文件。
  - **放行条件**：在允许规则内、内容是 core 历史中的某个版本、或随 core 一起删除，三者满足其一即可。其余改动都会报出，附提交和属主。
  - **退出码**：0 通过，1 有违规，2 无法运行。
  - 不加别的模式的 `--agent X` 等同于审计 HEAD；baseline 模式和 `.baseline_commit` 已移除（从来没有地方写过这个文件）。
- scope-guard：非 core agent 不能再用 `--no-verify`、`commit -n`（含 `-an`、`-nm` 这类组合）或 `core.hooksPath` 跳过提交 hook。
  匹配前会把引号里的内容遮掉，所以 commit message 里提到这些字样不会误拦。
- merge-audit.py 改为运行分支审计：路径钉在本 clone、区分退出码 1 和 2、超时 60 秒。
- `/sync-repos` 新增 Step 0：审计不通过的 clone 本轮不同步，其余照常；`/audit` 按 config 里的 agent 逐个审计；
  `/publish-knowledge` 收集前先审计。art_05 的合规门禁描述、art_12 第 3 款的防御层次、scope-enforcement-mechanism 都与实现对齐。
- 版本 0.50.0 → 0.51.0（0.50.0 没有单独发布）。
- 测试：新增 `test_check_scope_branch_audit.py`，25 个，用真实的 core 仓库和业务 clone。覆盖：
  在自己 scope 内的改动、改别的 agent 的文件、在分支上放宽 allow 文件、`-n` 提交、core merge、core 的旧版本、
  藏在 merge 冲突解决里的改动、删除、篡改 clone 自身 ref、在 clone 内审计、exit 2，以及 12 个 hook 绕过写法。
  反向校准（HEAD）：24 FAIL / 1 PASS（core agent 不受限）。全量（venv）pytest 456 passed，含 `__main__` 的 28 个全过；
  upgrade 无 drift，doctor exit 0。

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
