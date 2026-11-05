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

### 2026-11-05 — 起草 P-0131 + rotate_state 归档标题修复（0.48.4）

- **P-0131 已起草并提交评审（pending）**：merge 导入按来源提交归属。现状：`check_scope.py:279-290` 对与 MERGE_HEAD 相同的越界文件
  整体放行、不看来源；core 分支写死为本地 `master`，而 config 已有 `core_branches` / `upstream_branch`（`config.py:103` 对后者用了
  `.get` 默认值）。方案：从 config 推导 core 引用；只放行来自 core 历史的导入，非 core 提交（含 merge 提交的冲突解决 / 夹带改动，
  `--diff-merges=dense-combined` 实测可列出）触及的越界文件判 `IMPORTED_OUT_OF_SCOPE` 并点名提交。三个 phase。
  验收命令逐条预跑：`-k foreign` 会命中已有的 `test_foreign_pre_commit_left_alone`，改为 `-k foreign_agent_branch`。
- **deva-vani 0.48.3 实测**：四个 clone 都有 pre-commit + pre-merge-commit，doctor / check_agent_roles / audit_sub_constitutions 全过；
  `--no-ff --no-commit` + `git commit` 的 sync 通过；DEFER 路径尚未在真实 sync 中触发。
- **rotate_state 首次归档写入上游标题**（deva-vani 报）：`ARCHIVE_HEADER` 写死 "# Trade Agent 项目状态文档 — Archive"，hub 自己的
  STATE_ARCHIVE.md 也是这个标题。改为取 STATE.md 的 H1 加 " -- archive"（无 H1 时 "# STATE archive"）；已有归档保留原标题。
  首次新建归档时 stats 带 `archive_created` 并 WARN 提示与 STATE.md 一起暂存；`/wrap-up` Step 2 写明 rotation 改动或新建
  STATE_ARCHIVE.md 时必须一起 add。hub 归档标题已改。
- **测试**：+3（`test_rotate_state_archive.py`），对旧版反向校准 3 例全 FAIL。全量 pytest 350 passed，脚本风格全过。
  版本 0.48.3 → 0.48.4。**发布待 owner 确认**。
