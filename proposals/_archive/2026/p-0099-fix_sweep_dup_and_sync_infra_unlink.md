---
id: P-0099
agent: core
status: implemented
created: 2026-06-12
approved_at: 2026-06-12
started_at: 2026-06-12
implemented_in: 6916183
implemented_at: 2026-06-12
owner: core
---

# Proposal P-0099: Fix candidate sweep duplicate uplink (#90) + sync_infra tracked-hook deletion (#91)

## Trigger

Two consumer-reported bugs in package-source governance tooling (hub issues
**#90**, **#91**). Both ship to consumers via `upgrade`, so the fix is a
package-source change → PROPOSAL_REQUIRED. Root causes verified against current
source (see Scope). #90 directly explains the duplicate candidate uplink curated
in P-0098 (#87/#89).

## Scope

**Phase 1 — #90: `candidate.py sweep` duplicate uplink.**
- **RC1 (correctness)** `governance_core/tools/candidate.py` `cmd_sweep`: the
  `pending` list is built by scanning `is_uplinked(led, digest)` against the
  pre-scan in-memory ledger; two same-digest envelopes both pass and both
  uplink (the in-loop `record_uplink` writes to disk but `pending` is already
  fixed and the in-memory `led` is not updated). Fix: **dedup `pending` by
  digest** (keep one envelope per unique digest) before the uplink loop.
- **RC2 (amplifier)** `governance_core/candidates/collect.py`
  `collect_netnew_skills`: rebuilds a date-stamped envelope for every
  candidate-common skill every run, accumulating same-digest dirs across days.
  Fix: **skip building** when an outbox envelope with the same payload digest
  already exists (`skill_digest` vs existing `payload_digest`).

**Phase 2 — #91: `sync_infra._remove_local_copy` deletes git-tracked hooks.**
- `governance_core/tools/sync_infra.py` `_remove_local_copy` unconditionally
  `target.unlink()`s the clone's local hook for every `CENTRAL_HOOKS` entry.
  The 6 centralized hooks are gc-managed AND git-tracked in consumers, so git
  restores them and every sync re-deletes → perpetual uncommitted-deletion
  churn. Fix: **skip unlink when the local copy is git-tracked**
  (`git ls-files --error-unmatch <rel>` in the clone returns 0) — only remove
  genuinely-orphan untracked copies (the original migration intent). The
  `settings.local.json` reference-rewrite half stays unchanged.

Net-new unit tests for each fix; version bump (0.26.0 → 0.27.0); close #90/#91.

## Non-Goals

- No hub-side existing-issue guard for #90 (a network query per uplink; the
  RC1 dedup already stops duplicates — note it as a possible later hardening).
- No change to the date-stamped envelope id **format** (RC2 fix dedups by
  digest, it does not re-key the outbox dir by digest).
- No change to the `settings.local.json` reference-rewrite logic in #91.
- Single-agent hub does not exercise sync_infra (no clones); #91 is verified by
  unit test, not symptom dogfood (cf. hub-cannot-dogfood-crlf-drift).

## Guardrails

- `edit-write-guard`: package-source `.py` edits — not constitution files,
  allowed. `governance_core/` source edited, never the autonomy copy (Art.11.2).
- `boundary-guard` / `command-guard`: edits + tests inside repo boundary; new
  `git ls-files` subprocess in #91 is read-only.
- No `sensitive-data-guard` surface.

## Phases

### Phase 1: #90 — sweep/collect dedup by digest

- Deliverables:
  - `candidate.py cmd_sweep`: dedup `pending` by digest (RC1).
  - `collect.py collect_netnew_skills`: skip same-digest existing envelope (RC2).
  - Net-new test: `tools/test_candidate_sweep.py` (or extend) — two same-digest
    pending envelopes → exactly one uplink; collect twice → one envelope.
- Validation: new test + full `pytest tools/` green.
- Exit criteria: a sweep over ≥2 same-digest envelopes creates exactly one
  uplink; collect is idempotent for an unchanged skill.

### Phase 2: #91 — skip unlink of git-tracked centralized hooks

- Deliverables:
  - `sync_infra._remove_local_copy`: `git ls-files --error-unmatch` guard;
    tracked → keep (status `[KEEP]`), untracked orphan → unlink as before.
  - Net-new test: tracked file kept, untracked file removed.
- Validation: new test + full `pytest tools/` green; `sync_infra --execute`
  dry-run shows `[KEEP]` (not `[DEL]`) for the 6 tracked central hooks.
- Exit criteria: a tracked centralized hook is no longer unlinked; an untracked
  orphan still is.

## Approval Criteria

- Both root causes match the cited code; both fixes are minimal and localized.
- RC1 dedup-by-digest is accepted as the primary #90 fix (RC2 is hygiene).
- The git-tracked guard is accepted as the #91 fix; settings rewrite untouched.

## Validation Plan

- `python -m pytest tools/` green (incl. the two net-new tests).
- `governance-core upgrade --project-root .` + `doctor` exit 0.
- Wheel isolation: top-level only `governance_core*`, no `maintainer/` leak.
- Manual: simulate two same-digest envelopes → `candidate.py sweep --dry-run`
  reports one would-uplink (hub project skips real uplink; use a fixture).

## Rollback / Recovery

- Each phase is an isolated function edit + test; revert the file(s) + version
  bump and re-`upgrade`. No state migration, no data at risk.
- Pre-archive: revert commit, re-open the issues.

## Risks

- **Low**. Both fixes narrow behavior (dedup / skip-a-delete); neither changes
  the happy path.
- #90 RC2 collect-dedup must compare the SAME digest the ledger/uplink use
  (`skill_digest` vs `payload_digest` of the built envelope) — mis-keying would
  either over-skip (miss a genuine change) or under-skip (no hygiene gain);
  covered by the idempotency test.
- #91 `git ls-files` in a non-repo / detached path must fail safe (treat
  non-zero as "not tracked" → preserve current delete behavior); covered by
  the untracked-file test.

## State Log

- 2026-06-12: draft created by core agent (P-0099)
- 2026-06-12: draft → pending (submit for review: fix #90 sweep dup + #91 sync_infra tracked-hook unlink, 2 phases)
- 2026-06-12: pending → approved (user approval: '批准')
- 2026-06-12: approved → in-progress
- 2026-06-12: in-progress → implemented
