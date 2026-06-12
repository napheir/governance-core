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

### 2026-06-12 — P-0098 收编 gc #89 skill competing-design-proposals-with-deferred-adr（去域化）+ 0.26.0

- **curate #89**（trade-agent 候选 skill）→ 包源
  `governance_core/skills/competing-design-proposals-with-deferred-adr.md`：
  - frontmatter 重塑 learned→guide（`theme: universal` / `type: guide`；
    name/description/tags 保留；updated 06-12），H1 标题化 + 加 provenance 注。
  - **de-trade-ify**：唯一域泄漏 Note 行（"不可比红线/单流基线回归 delta=0"）
    泛化为通用基线回归守卫；机制/workflow 逐字保留。
- **#87 duplicate**：与 #89 payload 逐字相同（仅 candidate id 日期后缀 0611 vs
  0612 不同）。关 #87 指向 #89，**不**进 rejected_registry —— 内容实为 promoted，
  否则会给 trade-agent 发错 reject 信号。
- **关键坑**：hand-genericize 后**不能**用 `candidate.py promote`（它对 skill kind
  会把**原始** payload 拷回覆盖我去域化后的文件）；改直接调
  `registry.record_candidate` 记 promoted（同一库函数，Art.8 同路径）。
- **清理**：删 `.governance/candidate-outbox/` 两个死快照（command-guard
  `# P-0065 Phase 4 drift probe` 探针残留 + auth-guard pre-P-0082 旧快照；
  gitignored，live 自治层已无漂移、无需 promote）。
- 验证：28 pytest green；discovery 收录新 guide；upgrade + doctor exit 0；
  wheel 顶层仅 `governance_core*`、含新 skill、无 `maintainer/` 泄漏。
  版本 0.25.0 → **0.26.0**。
