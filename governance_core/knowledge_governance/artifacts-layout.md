---
title: Artifacts Output Layout
status: active
created: 2026-04-28
updated: 2026-04-28
owner: core
tags: [governance, artifacts, output-paths]
---

# Artifacts Output Layout

Originally constitution Article 10. Migrated here on 2026-04-28 — the
constitution keeps the red line "artifacts/ 不进 git" + a pointer to this
file.

---

## Per-source output paths

| Source | Output path |
|--------|-------------|
| rules (strangle) | `artifacts/strangle/{stage}/{exp_name}/` |
| rules (strangle50) | `artifacts/strangle50/{stage}/{exp_name}/` |
| rules (legacy) | `artifacts/rules/{run_name}/` |
| trade | `artifacts/trade/{YYYYMMDD_HHMMSS}/` |
| data | `artifacts/data/{task_name}/` |
| simu | `artifacts/simu/{run_name}/` |
| research | `artifacts/research/{task_name}/` |
| tests | `artifacts/tests/` |
| knowledge (shared dashboard) | `<install-root>/shared_state/knowledge/` (NOT in artifacts/) |

## Naming conventions

- `{exp_name}` — short kebab-case, e.g., `w150_hybrid`, `o2_baseline`
- `{run_id}` / `{run_name}` — timestamp-prefixed, e.g., `20260428_143022_baseline`
- `{stage}` — one of: `data` / `stage1` / `stage2` / `production` / `signals` / `oos_validation`
- `{task_name}` — kebab-case task description

## Datasets registry layer (rules pipeline)

For long-lived datasets under `artifacts/{pipeline}/datasets/**`, write goes
through `rules.strangle.dataset_registry.DatasetRegistry` (enforced by
`edit-write-guard.py` Layer 4). Vintage + lineage + supersedes-chain are
stamped automatically; see `proposals/dataset_registry_and_unified_artifacts_layout.md`.

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
- `knowledge/governance/data-flow.md` — what each pipeline produces under these paths
- `proposals/dataset_registry_and_unified_artifacts_layout.md` — datasets/ subtree governance
