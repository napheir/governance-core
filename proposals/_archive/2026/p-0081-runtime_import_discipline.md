---
id: P-0081
agent: core
status: implemented
created: 2026-05-29
approved_at: 2026-05-29
implemented_in: 53f003b
implemented_at: 2026-05-29
owner: core
---

# Proposal P-0081: Establish runtime-import-discipline invariant + doctor check (issue #3 root-cause)

## Trigger

Issue #3 ("auth-guard imports governance_core — breaks the copy-based 'runtime
never imports governance_core' invariant") was investigated and found to have a
stale premise but a valid core. Reality at 0.14.0: **6 hooks + 8 tools import
governance_core**, so the global "never import" invariant is not upheld. But the
*defensible* invariant is sharper — and auth-guard is its sole violator. User
chose the root-cause route: encode the invariant + a doctor check FIRST, then fix
auth-guard as the instance (a separate, higher-risk crypto refactor → P-0082).

**The sharpened invariant** (evidence-based): every current governance_core
importer EXCEPT auth-guard guards the import in `try/except` and **fails open**
(`sys.exit(0)`) — sensitive-data-guard even documents "auth-guard already fails
closed on a broken package." auth-guard alone (a PreToolUse `*` hook firing on
EVERY tool call) imports governance_core and **fails closed** (exit 2) on import
error → an unimportable/broken package freezes every tool call. A security gate
*must* fail closed on bad auth, so it cannot fail open on import error; therefore
it must be **self-contained**.

Touches governance documentation + adds an audit/doctor check → proposal applies.

## Scope

One phase, **no auth-guard code change** (that is P-0082). Establish + enforce
the invariant:

1. **New governance doc** `governance_core/knowledge_governance/
   runtime-import-discipline.md` (carrier_class: reference): states the invariant
   — *a hook that imports `governance_core` MUST guard the import and fail open;
   a hook that must fail closed (a security gate) MUST be self-contained (no
   `governance_core` import)* — with the rationale (freeze risk) and the current
   inventory (all importers fail-open except auth-guard).
2. **Doctor check** (extend `governance_core/installer.py` doctor, or a sibling
   audit invoked by it): scan each shipped hook in `hooks/`; if it imports
   `governance_core`, classify guarded-fail-open vs unguarded/fail-closed; a
   fail-closed importer is a violation. **auth-guard.py is grandfathered on an
   explicit, documented temporary-exception list** ("remove when P-0082 vendors
   it"), so doctor stays green now while the rule is enforced for all *new* hooks.
3. **Version bump** 0.14.0 → 0.15.0 (doctor check + doc ship in the wheel).

This mirrors the P-0075 prune-exempt pattern: grandfather the known violator,
enforce going forward, self-decay when the violator is fixed (P-0082 removes the
exception).

## Non-Goals

- **No auth-guard refactor** — the 636-line crypto vendor (codec + _ed25519 +
  revocation + pubkey.json) is P-0082, done carefully on its own.
- No change to the legitimately-fail-open importers (sensitive-data-guard, the
  SessionStart reminders, skill-usage-tracker) — they already comply.
- No change to tools importing governance_core (the invariant is about *hooks*
  that gate/observe tool calls, not CLI tools the user runs explicitly).
- Not (yet) a constitutional article — encoded as enforced governance doc +
  doctor check. If the user wants it entrenched in the constitution, that is a
  one-line Art.11 reference via /iterate-constitution (optional follow-up).

## Guardrails

- **edit-write-guard**: targets are package source (`governance_core/**`), not
  `CLAUDE.md`/`constitution/*` — not blocked. (Deliberately NOT a constitution
  edit, so /iterate-constitution is not required.)
- **Art.4**: the doctor check reads config/hook files with required-key access;
  no `.get(k, default)` config fallback.
- **doctor must stay exit 0**: the grandfather exception list keeps auth-guard
  from turning the new check red before P-0082.
- **Art.11.4**: new doc + any new check file under `governance_core/` — wheel
  stays `governance_core*` only.

## Phases

### Phase 0: Governance bootstrap

- Not applicable — encoded as a governance knowledge doc + doctor check, NOT a
  constitution/contract/agent_rules edit (see Non-Goals). No /iterate-constitution.

### Phase 1: Doc + doctor check (grandfather auth-guard)

- Deliverables:
  - Write `knowledge_governance/runtime-import-discipline.md` (invariant +
    rationale + inventory).
  - Add the doctor check + the documented `auth-guard.py` temporary-exception.
  - Bump 0.14.0 → 0.15.0.
  - Tests for the check (a self-contained hook passes; a fail-closed gc-importer
    is flagged; an exempted one passes).
  - `governance-core doctor` exit 0 (auth-guard grandfathered); dogfood upgrade.
  - wheel 0.15.0 isolation.
  - Comment on issue #3 recording the refined finding + the P-0081/P-0082 split;
    leave #3 OPEN (closed when P-0082 lands).
- Validation: see Validation Plan.
- Exit criteria: doc shipped; check detects fail-closed gc-importers + exempts
  auth-guard; doctor exit 0; tests green; wheel isolated.

## Approval Criteria

- Reviewer agrees with the sharpened invariant (fail-open-guarded OR
  self-contained; security gates self-contained) and the grandfather-then-fix
  sequencing (auth-guard fix deferred to P-0082).
- Reviewer accepts encoding as governance doc + doctor check (not a constitution
  article) for now.

## Validation Plan

- New check unit tests: self-contained hook → pass; synthetic fail-closed
  gc-importer → flagged; auth-guard → exempted (pass with a "tracked exception"
  note).
- `governance-core doctor` exit 0 with the new check active (auth-guard
  grandfathered, listed as a tracked exception).
- Full `tools/test_*.py` green; dogfood `governance-core upgrade` exit 0.
- wheel 0.15.0: top-level only `governance_core*`; the new doc + check present;
  `maintainer/` absent.

## Rollback / Recovery

- Pre-commit: `git checkout -- <files>` reverts.
- Post-commit: `git revert <hash>`; re-run `upgrade`. Doc + check are additive,
  no state/schema change — pure revert. The doctor check is advisory-grade (the
  exception list keeps it green), so a revert has no functional blast.

## Risks

- **Check false-positives/negatives** (low): static detection of "guarded
  fail-open" can be imprecise; mitigated by the explicit exception list + unit
  tests covering the discriminating cases. Worst case the check is advisory.
- **Invariant scope creep** (low): bounded to *hooks*; tools + fail-open
  importers explicitly out of scope.
- **auth-guard remains a freeze risk until P-0082** (accepted): unchanged from
  today; P-0081 only documents + tracks it. The risk is pre-existing and the
  issue is low-priority (consumers pip-install governance_core).
- **Version bump** 0.14.0 → 0.15.0.
- **Ceremonial-proposal critique** (accepted): single-agent self-review; weight
  justified by a new enforced governance rule + all-consumer blast radius.

## State Log

- 2026-05-29: draft created by core agent (P-0081)
- 2026-05-29: draft → pending (submit runtime-import-discipline invariant + doctor check (issue #3 root-cause); auth-guard vendor fix deferred to P-0082)
- 2026-05-29: pending → approved (user signal: 对,先批准P-0081)
- 2026-05-29: approved → implemented
