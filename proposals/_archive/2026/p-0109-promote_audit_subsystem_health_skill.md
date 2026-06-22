---
id: P-0109
agent: core
status: implemented
created: 2026-06-22
approved_at: 2026-06-22
implemented_in: 757b120
implemented_at: 2026-06-22
owner: core
---

# Proposal P-0109: Promote audit-subsystem-health-before-proposing-change skill (gc #105)

## Trigger

Consumer trade-agent offered a learned skill `audit-subsystem-health-before-proposing-change`
as a `candidate-common` envelope (gc issue **#105**, kind/skill, auto-eligible).
Curation accepted it as generic governance methodology; the user chose to promote.
Adding a skill to the gc skill system is a "改 skill 体系" change → proposal
governance applies.

## Current State (read, not assumed)

- `governance_core/skills/` holds 15 gc guide skills, **all `theme: universal`**
  (verified: `grep -l "theme: universal" governance_core/skills/*.md` → 15 of 15);
  e.g. `governance_core/skills/skill-router-registration.md:1-7` frontmatter is
  `name / description / theme: universal / owner: core / tags`.
- gc has **no** `INDEX.routing.json` (verified absent) and ships none — routing
  data is consumer-authored autonomy, not packaged. gc guide discovery is purely
  universal-tier SessionStart surfacing (`registry.py` scans `.claude/skills/`).
- Net-new: `grep -rln` for the skill's concepts in `governance_core/skills/` +
  `knowledge_governance/` → no existing skill; only partial overlap with the
  P-0108 `proposal-drafting-checklist.md` dim-4 nudge (measure+recency), which is
  a one-line draft-time prompt, not a consultable workflow.
- `pyproject.toml` package-data already globs `governance_core/skills/*.md` (the
  15 existing skills ship), so a 16th `.md` ships automatically.

## Scope

- Add `governance_core/skills/audit-subsystem-health-before-proposing-change.md`
  (genericized: gc guide frontmatter `theme: universal`; trade-specific Notes —
  P-0117 / auto-refine / gc #103 — rewritten as a generalized worked example;
  mechanism/Workflow kept verbatim; `## Discovery` documents the router-skip).
- Version bump `pyproject.toml` + `governance_core/__init__.py`.

## Non-Goals

- No `INDEX.routing.json` / scenario-cluster edits — gc uses universal tier; the
  skill documents an optional consumer-side router registration but ships none.
- No change to the P-0108 `proposal-drafting-checklist.md` dim-4 entry — the two
  are complementary (draft-time nudge vs consultable workflow), kept both.
- No code changes — this is a markdown guide skill.

## Alternatives & Rationale

- **Promote vs reject-as-redundant** — the P-0108 checklist dim-4 already
  captures measure+recency. Chose **promote**: the skill is a richer, separately
  triggered consultable workflow (4 dims incl automated-vs-manual + ownership)
  surfaced for "is X worth keeping?" questions, a different entry point than the
  draft-time checklist. Consumer offered it as common-layer.
- **universal tier vs scenario-cluster member** — chose **universal**, matching
  all 15 existing gc guide skills; gc has no cluster/routing infra, and universal
  surfacing (bounded name+description) is the proven gc pattern.
- **Genericize vs ship verbatim** — chose **genericize the Notes** (curate
  de-trade-ify): mechanism stays verbatim, only the trade-specific illustration
  changes.

## Guardrails

- `edit-write-guard`: new file is gc package source (not a constitution file) →
  permitted; the root autonomy copy must NOT be hand-edited (Art.11.2).
- Wheel isolation (Art.11.4): the new `.md` ships under the already-globbed
  `governance_core/skills/` — confirm in the wheel; no package-data change.

## Phases

### Phase 1: promote the genericized skill

- Deliverables: genericized skill file in `governance_core/skills/`; version bump.
- Validation: `registry --format table` discovers it; full test suite green;
  `upgrade` + `doctor` exit 0; wheel isolation (top-level `governance_core*`
  only, skill present, no `maintainer/` leak).
- Exit criteria: skill lands + ships; ledger records the promotion; #105 closed.

## Approval Criteria

1. `governance_core/skills/audit-subsystem-health-before-proposing-change.md`
   exists with `theme: universal` frontmatter and no trade-specific incident IDs
   in Notes.
2. `registry --format table` lists the skill (guide tier).
3. `upgrade` + `doctor` exit 0; full test suite green.
4. Wheel ships the skill; top-level stays `governance_core*` only.

## Validation Plan

- `python -m governance_core.discovery.registry --format table` shows the skill.
- Full suite: pytest `tools/` + script-style suites ([[gc-test-suite-two-styles]]),
  run from repo-root ([[gc-test-suite-run-from-autonomy-layer]]).
- `governance-core upgrade --project-root .` + `doctor` (exit 0).
- `rm -r build` then `python -m build --wheel`; assert top-level only
  `governance_core*`, skill present, `maintainer/` absent.

## Rollback / Recovery

- Single additive file + version bump — revert the commit to remove the skill;
  consumers stay on the prior version until they `upgrade`.

## Risks

- **SessionStart surface bloat** — prob low / impact low. One more universal
  guide line (16th); bounded name+description injection, body lazy.
- **Wheel drop** — mitigated: skills dir already globbed; wheel check confirms.

## State Log

- 2026-06-22: draft created by core agent (P-0109)
- 2026-06-22: draft → pending (submit: promote gc #105 audit-subsystem-health skill (genericized, universal guide))
- 2026-06-22: pending → approved (user selected 'promote 为通用 skill (推荐)' authorizing /proposal promote incl. approve)
- 2026-06-22: approved → implemented (reconcile clean: skill file in scope; __init__/pyproject/STATE are version+state plumbing)
