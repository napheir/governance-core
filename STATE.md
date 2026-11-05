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

### 2026-11-05 — 发布 v0.48.4、批准 P-0131、授权码泄露调研

- owner「发布。批准 P-0131。先处理授权码泄露」：推送 d7f5a42，`gh release create v0.48.4`，CI 成功；`gh release list` Latest = v0.48.4，
  PyPI 版本端点含 wheel + sdist；已通知 deva-vani。P-0131 pending → approved（note 记 owner 原话），实施排在授权码之后。
- **授权码调研（只读，未打印任何码）**：hub 公开仓库历史里有两份 hub 码 —— schema 1 永久码（13d1843 / 581f7e5，无到期、无吊销 feed，
  auth-guard 对 schema 1 直接放行）与当前 schema 2 码（到期 2027-05-18，吊销只能按 consumer_id，会冻结 hub 自己）。
  deva-vani / trade_agent 仓库为 PRIVATE；其他公开仓库（multi-agent-template 等）当前无跟踪的 config。本机可见的消费者码全是 schema 2。
  吊销 feed URL 签在每个 schema 2 码里，指向 hub 公开仓库的 raw 地址。方案对比交 owner 讨论。
