---
title: Dense Audit Data Source Discipline
status: active
created: 2026-04-28
updated: 2026-05-06
owner: rules
briefing: serendipity
tags: [methodology, dense-audit, lookback, event-samples, data-source]
related: [knowledge/methodology/known_pitfalls.md]
---

# Dense Audit Data Source Discipline

Migrated from `constitution/agent.md` R3 on 2026-04-28 per
`proposals/migrate_agent_md_historical_lessons_to_governance.md`.

Rules R3.1-R3.4 (red lines) stay in rules-agent agent.md; the *why*
(the 2026-04-20 cross-year mismatch that motivated them) lives here.

---

## The two-source rule

Dense Test audit / fill-in / analysis tasks need **historical lookback**
data (rolling windows, realized metrics, past-N-day statistics for
`(code, trade_date)` pairs). The data source rule:

| Scenario | Allowed sources | Forbidden |
|----------|-----------------|-----------|
| **Event sampling** (training reconstruction, event diagnosis) | `event_samples.csv`, snapshot's event-triggered artifacts | — |
| **Dense audit lookback** (rolling features, realized metrics, past-N statistics) | continuous raw klines (K_DAY or K_60M, full Futu pull); OOS base cache (continuous); `full_features.csv` (continuous) | `event_samples.csv` (sparse), `model_pre_hourly.csv` (event-triggered), any subset filtered by event/rule/votes |

The two scenarios look similar but have **incompatible row densities**.
Mixing them produces wrong answers.

## Why — 2026-04-20 cross-year mismatch incident

A Dense audit script merged `event_samples.csv` (~1 row/month per stock)
with the OOS K_60M cache (continuous). The audit then computed `past_60d`
features using **positional 60-bar lookback** (i.e., "the 60th row before
this one in the merged table").

For dense rows in mid-2025, the positional 60-bar lookback walked
backwards into the **2023 sparse event_samples** rows because the merged
table was sparse for early periods.

**Concrete failure**: HK.09999 @ 2025/7/15, `past_60td_maxdev` was 0.82.
True value (computed from continuous klines) was ~0.12. **6× inflated.**
Other stocks in the same audit hit max values up to 4.8 — a clear outlier
signature, but not detected until the user pointed it out.

The script had merged sparse + continuous without checking each stock's
trade_date continuity. Positional N-back lookback is meaningless when the
underlying timeline has gaps.

## What R3 enforces

- **R3.1**: explicit two-source separation table — no scenario crossover
- **R3.2**: standard procedure for fetching Dense lookback klines
  (compute earliest needed date with 1.5× factor + 30d slack, check
  continuous caches first, fall back to Futu raw pull)
- **R3.3**: Futu API rules — universe and date range derived from
  `dense_predictions.csv` (no hardcoding); single fetch failure must NOT
  fall back to sparse sources
- **R3.4**: review checks — outlier detection, continuity verification,
  module docstring must declare "non-event-sample source"

## See also

- `feedback_dense_audit_raw_klines.md` (memory) — the operational hook
- `knowledge/methodology/known_pitfalls.md` — broader pitfalls index
- `rules/strangle/_fetch_dense_lookback_klines.py` — the canonical
  implementation
