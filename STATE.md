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

### 2026-11-05 — P-0129 Phase A：agent 身份改为按 config 推导 + guard 加固

- **起因**：deva-vani core 报告 8 个问题（`artifacts/deva-vani/2026-11-05-issues-from-deva-vani.md`），本仓库核实全部属实，
  另找到 F7/F8。owner 批准 P-0129（10 项 F1–F10，分 A/B/E → 0.46.0、C/D/F → 0.47.0）。
- **F1（安全）**：`_guard_common` 新增 `load_topology / resolve_agent / detect_role / identity_failure`：
  身份 = clone 目录名对照 config `agents[].clone_dir`（单 agent 配置即唯一 agent），不再看分支、不调 git；
  无法解析 → `<unresolved>`，edit-write-guard 拦截所有写并写明原因。5 处写死的上游角色表全部删除：
  session-context、merge-audit、`proposal_lib.detect_agent`、`regen_constitution.detect_role`（两个 tool 按路径加载
  同一份 `_guard_common`）。scope-guard 改为按 hook 所在 clone 判定（原来按 cwd）。
- **F7**：跨仓库 Bash 模式改为 `<项目目录>/<clone>` + `../<clone>`，由真实 clone 位置推导；仍不含 core clone（沿用原策略）。
- **F8**：非 core 不得 Edit/Write 自己的 `.claude/hooks/**`、`.claude/settings{,.local}.json`。
- **doctor**：身份无法解析 → exit 10；OK 行带 `agent=`。条款 art_09 / art_12 去业务化并写入身份规则；
  `/proposal` 文档、core-manual 同步。`.role` 不再被读取（hub 的 `.role` 文件与宪法第二条表格待 /iterate-constitution 清理）。
- **测试**：新增 `test_agent_identity.py` 23 例（deva-vani 形状 4 clone 嵌套布局，含真实 guard 子进程）；
  反向校准：0.45.1 旧 guard 对"越权 Edit / 改自身 guard / Bash 写兄弟 clone"三场景都 exit 0。
  全量 pytest 271 passed，脚本风格 28 个文件全部通过；upgrade + doctor OK（agent=core）。

### 2026-11-05 — 新消费者 deva-vani：签发授权码 + bootstrap 绕行方案

- **背景**：owner 要为 Deva-Vani（丝巾品牌：官网 / App / 内容工厂 / 后续电商）新建多 agent 项目，
  拓扑 core + platform + experience + content，建在 `workshop-claude/deva-vani/`。
- **授权**：`maintainer/issue_auth_code.py --consumer-id deva-vani`（schema 2，到期 2027-11-05），
  登记进 `consumer_registry.json`；码只落 gitignored 文件，未打印。
- **发现**：`multi-agent-bootstrap new`（0.1.0a0）调 `governance-core install` 不带 `--auth-code` /
  `--accept-candidate-uplink`，过不了 P-0065 授权门；`expand` 已适配。绕行驱动脚本
  `artifacts/deva-vani/bootstrap.py`（gitignored）：`new --no-bootstrap` → 带码 + overrides install →
  `expand --no-backup`。仓内 trial 全程通过（4 clone 各 install + doctor OK），已删 trial。
  修 `new` 属 multi-agent-template 仓库，待单开会话。
- **正式 bootstrap**：写仓外，由 owner 以 `!` 运行（会话边界）——已完成：`workshop-claude/deva-vani/`
  下 `agent-{core,platform,experience,content}` 各 install + doctor OK，`shared_state/` 已初始化，
  授权码文件已删。下一步在 `deva-vani/agent-core` 新会话写宪法 + 五份数据契约。
- **品牌方规划页**：Artifact https://claude.ai/artifact/46mE3sQcbvMKdm7meggrBk （源
  `artifacts/deva-vani/brand-plan.html`，私有，需 owner 分享）。
