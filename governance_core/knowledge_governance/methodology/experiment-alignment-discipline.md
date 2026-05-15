---
title: Experiment Alignment Discipline (env / calendar / baseline / OOS)
status: active
created: 2026-04-28
updated: 2026-04-28
owner: rules
tags: [methodology, experiment-alignment, baseline-reproduction, oos]
related: [knowledge/methodology/experiment_protocol.md]
---

# Experiment Alignment Discipline

> **Example content disclaimer**: The specific examples in this document (stock symbols, pipeline names like Strangle/S50, Futu OpenAPI references, etc.) are drawn from the Trade Agent project where governance-core was first developed. The patterns and principles are project-agnostic; downstream projects should substitute their own domain examples when applying the principles described here.


Migrated from `constitution/agent.md` R2 on 2026-04-28 per
`proposals/migrate_agent_md_historical_lessons_to_governance.md`.

Rules R2.1-R2.5 (red lines) stay in rules-agent agent.md; the *why* (the
incidents that proved each rule's necessity) lives here.

---

## Why this discipline exists — 2026-03-30 lessons table

| Lesson | Date | Root cause | Impact |
|--------|------|-----------|--------|
| Experiment env mismatch produced phantom AUCPR gains | 2026-03-30 | `extract_trading_dates` used full_features calendar (719 dates) instead of event calendar (420 dates), yielding 13 windows where the production model had 5 | S30 new feature appeared +6.3% AUCPR; was actually baseline collapsing under more windows. After alignment, the gain was zero |
| OOS using hourly K_60M data inflated signal counts | 2026-03-30 | `oos_base_data` was K_60M granularity (~5 bars/stock/day), not aggregated to daily | Hybrid signal count was 5× inflated, precision diluted |
| Dense test contradicted event-sampled conclusions | 2026-03-30 | Event-sampled set was only 345 rows (20-day cooldown) — high statistical noise | S50 new feature looked good on event-sampled, was indistinguishable on dense test |
| Val→Test gap masked overfitting | 2026-03-30 | 13-window small-sample regime inflated val→test gap from 12% to 31% — the "improvement" was baseline degrading more, not new feature winning | Same feature was invalid in 5-window regime (gap 12%) but appeared valid in 13-window regime (gap 31%) |

These four lessons collectively forced the four R2 rules:

- R2.1 → environment alignment + production-config extraction (don't
  trust live config — extract `training_results.json` from artifact)
- R2.2 → Dense Test as primary metric, event-sampled as auxiliary only
- R2.3 → OOS at daily-level, fixed 63-stock pool, no hyper-tuning on OOS
- R2.5 → required reporting fields (per-stock AUCPR distribution etc.)

## What this means in practice

**Before any experiment**:
1. Extract production model's exact config from
   `artifacts/<pipeline>/production/*/training_results.json`
2. Identify calendar type (S30 = event calendar; S50 = full_features
   calendar) and monkey-patch `extract_trading_dates` if needed
3. Reproduce baseline AUCPR / auto_precision / signal count to within
   delta < 0.01 of production. If baseline doesn't reproduce, **stop**
   and root-cause before experimenting

**Evaluation hierarchy**:
- Primary: Dense Test precision (full_features.csv, daily-level)
- Auxiliary: Dense AUCPR, calibration monotonicity, hybrid tier precision
- Reference only: Event-sampled precision (statistical noise too high)
- Veto only: OOS — used for confirming/refusing, never selecting

**Reporting**:
- Must include per-stock AUCPR distribution (mean / median / P25 / P75)
- `prob_IQR_median` + `n_simpson_victims` — guards against pooled-vs-per-stock
  divergence (per `adr-per-stock-quality-gate.md`)

## See also

- `knowledge/decisions/adr-per-stock-quality-gate.md` — companion: gate
  enforcement at promotion
- `knowledge/methodology/experiment_protocol.md` — operational protocol
- `.claude/skills/validate-experiment-dense-vs-prod.md` — learned skill
  codifying the alignment + dense-vs-prod comparison flow
