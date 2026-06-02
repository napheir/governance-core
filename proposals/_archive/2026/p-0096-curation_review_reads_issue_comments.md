---
id: P-0096
agent: core
status: implemented
created: 2026-06-02
approved_at: 2026-06-02
implemented_in: a913747
implemented_at: 2026-06-02
owner: core
---

# Proposal P-0096: Curation semantic-review must read issue comments before acting on needs-human candidates

## Trigger

Discovered while curating gc #26 (P-0095): the candidate's issue **body** was
factually wrong, but the submitter had posted a **correction comment** retracting
it. The body alone was known-wrong; only the comment carried the truth. Today the
hub-side curation path reads only the issue body:

- `maintainer/curate_gate.py::_fetch_issue_body` fetches `--json body --jq .body`
  — comments are never fetched.
- `maintainer/curate_routine.md`'s LLM branches (step 2 `needs-human` semantic
  review, step 3 `feedback` triage) say "do a semantic review" / "triage" but do
  NOT instruct the agent to read the issue comments first.
- `/curate-candidate` skill step 3 says "Fetch the issue body" (singular).

So an automated or semi-automated curation review can act on a stale/retracted
body and miss a submitter's correction. User directive: file this gap as a
proposal (option "b"). Changes curation automation policy + a hub mechanism →
proposal governance applies.

## Scope

Make the **LLM-judgment** layer read comments; leave the **deterministic gate**
body-only by design.

- `maintainer/curate_routine.md`: in step 2 (`needs-human` / valid non-T0
  semantic review) and step 3 (`feedback` triage), add an explicit instruction:
  before recommending promote/hold/fix, fetch and read the issue comments
  (`gh issue view <N> --json comments`), and treat a submitter self-correction as
  authoritative over the original body (a comment may retract or revise the
  candidate). Mirror this in the embedded routine prompt.
- `governance_core/commands/curate-candidate.md` step 3: "Fetch the issue body"
  -> "Fetch the issue body **and comments**" + a one-line note that a submitter
  correction in a comment can supersede the body (cite gc #26 as the precedent).
- Optional (decide at implementation): a tiny helper
  `maintainer/curate_gate.py::_fetch_issue_comments(repo, issue)` for the routine
  to call — NOT wired into `evaluate()` (see Non-Goals).

## Non-Goals

- **Do NOT let comments affect the deterministic auto-promote gate.**
  `curate_gate.evaluate()` stays body/envelope-only: a comment must never flip
  `eligible` true/false. The trust model (P-0090) is that auto-promote is purely
  deterministic from the embedded envelope; free-text comments are LLM-judgment
  input only, never an auto-promote signal. (If anything, a fresh correction
  comment is a reason to route to a human, never to auto-promote.)
- No change to the candidate-intake CI (it acts on `issues.opened` before any
  comment exists).
- No new GitHub API scopes (gh already reads comments).

## Guardrails

edit-write-guard (curate-candidate.md is package source; curate_routine.md is
maintainer doc — both editable, not constitution files); boundary-guard (in-repo).
No command/sensitive-data surface.

## Phases

### Phase 0: Governance bootstrap

- Deliverables: this proposal (P-0096), submitted for user review.
- Validation: user approval signal before implementation.
- Exit criteria: approved.

### Phase 1: Wire comment-reading into the LLM review layer

- Deliverables: curate_routine.md steps 2/3 + embedded prompt updated;
  curate-candidate.md step 3 updated; optional `_fetch_issue_comments` helper +
  a test if added; version bump if package source (curate-candidate.md) changes.
- Validation: full `tools/test_*.py` suite green; if a helper is added,
  `test_curate_gate.py` covers it; `governance-core upgrade --project-root .` +
  `doctor` exit 0; wheel isolation; manual read-back that the gate's determinism
  is unchanged (comments do not feed `evaluate`).
- Exit criteria: committed referencing P-0096; archived.

## Approval Criteria

- The deterministic gate remains body-only (comments cannot change auto-promote
  eligibility) — reviewer can confirm `evaluate()` signature/inputs unchanged.
- The LLM review + the skill explicitly require reading comments before a
  promote/hold/fix recommendation, with submitter corrections authoritative.

## Validation Plan

1. Read-back of curate_routine.md + curate-candidate.md: comment-reading is
   mandatory in the LLM branches; gate stays body-only.
2. `python -m pytest tools/ -q` + script-style suite green.
3. If a helper lands: `governance-core upgrade --project-root .` + `doctor` → 0;
   wheel top-level only `governance_core*`.

## Rollback / Recovery

Revert the doc/prompt edits (single commit). If the optional helper landed,
revert it too. No state to migrate; the deterministic gate is untouched.

## Risks

- **Low — scope creep into the gate.** Mitigated by the explicit Non-Goal: the
  deterministic gate stays body-only; only the LLM layer reads comments.
- **Low — comment-injection.** A malicious comment could try to talk the LLM
  reviewer into promoting. Mitigated because the LLM branch never auto-promotes
  (only the deterministic gate promotes, and it ignores comments); the LLM only
  recommends promote/hold and a human acts.

## State Log

- 2026-06-02: draft created by core agent (P-0096)
- 2026-06-02: draft → pending (submit for review: file the curation-reads-comments gap (task b) per user directive)
- 2026-06-02: pending → approved (user directive: '批准实施P-0096' (explicit approval to implement))
- 2026-06-02: approved → implemented
