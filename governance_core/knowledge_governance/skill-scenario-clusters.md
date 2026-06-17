---
title: Skill scenario-cluster index (_scenario_clusters.json)
status: active
created: 2026-06-16
updated: 2026-06-16
owner: core
tags: [governance, skills, discovery, session-injection, p-0103]
---

TL;DR — `knowledge/skills/_scenario_clusters.json` is a **consumer-authored**
index that groups learned/guide skills into named **scenario clusters**. The
gc SessionStart hook reads it to inject a compact `cluster → members` map so an
agent can self-select and load the right cluster when it enters that scenario.
gc ships this **schema + the reader**; the data is owned per-clone (issue #100,
P-0103 part A).

## Why a `scenario` dimension

The P-0043 **reuse-tier** (`_tiers.json`: universal / project / branch) answers
*"how widely reusable is this skill?"*. The **scenario** dimension is
orthogonal and answers *"which task-shaped situation makes this skill
relevant?"*. SessionStart injects:

- the **universal tier** (from `_tiers.json` `tiers.universal.skills`) as
  `name + 1-line desc`, every session, bounded (≤ the injector's universal
  limit), and
- the **scenario-cluster map** from this file (cluster id → member names);
  cluster **bodies stay lazy** (loaded via the Skill tool on demand).

This re-balances `prefix_cost_optimization.md` C3 (counts-only) without
re-introducing the full manifest dump: only names + a compact map are
surfaced, bodies remain lazy. When neither index is authored (e.g. a hub with
0 learned skills) the hook falls back to the counts-only summary.

## Schema

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
