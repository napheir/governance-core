---
title: Artifacts Output Layout
status: active
created: 2026-04-28
updated: 2026-06-24
owner: core
tags: [governance, artifacts, output-paths]
---

# Artifacts Output Layout

> **Example content disclaimer**: The specific examples in this document (domain terminology, pipeline names, external API references, stock or asset identifiers, etc.) are drawn from the upstream project where governance-core was first developed. The patterns and principles are project-agnostic; downstream projects should substitute their own domain examples when applying the principles described here.


Originally constitution Article 10. Migrated here on 2026-04-28 — the
constitution keeps the red line "artifacts/ 不进 git" + a pointer to this
file.

---

## Per-source output paths

| Source | Output path |
|--------|-------------|
| per-agent (by variant / experiment) | `artifacts/<agent>/{stage}/{exp_name}/` |
| per-agent (by run) | `artifacts/<agent>/{run_name}/` |
| per-task | `artifacts/<task>/{task_name}/` |
| tests | `artifacts/tests/` |
| knowledge (shared dashboard) | `<install-root>/shared_state/knowledge/` (NOT in artifacts/) |

## Naming conventions

- `{exp_name}` — short kebab-case, e.g., `w150_hybrid`, `o2_baseline`
- `{run_id}` / `{run_name}` — timestamp-prefixed, e.g., `20260428_143022_baseline`
- `{stage}` — one of: `data` / `stage1` / `stage2` / `production` / `signals` / `oos_validation`
- `{task_name}` — kebab-case task description

## Datasets registry layer (optional, per consumer pipeline)

For long-lived datasets under `artifacts/{pipeline}/datasets/**`, a consumer may
route writes through a dataset-registry module (e.g.
`<consumer>.<pipeline>.dataset_registry.DatasetRegistry`) enforced by
`edit-write-guard.py`, so vintage + lineage + supersedes-chain are stamped
automatically.

## Why artifacts/ is gitignored (Art.9)

- Reproducible from source + config (input determinism)
- Large binary content would bloat repo
- Per-agent isolated runs would create constant merge conflicts

The exception is `<install-root>/shared_state/knowledge/dashboard.html`,
which lives **outside any clone** in shared runtime state — gitignored at
its physical location, single physical copy across all clones.

---

## See also

- `.gitignore` — enforces the "no commit" rule
