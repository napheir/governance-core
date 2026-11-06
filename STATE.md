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

### 2026-11-06 — 实施 P-0134：经提案批准启用 Workflow 多 agent 执行（0.50.0，未发布）

- 起因：deva-vani 的上游建议。owner「起草 Workflow 多 agent 编排提案」→「批准」。
  三个待定问题都按提案写明的默认处理：字段名用 `orchestration: workflow`，不复用 P-0119 的 `execution:`；
  批准提案即视为同意启用；Workflow 声明检查不设豁免。
- 契约：frontmatter schema 1.6.0 → 1.7.0（新增 §4.8 `orchestration`）；gate schema 1.0.0 → 1.1.0
  （新增 §5 Workflow Execution 声明、runner 打印声明，原 §5/§6 顺延为 §6/§7）。改版本号前用 git grep 确认两个号都没被预留。
- `proposal_lib.py`：
  - `ORCHESTRATION_VALUES`、`is_orchestrated`、`workflow_declaration_adequacy`（只查形式）：要求有 `### Workflow Execution` 一节；
    首行是 `> **[TOKEN WARNING]**` 且有实际内容；六个标签都已填写且不是占位符；Scale 含数字；
    Approval Criteria 里有一条点名 Workflow 的 `human-verify:` 同意项（脚手架自带的通用 human-verify 项不算）。
  - `create --orchestration workflow` 和新子命令 `orchestrate --set/--clear`（只能用在 draft 上）会写入字段、
    加上骨架和同意项。批准时声明不全就 BLOCK，不设豁免。`run` 对这类提案打印批准时冻结的声明，从不启动 Workflow；
    同时带 `execution:` 的照常跑 gate。脚手架的 Design & Contract 提示里加了一行。
- `audit_proposals.py`：新增 Check 22（WARN），与批准门共用同一个判断函数（只看 pending/approved/in-progress）；
  docstring 里的 schema 版本从过时的 v1.5.0 更正为 v1.7.0。
- `/proposal` skill 新增「Workflow 执行」一节：什么时候适用、怎么起草；请求批准时要在消息里再提醒一次 token 用量，并给出规模和成本；
  开跑前说明规模，先加载 workflow-authoring；超出声明的规模或写权限要先问 owner；`complete` 时记录实际规模和结果。
  core-manual §4 同步更新。
- 测试：新增 `test_proposal_orchestration.py`（30 个）。反向校准：在 HEAD 导出的 tools 上只跑行为用例，
  5 FAIL（不完整的声明被拦、run 打印声明 ×2、Check 22 ×2）/ 3 PASS（完整声明可批准、普通提案不受影响、run 拒绝普通提案）。
  全量（venv）pytest 431 passed，含 `__main__` 的 28 个全过；提案审计 0 失败；upgrade 无 drift；doctor exit 0。**发布待 owner 确认。**
- deva-vani 说他们停在 0.49.1，等 scope gate 修好后连同 0.49.2、0.50.0 一次升级。

### 2026-11-06 — 待办（owner）：P-0132 通知 auto-tax 与 trade；trade 跑 doctor 确认 schema 2；P-0133 两种启动方式验收

- owner「记一个todo，晚些提醒我」（15:05）。本会话已设一次性提醒（17:07，只在本会话内有效）。
- P-0132 结案还差两步：通知 auto-tax（还在 0.6.0）和 trade 升级（这次吊销对它们没有影响）；在 trade 项目跑 `governance-core doctor`，确认 auth 是 schema 2。
- P-0133 标为已实施前还差 owner 亲眼确认：用 `gchub` 启动时没有警告，直接 `claude` 启动时有警告。

### 2026-11-06 — 发布 v0.49.2

- owner「可以发」。推送 bcf0730..a2f825d（a90ece2 是 0.49.2 的代码，a2f825d 是 P-0133，只涉及 hub 自己的文件），
  GitHub Release v0.49.2，release CI run 42178638282 success，PyPI 0.49.2 可见（wheel + sdist）。
- 之前建议把 `regen_constitution.py:48` 写死的 `constitution/agent.md` 说明一起修进去，但这次没有放：
  这行文字会写进每个 clone 生成的 CLAUDE.md，session-context 每次启动都跑 `regen --check`，
  改了之后所有 clone 升级后都会提示"CLAUDE.md 过期"，而 hub 这边还要走 /iterate-constitution。
  所以改为和 check_scope `.baseline_commit` / art_05 条款一起，以后单独处理。
- 全局 Python 仍是 0.49.1。消费者用 `/upgrade`（`pip install -U`）自己升级。

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
