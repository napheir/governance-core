---
name: quality-gate-checks-form-human-judges-substance
description: When designing any gate meant to ensure a quality was achieved (research done before a proposal, review done, tests written, docs updated), split FORM (machine-verifiable presence — cheap, deterministic) from SUBSTANCE (adequacy — needs judgment). The machine enforces the floor (never let a zero-evidence artifact through); the human reviewer judges the ceiling. Do NOT build an LLM-judge to mechanize substance.
theme: universal
owner: core
tags: [governance, gate-design, enforcement, form-vs-substance, review]
---

# quality-gate-checks-form-human-judges-substance

When designing any gate meant to ensure a quality was achieved (research done
before a proposal, review done, tests written, docs updated): **split FORM
(machine-verifiable presence — cheap, deterministic) from SUBSTANCE (adequacy —
needs judgment).** The machine enforces the floor (never let a zero-evidence
artifact through); the human reviewer judges the ceiling. Do NOT build an
LLM-judge to mechanize substance.

## Preconditions

1. The quality has an objectively-detectable FORM proxy (a section, a file ref,
   a test path) even if substance needs judgment.
2. There is a human review/approval step that already owns the substance call —
   the machine is augmenting it, not replacing it.

## Workflow

1. Name the quality you want to guarantee, then split it: FORM = what a
   regex/check can verify is PRESENT (a `file:line` ref, a non-empty section, a
   test file exists); SUBSTANCE = whether it is ADEQUATE (did they read the
   RIGHT thing, is the test meaningful). A measure that can be satisfied by a
   fig leaf only checks form — accept that and design around it.
2. Put the machine on the FLOOR: hard-gate or WARN on absence of form (e.g.
   approve blocked if the evidence section is empty/placeholder/has no ref). This
   guarantees the reviewer is never asked to sign off on a zero-evidence
   artifact. Keep the check cheap and deterministic.
3. Leave SUBSTANCE to the human: the approval/review step IS the adequacy gate.
   Do not relocate that judgment onto a machine. Reject the LLM-judge option for
   routine gates — non-deterministic, expensive, another gate to maintain, and it
   diffuses accountability away from the person who is already there and
   responsible.
4. Encode the quality STANDARD where it is surfaced at authoring time (a
   checklist/template the author sees), not only inside the gate. Make the
   standard proportionate to blast radius (always-required dims + conditional
   dims for cross-boundary changes). The gate message itself should teach the
   standard when it blocks.
5. Make it backward-compatible: grandfather the pre-existing backlog
   (created-before-cutover = exempt from WARN; archive/legacy exempt) so the new
   check does not flood audit with un-actionable noise. Keep the hard-gate
   universal but provide an audited escape hatch (explicit flag, justify in a
   note) for genuine edge cases.

## Outputs

- A gate that checks form on the enforcement path (block/WARN), with substance
  left to the named human step.
- A surfaced standard (checklist/template) + a teaching gate message + a
  grandfather rule + an audited escape hatch.

## Notes

- Worked example (generalized): a proposal pipeline adds a hard research gate on
  `approve` that checks a Current State section's FORM (present, not placeholder,
  ≥1 `file:line` ref); whether the cited research is ADEQUATE stays the
  approver's call. A multi-dimension research standard (some dims always
  required, some conditional on blast radius) is surfaced at draft time via a
  checklist, not mechanized. An LLM-judge for adequacy was rejected as
  over-engineering + non-deterministic.
- This is the DESIGN PRINCIPLE of *what* to enforce mechanically vs *what* to
  leave to human judgment — distinct from the MECHANICS of *how* to implement a
  PreToolUse hard-block.
- Goodhart warning: once a measure becomes a target it stops being a good
  measure — which is exactly why form-only enforcement must be paired with human
  substance review, not trusted alone.

## Discovery

Surfaced as a universal guide at SessionStart (name + description; body lazy).
No separate router trigger is registered — the consuming project ships no
`INDEX.routing.json` by default, and universal-tier surfacing already makes this
skill consultable.

## See also

- `proposal-vs-plan-mode-vs-commit.md` and `proposal-drafting-checklist.md` —
  the gc proposal research gate is the canonical instance of this principle
  (machine checks the Current State form; the approver judges substance).
