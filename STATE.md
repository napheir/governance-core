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

### 2026-10-09 — P-0127：candidate 流水线两端去重 + candidate-common 判据（0.43.1，未发布）

- **根因**（读码确认）：① `candidate.py` sweep 只在本地账本**全空**时才查 hub（旧 `:253`），而账本
  `.governance/candidate-outbox/_uplinked.json` 是 gitignored、每 clone 一份 → 多 clone 各自重提；
  ② hub intake 的 `net-new` 只查目标路径是否已跟踪，从不比对 payload digest；③
  `lesson-classification` / `extract-skill` 写着"拿不准选 candidate-common"，无治理层判据。
- **消费者侧**：`ledger.list_hub_candidate_issues`（保留 number/state/title，`discover_uplinked_from_hub`
  成其投影）；`cmd_sweep` 改为**只要有 pending 就查 hub**（`_drop_pending_seen_on_hub`），hub 已有的
  digest 写回账本并跳过；无 pending 不发网络请求；无 `gh` / 离线退化为原行为。
- **hub 侧**：`maintainer/candidate_intake.py` 从 issue body 重算 digest（共享 parser），判
  `dup-of-rejected`（registry 精确 digest，含已 promote）/ `duplicate`（同 digest 的更小号 issue）/
  `revision`（同名、内容不同、原件仍 open）。重复件不给 `valid`/`auto-eligible`。**只打标签 + 评论，
  不自动关闭**（关闭超出已批规划，列为 Open Question 留给 owner）。失败一律 fail-open。
- **判据**：两问顺序制 —— Q1 charter（是否关于治理/harness 本身）否→`business`；Q2 通用性。拿不准
  Q1→`business`，仅拿不准 Q2→`candidate-common`。
- **文档**：`docs/core-manual.md` §11（sweep hub-check、intake 标签表、hub 必备标签）；
  `curate-candidate` 加"先合并重复"。repo 新建标签 `revision`。
- **验证**：recovery 20/20（+4）、sweep 22/22（+6）、intake 39/39（+14）、curate_gate 14/14、pytest
  160 passed、39 个 `tools/test_*.py` 脚本跑零失败；`upgrade` + `doctor` exit 0；wheel 干净。
  **回放**真实积压 #138–#147 body：#143 #145 → duplicate of #140；#144 #146 → duplicate of #141；
  #142 → revision of #141；其余 new —— 与人工判定一致。intake 的线上实证要等下一个真实 candidate。
- **bump**：0.43.0 → 0.43.1。**未发布**（core-A3 待人工确认）；消费者要升级后 sweep 侧才生效，hub
  侧 intake 随 push 到 master 即生效。
- **layer-2 例程实况**（`RemoteTrigger list`）：`gc-curation-routine`（`trig_01UjyaQUt3fpdNGDiDqU3Smh`，
  cron `0 0 * * *`）存在但 `enabled: false`，`updated_at` 2026-06-02（创建当天即关）—— 这就是积压
  issue 无 `advised` 的原因。**未重新启用**（owner 决策）。`maintainer/curate_routine.md` 已同步：
  跳过 `duplicate`/`dup-of-rejected`；并注明 trigger 自带 prompt 副本，启用前须同步。

### 2026-10-09 — P-0126：candidate 积压清理 + promote 两个 guard 类 guide（0.43.0，未发布）

- **积压**：10 个 open candidate issue 实为 5 个独立 candidate（verify-guard ×4、gate-on-change ×3
  为消费者 sweep 重复提交）。处置：dup 关闭 #141 #143 #144 #145 #146；reject + advisory #138
  （engine-swap，通用工程）/ #147（arbitrage，业务领域）—— commit `492155d`。
- **promote**（P-0126）：`governance_core/skills/verify-guard-fires-in-its-target-context.md`（取 #142
  修订版）+ `gate-on-change-content-not-target-path.md`（#140）。learned→guide、workflow 原样、
  去消费者痕迹（"measured 2026-08-20" / "93 hits to 0" / sync-tool 措辞）；verify-guard 加一条
  user-global enforcing copy 的 Note。
- **登记**：`consumer_registry.json` 两条 `promoted`（`registry.record_candidate`，非 `promote`）；
  `rejected_registry.json` 加 3 条 digest-keyed "already promoted" advisory（`block_by_name: false` ——
  只挡 byte-identical 重提，放行真修订；#142 即 #141 的同日合法修订，name-block 会误杀）。
- **验证**：pytest `tools/` 160 passed；candidate sweep/recovery/reminder 16/16、16/16、7/7；
  maintainer intake 25/25、curate_gate 14/14；`upgrade` + `doctor` exit 0；wheel top-level 仅
  `governance_core*`、两 guide 在、无 `maintainer/`（`build/` 未清：danger-guard 挡 `rm -rf`，
  本次纯新增文件，stale cache 不影响结论）。
- **bump**：0.42.1 → 0.43.0。**未发布** —— GitHub Release → PyPI 待人工确认（core-A3）。
- **遗留（按积压规划续做）**：① intake payload-digest 去重 + sweep 每次查 hub + candidate-common
  判据（流水线 proposal）；② layer-2 策展例程自 07-20 起无 `advised` 标签，疑未在跑；③ #139
  handoff linkage 机制（needs-human，仅 brief 无代码）。
