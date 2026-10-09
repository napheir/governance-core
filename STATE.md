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

### 2026-10-09 — 发布 v0.44.0（P-0128 Phase A：related-by-id / candidate #139）

- **发布**：owner 确认后 push master（`2c4bcd0`）→ `gh release create v0.44.0`（target master）→
  CI `release.yml` run 37875913852 success → OIDC Trusted Publisher。
- **核实**：PyPI `/governance-core/json` → `latest: 0.44.0`，wheel + sdist 均在；`gh release list`
  显示 v0.44.0 为 Latest。
- **消费者影响**：`upgrade` 后可用 `proposal_lib.py link`；已有 `related` 里若写了不存在的 id，
  `audit_proposals.py` Check 18 会报出。纯增量，无迁移。
- **#139**：已评论 Phase A 落地，保持 open 等 Phase B 的参考 diff。P-0128 仍 `in-progress`。
- **owner 决策**：`gc-curation-routine` **保持关闭**（两道开关均不动）；积压继续人工批量清理，
  靠 P-0127 的 intake 去重 + 自动关闭挡噪音。

### 2026-10-09 — P-0128 Phase A：`related` 接受全局 id + audit Check 18（0.44.0，已于下条发布）

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
