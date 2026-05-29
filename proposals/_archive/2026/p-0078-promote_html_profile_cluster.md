---
id: P-0078
agent: core
status: implemented
created: 2026-05-29
approved_at: 2026-05-29
implemented_in: b547e1d
implemented_at: 2026-05-29
owner: core
---

# Proposal P-0078: Promote trade-agent HTML profile cluster (candidates #16 + #10)

## Trigger

User asked to review open candidate issues and promote the usable, generic ones
into public capabilities. The HTML-profile cluster (candidates #16 + #10, both
from consumer `trade-agent`, label `candidate`/`kind/mechanism`) is the cleanest:
both are generic, net-new vs current package source, and mechanically verified to
apply. Folding them into `governance_core/` ships to **all** downstream consumers
via the package, so this is a P-0065 maintainer curation decision — proposal
governance applies as the durable curation record (not as cross-actor handoff;
single-agent core authors+executes here).

## Scope

Two package-source files, one phase, additive only:

1. **#16 → `governance_core/tools/build_knowledge_dashboard.py`** — add HTML
   profile (P-0054) rendering: parse `<meta name="kc:*">` head tags + a
   `<p class="summary">` element via `_extract_html_frontmatter`, and render HTML
   knowledge entries through a sandboxed `<iframe>` modal with a `.modal-wide`
   panel for wider tables/diagrams. Payload form: unified diff (7 hunks).
   Verified: `git apply -p1 --recount --check` → CLEAN against current source
   (baseline `1fabb66…` drifted to `9c299fd…`; hunks re-locate by context).

2. **#10 → `governance_core/knowledge_governance/knowledge-html-profile.md`** —
   add §2.2.1 (optional cross-ref `kc:*` tags: `briefing` / `related` /
   `supersedes` / `superseded-by`, each 1:1 with .md frontmatter) and §3.3.1
   (Mermaid strict-mode pitfalls: label quoting, `\n` line breaks instead of
   `<br/>`, ASCII special chars). Verified: baseline `432b407…` == current
   source; diff is **pure additions** to existing content (no edits to prior
   sections). §2.2.1 explicitly references the `_extract_html_frontmatter` hook
   added by #16 — the spec and renderer are mutually consistent.

After apply: `governance-core upgrade --project-root .` to dogfood (Art.11.3),
then `python tools/candidate.py promote <env> --decision promoted` to record the
curation decision for each, and close issues #16 / #10.

## Non-Goals

- Candidate #11 (learn.md carrier gate) — separate evaluation/proposal; it
  changes an agent-facing skill workflow and references html-profile §1.
- Classify-fast cluster #12/#13/#14 — incomplete bundle (missing hook + config +
  helper payloads); blocked pending resubmission, out of scope here.
- Skills #8/#9 and bugs #2/#3 — handled in their own tracks.
- No change to the kc:* base spec (§2.2) or to existing dashboard markdown path;
  HTML rendering is an added branch, markdown entries are untouched.

## Guardrails

- **edit-write-guard**: not triggered — neither target is `CLAUDE.md` /
  `constitution/*`. Both are package-source files core owns (Art.2 table).
- **boundary-guard**: in-boundary (cwd = repo); no cross-project write.
- **sensitive-data-guard**: payloads already secret-scanned at uplink (P-0065);
  re-confirm no secrets in applied hunks.
- **Art.11.2**: edit `governance_core/` source ONLY — never the root autonomy-layer
  copies. Dogfood via `upgrade`, never hand-patch installed copies.
- **constitutional-review** (Art.4): #16 adds module-level regexes/maps — confirm
  no `.get(k, default)` config fallback is introduced.

## Phases

### Phase 0: Governance bootstrap

- Not applicable — no constitution / contract / agent_rules change. (Per
  /iterate-constitution this slot is empty for non-constitutional proposals.)

### Phase 1: Apply both payloads + dogfood + record curation

- Deliverables:
  - Apply #16 unified diff to `governance_core/tools/build_knowledge_dashboard.py`.
  - Apply #10 additions (§2.2.1, §3.3.1) to
    `governance_core/knowledge_governance/knowledge-html-profile.md`.
  - `governance-core upgrade --project-root .` to refresh the autonomy layer.
  - `candidate.py promote` (decision=promoted) for both envelopes; close #16/#10.
- Validation: see Validation Plan.
- Exit criteria: tests green; dashboard renders an HTML-profile entry; upgrade
  clean; curation registry records both as `promoted`; issues closed.

## Approval Criteria

- Reviewer confirms both payloads are generic common-layer (not trade-specific)
  and net-new vs current source — established in the review preceding this draft.
- Reviewer accepts that promotion ships to all consumers and is the intended
  P-0065 curation outcome for these two candidates.
- Diff applicability already verified mechanically (recount CLEAN / pure-add).

## Validation Plan

- `git apply -p1 --recount --check artifacts/candidate-review/issue16.fixed.patch`
  → CLEAN (already confirmed); then real apply.
- After apply: run the test suite (`python -m pytest` / `tools/test_*.py`) — in
  particular any `build_knowledge_dashboard` tests; add a smoke test rendering a
  minimal HTML-profile fixture if none exists.
- `python tools/build_knowledge_dashboard.py` (or its entrypoint) runs without
  error and an HTML entry surfaces in the modal.
- `governance-core upgrade --project-root .` exits 0; `governance-core doctor`
  exits 0.
- `python tools/candidate.py review` shows both candidates as `promoted`.
- Confirm wheel/sdist still package only `governance_core*` (Art.11.4) — unchanged
  here since no new top-level dir.

## Rollback / Recovery

- Pre-apply: working tree clean except known artifacts; `git stash`/`git checkout
  -- <file>` reverts either file independently (additive, no cross-file coupling
  at the code level beyond the doc reference).
- Post-commit: `git revert <hash>` restores prior dashboard + spec; re-run
  `upgrade` to roll the autonomy layer back. No data migration, no state schema
  change — rollback is pure code/doc revert.
- candidate registry: a mistaken `promoted` record can be re-recorded via
  `candidate.py promote --decision rejected/override`.

## Risks

- **HTML render = injection surface** (low/med): renders consumer-authored HTML.
  Mitigated — #16 uses a **sandboxed** iframe; existing `_DANGEROUS_TAGS` handling
  remains. Re-check sandbox attrs in review.
- **Diff drift on real apply** (low): `--recount --check` passed, but commit the
  apply before other edits so the tree state matches the verified check.
- **Spec/code divergence** (low): §2.2.1 names `_extract_html_frontmatter`;
  ensure the function name/behavior in the applied #16 matches the spec text.
- **Ceremonial-proposal critique** (accepted): single-agent self-review; weight
  justified by curation-record + all-consumer blast radius, documented in Trigger.

## State Log

- 2026-05-29: draft created by core agent (P-0078)
- 2026-05-29: draft → pending (submit HTML profile cluster promotion for maintainer review)
- 2026-05-29: pending → approved (user signal: 批准实施)
- 2026-05-29: approved → implemented
