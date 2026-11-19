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

### 2026-11-19 — P-0139 结案归档；P-0140 批准

- **P-0139**：owner 在本会话亲口确认决策卡"好用"。按实施提交 d9e4256 标为 implemented，并归档到 `proposals/_archive/2026/`。对照检查：范围内的文件都改到了，范围外只多了版本号和 STATE。
- **P-0140**：owner 说"批准 P-0140"，按决策卡的默认执行：
  - OQ1：角色文件只许 core 改；
  - OQ2：hook 被改报 FAIL；
  - OQ3：MCP 工具调用这次不处理；
  - OQ4：嵌套的 `.claude/` 一律拦；
  - 以 0.54.0 发布。
- **P-0133**：之前我说"恢复会话时没有出现 [WARN]，所以检查通过"，这是错的。本会话的 PATH 前面没有 `.venv/Scripts`，所以不是用 gchub 启动的；在本会话里手动运行检查，确实会报 WARN。gchub 只定义在 Git Bash 的 `~/.bashrc` 里。

### 2026-11-19 — deva-vani 升到 0.53.0；起草 P-0140（待批）

- deva-vani 四个 clone 都已升到 0.53.0（四个 clone 都有 owner-decision-card 指南）。
- **P-0139 第 2 阶段**：那边的 core 会话转达 owner 的反馈，决策卡"好用"。已记入 P-0139。按本项目规则，转达不算确认，退出条件等 owner 在本会话亲口确认。
- **P-0140**（待批，在 shared_state）：业务 agent 可写的文件中，有些会决定 Claude Code 执行什么。提案把这些文件也归为只有 core 能改。由 deva-vani core 提出，本会话用文档和探针核实。细节在提案里，修复发布前不公开。
- P-0138 的重放还没做：deva-vani 的日志里还没有 `via: bash` 的记录。
- **仍在进行**：
  - P-0138 第 2 阶段（重放）；
  - P-0139 第 2 阶段（owner 确认）；
  - P-0140 审批；
  - P-0133（owner 确认两种启动方式）。

### 2026-11-18 — P-0136 现场验证通过（deva-vani，0.52.0）

- deva-vani 的 core 会话（agent-core-ee）报告第 1–3 步全部通过。我只读核对了他们的文件，结果一致：
  - 第 1 步：两条 info 通知（dea220、b593e0）的 `shown` 各有两个不同的会话 id，都以 `shown-2` 确认。期间两次 resume 没有被多算一次。
  - 第 2 步：content 改自己的 P-0047 被记为 `via edit`，没有产生通知。
  - 第 3 步：11-17 已通过。第 4 步测的是 0.51.2 已撤回的拦截，不再适用。
- deva-vani 现在没有任何未确认的通知。结果已写进 P-0136。
- 已回复他们：owner 看过预览后升级到 0.53.0，然后在新开的 platform 会话里做 P-0138 重放（`sed -i` 再 Edit，预期没有新告警），并反馈 owner 有没有看到决策卡。
- 按 P-0138 的退出条件，重放通过后，P-0135、P-0136、P-0138 一起完成并归档。归档会公开，需要 owner 同意。
- **仍在进行**：P-0138 第 2 阶段（重放）；P-0139 第 2 阶段；P-0133（`gchub -c` 确认）。

### 2026-11-17 — 发布 v0.53.0（P-0139 决策卡）

- **发布**：owner 说"发布 0.53.0"。
  - 推送 951b6a6..d9e4256。
  - GitHub Release v0.53.0（Latest），CI run 44006532167 成功。
  - PyPI 的 simple 索引已有 0.53.0 的 wheel 和 sdist；JSON API 还停在 0.52.1，是 CDN 延迟。
- **通知 deva-vani**（会话 agent-core-14）：按 owner 的要求，请他们在自己的会话里取得 owner 亲口确认，再确认那 7 条误报告警。我这边转达的消息不能算作确认。
  - 他们回复：7 条早已确认，都有 owner 的原话。platform 6 条于 11-16 在 platform 会话里确认；experience 1 条于 11-17 在 core 会话里确认（owner 说"两条 alert 确认 ack"）。
  - 同一句话也确认了 P-0136 第 3 步探针产生的告警 9c47aa。
  - 现在 platform 和 experience 都没有未确认的通知。
- **P-0136 现场验证**：
  - 第 3 步通过：告警写着"before edit:Edit by content; actor unknown"，和预期一致。
  - 第 1、2 步在等两个新开的 content 会话。
- 他们要等 P-0136 现场验证结束，再一次升级到 0.53.0（已包含 0.52.1）；之后我再发 P-0138 的重放步骤。
- **仍在进行**：
  - P-0136 现场验证（deva-vani）；
  - P-0138 第 2 阶段（重放）；
  - P-0139 第 2 阶段（owner 在 deva-vani 看到决策卡）；
  - P-0133（`gchub -c` 确认）。

### 2026-11-17 — 发布 v0.52.1（P-0138）；P-0139 Phase 1：决策卡成为 gc 自带能力（0.53.0，未发布）

- **发布 0.52.1**：owner 说"确认发布"。
  - 推送 b35b5ec..951b6a6。
  - GitHub Release v0.52.1（Latest），CI run 44003631124 成功。
  - PyPI 上 0.52.1 有 wheel 和 sdist。
  - deva-vani 正在 0.52.0 上做 P-0136 现场验证，验证完再升级。
- **P-0138 目录处理**：owner 说"保留"。
- **P-0139**：owner 说"批准"，默认值照卡执行：始终开启、不加配置项；只警告不拦截；加每次提醒；0.53.0。
  - 新增通用 skill `skills/owner-decision-card.md`（theme: universal）。
  - `constitution-reminder.py` 每次提醒加一句，指向这份 skill。
  - `proposal_lib`：
    - 提案模板开头加"决策卡"一节；
    - 新增 `decision_card_adequacy`；
    - submit/approve 时缺卡、仍是占位符或超过 8 行只警告；
    - `--allow-no-card` 可关掉警告。
  - `/proposal`、`/upgrade` 第 4 步、core-manual §6 和 §17 都已更新；合同 `proposal_gate_schema.md` 升到 1.2.0；版本 0.53.0。
  - 测试：新测试 11 个，全套 569 通过，command-guard 42/42，doctor OK，audit_knowledge 健康，wheel 干净。
  - P-0139 自己也加上了"决策卡"一节，检查通过。
- **待办**：0.53.0 发布要 owner 确认；P-0136 现场验证结果在等 deva-vani。

### 2026-11-17 — P-0138 Phase 1：shell 写入也记入日志（0.52.1，未发布）

- **owner 说"批准P-0138"**，三个默认值照卡执行：所有分区目标都记；命令失败也记；版本 0.52.1。
- **改动**：
  - 解析 shell 写入目标的代码从 scope-guard 移到 `_guard_common.shell_write_targets`。拦截和记日志用同一个函数，scope-guard 的行为不变（`test_shared_state_partitions.py` 46 个照过）。
  - `ownership.py`：VIAS 加 `bash`；新增 `shell_targets`；`capture_before` 和 `journal_edit` 处理 Bash。
  - `own-write-capture.py`：Bash 命令里没有 shared_state 目标时，不导入包直接退出。
  - 新 hook `own-write-journal-failure.py`（PostToolUseFailure），已登记为 fail-open importer。
  - manifest：两个 own-write hook 的 matcher 加 Bash，并加入新 hook。
  - 合同 `shared_state_ownership.md` 升到 1.3.0；core-manual §15；版本 0.52.1。
- **核实**：本机 Claude Code 2.1.286 有 PostToolUseFailure 事件，查的是二进制，公开 changelog 里没写。按 settings 文档，不认识这个事件的旧版客户端只跳过这一条。
- **和批准时不同的一处（已请 owner 裁定）**：目标是已存在的目录时（`mv a.md done/`），会记录目录下第一层的文件。更深层的仍然会报警。
- **测试**：新测试 15 个，全套 558 通过，command-guard 42/42，doctor OK（hooks=25、hooks_registered=24），wheel 干净。
- **待办**：owner 确认后发布；然后请 deva-vani 重放这次的现场情形。

### 2026-11-13 — 发布 v0.52.0（P-0137 + 撤回标题提示）

- **发布**：owner 说"发布"。
  - 推送 f73ed4f..e84d887。
  - GitHub Release v0.52.0（Latest），CI run 43353850530 成功。
  - PyPI 上 0.52.0 有 wheel 和 sdist。
- **通知 deva-vani**（会话 agent-core-a2）：请他们升级，然后在 core 跑 `python tools/sync_infra.py` 并回报结果，这是 P-0137 的消费者检查。
  - 发布时只读查看了他们的通知：platform 5 条未确认；experience 1 条未确认、1 条已确认；content 0 条未确认、3 条已确认。
  - owner 说"没有显示了"。
- **P-0133**：owner 用的是 WezTerm 里的 Git Bash，`gchub` 别名就在那里。
  - 这个会话是用普通的 `claude` 恢复的，所以出现了 `[WARN]`。
  - 下次用 `gchub -c` 或 `gchub --resume` 恢复，确认不再出现 `[WARN]`，然后就可以结案。
- **仍在进行**：
  - P-0136：等现场验证第 1–3 步；
  - P-0137 Phase 3：等各消费者跑检查；
  - P-0135：和 P-0136 一起结案。

### 2026-11-13 — 撤回会话标题提示（并入 0.52.0，未发布）

- **现场发现**（deva-vani 升到 0.51.3 后）：
  - ListAgents 里的会话名变成了 "[ALERT 5] platform" 和 "[ALERT 1] experience"。
  - 会话标题同时也是会话之间互发消息的地址，所以 platform 原来的名字 agent-platform-f2 不再能收到消息。
  - alert 数量每变一次，名字就跟着改一次；把 agent 名放在前面也一样会改地址。
- **撤回内容**：
  - 删掉 `notice-title.py`、它在 manifest 和 FAIL_OPEN 里的登记、`ownership.title_update` / `alert_title`，以及 `foreign-change-notice` 里设置标题的代码。
  - 删掉 7 个标题测试，新增 1 个防回归测试：确认没有通知类的 UserPromptSubmit hook，SessionStart 也不设标题。
  - 契约改为 1.2.1，core-manual §15 同步更新。
  - 保留 `notice_title.json` 的忽略规则。
  - upgrade 时会删掉已经装上的 notice-title.py（在 hub 上验证过）。
- **已通知 deva-vani**：
  - 发消息前先用 ListAgents 重新查名字；
  - 已被改掉的标题会一直保留，可以用 /rename 改回来或开新会话；
  - 在 0.51.3 下确认 alert 会再改一次名字。
- **教训**：两次想借 Claude Code 自带的渠道逼 owner 注意，都弄坏了 agent 依赖的东西：输入里会夹着同伴消息，标题又是同伴的地址。以后的提示只能放在没有 agent 依赖的地方，候选有可选的状态栏片段或待办台。
- **测试**：全部 543 个通过，command-guard 42/42，doctor 正常（注册了 23 个 hook）。

### 2026-11-12 — P-0137 Phase 2：文档统一到"只有一种接线方式"（0.52.0，未发布）

- **命令**：
  - `/wrap-up` 第 5 步改为跑只读检查：有 FAIL 必须先修，清单上改记"Infra 已检查"；5b 的触发条件 1 和 2b 的理由也跟着改了措辞。
  - `/sync-infra` 改写成检查说明。
  - `/iterate-constitution` 的 Step 5 传播表改为：已跟踪文件走 `/sync-repos`，gc 文件走发版加 upgrade。
  - `/update-skill` Step 3 不再提 COPY_COMMANDS 清单。
  - curate-candidate、learn、publish-knowledge 改了措辞。
- **条款 art_15**：`theme` 由 SessionStart 注入和 audit_knowledge 执行。
- **skill**：
  - 重写 `cross-clone-base-promotion`。原来的"反向漂移"讲的是 sync_infra，现在改成 `/sync-repos` 和 upgrade 这两条单向通道。
  - 重写 `slash-command-hot-reload`：merge 或 upgrade 改动了命令文件后，必须重启会话或重新调用命令。并补上 deva-vani 遇到的情况：照着会话早期加载的旧版 skill 做事。
  - 另有 5 个 skill 改了措辞。
- **知识库**：skill-scenario-clusters 删掉了"按 theme 路由"那一列，另外两篇改了措辞。
- **代码里的文字**：
  - 3 个 guard 的 FATAL 提示改为 `governance-core upgrade --project-root <this clone>`；
  - 各处 docstring；
  - session-context 的重启标记说明。现在已经没有地方写这个标记，但遗留的标记仍会显示一次。
- **docs**：architecture.md；core-manual 新增 §16"只有一种接线方式"，并补充了多 clone 项目经 master 合并拿到升级文件的说明（来自 deva-vani 的反馈）。
- **检查结果**：
  - 用 grep 核对过，已经没有任何文字说 sync_infra 会复制、路由或改接线。
  - 全部 549 个测试通过，command-guard 42/42，doctor 正常，知识库健康，regen --check 与宪法源一致。

### 2026-11-12 — 发布 v0.51.3；P-0137 Phase 1：sync_infra 改为只读检查（0.52.0，未发布）

- **发布 0.51.3**：owner 说"发布"。
  - 推送 db1a8cf..f73ed4f。
  - GitHub Release v0.51.3（Latest），CI run 43178391700 成功。
  - PyPI 和 simple 索引里都有 wheel 与 sdist。deva-vani 起初装不上，是索引延迟，已向他们说明。
  - deva-vani 从 0.51.1 直接升到 0.51.3 的预演很干净，正在等他们的 owner 确认；之后报告标题现场验证的 (a)(b) 两步。
- **P-0137 已批准**：owner 说"批准"，按决策卡上的默认值执行：
  - allow 列表只提示，不自动改；
  - `--execute` 直接报错退出（exit 2）；
  - 保留 sync_infra 这个名字；
  - 发布后先请 trade 跑一次检查。
- **Phase 1：`sync_infra.py` 重写为只读检查。**
  - 找 clone 的方式改为 core clone 的上级目录加 `clone_dir`，不再读 `install_root`。
  - 检查项：
    - FAIL：clone-missing、settings-missing、foreign-hook-ref、hook-unregistered；
    - WARN：wide-allow、copy-drift（不计换行符差异）。
  - 支持 `--json`。退出码：0 表示没有 FAIL，1 表示有 FAIL，2 表示检查跑不起来。`--execute` 一律拒绝。
  - 新代码里没有 `.get(k, default)`。
- **校准**：在多一层目录的布局里，0.51.3 的旧工具跳过了全部 2 个 clone，仍然报告"Total pending actions: 0"并返回 exit 0；新检查能找到这两个 clone。
- **只读实测**：deva-vani 的 3 个 clone、auto-tax 的 1 个 clone 都通过（0 FAIL / 0 WARN）。
- **测试**：
  - 撤掉 `test_sync_infra_remove_local_copy.py`，新增 `test_sync_infra_check.py`（10 个）。
  - 全部 549 个通过，command-guard 42/42，doctor 正常。
  - 版本升到 0.52.0。
- **下一步**：Phase 2 清理文档。包括 3 个 guard 的 FATAL 提示、`/wrap-up` 第 5 步、`/sync-infra`、`/iterate-constitution`、`/update-skill`，以及相关的 skill 和知识库文档。

### 2026-11-12 — 发布 v0.51.2；用会话标题提示未确认的 alert（0.51.3，未发布）

- **发布 0.51.2**：owner 说"按卡片发布"。
  - 推送 fd5d4b3..db1a8cf。
  - GitHub Release v0.51.2（Latest），CI run 43176222541 成功。
  - PyPI 上 0.51.2 有 wheel 和 sdist。
  - 已通知 deva-vani。他们预演过：4 个 clone 都会删掉 notice-gate.py，没有漂移。
- **做法 (b)**：owner 说"然后做 (b)"，记为 P-0136 Phase 5 范围修订。
  - 有 N 条未确认的 alert 时，会话标题显示 `[ALERT N] <agent>`，也就是输入框边框上那个标签；alert 都确认后改回 `<agent>`。
  - 由两处设置，都通过 `hookSpecificOutput.sessionTitle`：
    - SessionStart：`foreign-change-notice.py`；
    - 每次输入：新增的 `notice-title.py`（UserPromptSubmit）。它从不拦截，也不往上下文里加东西。
  - 只在数量变化时才改标题。从没有过 alert 的会话保持原标题；用户 `/rename` 的名字会一直保留，直到数量变化。
  - 各会话的计数记在 `.governance/notice_title.json`（clone 本地，已加入 gitignore，保留最近 50 个会话）。
  - 依据是 Claude Code 更新日志："SessionStart hooks can now set the session title via hookSpecificOutput.sessionTitle on startup and resume"，以及 UserPromptSubmit 的 sessionTitle。
- **涉及文件**：
  - `ownership.title_update` / `alert_title`；
  - `foreign-change-notice.py`；
  - 新增 `hooks/notice-title.py`，已登记到 manifest 和 FAIL_OPEN；
  - 契约升到 1.2.0，更新 core-manual §15；
  - 版本升到 0.51.3。
- **测试**：
  - 新增 7 个，另替换 1 个。其中 6 个在 0.51.2 上会失败；"无 alert 不改标题"在新旧代码上都通过。
  - 全部 543 个通过，command-guard 42/42，doctor 正常（注册了 24 个 hook）。
  - 单 agent 项目里，标题 hook 约 141 毫秒退出。
- **现场验证**：experience 的 8fc9aa 和 content 的 a404d1 先保留不确认。升级后标题应显示 `[ALERT 1] <agent>`，确认后应改回原名。
