---
name: audit-subsystem-health-before-proposing-change
description: When asked whether a skill/feature/subsystem is unused, broken, or worth keeping, measure with its own instrument before asserting. Run the subsystem funnel/audit, check whether a recent fix predates the cold data (recency artifact vs real failure), separate the automated mechanism from the manual one, and verify package/upstream ownership before proposing edits.
theme: universal
owner: core
tags: [audit, governance, measurement, recency-artifact, ownership, proposal-scoping]
---

# audit-subsystem-health-before-proposing-change

When asked whether a skill / feature / subsystem is unused, broken, or worth
keeping: **measure with its own instrument before asserting.** Run the
subsystem's funnel/audit, check whether a recent fix predates the cold data
(recency artifact vs real failure), separate the automated mechanism from the
manual one, and verify package/upstream ownership before proposing edits.

## Preconditions

1. The subsystem ships an instrument (funnel / audit / registry) or one can be
   written read-only.
2. You can read the producing source — never trust a counter by its name alone.

## Workflow

1. Reach for the subsystem's own instrument before reasoning from impression
   (e.g. a registry `--funnel` for skill usage; an audit CLI for compliance).
   Read the PRODUCING source to learn what each counter actually measures — do
   not trust a counter name.
2. Date-check: find when the relevant fix / instrumentation landed (`git log`).
   If the cold/zero data predates it, treat it as a pre-fix BASELINE (recency
   artifact), not proof the thing is broken.
3. Separate mechanisms that look like one: an automated path (gated on a
   producer call) vs a manual path (direct edit / re-extract). Verify each
   independently — grep the producer for callers; check the counter across ALL
   clones, not just one.
4. Before proposing edits to the implicated files, check ownership:
   package/upstream-managed (shipped by an installed package + listed in its
   install manifest) → file an upstream issue, do NOT edit the local copy (it is
   clobbered on the next upgrade); project-owned → edit in scope.
5. Scope the proposal to measurement + cleanup (a funnel checkpoint, dead-code
   retire, drift cleanup), not a speculative redesign. Let measured data trigger
   any escalation.

## Outputs

- A measured verdict (pass/fail with numbers) instead of an impression.
- A scoped measurement + cleanup proposal with upstream-managed parts routed to
  upstream issues, not local edits.

## Notes

- Worked example (generalized): a usage audit shows a subsystem "cold"
  (near-zero loads), but the cold window predates a recent
  instrumentation/behavior fix by a couple of days → it is a pre-fix BASELINE
  (recency artifact), not proof the subsystem is dead. Meanwhile two paths that
  looked like one diverge: an automated path with zero producers (genuinely
  dead) vs a manual path exercised the same day (alive). The implicated files
  are upstream/package-managed → the fix is filed as an upstream issue, not
  edited locally.
- The quartet **measure-before-asserting + recency-vs-failure +
  automated-vs-manual + ownership-check** generalizes to any "is X worth
  keeping?" governance question.

## Discovery

Surfaced as a universal guide at SessionStart (name + description; body lazy).
No separate router trigger is registered — the consuming project ships no
`INDEX.routing.json` by default, and universal-tier surfacing already makes this
skill consultable. A consumer that runs the prompt-context-router MAY add local
triggers (audit, unused, dead code, 没用, 死代码, 是否还需要) per
`skill-router-registration`.

## See also

- `proposal-drafting-checklist.md` — the draft-time "X 坏了/没用/慢 必先用工具量"
  nudge is the one-line counterpart of this fuller workflow.
- `proposal-vs-plan-mode-vs-commit.md` — once measured, scope the change.
