---
id: P-0110
agent: core
status: implemented
created: 2026-06-22
approved_at: 2026-06-22
implemented_in: 6901556
implemented_at: 2026-06-22
owner: core
---

# Proposal P-0110: Promote quality-gate-checks-form-human-judges-substance skill (gc #106)

## Trigger

Consumer trade-agent offered a learned skill
`quality-gate-checks-form-human-judges-substance` as a `candidate-common`
envelope (gc issue **#106**, kind/skill, auto-eligible). It generalizes the
form-vs-substance design principle behind P-0108's G1 research gate. Curation
accepted it as a generic gate-design principle; the user chose to promote.
Adding a skill to the gc skill system is a "改 skill 体系" change → proposal
governance applies.

## Current State (read, not assumed)

- `governance_core/skills/` holds 16 gc guide skills after P-0109 (15 original +
  `audit-subsystem-health-before-proposing-change.md`), **all `theme: universal`**;
  gc ships no `INDEX.routing.json` (verified absent) — discovery is universal-tier
  SessionStart surfacing (`governance_core/discovery/registry.py` scans
  `.claude/skills/`).
- Net-new: `grep -rln "form.*substance|quality.gate|gate.design"` over
  `governance_core/skills/` → no existing skill; the two
  `knowledge_governance/` hits (`proposal-classify-fast-path.md:16`,
  `scope-enforcement-mechanism.md:116`) are hard-block *mechanics*, not the
  *design principle* of what-to-enforce-vs-leave-human.
- This principle is exactly what built P-0108's gate:
  `governance_core/tools/proposal_lib.py` `current_state_adequacy()` checks FORM
  (section present / not placeholder / ≥1 file:line), the approver judges
  substance, and the LLM-judge option was rejected.
- `pyproject.toml` already globs `governance_core/skills/*.md`, so a 17th `.md`
  ships automatically.

## Scope

- Add `governance_core/skills/quality-gate-checks-form-human-judges-substance.md`
  (genericized: gc guide frontmatter `theme: universal`; Notes' P-0118-specific
  example rewritten as a generalized one; dropped the cross-ref to the
  consumer-only `augment-soft-governance-with-machine-hardblock` skill; mechanism
  Workflow kept verbatim; `## Discovery` documents the router-skip).
- Version bump `pyproject.toml` + `governance_core/__init__.py`.

## Non-Goals

- No `INDEX.routing.json` / scenario-cluster edits — gc uses universal tier.
- No code changes — markdown guide skill.
- No change to P-0108's gate or the `proposal-drafting-checklist.md` — this skill
  is the generalized *principle*; those are a concrete *instance* of it.

## Alternatives & Rationale

- **Promote vs reject-as-too-meta** — form-vs-substance is already embodied in
  P-0108's gate. Chose **promote**: the skill generalizes the principle to ANY
  quality gate (review, tests, docs), a reusable design heuristic for future
  gate-building, not tied to the proposal pipeline. Consumer offered it as
  common-layer.
- **universal tier** — matches all existing gc guide skills; no cluster/routing
  infra in gc.
- **Genericize vs verbatim** — genericize the Notes (curate de-trade-ify):
  mechanism verbatim, only the illustration + a dangling consumer-skill xref
  changed.

## Guardrails

- `edit-write-guard`: new file is gc package source (not a constitution file) →
  permitted; root autonomy copy must NOT be hand-edited (Art.11.2).
- Wheel isolation (Art.11.4): the new `.md` ships under the already-globbed
  `governance_core/skills/` — confirm in the wheel; no package-data change.

## Phases

### Phase 1: promote the genericized skill

- Deliverables: genericized skill file in `governance_core/skills/`; version bump.
- Validation: `registry --format table` discovers it; full test suite green;
  `upgrade` + `doctor` exit 0; wheel isolation.
- Exit criteria: skill lands + ships; ledger records the promotion; #106 closed.

## Approval Criteria

1. `governance_core/skills/quality-gate-checks-form-human-judges-substance.md`
   exists with `theme: universal` frontmatter and no trade-specific incident IDs
   in Notes.
2. `registry --format table` lists the skill (guide tier).
3. `upgrade` + `doctor` exit 0; full test suite green.
4. Wheel ships the skill; top-level stays `governance_core*` only.

## Validation Plan

- `python -m governance_core.discovery.registry --format table` shows the skill.
- Full suite: pytest `tools/` + script-style suites ([[gc-test-suite-two-styles]]),
  from repo-root ([[gc-test-suite-run-from-autonomy-layer]]).
- `governance-core upgrade --project-root .` + `doctor` (exit 0).
- `rm -r build` then `python -m build --wheel`; assert top-level only
  `governance_core*`, skill present, `maintainer/` absent.

## Rollback / Recovery

- Single additive file + version bump — revert the commit to remove the skill;
  consumers stay on the prior version until they `upgrade`.

## Risks

- **SessionStart surface bloat** — prob low / impact low. One more universal
  guide line (17th); bounded name+description injection, body lazy.
- **Wheel drop** — mitigated: skills dir already globbed; wheel check confirms.

## State Log

- 2026-06-22: draft created by core agent (P-0110)
- 2026-06-22: draft → pending (submit: promote gc #106 form-vs-substance gate-design skill (genericized, universal guide))
- 2026-06-22: pending → approved (user selected 'promote 为通用 skill (推荐)' authorizing /proposal promote incl. approve)
- 2026-06-22: approved → implemented (reconcile clean; STATE is state plumbing)
