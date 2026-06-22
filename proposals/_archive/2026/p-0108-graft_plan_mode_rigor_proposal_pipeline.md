---
id: P-0108
agent: core
status: implemented
created: 2026-06-22
approved_at: 2026-06-22
implemented_in: 9d1854e
implemented_at: 2026-06-22
owner: core
---

# Proposal P-0108: Graft Plan-mode engineering rigor onto the proposal pipeline

## Trigger

Consumer **trade-agent** (its proposal P-0118) audited gc's proposal pipeline
against an agent-assistant **Plan mode / Plan agent** and found the pipeline a
*superset* of plan-mode on the governance axis (durable, cross-actor,
approval-captured, rollback, audit ledger) but a *subset* on the
engineering-rigor axis. Filed as gc issue **#104** (an unlabeled design issue,
not a candidate envelope) because the three target files
(`commands/proposal.md`, `tools/proposal_lib.py`, `tools/audit_proposals.py`)
are all gc-managed. The change touches the governance machinery **and** adds a
blocking gate on `transition --to approved` → proposal governance applies.
Owner decision (this session): adopt the consumer's **evolved level-D** design
(issue comment 2, `444f837a`), not the issue body's softer WARN-only G1.

## Current State (read, not assumed)

- `governance_core/tools/proposal_lib.py:462` `_v2_scaffold` emits Trigger /
  Scope / Non-Goals / Guardrails / Phases / Approval Criteria / Validation Plan
  / Rollback / Risks / State Log — **no** Current State, **no** Alternatives
  section. `transition_proposal` (:577) has **no** adequacy gate on
  `--to approved`. No `reconcile` function.
- `governance_core/tools/audit_proposals.py`: docstring header lists Checks
  1–12; P-0105 extended live checks to **Check 16**. No current-state check.
- `governance_core/knowledge_governance/proposal-drafting-checklist.md` exists;
  parsed by `proposal_suggest.py parse_checklist`, which requires each entry be
  a `### 标题` with four fields (`触发` / `教训` / `怎么做` / `来源`). No
  research paradigm encoded.
- **Net-new verified**: `grep -rn "Current State|Alternatives & Rationale|def
  reconcile|current_state_adequacy|allow-empty-current-state|_check_current_state"
  governance_core/` returns empty. The issue's "confirmed net-new" claim holds.

## Scope

Edit gc **package source** (`governance_core/`) only (Art.11.2):

1. `proposal_lib.py`: add `## Current State (read, not assumed)` (after Trigger)
   and `## Alternatives & Rationale` (after Non-Goals) to `_v2_scaffold`;
   add `current_state_adequacy(body)` predicate; add an adequacy **BLOCK** on
   `transition_proposal(--to approved)` with `--allow-empty-current-state`
   override; add `reconcile()` + `_extract_scope_file_tokens` +
   `_commit_changed_files` + a `reconcile` CLI subcommand.
2. `audit_proposals.py`: new check (next free number) reusing the SAME
   `current_state_adequacy` predicate, WARN-only, grandfathering pre-cutover
   proposals.
3. `commands/proposal.md`: classify output gains an `evidence:` line; `create`
   docs the two new scaffold sections; `complete` gains step 0 = run `reconcile`
   before marking implemented, deviations recorded in State Log.
4. `proposal-drafting-checklist.md`: encode the 5-dimension research paradigm in
   `parse_checklist` format.

## Non-Goals

- **No retroactive rewrite** of the 135 existing proposals; missing sections =
  WARN/grandfathered, never a new FAIL (mirrors P-0104/P-0105 tolerance).
- **No LLM-judge adequacy gate** — the machine check is FORM-only (section
  present, not placeholder, ≥1 concrete file/line ref); the human approver
  judges substance. Approval IS the adequacy ceiling.
- G2 (Alternatives) and G3 (reconcile) stay **advisory** — not blocking.
- Not touching the consumer's local reference implementation; gc re-authors in
  its own package source.

## Alternatives & Rationale

- **G1 strength** — (a) soft `required section + audit WARN + soft evidence
  line` (issue body); (b) **level-D hard BLOCK on `--to approved` + override +
  grandfather + research paradigm** (comment 2, consumer-evolved); (c) hard gate
  shipped default-off behind a config flag. **Chose (b)** per owner decision:
  it is the corrected kernel (comment supersedes body, gc #26 precedent), the
  form-vs-substance split guarantees a research floor without machine-judging
  substance, and override + grandfather backstop the friction. (c) rejected — a
  default-off gate is dead code + an extra config dimension.
- **Shared predicate** — separate WARN/BLOCK logic vs one `current_state_adequacy`
  reused by both. **Chose shared** so audit WARN and transition BLOCK can never
  disagree.
- **G3 reconcile** — (a) prose reminder (weakest); (b) fully-automatic
  Scope-parse + diff verdict (deterministic but brittle on imperfect parsing);
  (c) helper lists coverage gaps, agent reviews. **Chose (c)** — machine-assisted,
  loose token match, advisory.
- **G2 alternatives section** — always-on vs architecture-only. **Chose
  always-on + proportionate prompt** (a single obvious approach states so; a
  design choice weighs ≥2).

## Guardrails

- `edit-write-guard`: edits are gc package source (not the three constitution
  files) → permitted; root autonomy-layer copies must NOT be touched (Art.11.2).
- The new `current_state_adequacy` BLOCK is itself a guard on the approve
  transition — must ship with the `--allow-empty-current-state` hatch so a
  legitimate greenfield/legacy proposal is never wedged.
- Wheel isolation (Art.11.4): wheel top-level stays `governance_core*` only;
  `maintainer/` must not leak. `proposal-drafting-checklist.md` already ships
  (its dir is globbed) — confirm no NEW non-`.py` file needs a package-data glob.

## Phases

### Phase 1: G2 + G3 — additive, low-risk

- Deliverables: `_v2_scaffold` emits the two new sections in order;
  `reconcile()` + helpers + `reconcile` CLI subcommand; `commands/proposal.md`
  `create` docs the new sections, `complete` step-0 runs reconcile, classify
  gains `evidence:` line.
- Validation: `proposal create` scaffold `grep -c` == 1 for each new heading;
  `reconcile --id P-NNNN <hash>` exits 0 and prints `[in scope, NOT touched]` /
  `[touched, NOT in scope]`; full `tools/test_*.py` suite green + new tests.
- Exit criteria: scaffold + reconcile land in `governance_core/`, version
  bumped, `upgrade --project-root .` + `doctor` exit 0, wheel isolation passes.

### Phase 2: G1 — level-D hard research gate

- Deliverables: `current_state_adequacy(body)` predicate; `transition_proposal`
  BLOCKs `--to approved` when it fails, `--allow-empty-current-state` overrides
  (justify in `--note`); new audit check reuses the SAME predicate (WARN-only)
  and grandfathers pre-cutover proposals.
- Validation: empty/placeholder Current State → BLOCK with teaching message;
  filled → OK; override → OK; downstream transitions (submit/start/complete)
  unaffected; audit shows **0 new FAILs** on the 135 existing proposals.
- Exit criteria: gate + shared predicate land, tests cover BLOCK/OK/override +
  grandfather, version bumped, upgrade + doctor exit 0.

### Phase 3: research paradigm

- Deliverables: the 5-dimension paradigm (2 always machine-checkable form dims;
  3 conditional approver-judged dims) encoded in
  `proposal-drafting-checklist.md` in `parse_checklist` format; keyword-surfaced
  at draft time via `proposal_suggest`.
- Validation: `proposal_suggest.py parse_checklist` round-trips the new entries
  (no parse break); keyword recall surfaces them for a matching description.
- Exit criteria: paradigm lands, suggest still parses, version bumped, upgrade +
  doctor exit 0.

## Approval Criteria

Machine-checkable (lifted from issue #104 acceptance + the level-D evolution):

1. `proposal create` scaffold contains `## Current State (read, not assumed)`
   and `## Alternatives & Rationale` — `grep -c` == 1 each.
2. `commands/proposal.md` classify output documents an `evidence:` line.
3. `proposal_lib.py reconcile --id P-NNNN <hash>` exits 0 and prints both
   coverage-gap lists.
4. `transition --to approved` BLOCKs a proposal with empty/placeholder Current
   State; `--allow-empty-current-state` overrides; a filled one passes.
5. The new audit check reuses the same `current_state_adequacy` predicate and
   reports WARN (never new FAIL); 0 new FAILs across the 135 existing proposals.
6. 5-dim research paradigm present in `proposal-drafting-checklist.md` and
   `parse_checklist` still parses the file.

## Validation Plan

- Run BOTH gc test styles ([[gc-test-suite-two-styles]]): pytest-style +
  per-file script suites; run from repo-root ([[gc-test-suite-run-from-autonomy-layer]]).
- Add net-new tests: scaffold-section presence, reconcile coverage lists,
  `current_state_adequacy` truth table, transition BLOCK/override, audit
  grandfather, checklist parse round-trip.
- `governance-core upgrade --project-root .` then `governance-core doctor`
  (exit 0) after each version bump.
- Wheel isolation: `rm -r build` ([[stale-build-lib-cache-masks-file-removal]])
  then `python -m build --wheel`; assert top-level only `governance_core*`
  (+ dist-info), new symbols present, `maintainer/` absent.

## Rollback / Recovery

- Each graft is independently revertible (separate phases / commits).
- G1 has a runtime hatch (`--allow-empty-current-state`); if the gate proves too
  noisy, downgrade the shared predicate to WARN-only without touching the
  scaffold or reconcile.
- Version bumps revert via the standard release path; consumers stay on the
  prior version until they `upgrade`.

## Risks

- **G1 friction on gc's own approve step** — prob med / impact low. Mitigation:
  form-only check + `--allow-empty-current-state` + grandfather of pre-cutover
  proposals.
- **`parse_checklist` format coupling** — adding the 5-dim paradigm in the wrong
  shape breaks `proposal_suggest`. Mitigation: round-trip parse test in Phase 3.
- **Stale audit-check numbering** — docstring says 12, live is 16; pick the next
  free number at implementation, don't trust the header.
- **Wheel drop for any new non-`.py`** — Mitigation: wheel-isolation assertion
  ([[wheel-package-data-nonpy]]); editable install masks the drop.

## State Log

- 2026-06-22: draft created by core agent (P-0108)
- 2026-06-22: draft → pending (submit for review: graft plan-mode rigor (G1 level-D hard gate + G2 alternatives + G3 reconcile) per gc #104, owner-approved level-D strength)
- 2026-06-22: pending → approved (user approval signal: '批准')
- 2026-06-22: approved → implemented (reconcile step-0 clean: 0 in-scope gaps; out-of-scope touches are version/test/STATE plumbing per Validation Plan)
