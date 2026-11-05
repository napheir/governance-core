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
