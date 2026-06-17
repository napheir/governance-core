---
id: P-0104
agent: core
status: implemented
created: 2026-06-17
approved_at: 2026-06-17
started_at: 2026-06-17
implemented_in: 8541774
implemented_at: 2026-06-17
owner: core
---

# Proposal P-0104: extract-skill business-path + audit Check 11/16 pending-catalog tolerance for non-hub clones (gc #101)

## Trigger

gc issue **#101** from consumer **trade-agent** (follow-on of #100 / gc 0.31 /
P-0103). The federated learned-skill loop breaks for any **non-hub** agent: a
business clone can write a learned skill to `.claude/skills/learned/` but cannot
**complete `/extract-skill`**, because the cataloging steps are hub/core-owned
and out of the business clone's scope. Verified against current package source:

- `governance_core/commands/extract-skill.md` steps 6 / 6b / 7 / 8 require
  editing `knowledge/skills/_tiers.json` (reuse-tier catalog) + rebuilding
  `knowledge/skills/INDEX.md` + passing audit Check 11 (bijection) and Check 16
  (scenario-surface). `_tiers.json` / `INDEX.md` are hub-owned.
- `governance_core/tools/audit_knowledge.py` Check 11a (`:363-368`) hard-**FAIL**s
  on a skill that is registry-present but `_tiers.json`-absent; Check 16a
  (`:492-497`) hard-**FAIL**s on a md-skill that is neither universal nor
  clustered. In a business clone these hard-fail for a just-extracted,
  not-yet-cataloged skill the owner cannot fix → the agent rolls back the
  extraction → the loop becomes hub-only.

Governance applies: touches the gc skill system (`extract-skill.md`) + a
governance audit tool (`audit_knowledge.py`) + the config loader, changes
cross-clone learned-skill behavior shipped to all consumers — `/proposal
classify` returned `PROPOSAL_REQUIRED`.

## Scope

Two gc-managed, generic capabilities (both edit `governance_core/` package
source only — Art.11.2):

- **Part A — extract-skill business-path.**
  `governance_core/commands/extract-skill.md` gains a non-hub branch: create the
  learned-skill file (in scope) + add it to the agent's own scenario cluster in
  `knowledge/skills/_scenario_clusters.json` (owner-maintained, in scope), then
  **SKIP** the hub-owned catalog steps (step 6 `_tiers.json` edit, step 7 INDEX
  rebuild, step 8 Check 11), noting the hub catalogs it later via a sweep. The
  hub path (core agent) is unchanged — it still runs the full catalog steps.

- **Part B — audit pending-catalog tolerance.**
  `governance_core/tools/audit_knowledge.py` Check 11a + Check 16a record
  **WARN (pending-catalog) instead of FAIL** for a learned skill that is
  registry-present-but-catalog-absent **when the running clone is not the hub**.
  Requires a hub-detection primitive sourced from
  `.governance/config.json` `authorization.consumer_id` (hub == `governance-core`),
  added to `governance_core/config.py` as an Art.4-clean accessor (membership
  test, no `.get(k, default)`), defaulting to **strict/hub** when the field is
  absent. The hub (core) audit behavior is unchanged — it stays strict FAIL.

## Non-Goals

- The **hub-side cataloging sweep** (collect business-clone learned-skill files
  to the hub → classify branch-tier → rebuild INDEX → propagate). It is
  consumer-buildable and tracked consumer-side as trade-agent **P-0114 WS-1**.
- Changing the hub's own (core) strict audit behavior — Check 11/16 stay FAIL at
  the convergence hub.
- Multi-clone distribution / `sync_infra` wiring (N/A for the single-agent hub).
- Broadening the tolerance to non-learned skills, or to any registry-only skill
  regardless of source — kept narrow (see Risks).

## Guardrails

- **edit-write-guard**: not triggered — `extract-skill.md`, `audit_knowledge.py`,
  `config.py` are NOT constitution-protected files (only `total.md` /
  `agent.core.md` / `CLAUDE.md` are). No `/iterate-constitution` needed.
- **Art.11.2 source/instance**: edit `governance_core/` package source ONLY; do
  not touch root autonomy-layer copies; `upgrade --project-root .` to dogfood.
- **Art.4 zero-hardcode**: hub-detection accessor must use membership tests, not
  `.get(k, default)` (constitutional-review blocks defaulted lookups in package
  code).
- **runtime-import-discipline**: audit tool already imports `governance_core`; no
  new fail-closed hook is introduced, so no FAIL_OPEN registration needed.
- command-guard / sensitive-data-guard / boundary-guard: no relevant surface.

## Phases

### Phase 0: Governance bootstrap

- N/A — no constitution (`total.md` / `agent.core.md` / `CLAUDE.md`) change. The
  skill body change is the skill's own single source of truth (Art.99 pointer
  rule); the constitution's `/extract-skill` pointer needs no edit.

### Phase 1: Part B — hub-detection primitive + audit pending-catalog tolerance

- Deliverables:
  - `governance_core/config.py`: hub-detection accessor (e.g. `consumer_id`
    first-class field + `is_hub` property) sourcing
    `raw["authorization"]["consumer_id"]`, Art.4-clean, default-strict on absence.
  - `governance_core/tools/audit_knowledge.py`: in `_audit_skill_tiers` (11a) and
    `_audit_scenario_coverage` (16a), when `not is_hub(root)` and a learned skill
    is registry-only / unsurfaced, emit `WARN: ... pending hub catalog` and do
    NOT increment `failed`. Hub path unchanged.
  - Unit tests (`governance_core/tools/test_audit_knowledge*.py` or new file):
    non-hub fixture via `--root` → registry-only learned skill is WARN not FAIL;
    hub fixture → same skill is FAIL (strictness preserved); absent
    `authorization` → strict.
- Validation: `python tools/audit_knowledge.py` (hub) still exit 0 / strict;
  new tests pass; full `tools/test_*.py` suite green.
- Exit criteria: non-hub clone audit no longer hard-fails on a pending learned
  skill; hub strictness unchanged; tests cover both branches + the default.

### Phase 2: Part A — extract-skill.md business-path branch

- Deliverables: `governance_core/commands/extract-skill.md` gains a non-hub
  branch (create skill file + add to `_scenario_clusters.json`; SKIP steps 6/7/8;
  note hub sweep). Hub path retained verbatim. Cross-reference Part B (audit
  records pending, not fail).
- Validation: read-through for internal consistency; confirm the skill still
  points at the single source of truth and does not restate constitution clauses.
- Exit criteria: skill has a clear hub vs non-hub fork; a business agent can
  follow it to completion without touching hub-owned catalog files.

### Phase 3: Dogfood + release

- Deliverables: version bump (`pyproject.toml`); `governance-core upgrade
  --project-root .`; `governance-core doctor` exit 0; wheel build + isolation
  check; close #101 with curation outcome + thank contributor; archive P-0104.
- Validation: see Validation Plan.
- Exit criteria: shipped to consumers via the released wheel; #101 closed;
  proposal archived.

## Approval Criteria

- Part A keeps the hub (core) path identical and only ADDS a non-hub branch.
- Part B keeps hub audit strict (FAIL) and only relaxes to WARN for non-hub
  registry-only learned skills; default-strict when hub identity is unreadable.
- No `.get(k, default)` introduced (Art.4); no autonomy-layer file edited
  (Art.11.2); no constitution file touched.
- Net-new code has tests covering hub / non-hub / absent-config branches.

## Validation Plan

- `python tools/test_audit_knowledge*.py` (new + existing) — both branches green.
- Full suite: `tools/test_*.py` from repo root (script + pytest styles).
- `python tools/audit_knowledge.py` at the hub → exit 0, Check 11/16 still strict.
- `governance-core upgrade --project-root .` then `governance-core doctor`
  (exit 0).
- Wheel isolation: `rm -r build`, `python -m build --wheel`, assert wheel
  top-level is only `governance_core*` (+ dist-info), `maintainer/` absent, and
  any changed/new files present (no new non-`.py` data file expected; if one is
  added it must be in `pyproject.toml` package-data).

## Rollback / Recovery

- Per phase: revert the phase commit. Part B is additive (a new WARN branch);
  reverting restores the prior hard-FAIL behavior with no migration. Part A is a
  doc/skill change; reverting restores the single hub path. The hub's own audit
  is untouched throughout, so a faulty non-hub relaxation cannot weaken hub
  convergence. If the hub-detection primitive misbehaves, default-strict means
  the failure mode is "too strict" (safe), not "silently lax".

## Risks

- **Over-broad tolerance hides a genuinely misclassified skill in a business
  clone** (prob: med, impact: low). Mitigation: scope the WARN to non-hub +
  registry-only/learned; WARN is visible (not silent); the hub stays strict so
  convergence still catches it at catalog time.
- **Hub mis-detected as non-hub → hub loses strictness** (prob: low, impact:
  high). Mitigation: default-strict on any ambiguity/absence; unit-test the hub
  branch explicitly; hub's `consumer_id` is `governance-core` by P-0066.
- **Art.4 violation via defaulted lookup in the new accessor** (prob: low,
  impact: med — constitutional-review/test would block). Mitigation: membership
  test accessor; covered by the zero-hardcode review.
- **Wheel drift** if a new data file is added without package-data (prob: low —
  none expected). Mitigation: wheel-isolation check in Phase 3.

## State Log

- 2026-06-17: draft created by core agent (P-0104)
- 2026-06-17: draft → pending (submit for review)
- 2026-06-17: pending → approved (user approval: 不需要调整，批准)
- 2026-06-17: approved → in-progress (begin Phase 1 Part B)
- 2026-06-17: in-progress → implemented
