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

### 2026-10-16 — 发布 v0.45.1（SessionStart 列出仓内 shared_state 提案）

- **发布**：owner 确认（"是的，发布"）后 push master（`4f409d6`）→ `gh release create v0.45.1`
  （target master）→ CI `release.yml` run 38834240931 success → OIDC Trusted Publisher。
- **核实**：PyPI `/governance-core/0.45.1/json` 有 wheel + sdist；主 JSON 首次查询仍是 0.45.0（CDN
  缓存），带 no-cache 重查为 `latest: 0.45.1`；`gh release list` 显示 v0.45.1 为 Latest。
- **消费者影响**：单仓布局（`shared_state/` 在仓内）的项目 `upgrade` 后 SessionStart 开始列出在途
  提案；多 clone 布局行为不变。无迁移。

### 2026-10-16 — fix: SessionStart 不显示 hub 自己的待审提案（0.45.1，未发布）

- **bug**：`session-context._check_proposals` 只扫 `../shared_state/proposals`（多 clone 布局）；
  hub 的 `shared_state/` 在仓库内，所以 hub 开会话时从不列出自己的 pending/approved/in-progress
  提案（P-0107 一直看不到）。P-0128 Phase B 合入时发现，owner 要求修。
- **修复**：新 helper `_shared_state_proposal_roots(root)` 返回仓内 + 同级两处中存在的目录（去重、
  仓内优先）；`_check_proposals` 与 `_check_open_handoffs` 共用它；同一文件在两处只列一次。
  无需提案（单文件、清晰复现、低风险）。
- **范围核查**：`edit-write-guard` 的 `../shared_state` 只是给仓外同级目录开白名单（仓内本来就在
  边界内），`migrate_proposals_to_shared_state` 只在缺配置时兜底——均非同类 bug，未动。
- **验证**：新 `tools/test_session_context_proposals.py` 11 passed（对旧 hook 3 failed，即仓内布局
  的几例）；pytest `tools/` 248 passed；脚本套件零失败；`upgrade` + `doctor` exit 0；audit 0/62；
  wheel 干净。**live**：hub SessionStart 现显示 `Pending proposals (core, shared_state):
  p-0107-skill_self_improvement_v2.md`。
- **bump**：0.45.0 → 0.45.1。**未发布**（需 owner 确认）。

### 2026-10-15 — 发布 v0.45.0（P-0128 Phase B：handoff_to / candidate #139）

- **发布**：owner 确认（"OK，发布"）后 push master（`7deb957`）→ `gh release create v0.45.0`（target
  master）→ CI `release.yml` run 38722786881 success → OIDC Trusted Publisher。
- **核实**：PyPI JSON `latest: 0.45.0`，wheel + sdist 均在；`gh release list` 显示 v0.45.0 为 Latest。
- **#139**：评论落地内容与相对参考 diff 的改动，已关闭（completed）。hub 当前无 open issue。
- **消费者影响**：`upgrade` 后可用 `link --handoff-to`；多 agent 消费者的 Check 19/20 与 SessionStart
  提示开始生效，单 agent 项目静默。纯增量，无迁移。
- **遗留**：hub `session-context._check_proposals` 只扫 `../shared_state`，hub 自己的 pending 提案
  （P-0107）不在 SessionStart 显示——已报告 owner，未修。

### 2026-10-15 — P-0128 Phase B：`handoff_to` + open-handoff 审计（0.45.0，未发布）

- **来源**：消费者 2026-10-09 在 #139 贴出 Phase B 参考 diff（5 文件 / 556 行 / 28 测试，基于
  `a3a2af6`）。`git apply` 干净，原样 28 passed；在此基础上按 hub 规范改写。
- **采纳**：`proposal_suggest.handoff_targets`（per-token co-owner skip）、create 提示、audit
  **Check 19**（open-handoff，WARN）/ **Check 20**（缺 `handoff_to` 兜底，WARN）、session-context
  "Open handoffs to you"。
- **hub 改动**：① 新写入口 `proposal_lib.py link --handoff-to <agent>` / `--clear-handoff`
  （须为配置内 agent、不得是自己；与 `--related` 同命令时先整体校验再写）；create 提示改为给出该命令，
  emoji 换 `[HANDOFF]`；② `HANDOFF_CUTOVER` 改为 2026-10-15；③ Check 20 的 allow map 跟随
  `--root`（`<root>/agent_rules`），导入用 `Path(__file__)` 惯例；④ Art.4：去掉 `fm.get(...)`；
  ⑤ 关闭谓词加 (c)：`rejected` 视为已关闭（参考实现会让被否决的建议永远挂账）；⑥ session hook 同时
  查仓内 `shared_state/` 与 `../shared_state/`，只读 frontmatter 段（参考实现读前 1200 字符、只看
  `../`，在 hub 布局下看不到 in-flight）；⑦ `handoff_to` 进 serializer 字段序。
- **契约**：`proposal_frontmatter_schema.md` v1.4.0 → **v1.5.0**（§4.6 行 + 新 §5.8 关闭语义 + §7）。
  `commands/proposal.md`（`link --handoff-to` + 红线）、`docs/core-manual.md` §4。
- **验证**：`tools/test_handoff_linkage.py` 46 passed（消费者 28 + hub 18）；pytest `tools/` 237
  passed；全部脚本套件零失败；`upgrade` + `doctor` exit 0；真实语料 audit 0/62 failures、0 warnings
  （hub 无新 WARN）；wheel 干净（仅 `governance_core*`，schema 1.5.0，新测试在内）。**live dogfood**：
  hub 上 `--handoff-to core`（自己）/ `trade`（未配置）均 rc=1 且文件不变，`--related`+坏
  `--handoff-to` 不会半写，空 `link` rc=2；session hook 在单 agent hub 上不输出 handoff 行。
- **bump**：0.44.0 → 0.45.0。**未发布**（发布需 owner 确认）。#139 待发布后评论并关闭。

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
