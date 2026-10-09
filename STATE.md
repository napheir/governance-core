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

### 2026-10-09 — P-0128 Phase A：`related` 接受全局 id + audit Check 18（0.44.0，未发布）

- **批准**：owner 2026-10-09 批 P-0128 并接受各倾向（Phase B 等消费者 diff；`link` 子命令；
  ledger-only id 可解析；Phase A 单独发）。P-0128 现为 `in-progress`（Phase B 未做）。
- **契约**：`proposal_frontmatter_schema.md` v1.3.0 → **v1.4.0**（§4.6 + 新 §5.7 + §7 不变量）。
  增量兼容：自由文本 `related` 含义不变、不校验。
- **写入口**：`proposal_lib.py link --id P-NNNN --related <ref>`（可重复）——`related` 的唯一
  writer；写入时 fail-fast（须能解析 / 非自身 / 非畸形 id），幂等，追加一行 State Log，不动被引用方。
- **审计**：Check 18（FAIL）—— id 形式的 `related` 须在 in-flight/archive/legacy 或 id ledger 中
  解析到；自引用、畸形 id（`P-12`/`p-0123`）也 FAIL；单向、不要求反向引用。writer 与 auditor
  共用 `proposal_lib.classify_related_ref`。
- **文档**：`commands/proposal.md`（`link` 子命令）、`docs/core-manual.md` §4。
- **验证**：新增 `tools/test_audit_proposals_related.py` 31 passed；pytest `tools/` 191 passed；
  全部脚本套件零失败；`upgrade` + `doctor` exit 0；wheel 干净。**live dogfood**：
  `link --id P-0128 --related P-0126` 成功、重复执行无变更、`P-9126` / `p-0126` 被拒（rc=1）；
  真实语料 audit 0/62 failures。
- **bump**：0.43.1 → 0.44.0。**未发布**（0.44.0 的发布未获确认；owner 只确认了 0.43.1）。
- **0.43.1 已发布并核实**：`gh release create v0.43.1` → CI `release` success → PyPI JSON
  `latest: 0.43.1`，wheel + sdist 均在。master 已 push（`abd3d4b`）。

### 2026-10-09 — intake 自动关闭 byte-identical 重复件（P-0127 Open Question，owner 裁定：是）

- owner 2026-10-09 裁定四项待决：① 批 P-0128 并接受各 Open Question 的倾向；② push + 发布
  0.43.1；③ 策展例程启用与否待后续讨论；④ intake 对 byte-identical 重复件自动关闭。
- **改动**：`maintainer/candidate_intake.py` 加 `close_duplicate`（`gh issue close --reason "not
  planned"`，失败只记日志不抛）；`duplicate` / `dup-of-rejected` 打标签 + 评论后即关闭，`revision`
  永不关闭，fail-open 路径不关闭任何东西。评论改为"要复议请 reopen 并说明"。
- **文档**：`docs/core-manual.md` §11、`curate-candidate` 同步（不再说 intake 不关 issue）。
- **验证**：intake 42/42（+3：关闭调用形态、关闭失败被吞、fail-open 不关闭）；curate_gate 14/14；
  pytest 160 passed；`upgrade` + `doctor` exit 0。线上实证仍待下一个真实重复 candidate。

### 2026-10-09 — P-0128 起草（pending）：candidate #139 handoff linkage 机制

- **判断**：#139 在 charter 内、通用、论证扎实（实读确认：`related` 现为自由文本，
  `audit_proposals.py` 从不读它；Check 止于 17）。但改 `contracts/proposal_frontmatter_schema.md`
  且 bundle 只有 brief 无代码；hub 单 agent（`agent_rules/` 仅 `shared.*`，`load_allow_map` 恒空）
  无法 dogfood handoff 半边。
- **P-0128（pending，未自批 —— needs-human + 契约变更）**：Phase A `related` 接受 `P-NNNN` +
  Check 18（hub 可验）；Phase B `handoff_to` + `handoff_targets` + Check 19/20 + session surface
  （等消费者参考 diff）。4 条 Open Question 待 owner 裁定（是否等 diff、`link` 子命令、ledger-only
  id、Phase A 单独发）。
- **#139**：已评论（recommend promote 分两期 + 索要参考实现 diff 与测试）并标 `advised`，保持 open。
- **待 owner 决策汇总**：① 批 P-0128；② 发布 0.43.1（含 P-0126/P-0127）+ push master（intake 改动
  push 后才生效）；③ 是否重新启用 `gc-curation-routine`（启用前同步 prompt）；④ intake 是否对
  byte-identical 重复件自动关闭。
