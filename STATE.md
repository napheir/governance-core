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

### 2026-11-05 — 实施 P-0132 Phase A+B：码移出 git、按码吊销、停用 schema 1（0.49.0，未发布）

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

### 2026-11-05 — 起草 P-0132（授权码泄露修复，A + C）

- owner 选 A + C（码移出 git + 按码吊销 / 停用 schema 1；不轮换密钥、不重签其他消费者、不 yank）。P-0132 已起草并提交评审（pending）。
  三个 phase：A 契约 `contracts/authorization_schema.md` + `.governance/auth_code`（gitignored）存储与迁移；B feed 条目加 `code_sha256`
  （保留 consumer_id 兼容旧客户端）、`SUPPORTED_SCHEMAS = (2,)`、安装时尽力查 feed、revoke 工具按码吊销；C 发布 0.49.0 后由维护者
  重签 hub 码、删 config 里的码、吊销 `99411b5a`，每步人工确认。
- trade-agent 的码不在本机，trade_agent 仓库各分支都没跟踪 config；注册表登记时间晚于 schema 2 成为默认值、expiry = 签发日 + 365，
  判断为 schema 2，验收里要求 owner 在 trade 项目跑一次 doctor 确认。owner 问 trade 码是否快过期：2027-05-19 到期，还剩 195 天；
  hub / auto-tax / trade 三个码都在 2027-05-18~19 到期。
- 验收命令逐条预跑：三条都还选不中测试（实施前失败）。
