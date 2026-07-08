---
title: Skill reuse tiers + scenario-cluster index
status: active
created: 2026-06-16
updated: 2026-07-08
owner: core
tags: [governance, skills, discovery, session-injection, reuse-classification, p-0103, p-0118]
---

TL;DR — `knowledge/skills/_scenario_clusters.json` is a **consumer-authored**
index that groups learned/guide skills into named **scenario clusters**. The
gc SessionStart hook reads it to inject a compact `cluster → members` map so an
agent can self-select and load the right cluster when it enters that scenario.
gc ships this **schema + the reader**; the data is owned per-clone (issue #100,
P-0103 part A).

## Why a `scenario` dimension

The **breadth** dimension (the per-skill `theme:` frontmatter field: universal /
core-only / <agent> — see "Reuse / breadth" below) answers *"how widely does this
skill apply?"*. The **scenario** dimension is orthogonal and answers *"which
task-shaped situation makes this skill relevant?"*. SessionStart injects:

- the **universal** skills (every `learned` skill + every guide with
  `theme: universal`; P-0118 derives this from `theme`, retiring the central
  `_tiers.json`) as `name + 1-line desc`, every session, bounded (≤ the injector's
  universal limit), and
- the **scenario-cluster map** from this file (cluster id → member names);
  cluster **bodies stay lazy** (loaded via the Skill tool on demand).

This re-balances `prefix_cost_optimization.md` C3 (counts-only) without
re-introducing the full manifest dump: only names + a compact map are
surfaced, bodies remain lazy. When neither index is authored (e.g. a hub with
0 learned skills) the hook falls back to the counts-only summary.

## Reuse / breadth: the `theme` field (P-0118)

**Orthogonal to scenario.** "How widely does this skill apply?" is answered by the
**pre-existing per-skill `theme:` frontmatter field** — `sync_infra`'s cross-clone
routing field — NOT a new field. P-0118's finding: gc already had a gc-native,
per-skill, frontmatter breadth field (`theme`); the central
`knowledge/skills/_tiers.json` was a *second, overlapping* breadth axis. So P-0118
retires `_tiers.json` authoring and derives injection / index from `theme`, rather
than inventing a third term.

### The field (owned by sync_infra, now also read by injection)

```yaml
# on .claude/{commands,agents,skills}/*.md frontmatter; enforced by sync_infra
theme: universal
```

| value | routing (sync_infra) | injection / index (P-0118) |
|-------|----------------------|-----------------------------|
| `universal` | copied to every clone | in the SessionStart always-inject pool + "universal" index group |
| `core-only` | stays only in core | not every-session; reachable via a scenario cluster |
| `<agent>` (e.g. `trade`) | copied only to that clone | that agent's index group; not in the universal pool |

`learned` skills (`.claude/skills/learned/`) carry **no** `theme` — they are per-agent
session extractions, deliberately excluded from `sync_infra` routing. For injection
they are always treated as the owning agent's own universal set (every learned skill
is in the pool).

### Injection derivation

`registry.emit_bounded_injection` builds the SessionStart always-inject pool as **every
`learned` skill + every `guide` with `theme == "universal"`**, ordered by
`(score desc, name)` and capped at `_UNIVERSAL_INJECTION_LIMIT`. It no longer reads
`knowledge/skills/_tiers.json`; a lingering `_tiers.json` in a mid-migration repo is
ignored. `theme: core-only` / `theme: <agent>` skills reach the surface via a scenario
cluster (below), not the every-session pool.

### Why `theme`, not a new `reuse` field

`theme` already carries the routing-critical agent identity (`theme: trade` vs
`theme: rules`); collapsing that into a coarse `reuse: business` would lose it, and
adding a *parallel* `reuse` field would be a fifth breadth axis — the exact
axis-proliferation this consolidation removes. `theme` is enforced on every shared
skill already, so injection / index derive from it with zero new vocabulary and zero
backfill.

## Schema (scenario clusters)

```json
{
  "schema": 1,
  "clusters": {
    "<cluster-id>": {
      "description": "<one line: the scenario this cluster serves>",
      "members": ["<skill-name>", "<skill-name>"]
    }
  }
}
```

- `<cluster-id>` — kebab-case scenario name (e.g. `release-pipeline`,
  `incident-triage`). Keep clusters **few and domain-shaped** (a scenario the
  agent enters), not one-per-skill — the map is injected every session.
- `members` — skill names as they appear in the registry (the `.md` stem under
  `.claude/skills/` or `.claude/skills/learned/`).
- `description` — one line; rendered next to the cluster id in the map.

## Ownership

Membership is **consumer-authored** and lives in the gitignored
`knowledge/skills/` install region — gc never ships a `_scenario_clusters.json`
(doing so would clobber a consumer's file on `upgrade`). gc ships only this
contract and the reader (`governance_core.discovery.registry.emit_bounded_injection`).
Universal/hub-shaped clusters belong in each clone's own file; the examples
above are a template, not a shipped seed. Authoring is wired into
`/extract-skill` (P-0103 part C: each new skill is categorized
`universal | scenario:X`).

## Consumed by

- `governance_core/hooks/session-context.py::_emit_skill_injection` — emits the
  bounded menu, falling back to counts-only when this file (and `_tiers.json`)
  are absent.
- `governance_core/discovery/registry.py::emit_bounded_injection` — the reader;
  records path-A surfacing via the usage funnel (`record_surfaced`).
