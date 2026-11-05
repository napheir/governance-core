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

### 2026-11-05 — P-0130 Phase C：check_agent_roles / audit_hooks v2 + 文档，版本 0.48.0（未发布）

- **G3**：`check_agent_roles.py` 重写：agent / clone 根取自 config（单 agent = 本仓库，多 clone = `<父目录>/<clone_dir>`）；核心角色 =
  `<agent>-*.md`；文件名前缀为**另一个** agent 名才算跨 scope（共享角色不报）；`main(root, argv)` 可测试。
- **G4**：`audit_hooks.py` 重写：clone 取自 config，期望 hook = `hooks_manifest.json`（与 installer / doctor 同源，复用
  `installer._load_hooks_manifest` / `_hook_file_of`）；检查存在、注册、重复、与 core 副本一致、settings.json 无 hooks/plugins；
  删除写死的 5 clone 与已不存在的 `sensi-guard.py` / `pipeline-check.py`。**偏差**：删除 `_check_stale_local_refs` —— 它按字面
  `agent-core` 判断 sync_infra 的集中引用模型，在 installer（`${CLAUDE_PROJECT_DIR}` 本地接线）装出的消费者里只会误报。
- **G5**：skill `settings-json-merge-semantics` 第 3 条改为"settings.json 不放 hooks / enabledPlugins；只含 projectRoot 锚不是漂移"，
  与 sync_infra / 0.47.0 一致。**G6**：`skill-scenario-clusters.md` 示例改为 `platform`；另把 `check_scope.py` 注释示例去业务化。
- **门禁**：带引号的上游角色名 token grep 在 `governance_core/`（除测试与一次性迁移工具）为零。core-manual 新增 "Agent enums come from config"。
- **测试**：新增 `test_check_agent_roles.py` 7 例、`test_audit_hooks.py` 7 例（clone 由真实 `install()` 生成，含 installer 写的 projectRoot
  settings.json 不误报）。全量 pytest 334 passed，脚本风格全过；hub 上 doctor / audit_proposals / audit_knowledge / audit_hooks /
  check_agent_roles 全部通过。版本 0.47.0 → 0.48.0，wheel 干净。**发布待 owner 确认**。

### 2026-11-05 — P-0130 Phase B：knowledge `owner` 改为取自 config

- **G2**：`contracts/knowledge_frontmatter_schema.md` 1.2.0 → 1.3.0，§3.2 不再列上游角色表，`owner` = config `agents[].name`
  ∪ 字面 `core`（core agent 别名，shipped 文档都写 `owner: core`）；新增 §8.3 发布说明。`audit_knowledge.load_owner_enum`
  取代 `parse_enum(... 3.2 ...)`，缺 config 即 FATAL；`migrate_knowledge_frontmatter` 删 `VALID_OWNERS`，改为 `load_valid_owners` 显式传参。
- **偏差**：原计划的 carrier_class 必填切换 "v1.3.0" 在 5 个文件里被引用 11 次，统一顺延为 v1.4.0（只改编号、不改范围），
  以符合契约自己的 SemVer（新增 owner 值 = minor）。
- **测试**：`test_config_derived_enums.py` 新增 5 例 knowledge（含 `core_agent_name: lead` 时 `owner: core` 仍有效、缺 config FATAL）；
  `test_audit_index_absent.py` 夹具补 config。hub `audit_knowledge` Failed 0（owner_enum=['core']）；全量 pytest 320 passed，脚本风格全过。

### 2026-11-05 — P-0130 Phase A：提案 `agent` 改为取自 config

- **起因**：deva-vani 报 knowledge owner / check_agent_roles 写死上游角色；本仓库按角色名 token 扫描找到同族 6 处（G1–G6），
  起草 P-0130，owner 批准（Q1–Q4 按默认：归档不在册 WARN、`core` 别名、audit_hooks 改 v2、一次发布 0.48.0）。
- **G1**：`contracts/proposal_frontmatter_schema.md` 1.5.0 → 1.6.0，`agent` 取值 = config `agents[].name`；`audit_proposals.py`
  删 `VALID_AGENTS`，改用 `_config_agents`（`load_proposals_config`）：in-flight 不在册 FAIL，归档/legacy 只做形式校验
  `^[a-z][a-z0-9_-]*$`，不在册由新增 Check 21 WARN。`_validate_one` 新增可选参数 `valid_agents`（旧调用方不受影响）。
- **测试**：新增 `test_config_derived_enums.py` 7 例（提案部分）；hub `audit_proposals` 仍 0 failures；全量 pytest 314 passed，脚本风格全过。
