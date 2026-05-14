---
theme: universal
name: external-design-reverse-feed
description: When the user points at an external tool's design (another Claude project, codex, a coworker's setup, a blog post architecture) and asks "should we adopt this in our project?", run this comparison-and-adaptation workflow. Output a proposal with explicit Non-Goals — articulate what you're rejecting and WHY, not just what you're keeping. Cargo-cult adoption (port everything wholesale) and convenient-rejection (silently drop the unfamiliar bits) both fail differently; the proposal Non-Goals section forces you to address each external feature explicitly.
type: guide
tags: [governance, process, proposals, design, meta]
created: 2026-05-12
updated: 2026-05-12
---

# External Design Reverse-Feed

## When this triggers

- User shares another tool / project / agent harness's design and asks if we should adopt it
- User says "look at how X does Y, can we do similar?"
- During a refactor, you notice a more mature pattern in an adjacent system
- A skill / workflow / schema you maintain is showing pain points another design solves

This skill is **not** for greenfield "what should we build?" — it's for the specific case where an external reference exists and partial adoption is plausible.

## The four-axis comparison

For every distinct feature in the external design, place it on two axes:

1. **Pain-fit**: does this feature address a pain we actually have?
2. **Cost-fit**: does the implementation cost survive our constraints (existing contracts, scope rules, audit invariants, user habits)?

| Pain-fit | Cost-fit | Action |
|---|---|---|
| Yes | Yes | **Adopt as-is** (or with minor adaptation) |
| Yes | No | **Adopt the idea, not the form** — re-implement under our constraints; document the form mismatch |
| No | Yes | **Reject** — even free additions add cognitive load; only keep what solves a real pain |
| No | No | **Hard reject** — explicit in Non-Goals |

The third row is the most-missed: features that are "free to add" still cost cognitive load and surface area. Default to reject unless the pain is real.

## Why Non-Goals are mandatory

A proposal that lists only what you're **adopting** invites cargo-cult drift later: "we already pulled in their idea X, let's also grab Y since we're at it" — but Y was deliberately not in scope. The Non-Goals section pre-empties that by making each rejection auditable.

For every rejected feature, the Non-Goals entry must answer:

- **What** is rejected (one line, naming the external feature)
- **Why** rejected (which axis — pain or cost — fails)
- **What's the alternative** if the rejected feature solved a real but minor pain (we just chose differently)

If you can't articulate "why" in a sentence, you haven't decided yet — go back to the comparison.

## Worked example: P-0001 proposal skill v2 (2026-05-12)

User pointed at codex's `~/workshop/.agents/skills/{proposal-gate, proposal-workflow, proposal-state}` and asked for reverse-feed into our `/proposal` skill.

**Adopted** (pain real, cost survivable):
- `classify` three-value gate (`NO_PROPOSAL` / `PROPOSAL_REQUIRED` / `NEEDS_CLARIFICATION`) — pain: ceremonial proposals piling up (28 pending). Cost: just a new subcommand.
- 9-section required scaffold (Trigger / Scope / Non-Goals / Guardrails / Phases / Approval Criteria / Validation Plan / Rollback / Risks) — pain: half-drafted proposals lacking validation/rollback plans. Cost: ~10 extra body lines per new proposal.
- Body-internal `## State Log` — pain: state transitions only visible via `git blame` on frontmatter. Cost: append one line per transition.

**Rejected** (no real pain or cost too high):
- `READY` state separation from `APPROVED` — no pain (our single-developer 5-clone setup doesn't need staged readiness); cost: adds friction.
- `BLOCKED` state — no pain (`TaskCreate` already handles temporary blockers); cost: double-bookkeeping.
- `VALIDATING` state — no pain (commit + CI is our validation gate); cost: dilutes source-of-truth.
- Strict literal `approve P-xxxx` approval keyword — no pain (our mixed Chinese/English approval set works); cost: friction without proportional safety gain.
- ID renumbering for 76 legacy proposals — no pain (legacy proposals are referenced externally by filename); cost: high (rename + reference rewriting).

**Adapted, not literal** (idea good, form wrong):
- `id` field three-way consistency (filename ↔ frontmatter ↔ body H1). Codex didn't have this. Our schema needed it because our migration tool renames files and we wanted audit-detectable drift.
- `shared_state/proposals/<agent>/` co-location. Codex stored under `workshop/state/proposals/`. We needed cross-clone visibility, which our `shared_state/` infrastructure (Art.4-之一) already provides. Form differs, idea identical.

Each rejection went into the proposal's Non-Goals section with a one-line "why". When the user later asked "what about X?" mid-implementation, the answer was already written down — no re-litigating.

## Anti-patterns

### Wholesale port

"They have 12 features, we have 3, let's port all 12."

Most external systems carry features that solve THEIR pain, not yours. Importing those without their context creates dead surface area that future readers think is load-bearing. Reject everything until proven needed.

### Convenient silence

"They have READY state, we'll just not mention it in the proposal."

Silence is worse than rejection. The next person comparing the two systems will ask the same question and waste cycles deriving the answer again. Make Non-Goals explicit so the decision is auditable.

### Adapt-without-naming

"We have something similar — kind of, sort of, in spirit."

If the form differs, say so. "Codex stores X at path A; we store it at path B because of constraint C" is documentation. "We have similar functionality" is hand-waving that breaks down on first edge case.

### Skip the multi-phase split

External design has 5 features and your adoption has 5 → don't ship as 1 commit. Phase them:
- Phase 0: governance bootstrap (constitution / schema updates if any)
- Phase 1: storage / config infrastructure
- Phase 2: skill / behavior body
- Phase 3: validators / hooks / migration tools
- Phase 4: execute migration / cleanup legacy

Each phase has its own commit + wrap-up, can revert independently. P-0001 ran exactly this 5-phase structure (commits `37d8cf42` / `e75928ba` / `03b6fbea` / `63e02874` / `4cde986e`); each phase exposed bugs the others would have hidden.

### Skip the dogfood

The proposal itself should be the first real user of the new design. P-0001 walked through its own v2 state machine (draft → pending → approved → in-progress → implemented → archive) and exposed 2 bugs only dogfood would reveal:
- Body whitespace accumulating across read-modify-write cycles
- Migration tool renaming filename + frontmatter but leaving body H1 stale

Synthetic test proposals don't catch the "use it for real" failure modes. Make the proposal eat its own dog food.

## Output checklist (every reverse-feed proposal)

When this skill produces a proposal, the proposal MUST contain:

- [x] **Trigger** section names the external system + the exact path / URL / commit you read
- [x] **Scope** lists adopted features as a positive enumeration (A, B, C…)
- [x] **Non-Goals** lists rejected features with one-line "why" each
- [x] **Adapted-not-literal** features explicitly note the form difference vs the original
- [x] **Phase structure** separates governance / infra / behavior / tooling / migration
- [x] **Approval Criteria** include "post-implementation Non-Goals still hold" as one bullet (auditable later)

If any line in the proposal could equally well describe the external system as-is, you haven't adapted yet — go specify the difference.

## Cross-reference

- This skill was distilled from P-0001 (2026-05-12, archived at
  `proposals/_archive/2026/p-0001-proposal_skill_v2_gate_template_statelog.md`)
  where codex's 3-skill proposal design was reverse-fed into Claude Code's
  `/proposal` skill.
- Sibling skill: `proposal-vs-plan-mode-vs-commit.md` (decides if any change
  needs a proposal at all — run that gate first).
- Constitution Art.13 governs proposals process; Art.5 governs cross-actor
  authorization. This skill operates within those constraints.
