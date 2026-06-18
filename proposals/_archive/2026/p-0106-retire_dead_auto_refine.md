---
id: P-0106
agent: core
status: implemented
created: 2026-06-18
approved_at: 2026-06-18
started_at: 2026-06-18
implemented_in: 08f69cb
implemented_at: 2026-06-18
owner: core
---

# Proposal P-0106: Retire dead Hermes auto-refine path (gc #103)

## Trigger

trade-agent consumer reported (plain GitHub issue **gc #103**, unlabeled;
consumer proposal P-0117) that the Hermes auto-refine path is **structurally
dead** in every consumer. Hub-side verification confirmed the analysis end to
end. Per `/curate-candidate` Step 8, a curation that changes a gc-managed
capability (here: removing the `--auto-refine` machinery from
`commands/wrap-up.md` + `discovery/extractor.py` + `discovery/tracker.py`) must
go through `/proposal`. classify returns `PROPOSAL_REQUIRED` (skill/governance
machinery across three gc-managed files).

Verified dead chain (package source):
- `diff_and_refine(name)` (`extractor.py:238`) returns `None` whenever
  `tracker.steps_taken_this_session()` is empty (`extractor.py:274-275`).
- The only mutator of `steps_taken` is `SkillTracker.record_step()`
  (`tracker.py:316`, append at :326). A repo-wide grep (package +
  `.claude/hooks/` + `tools/`) finds **zero callers** of `record_step` —
  definition only.
- Therefore `steps_taken` is always `[]`, `diff_and_refine` always returns
  `None`, and `commands/wrap-up.md` Step 4b's
  `python -m governance_core.discovery.extractor --auto-refine <skill>`
  (`wrap-up.md:148`) is a perpetual no-op `[SKIP]` (consumer evidence:
  wrap-up use_count 108-127 across 5 clones, `refinement_count == 0`
  everywhere, zero `## Refinement` sections).
- `refine_skill()` (`extractor.py:198`) and `record_refinement()`
  (`tracker.py:210`) are reachable **only** through the dead `diff_and_refine`;
  `_extract_workflow_steps`/`_find_novel_steps` serve only `diff_and_refine`.
  The live extraction path `extract_skill()` (`extractor.py:130`, the CLI
  `extract` branch) does not touch any of them.

Manual refinement (agents directly edit / re-extract learned skills) is
unaffected — it never went through `refine_skill()`. Only the automated
drift-detection path is dead. Chosen disposition: **option (a) retire** (the
submitter's preferred option; option (b) wiring a `record_step` producer was
self-assessed as unclear-ROI and is declined).

**Intent preserved, not discarded.** The owner affirmed the original goal —
learned skills self-improving from real usage — is worth keeping. The v1
machinery this proposal removes is naive beyond the missing producer (≥50%
word-overlap novelty detection, append-only writes, format-fragile extraction),
so the intent is re-homed in **P-0107** (v2 design: LLM-reflection at wrap-up
gated by `/update-skill`), NOT revived here. The gc #103 closure comment will
point contributors at P-0107 as the forward path.

## Scope

Remove the dead auto-refine subsystem and its orphaned plumbing:

- `governance_core/commands/wrap-up.md` — delete Step 4b (`--auto-refine`
  block); keep 4a (extract) and 4c (registry verify). Renumber/relabel only as
  needed so the checklist stays coherent.
- `governance_core/discovery/extractor.py` — remove `diff_and_refine`,
  `refine_skill`, `_extract_workflow_steps`, `_find_novel_steps`, and the
  `--auto-refine` argparse argument + its handler branch. Keep `extract_skill`
  and the `extract` CLI path intact.
- `governance_core/discovery/tracker.py` — remove `record_step`,
  `steps_taken_this_session`, `record_refinement`, and the now-orphaned
  `steps_taken` field plumbing (session-dict defaults, the
  `weighted_scores()` `// 10` term, and the `steps_taken_today` get_stats
  field + its print line).
- `governance_core/commands/extract-skill.md` — remove the line pointing at
  `refine_skill()` for incremental refinement (the helper is gone).
- `governance_core/commands/update-skill.md` (line 19) — the
  `learned/*.json` does-NOT-trigger rule stays valid, but its stated reason
  ("由 extractor auto-refine 处理") goes stale. Reword the parenthetical to
  drop the auto-refine claim (e.g. "per-agent runtime tracker state, not
  constitution-coupled"); keep the exclusion itself. (Surfaced during the
  pre-approval dead-code sweep — not in the original draft scope.)
- Version bump; curation ledger record for gc #103; close gc #103.

## Non-Goals

- NOT touching the live extraction path (`extract_skill` / `/extract-skill`
  Step-by-step) or the should-extract complexity gate's OTHER score terms
  (only the always-zero `steps_taken` term is removed; numeric behavior is
  preserved because that term was always 0).
- NOT pursuing option (b) (wiring a `record_step` producer) — declined.
- NOT changing manual-refinement guidance beyond removing the dead
  `refine_skill()` pointer.
- NOT altering `record_use`/`record_surfaced`/`record_triggered` (the live
  A/B/C usage funnel) — only the dead refinement counters go.

## Guardrails

- **edit-write-guard**: all targets are `governance_core/` package source
  (allowed). `wrap-up.md` and `extract-skill.md` are command skills, NOT the
  constitution trio, so edit-write-guard's L? constitution block does not
  apply; proposal frontmatter/State Log mutated only via `proposal_lib.py`.
- **boundary-guard**: all edits in-boundary (cwd = this repo); gh issue close
  is outward, done at the end.
- **Art.11.2**: edit package source ONLY — never the root autonomy-layer copy;
  re-install via `upgrade` to dogfood.
- **Art.4**: no `.get(k, default)` fallback introduced.
- Stale-build hygiene: clean `build/` before the wheel-isolation build
  (a prior wheel build left `build/lib/`; stale lib can mask removals).

## Phases

### Phase 0: Governance bootstrap (N/A)

- No constitution / contract change. wrap-up.md and extract-skill.md are
  command skills (Skill single-source), not the constitution trio; editing
  them does not invoke `/iterate-constitution`. Phase 0 is a no-op.

### Phase 1: Remove the dead subsystem + verify + dogfood

- Deliverables:
  - The five-file removal in Scope, leaving the live `extract_skill` path and
    A/B/C usage funnel untouched.
  - A regression test asserting: (i) the extractor CLI no longer accepts
    `--auto-refine` (arg removed); (ii) `extract_skill` still works; (iii)
    tracker `weighted_scores()`/`get_stats()` produce the same numbers as
    before for a fixture session (the removed term was always 0); (iv) no
    dangling import of a removed symbol (module imports clean).
  - Version bump; curation ledger record for gc #103.
- Validation:
  - `python -m pytest governance_core/tools/ -q` + script-style suites green;
    grep confirms zero references to the removed symbols remain in
    `governance_core/`.
  - `governance-core upgrade --project-root .` then `governance-core doctor`
    exit 0; a real wrap-up Step 4 no longer prints the `--auto-refine` line.
  - Clean `build/` then `python -m build --wheel`; wheel top-level is only
    `governance_core*` (+ dist-info), `maintainer/` absent, changed modules
    present.
- Exit criteria: all validation green; commit `Implements: P-0106` +
  `Closes #103`; gc #103 closed with the curation outcome.

## Approval Criteria

- The diff removes ONLY the dead auto-refine cluster (the symbols enumerated in
  Scope) — `extract_skill`, `record_use`, `record_surfaced`,
  `record_triggered`, and the other complexity-score terms are byte-for-byte
  preserved.
- A repo-wide grep for each removed symbol returns no remaining reference in
  `governance_core/` (no dangling caller or import).
- The regression test demonstrates `weighted_scores()`/`get_stats()` numbers
  are unchanged and the extractor module imports without error.
- No new dependency; no `.get` fallback; no autonomy-layer edit.

## Validation Plan

- Unit: gc test suite per-file (pytest-style + script-style, per
  gc-test-suite-two-styles); new regression test passes; grep clean for
  removed symbols.
- Dogfood: `upgrade --project-root .` + `doctor` exit 0; inspect the installed
  `commands/wrap-up.md` Step 4 to confirm the `--auto-refine` line is gone.
- Packaging: clean `build/` (stale-lib hygiene) then `python -m build --wheel`;
  inspect wheel for isolation + presence of changed modules.

## Rollback / Recovery

- Single commit, pure deletion across well-isolated symbols. Revert the commit
  to restore the (dead) subsystem; re-run `upgrade` to re-install. No data
  migration, no schema/contract change, no tracker-state format change (the
  `steps_taken` key simply stops being written/read — existing tracker JSON
  files with a stale `steps_taken` key are ignored harmlessly). Clean rollback.

## Risks

- **Low**: a live path unexpectedly depends on a removed symbol. Mitigation:
  pre-removal grep (already done: callers map only to the dead chain) +
  module-import + `extract_skill` regression test.
- **Low**: removing the `steps_taken` term shifts the should-extract
  complexity score. Mitigation: the term was always 0 (no producer); a
  regression test pins `weighted_scores()` output before/after.
- **Very low**: someone was about to wire option (b). Mitigation: the code is
  recoverable from git history + the archived proposal if the capability is
  ever revived with a real producer.
- **Very low**: packaging regression. Mitigation: wheel-isolation check.

## State Log

- 2026-06-18: draft created by core agent (P-0106)
- 2026-06-18: draft → pending (submit for review: retire dead auto-refine path (gc #103, option a))
- 2026-06-18: pending → approved (user approval signal: P-0106 批准)
- 2026-06-18: approved → in-progress (begin Phase 1 retirement)
- 2026-06-18: in-progress → implemented
