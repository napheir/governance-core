---
id: P-0079
agent: core
status: implemented
created: 2026-05-29
approved_at: 2026-05-29
implemented_in: 471f230
implemented_at: 2026-05-29
owner: core
---

# Proposal P-0079: Promote trade-agent /learn carrier-class gate (candidate #11), de-trade-ified

## Trigger

Second item in the user-approved candidate-curation priority list (after the
HTML-profile cluster, P-0078). Candidate #11 (from consumer `trade-agent`,
`kind/mechanism`) adds a mandatory **Step 0** to the `/learn` skill: declare
`carrier_class` (P-0053) + carrier form (MD vs HTML profile, P-0054) before any
`knowledge/**` write. Folding it into the core `/learn` skill changes an
agent-facing workflow and ships to all consumers — a P-0065 curation decision,
so proposal governance applies (same rationale as P-0078).

## Scope

One package-source file, one phase:

**#11 → `governance_core/commands/learn.md`** — insert a `### Step 0: 判定
carrier_class + 载体形式` section between `## 执行流程` and `### Step 1`,
containing: Step 0.1 carrier_class decision table (6 classes), Step 0.2
carrier-form (MD vs HTML profile) decision table, Step 0.3 declared-output
format, and a 误用红线 list. Both referenced docs already exist in package
source: `knowledge_governance/knowledge-carrier-classes.md` §2 (P-0053) and
`knowledge-html-profile.md` §1 (P-0054, just extended by P-0078).

**Curation edit — de-trade-ify the examples.** The verbatim payload's examples
are trade-flavored (`knowledge/trading/trade-end-to-end-flow.html`, the phrase
`写"trade 全流程"`). Since this ships to ALL consumers, replace trade-specific
examples with domain-neutral ones (e.g. `knowledge/<domain>/<topic>-flow.html`,
drop "trade" from the red-line bullet). The mechanism is preserved verbatim;
only the illustrative examples are genericized.

Verification (done): semantic diff (`git diff --ignore-cr-at-eol`) of the
payload vs current source is **2 hunks / 44 additions / 0 deletions** — pure
add (the raw diff's noise was CRLF-vs-LF; sha differed for the same reason, the
content is otherwise baseline-equal). No conflict with current source.

After apply: `governance-core upgrade --project-root .` dogfood, then
`candidate.py promote <env> --decision promoted` and close issue #11.

## Non-Goals

- No change to the carrier-class/HTML-profile specs themselves (P-0053/54 docs
  unchanged; this only adds the decision *gate* to /learn).
- Not importing the payload's trade-specific examples verbatim (genericized).
- Other open candidates (#12/#13/#14 classify, #8/#9 skills) — separate tracks.
- No change to /wrap-up Step 3 (which invokes /learn) — the gate lives in /learn.

## Guardrails

- **edit-write-guard**: `/learn` is `governance_core/commands/learn.md`, NOT
  `CLAUDE.md`/`constitution/*` — not blocked; core owns it (Art.2). (Note: the
  skill text is the single source of truth — Art.99 appendix; this proposal
  adds a section, it does not duplicate skill steps into the constitution.)
- **boundary-guard**: in-boundary; no cross-project write.
- **Art.11.2**: edit `governance_core/` source only; dogfood via `upgrade`.
- **sensitive-data-guard**: doc-only payload, no secrets.

## Phases

### Phase 0: Governance bootstrap

- Not applicable — no constitution / contract / agent_rules change. Adding a
  step to a skill body is not a constitutional edit (skill is its own SoT).

### Phase 1: Insert genericized Step 0 + dogfood + record curation

- Deliverables:
  - Edit `governance_core/commands/learn.md`: insert the Step 0 section after
    `## 执行流程`, with trade-specific examples replaced by domain-neutral ones.
  - `governance-core upgrade --project-root .` to refresh the autonomy layer.
  - `candidate.py promote` (decision=promoted, note records the de-trade-ify) +
    close issue #11.
- Validation: see Validation Plan.
- Exit criteria: Step 0 present in package source + dogfooded copy; references
  resolve; no trade leakage; registry records `promoted`; issue #11 closed.

## Approval Criteria

- Reviewer agrees the carrier-class gate is generic common-layer discipline and
  that the trade-specific examples should be genericized before shipping.
- Reviewer accepts adding a *mandatory* Step 0 to the core /learn workflow.
- Net-new vs current source confirmed (no Step 0 today); references present.

## Validation Plan

- After edit: `grep -n "Step 0\|carrier_class\|carrier_form"
  governance_core/commands/learn.md` shows the new section; `grep -ni "trade"`
  shows no trade leakage in the added lines.
- Confirm referenced anchors exist: `knowledge_governance/
  knowledge-carrier-classes.md` §2 and `knowledge-html-profile.md` §1.
- Full test suite `tools/test_*.py` stays green (skill text isn't unit-tested,
  but run to confirm no collateral breakage); `audit_knowledge` unaffected.
- `governance-core upgrade --project-root .` exits 0; dogfooded
  `.claude/commands/learn.md` carries Step 0.
- `candidate.py review` shows #11 `promoted`.

## Rollback / Recovery

- Pre-commit: `git checkout -- governance_core/commands/learn.md` reverts.
- Post-commit: `git revert <hash>` removes the Step 0 section; re-run `upgrade`.
- Doc-only, additive, no state/schema change — rollback is a pure revert.

## Risks

- **Trade leakage if genericization is incomplete** (low): mitigated by the
  `grep -ni trade` validation gate on the added lines.
- **Mandatory gate adds friction to every knowledge write** (low/accepted):
  intended — it enforces existing P-0053/54 carrier discipline that today is
  only documented, not gated. Consumers who dislike it can edit their own
  install-managed copy (autonomy carve-out), though that drifts.
- **Version bump** (process): like P-0078, learn.md ships in the wheel — bump
  0.10.0 → 0.11.0 so consumers receive the gate via `upgrade`.
- **Ceremonial-proposal critique** (accepted): single-agent self-review;
  weight justified by all-consumer blast radius + curation-record (as P-0078).

## State Log

- 2026-05-29: draft created by core agent (P-0079)
- 2026-05-29: draft → pending (submit /learn carrier-gate promotion (de-trade-ified) for maintainer review)
- 2026-05-29: pending → approved (user signal: 批准)
- 2026-05-29: approved → implemented
