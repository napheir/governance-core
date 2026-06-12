---
id: P-0098
agent: core
status: implemented
created: 2026-06-12
approved_at: 2026-06-12
implemented_in: 31cb022
implemented_at: 2026-06-12
owner: core
---

# Proposal P-0098: Promote competing-design-proposals-with-deferred-adr skill into common layer (genericized)

## Trigger

Hub-side curation of candidate issues #87/#89 (`/curate-candidate`). trade-agent
uplinked the learned skill `competing-design-proposals-with-deferred-adr` (twice,
identical payload — #89 is canonical, #87 is a duplicate). Promoting it adds a
guide to the package source's skill 体系 → governance-level change →
PROPOSAL_REQUIRED (Art.13 + `/curate-candidate` step 8).

## Scope

- Add `governance_core/skills/competing-design-proposals-with-deferred-adr.md`
  (the curated guide), reshaped from the consumer `learned` form to the package
  `guide` form: `theme: universal`, `type: guide`; `name` / `description` /
  `tags` preserved; `updated: 2026-06-12`.
- **De-trade-ify**: genericize the one domain-leaking Note line
  (`若涉排序或算法 保持不可比红线加单流基线回归 delta=0` → a domain-neutral
  baseline-regression guard). Mechanism/workflow stays verbatim.
- Add a one-line provenance note (house style, cf. `lesson-classification.md`).
- Version bump (ships to consumers via `upgrade`).
- Record curation decision `promoted` in the consumer registry; close #89 with
  outcome, close #87 as duplicate.

## Non-Goals

- No rewrite of the contributor's mechanism prose (only frontmatter reshape +
  the single domain-leak illustration is changed).
- No new hook / tool / contract / config; no `pyproject` change (`skills/*.md`
  is already globbed into the wheel).
- No `knowledge/` doc and no routing-index entry (skill is dir-scan discovered;
  routing entry is a possible later enhancement, out of scope here).

## Guardrails

- `edit-write-guard`: not a constitution file — Edit/Write of the new skill is
  allowed. `governance_core/` source edited, never the autonomy copy (Art.11.2).
- `boundary-guard`: all writes inside repo boundary.
- No `command-guard` / `sensitive-data-guard` surface (a guidance .md, no
  secrets, no destructive commands).

## Phases

### Phase 1: Promote + wire + validate

- Deliverables:
  - `governance_core/skills/competing-design-proposals-with-deferred-adr.md`
    (curated, genericized, package-guide frontmatter).
  - Version bump in `pyproject.toml` (+ wherever the single version source is).
  - Curation decision recorded; #89 closed with outcome, #87 closed as dup.
- Validation:
  - `python tools/run_all_tests.py` (or `tools/test_*.py`) green.
  - `governance-core upgrade --project-root .` then `governance-core doctor`
    exit 0 (the new skill installs into `.claude/skills/` and is discovered).
  - Wheel isolation: `python -m build --wheel`; assert top-level is only
    `governance_core*` (+ dist-info), the new skill .md is present, `maintainer/`
    did not leak (Art.11.4).
- Exit criteria: tests green, doctor exit 0, wheel clean, both issues closed,
  decision in `maintainer/consumer_registry.json`.

## Approval Criteria

- Reviewer agrees the skill is generic common-layer material (proposal-lifecycle
  / decision-record pattern), not consumer-domain-coupled after de-trade-ify.
- Reviewer agrees with promoting #89 and closing #87 as a duplicate.
- The genericized Note line is acceptable.

## Validation Plan

- Diff the curated skill vs the #89 payload to confirm only frontmatter + the
  one Note line changed (mechanism verbatim).
- Test suite + `doctor` + wheel-isolation check as above.
- `python tools/candidate.py review` shows #89 decided `promoted`.

## Rollback / Recovery

- Pre-archive: revert the new skill file + version bump; re-open the issues.
- The candidate envelopes live only as GitHub issues (no committed state until
  the registry decision), so rollback is a file revert + `gh issue reopen`.

## Risks

- **Low**: skill is a guidance doc; no runtime code path. Worst case is an
  unhelpful guide, removable by deleting the file + `upgrade`.
- **De-trade-ify fidelity**: genericizing the Note line could drop nuance — kept
  the baseline-regression-guard mechanism, dropped only trade-specific terms.
- **Duplicate handling**: closing #87 without curating it is safe — payload is
  byte-identical to #89 (verified), so no content is lost.

## State Log

- 2026-06-12: draft created by core agent (P-0098)
- 2026-06-12: draft → pending (submit for review: promote competing-design-proposals-with-deferred-adr (genericized), close #87 dup)
- 2026-06-12: pending → approved (user approval: '批准')
- 2026-06-12: approved → implemented
