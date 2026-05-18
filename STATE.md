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

### 2026-05-18 — P-0068 config-aware skills (Phases 1–3)

- 改动：单 agent skill 降级 —— Phase 1 去硬编码 4 处；Phase 2 给 7 个多 agent
  步骤加拓扑门控；Phase 3 桶 C（lesson 归档 .gitignore 例外、skill-extraction
  能力门控、STATE.md capability 进 installer）。
- 涉及：`governance_core/commands/{wrap-up,extract-skill,update-skill,
  sync-repos,sync-infra,publish-knowledge}.md`、`skills/{lesson-classification,
  _template}.md`、`installer.py`、`.gitignore`、`STATE.md`。
- 关键决策：三桶模型 A/B/C；安装完即所得；复用不 fork；3b（打包
  skills.discovery）拆出为 P-0069。
- 测试：每 phase `governance-core upgrade` exit 0 + 结构校验通过；P-0068
  commits 66d3929 / b58aee1 / 25c9bf9。
