---
title: Strangle Pipeline Data Flow
status: active
created: 2026-04-28
updated: 2026-05-06
owner: core
tags: [governance, pipeline, strangle, data-flow]
---

# Strangle Pipeline Data Flow

Originally constitution Article 6. Migrated here on 2026-04-28 — the
constitution keeps the red line "agents 间通过 contracts 交换数据" + a
pointer to this file.

The legacy scorecard pipeline (`data/abc.xlsx` → rules legacy → trade)
was deprecated 2026-05-06 (see `proposals/deprecate_legacy_synergy_scorecard.md`)
and removed from this file.

---

## Strangle pipeline (current production path)

```
[Futu API K_60M]
    ↓ skills/analysis/indicator_skill.py
[Technical indicators]
    ↓ models/tests/test_strangle_data.py
[Event sampling + feature normalization] → artifacts/strangle/data/
    ↓ rules/strangle/train_stage1.py
[XGBoost model] → artifacts/strangle/stage1/
    ↓ rules/strangle/promote_model.py
[Production model] → artifacts/strangle/production/
    ↓ rules/strangle/generate_signals.py
[Signals] → artifacts/strangle/signals/{YYYYMMDD}/signals.jsonl
    ↓ contracts/strangle_signal_contract.md (format definition)
[Trade consumption] → artifacts/trade/{run_id}/
```

Two pipelines coexist (S30 + S50), share most stages but differ in:
- Stock pool (S50 excludes low-vol per `exclude_low_vol_threshold`)
- Hybrid 4-rule + tier vote in S50 (vs single auto_threshold in S30)
- Cross-pipeline resonance (S50 reads S30 signals to up-tier)

S50 promotion adds a **per-stock quality gate** (Simpson paradox defense,
see rules-agent R1.4).

## Cross-pipeline interaction

| From | To | Path | Contract |
|------|----|----- |----------|
| rules (strangle) → trade | `artifacts/strangle/signals/{YYYYMMDD}/signals.jsonl` | `contracts/strangle_signal_contract.md` |
| rules (strangle50) → trade | `artifacts/strangle50/signals/{YYYYMMDD}/signals.jsonl` | `contracts/strangle50_signal_contract.md` |
| rules → simu | `artifacts/strangle/` or `artifacts/rules/` | (same as above) |

---

## See also

- `contracts/` — every cross-agent boundary's format spec
- `knowledge/operations/rules-manual.md` — how to actually run signal generation
- `knowledge/operations/trade-manual.md` — how trade consumes signals
