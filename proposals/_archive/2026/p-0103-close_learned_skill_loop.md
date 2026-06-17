---
id: P-0103
agent: core
status: implemented
created: 2026-06-16
approved_at: 2026-06-16
started_at: 2026-06-16
implemented_in: 6674f66
implemented_at: 2026-06-17
owner: core
---

# Proposal P-0103: Close the learned-skill discover->consult->apply loop: universal names + scenario-cluster injection + funnel (#100)

## Trigger

GitHub issue #100 (reporter: consumer trade-agent). Across all 5 agent clones,
**0 of ~50 learned skills are ever applied** (`use_count=0`). Root cause is a
genuine **discovery regression** in gc's own SessionStart hook, verified live
in this session (the SessionStart banner is literally `[Skills (L0)] 0 learned
+ 16 guides discovered`):

- `session-context.py::_emit_skill_injection` emits a **counts-only** summary
  (no skill names) since `prefix_cost_optimization.md` C3 (approved
  2026-05-07, to cut a ~1650-token SessionStart prefix). The agent cannot
  consult what it cannot see.
- `record_surfaced` exists in `tracker.py` (schema-v2 funnel) and a
  names-emitting injector exists in `registry.py`, but the LIVE hook
  (`_emit_skill_injection`) calls neither — so the funnel's "surfaced" arm is
  always 0, unmeasurable.
- No standing directive tells the agent to consult skills before re-deriving.

The consumer offers trade-agent's P-0113 prototype for generalization into gc
(A/B/C/D below); the local graft + a consumer constitution clause are removed
in favor of the gc-native version once shipped.

**Proposal governance applies (PROPOSAL_REQUIRED)**: touches a SessionStart
hook + the skill-discovery/registry/extract-skill system + the funnel;
multi-phase; and **re-balances an already-approved optimization** (C3) — so
this is a deliberate trade-off revisit, not a pure bug fix. (User chose the
full A/B/C/D scope.)

> **Key grounding (read before drafting, per recall):** most machinery already
> exists — the fix is largely **wiring + a new scenario index + bounding**,
> not greenfield. `tracker.py` already has `record_surfaced` /
> `record_triggered` / `record_use` / `funnel_row`. `registry.py` already has
> a names-emitting injector that calls `record_surfaced` and
> `manifest_for_injection(source_types)`. `knowledge/skills/_tiers.json` (P-0043
> reuse-tier universal/project/branch) + `audit_knowledge.py` Check 11 (tier
> bijection coverage gate) already exist; the new `scenario` dimension is
> orthogonal and mirrors them.

## Scope

Close the **discover → consult → apply** loop with four coordinated parts,
preserving the C3 token budget:

- **A (discover)** — rewire `session-context.py::_emit_skill_injection` to emit,
  within a bounded budget: (i) **universal-tier** skills as `name + 1-line
  desc` (the `universal` set already in `_tiers.json`, via
  `manifest_for_injection`), and (ii) a compact **scenario-cluster MAP**
  (`cluster → member names`) from a new gc-schema
  `knowledge/skills/_scenario_clusters.json`; cluster bodies stay lazy (Skill
  tool). Reuse `registry.py`'s existing names-emitter (bounded) so the live
  path also calls `record_surfaced`. **Fallback to counts-only** when no
  `_tiers`/`_scenario_clusters` are authored (the hub's own 0-skill case).
- **B (consult)** — ship a gc-native, domain-neutral consult-directive ("at
  task start, consult the surfaced skills/clusters; load the relevant one
  rather than re-deriving") as a clause / agent-template line, so every
  consumer inherits it via `upgrade`.
- **C (register-enforce)** — extend `extract-skill` to require a `scenario`
  categorization (`universal | scenario:X`) and add a **coverage gate**
  (a scenario-bijection audit mirroring Check 11's tier bijection) so a new
  skill must enter the surface — closing the "author forgets to register"
  recurrence.
- **D (measure)** — `record_surfaced` on the live path (lands with A) + surface
  the deferred P-0084 Phase 2 funnel counters (surfaced/triggered/loaded) via
  a `--funnel` view; turns surfaced=0 into a measurable signal.

The `scenario` dimension is **orthogonal** to the P-0043 reuse-tier; universal
+ hub/core clusters ship as gc seeds, and **each consumer authors its own
scenario clusters** in its own clone (ownership-scoped).

## Non-Goals

- **Not** reverting C3 / dumping the full ~55-line manifest. The new injection
  stays bounded (universal `name+desc` ≤ N; cluster map = cluster + member
  names only; all bodies lazy). The token-budget rationale is preserved, just
  re-balanced.
- **Not** automating skill **retirement** — the funnel stays a human-gated
  proxy (per P-0084); D only measures.
- **Not** replacing the keyword router (path B `record_triggered`) — it stays
  as a supplement to the LLM self-selecting a cluster.
- **Not** authoring consumers' domain scenario clusters — gc ships the schema,
  the universal set, and hub/core seeds only.
- **Not** changing the P-0043 reuse-tier semantics.

## Guardrails

- **edit-write-guard**: edits to `governance_core/hooks/session-context.py`,
  `governance_core/discovery/{registry,tracker}.py`,
  `governance_core/commands/extract-skill.md`, a new schema doc, and
  (B) possibly a clause. If B is implemented as a **constitution clause**, it
  routes through `/iterate-constitution` (Art.13) — see Phase 0.
- **command-guard / boundary-guard**: `upgrade`, tests, build — in-repo only.
- **Art.11**: edit package source; `upgrade --project-root .` to dogfood.

## Phases

### Phase 0: Governance bootstrap

- Deliverables: this design approved. Decide B's carrier: a gc agent-template /
  skill-directive (no constitution change) vs a constitutional clause. If the
  latter, the clause edit runs via `/iterate-constitution` (its own gate).
- Validation: `submit` → user `approve`; B-carrier decision recorded.
- Exit criteria: status `approved`; B carrier chosen.

### Phase 1: A + live record_surfaced — bounded names + cluster map

- Deliverables: `_emit_skill_injection` emits bounded universal `name+desc` +
  a scenario-cluster map, reusing `registry`'s names-emitter (which calls
  `record_surfaced`); new `knowledge/skills/_scenario_clusters.json` gc schema
  + a hub/core seed; counts-only fallback when unauthored.
- Validation: unit tests with synthetic `_tiers`/`_scenario_clusters` fixtures
  (the hub has 0 learned skills — symptom not hub-dogfoodable, per
  `hub-cannot-dogfood-crlf-drift`); assert the emitted prefix stays within a
  declared token/line bound; assert `record_surfaced` is invoked.
- Exit criteria: SessionStart surfaces names + cluster map within budget; the
  surfaced arm is live.

### Phase 2: D — funnel surfacing

- Deliverables: revive the deferred P-0084 Phase 2 counters
  (surfaced/triggered/loaded) and a `--funnel` view over `funnel_row`.
- Validation: funnel view shows non-zero surfaced after a SessionStart; tests.
- Exit criteria: the loop is measurable end-to-end.

### Phase 3: B — consult-directive

- Deliverables: ship the domain-neutral consult-directive per the Phase 0
  carrier decision (agent-template line or, via `/iterate-constitution`, a
  clause).
- Validation: a fresh consumer `upgrade` materializes the directive.
- Exit criteria: every consumer inherits "consult before re-deriving".

### Phase 4: C — register-enforce + coverage gate

- Deliverables: `extract-skill` requires `universal | scenario:X`; a
  scenario-bijection audit (mirroring Check 11) FAILs on an uncategorized
  md-skill.
- Validation: audit FAILs a deliberately-uncategorized fixture skill; passes
  when categorized.
- Exit criteria: a new skill cannot silently miss the surface.

### Phase 5: Dogfood + release

- Deliverables: `upgrade --project-root .`; full hook + discovery + audit test
  suites; wheel check; STATE.md before the phase commit; version bump; close
  #100.
- Validation: all suites green; wheel clean; `doctor` exit 0.
- Exit criteria: implemented + #100 closed; release (human-approved outward).

## Approval Criteria

- Reviewer agrees re-balancing C3 is warranted (0/50 applied) and the new
  injection stays bounded (the design must state the concrete budget: universal
  ≤ N name+desc lines + a compact cluster map, bodies lazy).
- Reviewer agrees to reuse existing machinery (registry names-emitter +
  `record_surfaced` + tracker funnel + `_tiers.json` + Check-11-style gate)
  rather than rebuild.
- Reviewer agrees the `scenario` dimension is orthogonal to the reuse-tier and
  consumer-owned (gc ships schema + universal + hub seeds only).
- Reviewer picks B's carrier (agent-template vs constitution clause).

## Validation Plan

- Phase 1: fixture-driven unit tests for `_emit_skill_injection` (universal
  names+desc rendered; cluster map rendered; counts-only fallback when
  unauthored; emitted size within the declared bound; `record_surfaced`
  called). Drive via subprocess (memory `hook-stdout-rebind-breaks-inprocess-import`).
- Phase 2: `--funnel` shows surfaced>0 post-SessionStart on a fixture.
- Phase 4: scenario-bijection audit FAIL/PASS on categorized vs not.
- Phase 5: script-style + `pytest tools/`; `upgrade` + `doctor` exit 0; wheel
  top-level `governance_core*`, includes the new schema, no maintainer leak.

## Rollback / Recovery

- Per phase: each is a package-source change reversible by `git revert` +
  `upgrade --project-root .`. The counts-only fallback means a bad
  `_scenario_clusters.json` degrades gracefully (no names, just counts) rather
  than breaking SessionStart.
- B (clause/template) is additive text; removing it drops the directive only.
- No data migration; funnel counters are diagnostic state (gitignored cache).

## Risks

- **Token-budget regression** (med prob, high impact): the whole point of C3
  was prefix cost. Mitigation: hard bound on universal count + compact map +
  lazy bodies; a test asserting the emitted prefix size ceiling; counts-only
  fallback.
- **Hub can't dogfood the symptom** (high prob, low impact): hub has 0 learned
  skills. Mitigation: fixture-driven unit tests + ship seeds; the real
  validation is a consumer `upgrade` (out-of-band, by trade-agent).
- **Scope creep across A/B/C/D** (med): four parts. Mitigation: phased; A+D
  (Phases 1-2) close the loop minimally, B/C (Phases 3-4) harden — each phase
  independently shippable; could split into follow-up proposals if review prefers.
- **Ownership leakage** (low): a consumer's domain clusters must not ship from
  gc. Mitigation: gc ships only universal + hub/core seeds; the schema doc
  states cluster membership is per-owner.
- **Coverage-gate false-positives on library skills** (low): Check 11 already
  excludes library code (not workflows); the scenario gate inherits that
  carve-out.

## State Log

- 2026-06-16: draft created by core agent (P-0103)
- 2026-06-16: draft → pending (submit for review: close learned-skill loop A/B/C/D (#100))
- 2026-06-16: pending → approved (user approval: 批准. Decisions: (1) re-balancing C3 endorsed; (2) B carrier = constitution clause via /iterate-constitution (Phase 3).)
- 2026-06-16: approved → in-progress (begin Phase 1: A + live record_surfaced wiring + scenario-cluster schema)
- 2026-06-17: in-progress → implemented
