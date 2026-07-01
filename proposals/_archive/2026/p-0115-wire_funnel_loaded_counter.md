---
id: P-0115
agent: core
status: implemented
created: 2026-07-01
approved_at: 2026-07-01
implemented_in: 2009e98
implemented_at: 2026-07-01
owner: core
---

# Proposal P-0115: Wire the skill-usage funnel 'loaded' counter to body-load (Read) - complete P-0113 WS-D (#122)

## Trigger

Issue #122 (governance-core internal, not a `candidate`): the skill-usage funnel's
`load` column is stuck at 0 for every learned/guide skill because they are consulted
by **reading the `.md` body** (Read tool), never through the Skill tool — the only
path the tracker instruments. Completes the funnel design's deferred WS-D (P-0113
Phase 4). Touches hook source + the skill discovery/tracking subsystem → classify
PROPOSAL_REQUIRED. Paired with the promoted #121 guide (policy↔instrument seam).

## Current State (read, not assumed)

- `governance_core/discovery/tracker.py:184-262`: `record_use` (path C, Skill-tool),
  `record_surfaced` (A, per-day deduped on `last_surfaced`), `record_triggered`
  (B, per-event). **No `record_loaded`; no `loaded_count`/`last_loaded`.** Schema-v2
  fields are lazy-migrated via `_int_field` (`tracker.py:84-93`).
- `governance_core/discovery/registry.py:552-566` `_emit_funnel`: the `load` column
  is `row["use_count"]` — 0 for learned/guide (they are Read, not Skill-tool loaded).
  `retire`/`slim` classification keys on this `load` value (`registry.py:558-568`).
- `governance_core/hooks/skill-usage-tracker.py`: PostToolUse **Skill** matcher only
  (`hooks_manifest.json:16`); fires `record_use`. No PostToolUse **Read** hook exists.
- `governance_core/runtime_import_audit.py:35-52`: `FAIL_OPEN_GC_IMPORTERS` — a new
  hook importing `governance_core` that is NOT listed makes `doctor` exit 9.
  `skill-usage-tracker.py` is already listed (line 40).
- `governance_core/tools/test_skill_funnel.py`: covers the P-0092 funnel; a `record_use`
  seeds the "star" (loaded) skill (line 227) — the load axis has no Read-based case.

## Scope

- `tracker.py`: ADD `record_loaded(name)` (per-day deduped, mirrors `record_surfaced`;
  distinct from `record_use`); extend `funnel_row` to return `loaded_count`/`last_loaded`.
- `registry.py` `_emit_funnel`: `load` column = `use_count + loaded_count` (both are
  body-load paths — see Alternatives); `last` falls back last_triggered → last_loaded
  → last_used.
- NEW hook `governance_core/hooks/skill-read-tracker.py` (PostToolUse, matcher `Read`).
- `hooks_manifest.json`: register the hook (installer regenerates settings).
- `runtime_import_audit.py`: add the hook to `FAIL_OPEN_GC_IMPORTERS`.
- `knowledge_governance/runtime-import-discipline.md`: add the discipline-table row.
- Tests (test_skill_funnel.py): `record_loaded` dedup + hook name-derivation + funnel
  counts a Read-loaded skill. Version bump; close #122.

## Design & Contract

### Interfaces, I/O & Realization
- `SkillTracker.record_loaded(name: str) -> None` (`tracker.py`): INPUT skill name.
  MUTATES `.usage.json` `skills[name]`: `loaded_count += 1`, `last_loaded = today`,
  **per-day deduped** on `last_loaded` (mirrors `record_surfaced`); lazy-migrates both
  fields; atomic `_save`. Distinct from `record_use` so Read-consults never conflate
  with Skill-tool command loads. Realizer: the tracker module.
- `SkillTracker.funnel_row(name)`: extended to add `loaded_count` + `last_loaded`
  (existing keys unchanged — backward-compatible).
- `registry._emit_funnel` (`--funnel` CLI): `load` value = `use_count + loaded_count`.
  Realizer: `python -m governance_core.discovery.registry --funnel`.
- NEW hook `skill-read-tracker.py` (PostToolUse / matcher `Read`): INPUT the PostToolUse
  JSON on stdin (`tool_name`, `tool_input.file_path`). When `tool_name == "Read"` and
  `file_path` is under `.claude/skills/**` ending `.md` (excluding `README`/`_template`),
  derives `name = basename stem` → `record_loaded(name)`. Non-blocking, silent-on-failure,
  `exit 0` — same contract as `skill-usage-tracker.py`. Realizer of the Read→loaded path.
- Manifest wiring (`hooks_manifest.json`): `"skill-read-tracker.py": {"event":
  "PostToolUse", "matcher": "Read"}`. Realizer that auto-registers the matcher:
  `installer.py` regenerates `.claude/settings.local.json` from the manifest (P-0067).
- Import classification (`runtime_import_audit.py`): add `skill-read-tracker.py` to
  `FAIL_OPEN_GC_IMPORTERS` (guarded import, fails open) — else `doctor` exits 9.

### Field Dictionary
| field | type | meaning | producer | consumer | constraints |
|-------|------|---------|----------|----------|-------------|
| `loaded_count` | int | days the skill's `.md` body was Read | `record_loaded` | `_emit_funnel` load col | per-day deduped; lazy-migrated; ≥0 |
| `last_loaded` | ISO date str | last day the body was Read | `record_loaded` | dedup gate + funnel `last` | `YYYY-MM-DD` |

Governing store: the tracker's per-agent `.usage.json` schema — **not** a `contracts/`
file, consistent with the existing `surfaced_count`/`triggered_count` (P-0092) which
are also per-agent runtime state, not cross-agent contract fields.

### Flow
agent Reads a skill `.md` → PostToolUse `Read` event → `skill-read-tracker.py` →
`SkillTracker.record_loaded(stem)` → `.usage.json` (`loaded_count++`, per-day dedup)
→ `registry --funnel` reads `loaded_count` → `load = use_count + loaded_count` →
retire/slim classification.

## Non-Goals

- **No intent classification in v1** (per issue design decision): a Read of a learned
  skill may be curation (extract-skill validation, tier audit), not consultation; v1
  counts it anyway. Curation reads concentrate in the core/curator role, largely
  out-of-scope of the business-cluster funnel consumer; per-day dedup + the funnel's
  proxy-not-causal contract absorb residual noise. A downstream revisit is tracked if
  residual noise degrades the signal once data accrues.
- **No `sync_infra` `CENTRAL_HOOKS` entry** (`sync_infra.py:260-268`): that is the
  multi-clone central-reference distribution, N/A for the single-agent hub; the hook
  ships per-install like the majority of hooks. A multi-clone consumer's sync config
  is theirs.
- No change to `record_use` semantics (Skill-tool command loads keep `use_count`).
- No auto-retire threshold — the funnel stays proxy-not-causal, human-interpreted.

## Open Questions

- `load = use_count + loaded_count` (sum) vs the issue's literal `loaded_count`-only.
  **Resolved: sum** (see Alternatives) — no regression on Skill-tool-loaded guides.

## Alternatives & Rationale

- **Reuse `record_use`** — rejected (issue): conflates Read-consults with Skill-tool
  command loads, corrupting existing command-skill semantics.
- **Intent-filter in the hook** — rejected (issue): fragile from a stateless
  PostToolUse hook; deferred to the downstream revisit.
- **`load = loaded_count` only (issue's literal spec)** vs **`use_count + loaded_count`
  (chosen)**: guides ARE loadable via the Skill tool (tier-C, `skill-injection-tiers`),
  so `use_count` is a real body-load signal for them; reading `loaded_count` alone would
  silently drop it — a regression. Summing surfaces the previously-invisible Read path
  AND keeps the Skill path; the two counters are disjoint event sources, so no
  double-count. This refines the issue spec; the intent (surface the Read path) is met.

## Guardrails

- `edit-write-guard`: all edits under `governance_core/` package source, not the
  constitution trio — allowed.
- `runtime_import_audit` (doctor exit 9): the new gc-importing hook MUST be classified
  in `FAIL_OPEN_GC_IMPORTERS` — in scope.
- Package isolation (Art.11.4): new hook is a `.py` under `governance_core/hooks/`
  (already globbed); wheel-content check confirms inclusion + no `maintainer/` leak.
- The hook itself is non-blocking (`exit 0` always) — cannot freeze a Read.

## Phases

### Phase 1: Implement counter + hook + wiring + tests

- Deliverables:
  - `record_loaded` + `funnel_row` extension; `_emit_funnel` load = use+loaded.
  - `skill-read-tracker.py`; manifest entry; `FAIL_OPEN_GC_IMPORTERS` entry;
    discipline-doc row.
  - New test cases; version bump; #122 closed.
- Validation:
  - `test_skill_funnel.py` + touched suites green; new cases pass.
  - Drive a synthetic PostToolUse `Read` event through the hook (subprocess) →
    `loaded_count` increments; a non-skill Read is a no-op.
  - `upgrade` + `doctor` exit 0 (hook registered, not exit 9).
  - `registry --funnel`: a Read-consulted skill shows `load > 0`, out of retire/slim.
  - Wheel isolation: top-level `governance_core*` only, new hook present, no `maintainer/`.
- Exit criteria: all validation green; #122 closed.

## Approval Criteria

- [ ] `record_loaded` per-day deduped, distinct from `record_use`, lazy-migrates
      `loaded_count`/`last_loaded`.
- [ ] New hook fails open (exit 0), fires only on Read of `.claude/skills/**/*.md`.
- [ ] Hook in `hooks_manifest.json` + `FAIL_OPEN_GC_IMPORTERS` → `doctor` exit 0 (not 9).
- [ ] Funnel `load` = `use_count + loaded_count`; retire/slim classification honors it.
- [ ] Field Dictionary entries name their governing store (per-agent `.usage.json`, N/A
      for `contracts/` — consistent with P-0092).
- [ ] Tests: `record_loaded` dedup + hook name-derivation + funnel counts a Read-load.
- [ ] Open Questions resolved (sum); cross-link #121 recorded.

## Validation Plan

1. `python tools/test_skill_funnel.py` (after `upgrade`) + `test_candidate_recovery.py` green.
2. Subprocess-drive a `Read` PostToolUse JSON into the hook → assert `loaded_count++`;
   a non-skill path → no-op.
3. `governance-core upgrade --project-root .` then `governance-core doctor` → exit 0.
4. `python -m governance_core.discovery.registry --funnel` → Read-loaded skill load>0.
5. `python -m build --wheel` → top-level `governance_core*` only, hook present, no `maintainer/`.

## Rollback / Recovery

Drop the `Read` matcher from `hooks_manifest.json`, remove `record_loaded` + the hook
file + the `FAIL_OPEN_GC_IMPORTERS` entry, and revert `_emit_funnel` to `use_count`.
Counter is additive and non-blocking; the hook is silent — pure measurement, no
functional risk.

## Risks

- **Meta-read noise** (medium, accepted v1): curation reads counted as loads; mitigated
  by per-day dedup + curator-role concentration + proxy-not-causal contract; downstream
  revisit tracked.
- **Per-Read overhead** (low): the hook is a stdin-parse + early-exit on non-skill
  paths; only a `.claude/skills` `.md` triggers the guarded `governance_core` import.

## State Log

- 2026-07-01: draft created by core agent (P-0115)
- 2026-07-01: draft → pending (submit for review: wire funnel loaded-counter (#122))
- 2026-07-01: pending → approved (user approval: 批准实施(含 sum refinement) (AskUserQuestion 2026-07-01))
- 2026-07-01: approved → implemented
