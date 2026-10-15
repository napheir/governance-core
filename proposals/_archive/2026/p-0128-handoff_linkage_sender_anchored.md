---
id: P-0128
agent: core
status: implemented
created: 2026-10-09
approved_at: 2026-10-09
started_at: 2026-10-09
implemented_in: 3876c9c
implemented_at: 2026-10-15
related: [P-0126]
owner: core
---

# Proposal P-0128: Sender-anchored cross-agent handoff linkage (candidate #139): related-by-id, then handoff_to + open-handoff audit

## Trigger

Candidate issue #139 (`kind: mechanism`, `layer: candidate-common`, from
trade-agent; intake: `needs-human`). In a multi-agent proposal system a
research → implementation handoff loses its chain when the implementing agent
drafts a fresh proposal: the implementer works in its own scope and cites
nothing about the origin, so the gap is undetectable from its side. The
candidate anchors the link on the SENDER (the only side with a mechanical,
cross-scope signal) and keeps a missing link as a standing audit WARN.

Curation verdict (2026-10-09): in charter (proposal state machine, audit,
session surface), generic, sound. But it is a contract change plus four code
surfaces, and the bundle carries a design brief only -- no code. Capability add
+ `contracts/` change → PROPOSAL_REQUIRED, human approval required.

## Current State (read, not assumed)

- **`related` exists but is free-form and unvalidated.**
  `governance_core/contracts/proposal_frontmatter_schema.md:156` (§4.6, schema
  v1.3.0): `related | list[string] | conceptually linked proposals or knowledge
  entries`. `governance_core/tools/proposal_lib.py:193` only orders it when
  serializing. `governance_core/tools/audit_proposals.py` never reads it (grep
  for `related`: no hit). No `handoff_to` anywhere in `governance_core/`.
- **Audit checks end at 17** (`audit_proposals.py:44`, `:270` -- Check 17 is the
  `upstreamed_to` external-ref format, P-0123). The `upstreamed` terminal is the
  precedent for a deliberately single-directional, record-don't-resolve link.
- **Scope-owner inference exists.** `governance_core/tools/proposal_suggest.py:228`
  `load_allow_map` builds `{agent: [owned prefixes]}` from
  `agent_rules/*.allow.txt`; `:269` `scope_hits` maps description path tokens to
  owners. `proposal_lib.py:1458` calls `_emit_create_recall(args.title)` inside
  `_cmd_create` (`:1451`) -- the natural hook point for a create-time hint.
- **Session surface exists.** `governance_core/hooks/session-context.py:435`
  `_check_proposals(root, role)` already scans the self bucket and other agents'
  buckets by frontmatter status.
- **The hub cannot dogfood the handoff half.** `.governance/config.json:12` lists
  one agent (`core`); `agent_rules/` holds only `shared.*` files, so
  `load_allow_map` returns `{}` and every handoff signal is empty by
  construction here. Only 2 archived proposals carry a `related:` field. The
  `related`-by-id half IS exercisable on the hub.
- **Bundle completeness.** #139's payload is `gc-handoff-linkage-brief.md` only.
  The brief states "a working reference implementation exists in a consumer
  project" with tests; none of it was uploaded. Comments: intake only, no
  submitter correction.

## Scope

Phase A (hub-dogfoodable):
- `governance_core/contracts/proposal_frontmatter_schema.md` -- v1.3.0 → v1.4.0:
  `related` elements may be a global proposal id `P-NNNN` (in addition to a
  relative path); single-directional.
- `governance_core/tools/audit_proposals.py` -- Check 18 (FAIL): every `P-NNNN`
  element of `related` resolves to an existing proposal.
- `governance_core/commands/proposal.md` -- document `related`-by-id.
- Tests in `governance_core/tools/`.

Phase B (multi-agent only; needs the consumer's reference diff):
- Same contract: add `handoff_to` (§4.6) + closure semantics → v1.5.0.
- `governance_core/tools/proposal_suggest.py` -- `handoff_targets(desc,
  drafting_agent, amap)` with the per-token co-owner skip.
- `governance_core/tools/proposal_lib.py` -- create-time advisory hint; add
  `handoff_to` to the serializer field order.
- `governance_core/tools/audit_proposals.py` -- Check 19 open-handoff (WARN),
  Check 20 missing-`handoff_to` backstop (WARN, cutover-dated).
- `governance_core/hooks/session-context.py` -- "Open handoffs to you".
- `governance_core/commands/proposal.md` -- `handoff_to` semantics + red line.

## Design & Contract

### Interfaces, I/O & Realization

**A1. `related` by id** (contract). INPUT: frontmatter `related: [P-0123,
../x.md]`. An element matching `^P-\d{4}$` is an id; anything else keeps today's
meaning (path / knowledge entry, unvalidated). Realizer: authored by the
drafting agent in the proposal body's frontmatter (via Edit of the body file is
NOT allowed for frontmatter -- so `proposal_lib.py` gains
`link --id P-NNNN --related P-MMMM`, the realizer for the mutation).

**A2. Check 18** (`audit_proposals.py`, realizer = `python tools/audit_proposals.py`
run by `/wrap-up` 2c and CI). INPUT: the scanned corpus (in-flight ∪ archive ∪
legacy) plus `shared_state/proposals/_id_ledger.json`. OUTPUT: one FAIL line per
`related` id that resolves in neither. No reverse-reference requirement.

**B1. `handoff_to: <agent>`** (contract). Set on a proposal that recommends work
in another agent's scope and expects a SEPARATE implementing proposal. Allowed
values: the agent names in `.governance/config.json` `agents[].name`. Realizer
of the mutation: `proposal_lib.py link --id P-NNNN --handoff-to <agent>`.

**B2. `proposal_suggest.handoff_targets(desc: str, drafting_agent: str, amap:
dict) -> list[str]`** -- owners `scope_hits` infers from `desc`, minus
`drafting_agent`, skipping any token the drafting agent co-owns. Pure. Consumed
by B3 and Check 20.

**B3. Create hint** -- `_cmd_create` prints an advisory line when
`handoff_targets` is non-empty. stdout only; no lifecycle write.

**B4. Check 19 open-handoff (WARN)** -- a `handoff_to: X` proposal is OPEN until
(a) it is terminal-done and owned by X, or (b) some proposal owned by X lists its
id in `related`. **Check 20 backstop (WARN)** -- an in-flight, non-terminal draft
created on/after the cutover date whose title targets another agent's exclusive
scope but has no `handoff_to`.

**B5. Session surface** -- `session-context.py` lists proposals with
`handoff_to == <this agent>` that are not closed. Realizer: the SessionStart
hook, regex scan only, no `governance_core` import (runtime-import discipline).

### Field Dictionary

| field | type | meaning | producer | consumer | constraints / allowed values |
|-------|------|---------|----------|----------|------------------------------|
| `related` (extended) | list[string] | linked proposals; element may now be a global id | drafting agent via `proposal_lib link` | Check 18, Check 19 closure (b) | `contracts/proposal_frontmatter_schema.md` §4.6; id form `^P-\d{4}$`, else free-form as today |
| `handoff_to` (new, Phase B) | string | target agent of a cross-agent research→impl handoff | sending agent via `proposal_lib link` | Check 19, Check 20, session-context | `contracts/proposal_frontmatter_schema.md` §4.6; one of `agents[].name`; optional |

### Flow

```
Phase A:  author sets related: [P-NNNN] → audit Check 18 → resolve in corpus ∪ id-ledger → FAIL on typo
Phase B:  sender drafts → create hint (handoff_targets) → handoff_to: X
          → audit Check 19 WARN (every run) + X's SessionStart "Open handoffs to you"
          → X implements own proposal with related: [sender id] → Check 19 closes
```

## Non-Goals

- Implementer-side detection (the brief shows it is inverted: the implementer is
  `agent == owner`).
- Any BLOCK: every handoff check is WARN; only a malformed id reference FAILs.
- Reverse back-reference requirement on the target (mirrors `upstreamed`).
- The consumer's `from_todo` / todo-graduation bridge (explicitly excluded by #139).
- Verbal / out-of-band handoffs: handled by the documented red line, not code.

## Open Questions

- **Phase B without the reference diff?** Leaning: WAIT. The brief's
  make-or-break details (per-token co-owner skip, closure predicate, cutover
  grandfathering) were tuned against a real multi-agent corpus the hub does not
  have; re-deriving them here means shipping multi-agent logic the hub cannot
  exercise. #139 has been asked for the diff. If it does not arrive, implement
  from the brief with synthetic multi-agent fixtures.
- **Is a new `link` subcommand the right mutation path?** Leaning YES: the
  `/proposal` skill forbids hand-editing frontmatter, and neither `related` nor
  `handoff_to` has a writer today. Alternative: accept them as `create` flags only.
- **Should Check 18 also accept ids that exist only in the id-ledger (allocated,
  file not visible in this clone)?** Leaning YES (the brief's "corpus ∪ ledger"):
  in a multi-clone consumer the origin often lives in another clone.
- **Phase A alone worth shipping?** Leaning YES: it gives `related` a validated
  form on every topology and is the closure key Phase B depends on.

## Alternatives & Rationale

- **Reject as multi-agent-only / not dogfoodable.** Rejected: governance-core
  ships multi-agent machinery to consumers (Art.5 is "inherited, degraded" here,
  not absent); undogfoodable parts get fixture tests, as P-0057 / P-0123 did.
- **Promote verbatim from the brief in one phase.** Rejected: a contract bump +
  hook + audit + suggest change with no reference code and no live multi-agent
  corpus is the highest-risk shape; a wrong WARN that never closes trains agents
  to ignore the audit.
- **Ask for the code and hold everything.** Rejected: `related`-by-id is
  independently useful and unblocks Phase B.
- **Chosen**: Phase A now (after approval), Phase B on the reference diff.

## Guardrails

- Contract change → version bump + `/wrap-up`; no constitution text changes
  (`/iterate-constitution` not triggered: Art.3/Art.5 already point at the contract).
- `session-context.py` change (Phase B): regex-only, no new `governance_core`
  import; fail-open; `runtime_import_audit` unaffected.
- The status-enum family is NOT touched (no new status), so the multi-site
  enum checklist does not apply; the frontmatter FIELD family does: schema §4.6,
  serializer field order, audit, skill doc.
- Art.4: no `.get(k, default)` in new package code.

## Phases

### Phase A: related-by-id + Check 18

- Deliverables: schema v1.4.0; `proposal_lib link --related`; Check 18; skill doc; tests.
- Validation: audit over the real corpus stays 0 failures; fixture with a typo id FAILs; an id present only in the ledger resolves.
- Exit criteria: suites green; `doctor` exit 0.

### Phase B: handoff_to + open-handoff audit + session surface

- Deliverables: schema v1.5.0; `handoff_targets`; create hint; Checks 19/20; session surface; skill doc; multi-agent fixture tests.
- Validation: fixture reproduces the brief's worked example -- open-handoff opens, closes on back-link; shared-dir token does not false-fire; single-agent hub emits nothing.
- Exit criteria: suites green; zero new WARN on the hub corpus.

## Approval Criteria

- [ ] Every Field Dictionary entry names its governing contract — human-verify: both rows cite proposal_frontmatter_schema.md §4.6
- [ ] Every mutation has a named realizer — human-verify: `proposal_lib link` named for both fields
- [ ] Open Questions decided by the approver — human-verify: four questions each resolved or deferred
- [ ] Phase A: audit clean on the real corpus — cmd: python tools/audit_proposals.py
- [ ] Phase A: typo id FAILs, ledger-only id resolves — cmd: python -m pytest tools/test_audit_proposals_related.py -q
- [ ] Phase B: handoff fixture opens and closes; single-agent emits nothing — cmd: python -m pytest tools/test_handoff_linkage.py -q
- [ ] Self-install healthy — cmd: governance-core doctor

## Validation Plan

Per phase: the commands above + `pytest tools/` + all script-style suites +
`upgrade` / `doctor` + wheel isolation check. Phase B additionally replays the
consumer's reference tests if the diff arrives.

## Rollback / Recovery

Phase A: revert; `related` ids become unvalidated free-form strings again (still
valid under v1.3.0). Phase B: revert; `handoff_to` is optional, so existing
proposals carrying it stay schema-valid under "unknown optional field" only if
the audit tolerates it -- confirm before release, else ship a one-line tolerance.

## Risks

- **Standing WARN fatigue** (medium, Phase B): a handoff fulfilled in place never
  closes until someone back-links. Mitigation: documented in the skill; closure
  (a) covers the target-implemented case.
- **Undogfoodable logic rots** (medium, Phase B): fixtures only. Mitigation: wait
  for the consumer diff + its tests; consumer runs it live.
- **Contract bump breaks consumer audits** (low): both changes are additive and
  optional.

## State Log

- 2026-10-09: draft created by core agent (P-0128)
- 2026-10-09: draft → pending (submit for owner review: candidate #139; needs-human (contract change); Phase B waits on consumer reference diff)
- 2026-10-09: pending → approved (owner approval 2026-10-09: '1. 批准，并接受你在proposal中的倾向' -- Open Questions resolved per stated leanings: Phase B WAITS for the consumer reference diff; link subcommand YES; ledger-only ids resolve YES; Phase A ships alone YES)
- 2026-10-09: approved → in-progress (Phase A start)
- 2026-10-09: linked related P-0126
- 2026-10-15: in-progress → implemented (Phase B landed (consumer reference diff on #139, adapted: link --handoff-to writer, rejected closes, --root allow map, in-repo shared_state); reconcile: all scope files touched, extras = STATE/manual/version/test)
