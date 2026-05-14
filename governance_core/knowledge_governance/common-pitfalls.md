---
title: Common Pitfalls Reference (Living List)
status: active
created: 2026-04-28
updated: 2026-05-06
owner: core
tags: [governance, pitfalls, troubleshooting, reference]
---

# Common Pitfalls

Originally constitution Article 11. Migrated here on 2026-04-28 — this
list is a reference, not a red-line; agents grep when stuck rather than
needing it always-loaded.

The list grows over time. New entries can be added without a proposal —
the doc is operational reference, not governance.

---

## Futu API

- **Don't create Futu connections inside loops** — open once, reuse, close
  in `finally`. Connection setup is rate-limited and slow.
- **OpenD must be running** before any `import futu` — see Art.15 + `/futu-check`.

## Data quirks

- **`numpy` version compat** — use `np.trapz`, NOT `np.trapezoid` (1.26 deprecation).

## Caching gotchas

- After **modifying code**, clear `__pycache__/` before running tests
  (or use `find -name __pycache__ -exec rm -rf {} +`).
- Before loading **changed config**, call `clear_cache()` on the config
  loader — otherwise the previous load is reused and your edit looks
  ignored.

## Common config mistakes

- ❌ `kline_lookback_days` set in calendar days but feature requires N
  trading bars → use ~1.5× factor + 30d slack (see rules R1.2 SMIC incident).
- ❌ Hardcoded thresholds in code → must live in `config/` (Art.4).
- ❌ `.get(key, default)` for config → forbidden, must raise on missing.

## Multi-clone coordination

- Don't manually copy files across clones — `tools/sync_infra.py --execute`
  is the only sanctioned channel.
- Don't write `shared_state/positions/` from trade scope without filelock —
  see SMIC 2026-04-08 incident.
- knowledge/** writes from non-core require `/learn` skill or
  `experiment-manager` subagent (entry-point enforcement).

## Constitution drift

- Don't edit `CLAUDE.md` directly — it's regenerated from
  `constitution/total.md` + `constitution/agent.md` by
  `tools/regen_constitution.py`. Pre-commit hook blocks direct edits.
- Don't list skill names inside the constitution — the registry is the
  single source of truth, see `.claude/skills/skill-injection-tiers.md`.

---

Add an entry when you've burned > 30 minutes on something a one-line note
would have saved. Format: `- **One-line title** — explanation + workaround`.
