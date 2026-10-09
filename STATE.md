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
