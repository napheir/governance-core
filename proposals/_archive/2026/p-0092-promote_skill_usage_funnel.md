---
id: P-0092
agent: core
status: implemented
created: 2026-06-02
approved_at: 2026-06-02
implemented_in: 7e5835b
implemented_at: 2026-06-02
owner: core
---

# Proposal P-0092: promote skill-usage funnel counters (gc #25)

## Trigger

Curation of GitHub candidate **#25** (`mechanism`, from trade-agent): a
skill-usage **funnel** — Surfaced (path A) / Triggered (path B) / Loaded
(path C). Proposal governance applies because the change touches the skill
**discovery system** (tracker + registry) and a **shipped hook source**
(`prompt-context-router.py`), and adds a capability that ships to all
consumers via `upgrade` (classify → PROPOSAL_REQUIRED).

## Scope

Promote the candidate's verified design into `governance_core/`:

- `discovery/tracker.py`: atomic `_save()` (tmp + `os.replace`); two new
  recorders — `record_surfaced(names)` (path A, per-day deduped) and
  `record_triggered(name)` (path B, per-event, counts dedup-suppressed
  re-matches); a `funnel_row(name)` public accessor; schema v2 fields
  (`surfaced_count` / `triggered_count` / `last_*`) lazy-migrated.
- `hooks/prompt-context-router.py`: `_match_routes` records the trigger
  **before** the dedup gate (relevance ≠ injection-output), via a best-effort
  `_make_trigger_recorder()` that guards the `discovery.tracker` import and
  fails open.
- `discovery/registry.py`: `_emit_injection` records path-A surfacing
  (best-effort); new `--funnel` CLI report classifying retire / slim / star.
- `runtime_import_audit.py`: register `prompt-context-router.py` in
  `FAIL_OPEN_GC_IMPORTERS` (new guarded gc-importer); doc table updated.
- Tests: `tools/test_skill_funnel.py` (12 cases). Version 0.22.0 → 0.23.0.

## Non-Goals

- No change to `weighted_scores()` formula or injection ordering — the funnel
  is a standalone diagnostic.
- No retirement / slimming of any skill — the funnel only *enables* those
  human-reviewed decisions.
- No new config keys; `INDEX.routing.json` unchanged.

## Guardrails

- `edit-write-guard`: not triggered (no constitution files touched).
- `constitutional-review` (Art.4): enforced on tracker/registry/router/audit
  edits; funnel counter reads spelled via `_int_field` membership test to
  avoid the `.get(key, default)` config-fallback rule (data-dict access, not
  config). `tools/` is skip-listed, so `upgrade_review`-style files are exempt.
- `runtime-import-discipline` (P-0081): the new router import is guarded +
  fails open and is registered in `FAIL_OPEN_GC_IMPORTERS`; `doctor` exit 0.

## Phases

### Phase 1: Promote + wire + validate (single phase)

- Deliverables: the Scope edits + `tools/test_skill_funnel.py`; version bump.
- Validation: see Validation Plan.
- Exit criteria: full suite green, doctor exit 0, wheel isolated, archived.

## Approval Criteria

- Mechanism is generic (observability of skill delivery); no domain coupling.
- `governance_core/` edited only — no autonomy-layer copy hand-edited (Art.11.2).
- New funnel counters do not alter scoring/injection behavior (non-goals hold).
- Router import guarded + fail-open; registered; doctor clean.

## Validation Plan

- `python tools/test_skill_funnel.py` → 12/12 (tracker schema-v2 migration,
  per-day surfaced dedup, per-event triggered, atomic save, router
  dedup-suppressed-still-triggers, funnel retire/slim classification).
- Full suite `tools/test_*.py` → 25/25.
- `governance-core upgrade --project-root .` then `doctor` → exit 0, router
  classified fail-open (no unclassified-importer warning).
- `python -m build --wheel`: top-level only `governance_core*`; new files
  present; no `maintainer/` leak.

## Rollback / Recovery

Single commit; `git revert` restores 0.22.0 behavior. The funnel is additive
and best-effort — disabling is also possible by reverting only the router
`on_trigger` wiring and the `_emit_injection` record call (counters then stay
at 0, harmless).

## Risks

- Tracker write contention (router now writes per-prompt): **mitigated** by
  atomic `os.replace` save; a lost write under a rare race is acceptable
  (counters are a proxy), a corrupt file is not (never produced).
- `total_tracked_skills` rises (~12 → ~60) as surfaced entries are created:
  intended (more accurate), not a regression.
- Best-effort tracker failure in the router: swallowed; injection still emits
  (verified by test + fail-open registration).

## State Log

- 2026-06-02: draft created by core agent (P-0092)
- 2026-06-02: draft → pending (submit for review: curate gc #25 funnel)
- 2026-06-02: pending → approved (user: 批准 (approve, archive and close both issues))
- 2026-06-02: approved → implemented
