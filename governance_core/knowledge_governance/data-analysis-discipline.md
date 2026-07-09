---
title: Data Analysis & Pipeline Validation Discipline
status: active
created: 2026-04-28
updated: 2026-06-24
owner: core
carrier_class: reference
tags: [governance, data-analysis, pipeline-validation, insights-driven]
---

# Data Analysis & Pipeline Discipline

Originally constitution Article 7.1 (Insights-driven additions). Migrated
here on 2026-04-28 — the constitution keeps the red line "禁止静默丢列 /
禁止四舍五入隐藏精度" + a pointer to this file.

Source: Claude Code Insights report (564 messages / 74 sessions) identified
the high-frequency friction points encoded below.

---

## 1. Data analysis completeness

When generating comparison tables or analysis results, you MUST:

1. Include **all** datasets (test AND OOS), no omission
2. Include **all** stocks, no silent filtering via `dropna`
3. Provide **precise** precision values (no rounding before display)
4. **Double-check** completeness before presenting

**Review standard**: when an analysis table contains "N/A", missing rows, or
abnormally few rows, you MUST explain why before presenting.

## 2. Data pipeline validation

Before modifying a data pipeline or feature set, you MUST:

1. Verify **all expected columns** exist in output CSV/DataFrame
2. Check whether config filtering **silently drops columns** (e.g., a
   config passing only a subset of features through)
3. Print the intermediate DataFrame shape and column names
4. Compare row count against expected total — > 5% deviation = data leak signal

**Forbidden**:
- ❌ Running analysis without verifying column count
- ❌ Training a model without checking `dropna` impact

## 3. Backend / API development

After adding or modifying an API endpoint, you MUST:

1. **Restart** the running server before testing
2. Verify the server is bound to the correct port
3. Confirm the new endpoint returns 200 with valid JSON schema

**Common errors**: not restarting → 404; port-binding conflicts → wasted
debug time.

---

## See also

- `/validate-pipeline` skill — codifies the column / dropna verification flow
- rules-agent `R3` — specific Dense audit data discipline (don't mix sparse
  event-sample sources into Dense lookback)
