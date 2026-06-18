---
id: P-0105
agent: core
status: implemented
created: 2026-06-18
approved_at: 2026-06-18
started_at: 2026-06-18
implemented_in: 9875ebf
implemented_at: 2026-06-18
owner: core
---

# Proposal P-0105: Check 16 (16a) exempt source_type=command from coverage FAIL

## Trigger

trade-agent consumer offered a capability candidate via plain GitHub issue
**gc #102** (unlabeled; consumer proposal P-0115 / todo T-0032). Hub-side
`/curate-candidate` review classified it as a **promotable generic refinement**
of the package audit gate. Per `/curate-candidate` Step 8, a curation that
**adds/changes capability** (here: alters Check 16's FAIL surface in
`governance_core/tools/audit_knowledge.py`) must go through `/proposal` for the
audit trail. The change touches the governance audit machinery, so classify
returns `PROPOSAL_REQUIRED`.

The substance: Check 16 (`_audit_scenario_coverage`, 16a coverage sub-check,
added in #100 / P-0103) over-fires on **slash commands**. Once a project authors
`knowledge/skills/_scenario_clusters.json`, every md-skill not in the
`universal` tier or a scenario cluster FAILs. #101 / P-0104 softened this to
WARN for **learned** skills on non-hub clones, but **commands still hard-FAIL**.
Slash commands are always listed in the harness Skill-tool menu and invoked by
name, so their discoverability does NOT depend on SessionStart cluster
surfacing — the very gap (P-0113, ~50 skills at use_count=0) that the coverage
gate exists to close. Forcing commands into consult-routing clusters fixes no
real "couldn't find it" problem, bloats the injection, and adds perpetual
re-clustering maintenance. Measured on trade-agent (clusters authored):
Failed=25 = 19 command (noise) + 6 guide (legit) + 16 learned (already WARN on
non-hub). The 19 command FAILs block every flow that treats `audit_knowledge`
as a clean gate (notably `/publish-knowledge` Step 4.6 `Failed=0`).

## Scope

- `governance_core/tools/audit_knowledge.py` — in `_audit_scenario_coverage`,
  build a `command_skills` set (`source_type == "command"`) alongside the
  existing `learned_skills` set; in the 16a coverage loop, `continue` past any
  name in `command_skills` BEFORE the existing non-hub/learned WARN branch, so
  the two carve-outs compose (additive to #101, not a replacement).
- A new test asserting: (a) an unsurfaced `command` skill produces neither FAIL
  nor WARN in 16a; (b) the #101 non-hub-learned WARN path still fires; (c) an
  unsurfaced `guide` skill still FAILs; (d) 16b phantom-member detection is
  unaffected.
- Version bump (ships to consumers via `upgrade`).
- Curation ledger record (`candidate.py`/registry) + `/proposal complete` +
  close gc #102 with the curation outcome (commit + version).

## Non-Goals

- NOT exempting `guide` or `learned` from the coverage gate — both remain
  consult-only and genuinely depend on SessionStart surfacing.
- NOT touching 16b (phantom-member) logic.
- NOT changing the `_scenario_clusters.json` gating (a project without clusters
  is still never penalized).
- NOT altering #101's non-hub-learned WARN behavior — only composing alongside.
- NOT authoring `_scenario_clusters.json` on the hub (the hub has none; Check 16
  is gated off here — change is verified by unit test, not hub dogfood symptom,
  cf. hub-cannot-dogfood limitations).

## Guardrails

- **edit-write-guard**: target is `governance_core/` package source (allowed);
  proposal frontmatter/State Log mutated only via `proposal_lib.py` (not direct
  Edit).
- **boundary-guard**: all edits in-boundary (cwd = this repo); gh issue close is
  an outward action, done at the end with explicit confirmation.
- **Art.11.2**: edit the package source `governance_core/tools/audit_knowledge.py`
  ONLY — never the root autonomy-layer copy; re-install via `upgrade` to dogfood.
- **Art.4**: no `.get(k, default)` fallback introduced (the function already uses
  membership-test `_field` for data-file reads).

## Phases

### Phase 0: Governance bootstrap (N/A)

- No constitution / contract change. Check 16 is a refinement within an existing
  audit mechanism; no clause text changes. Phase 0 is a no-op.

### Phase 1: Implement command carve-out + test + dogfood

- Deliverables:
  - `command_skills` set + 16a `continue` guard in `_audit_scenario_coverage`,
    composing with the #101 non-hub/learned branch.
  - Net-new test covering exempt-command / still-WARN-learned /
    still-FAIL-guide / phantom-unaffected.
  - Version bump in the package; curation ledger record for gc #102.
- Validation:
  - `python tools/test_*.py` (script + pytest styles) green; new test passes.
  - `governance-core upgrade --project-root .` then `governance-core doctor`
    exit 0.
  - `python -m build --wheel`; assert wheel top-level is only `governance_core*`
    (+ dist-info), `maintainer/` did not leak (Art.11.4).
- Exit criteria: all validation green; commit with `Implements: P-0105` +
  `Closes #102`; gc #102 closed with curation-outcome comment.

## Approval Criteria

- The diff to `_audit_scenario_coverage` adds ONLY a `command_skills` set and a
  single `continue` guard placed before the non-hub/learned branch — 16b and the
  #101 WARN path are byte-for-byte preserved.
- The new test demonstrates all four behaviors (exempt command, WARN learned on
  non-hub, FAIL guide, phantom intact).
- No new dependency; no `.get` fallback; no autonomy-layer edit.

## Validation Plan

- Unit: run the gc test suite per-file (script-style + pytest-style, per
  gc-test-suite-two-styles); confirm the new audit test passes and
  `audit_knowledge` over a fixture with an unsurfaced command yields Failed=0.
- Dogfood: `upgrade --project-root .` + `doctor` exit 0.
- Packaging: `rm -r build` then `python -m build --wheel`; inspect wheel
  contents for package isolation and presence of the changed module.

## Rollback / Recovery

- Single-commit, additive change confined to one function + one test. Revert the
  commit to restore prior behavior; re-run `upgrade` to re-install. No data
  migration, no state mutation, no schema/contract change — clean rollback.

## Risks

- **Low**: a command that a consumer genuinely wants proactively surfaced is no
  longer forced into a cluster. Mitigation: exemption removes the FAIL, not the
  ability — a consumer may still cluster a command voluntarily; coverage was
  never the right lever for command discoverability (menu-based).
- **Low**: composition bug with #101's branch. Mitigation: the test explicitly
  asserts the non-hub-learned WARN path still fires after the carve-out.
- **Very low**: packaging regression. Mitigation: wheel-isolation check in
  Validation.

## State Log

- 2026-06-18: draft created by core agent (P-0105)
- 2026-06-18: draft → pending (submit for review: candidate gc #102 command carve-out for Check 16 16a)
- 2026-06-18: pending → approved (user approval signal: 批准)
- 2026-06-18: approved → in-progress (begin Phase 1)
- 2026-06-18: in-progress → implemented
