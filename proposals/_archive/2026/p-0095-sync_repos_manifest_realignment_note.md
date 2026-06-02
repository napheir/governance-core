---
id: P-0095
agent: core
status: implemented
created: 2026-06-02
approved_at: 2026-06-02
implemented_in: b73cc8c
implemented_at: 2026-06-02
owner: core
---

# Proposal P-0095: Doc-note: realign gitignored manifest via upgrade after /sync-repos merge

## Trigger

Curation of candidate issue gc #26 (`mechanism`, from trade-agent). User
directive: "curate 这两个 candidate" + explicit "Promote 更正后的内核". The
candidate's submitted body is **factually wrong** (verified against this hub's
own `sync-repos.md`) and was **retracted by the submitter in a follow-up
comment**. We promote only the submitter's *corrected* kernel. Changing shipped
skills (`sync-repos.md`, `wrap-up.md`) is a package-source capability change →
proposal governance applies.

## Scope

Add a corrected manifest-realignment doc-note to the package-source skills:

- `governance_core/commands/sync-repos.md` — a note that `/sync-repos` (git
  merge) correctly carries gc-managed *file content* (merge-exemption +
  `--no-verify`), but git does NOT carry the **gitignored**
  `installed_files.json` manifest; after a sync that pulled gc-managed files,
  run `governance-core upgrade --project-root <clone>` to realign the manifest,
  else the next `upgrade` misclassifies the merge-imported files as drift (noise,
  not data loss; nothing is lost).
- `governance_core/commands/wrap-up.md` Step 5b — one-line cross-reference to the
  same rule.
- Ledger `promoted` record for gc #26 noting the corrected (not as-submitted)
  scope; close issue #26 with an outcome comment.

## Non-Goals

- Do NOT ship the candidate's as-submitted claims ("sync can't carry gc-managed
  files", "git-merge silently destroys local drift") — both are false:
  `/sync-repos` Step 2 is `git merge`, Step 4 `--no-verify` exists precisely
  because `check_scope.py`'s `MERGE_HEAD` exemption covers the merge stage.
- No behavior change to `upgrade` / `sync_infra` / `sync-repos` — doc-note only.
- Does NOT auto-invoke `upgrade` from `/sync-repos` (the submitter floated this
  as an optional product fix; out of scope — flagged for a future candidate).
- Does NOT fix CRLF false drift — that is P-0094.

## Guardrails

edit-write-guard (command .md sources are package source, not constitution
files — allowed); boundary-guard (in-repo). No other guard surface.

## Phases

### Phase 0: Governance bootstrap

- Deliverables: this proposal (P-0095) created + approved by explicit user
  "Promote" directive.
- Validation: user directive recorded as approval signal.
- Exit criteria: status approved.

### Phase 1: Ship corrected doc-note

- Deliverables: corrected note in `sync-repos.md` + `wrap-up.md` Step 5b;
  version bump; ledger `promoted` (corrected scope) for gc #26; issue #26 closed
  with an outcome comment thanking the contributor and crediting the correction.
- Validation: full `tools/test_*.py` suite green (doc-only change should not
  perturb tests); `governance-core upgrade --project-root .` + `doctor` exit 0;
  wheel-isolation; the shipped note states the *corrected* rule, not the
  retracted body.
- Exit criteria: committed referencing P-0095; issue closed.

## Approval Criteria

- The shipped note reflects the corrected rule (manifest realignment), NOT the
  retracted body.
- Technical premise verified: `sync-repos.md` Step 2 = `git merge`, Step 4 =
  `--no-verify` due to `MERGE_HEAD` exemption (confirmed in current source).
- Note is generic to any multi-clone gc consumer; hub is single-agent so it does
  not dogfood the path (acknowledged).

## Validation Plan

1. `python -m pytest tools/ -q` from repo root — full suite green.
2. `governance-core upgrade --project-root .` then `doctor` → 0.
3. `python -m build --wheel`; wheel top-level only `governance_core*`, no
   `maintainer/` leak.
4. Manual read-back: the note does not contain the retracted false claims.

## Rollback / Recovery

Revert the two doc edits (single commit). No state to migrate.

## Risks

- **Low — shipping wrong guidance.** Mitigated by promoting the corrected kernel
  only (read from the submitter's correction comment, not the issue body) — the
  exact discipline this curation demonstrates.
- **Low — note never dogfooded by hub.** The hub is single-agent; the rule is
  for multi-clone consumers. Acknowledged; the premise was verified against the
  shipped `sync-repos.md` source instead.

## State Log

- 2026-06-02: draft created by core agent (P-0095)
- 2026-06-02: draft → pending (submit for review)
- 2026-06-02: pending → approved (user directive: 'curate 这两个 candidate' + AskUserQuestion answer 'Promote 更正后的内核')
- 2026-06-02: approved → implemented
