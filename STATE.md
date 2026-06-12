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

### 2026-06-12 — P-0099 修 consumer bug #90 sweep 重复 uplink + #91 sync_infra 删 tracked hook + 0.27.0

- **#90 `candidate.py sweep` 重复 uplink**（即 #87/#89 的成因）：
  - **RC1** `cmd_sweep` 抽出纯函数 `_dedup_pending_by_digest`，uplink 循环前按
    digest 去重 `pending`（pre-scan ledger 快照下两个同 digest envelope 都过
    `is_uplinked` → 都 uplink → 重复 issue）。
  - **RC2** `collect.py collect_netnew_skills`：已存在同 digest envelope 时跳过
    新建（`skill_digest` vs 现存 `payload_digest`；延迟 import ledger 避循环）。
    改后 collect 对未变 skill 幂等，变更 skill（新 digest）仍 stage 为 update。
- **#91 `sync_infra._remove_local_copy` 删 git-tracked 集中化 hook**：加
  `_is_git_tracked`（`git ls-files --error-unmatch`，任何失败 fail-safe→False）；
  tracked 的本地副本改为 `[KEEP]` 保留（settings 已指向 core 绝对路径、永不执行），
  只删 untracked orphan（迁移本意）。settings 引用重写半边不动。
- 测试：`test_candidate_sweep` +6（2 RC1 纯函数 + 4 RC2 collect 幂等/edited）；
  新 `test_sync_infra_remove_local_copy.py` 4 例（tracked keep / orphan del /
  dry-run / 非 repo fail-safe）。
- 验证：pytest 32（28+4）green；24 个脚本式测试全绿（command-guard 42/42 等
  无回归）；upgrade + doctor exit 0；wheel 顶层仅 `governance_core*`、含改动、
  无 `maintainer/` 泄漏。版本 0.26.0 → **0.27.0**。关 #90/#91。

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
