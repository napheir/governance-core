---
id: P-0097
agent: core
status: implemented
created: 2026-06-03
approved_at: 2026-06-03
implemented_in: cb50227
implemented_at: 2026-06-03
owner: core
---

# Proposal P-0097: Repo-deletion hardening: gh/API deny patterns + delete_repo token-scope check in doctor (gc #85)

## Trigger

Curation of candidate gc #85 (`mechanism`, trade-agent) — "Repo-deletion
hardening". User directive: "看看新的candidate，我们需要做一些防御" + AskUserQuestion
answer choosing doctor integration for the token-scope verifier. #85 is a strict
**superset** of sibling #84 (its deny-list payload contains all 4 of #84's gh
patterns), so #84 is superseded by this. Touches a security hook deny-list +
installer doctor path → proposal governance applies.

## Scope

Close command-line GitHub repo-removal vectors at two layers:

- **Deny-list (command-guard Layer 1.5)** — add 11 patterns to
  `governance_core/agent_rules/shared.deny_commands_regex.txt` (pure-add,
  verified by `git diff --ignore-cr-at-eol`):
  - 4 gh-CLI: `gh repo delete`, `gh repo archive`, `gh release delete`,
    `gh secret (delete|remove)`.
  - 7 raw-API/GraphQL/curl/PowerShell/transfer/scope-grant, precision-tuned to
    the repo ROOT path so sub-resource DELETEs (labels/comments/refs/runs) stay
    allowed.
  - `gh issue delete` intentionally NOT denied (used by candidate-sweep cleanup).
- **Root-cause check** — add `governance_core/tools/check_github_token_scope.py`
  (net-new, verbatim from #85, generic): surfaces whether the active gh token
  carries the `delete_repo` OAuth scope (without which GitHub rejects every
  deletion regardless of how issued).
- **doctor wiring** — `governance_core/installer.py::doctor` invokes the tool as
  a best-effort subprocess and loud-warns if `delete_repo` is present.
- **tests** — add gh/API block + allow cases to `test_command_guard.py` (run via
  the real hook, so the allow-prefix bypass is exercised); a unit test for the
  token-scope parser.
- Version bump; supersede + close #84; promote-record #85.

## Non-Goals

- Do NOT deny `gh issue delete` (relatively safe; candidate-sweep relies on it).
- Sub-resource API DELETEs (labels/comments/refs/runs) MUST stay allowed — the
  patterns are anchored to `/repos/{owner}/{repo}` + terminal boundary.
- doctor's token-scope check is **advisory**: it loud-warns on `delete_repo` but
  does NOT change doctor's exit code (an auth-environment concern, not an
  install defect; keeps dogfood/CI `doctor` exit-0 expectations intact).
- Do NOT wire the verifier into session-start (chosen: doctor — token scope is
  stable; avoids per-session `gh auth status` latency).
- The verifier does not PREVENT deletion (it is a check/warning); prevention is
  the deny-list layer + GitHub's authz layer (token lacking delete_repo).

## Guardrails

This proposal EDITS the command-guard deny-list (a security control). Adding
deny patterns only tightens it; the probe (13 block / 12 allow) + the real-hook
regression confirm no over-block of hub gh usage. edit-write-guard
(deny-list/tool/installer are package source, not constitution files);
boundary-guard (in-repo). Verified `gh`/`curl` are NOT in
`shared.allow_commands.txt`, so Layer 0.5 does not bypass the new patterns.

## Phases

### Phase 0: Governance bootstrap

- Deliverables: this proposal (P-0097) approved by explicit user defense
  directive + the doctor-integration choice.
- Validation: directive + AskUserQuestion answer recorded as approval.
- Exit criteria: approved.

### Phase 1: Ship the two-layer hardening

- Deliverables: 11 deny patterns inserted; `check_github_token_scope.py` added;
  doctor wiring; `test_command_guard.py` gh/API cases + token-scope unit test;
  version bump; #85 promote-record; #84 superseded + closed; both issues closed
  with outcome comments.
- Validation: real-hook regression (new block cases exit 2, new allow cases
  exit 0); full `tools/test_*.py` suite green; `governance-core upgrade
  --project-root .` then `doctor` exit 0 AND doctor prints the token-scope line;
  wheel top-level only `governance_core*` (tool present, no `maintainer/` leak).
- Exit criteria: committed referencing P-0097; issues closed; archived.

## Approval Criteria

- Deny delta vs current source is exactly the 2 added blocks (pure-add) — no
  removal/reorder of existing patterns.
- Through the REAL command-guard hook: repo-removal vectors block (exit 2); hub
  gh usage (`gh release create`, `gh issue close/comment`, `gh run watch`,
  sub-resource `gh api ... DELETE`, `gh issue delete`) is allowed (exit 0).
- doctor surfaces the token-scope verdict; current hub token lacks `delete_repo`
  (verified: scopes gist/read:org/repo/workflow).

## Validation Plan

1. `git diff --no-index --ignore-cr-at-eol <source> <payload>` → only the 2
   added blocks (done at curation time).
2. Real-hook regression in `test_command_guard.py` (new DESTRUCTIVE + ROUTINE
   cases) green; token-scope parser unit test green.
3. `python -m pytest tools/ -q` + script-style suite green.
4. `governance-core upgrade --project-root .` then `doctor` → exit 0 with a
   `[doctor] ... token ... delete_repo ...` line.
5. `python -m build --wheel`; wheel top-level only `governance_core*`,
   `check_github_token_scope.py` present, no `maintainer/` leak.

## Rollback / Recovery

Revert the commit: deny patterns removed, tool removed, doctor wiring removed.
The deny-list is fail-closed on bad regex — the probe + suite guard against a
malformed pattern bricking command execution. No state to migrate.

## Risks

- **Low — over-block (false positive).** A too-broad pattern could block
  legitimate gh usage. Mitigation: probe (12/12 allow) + real-hook regression;
  patterns anchored to repo-root; `gh issue delete` explicitly allowed.
- **Low — fail-closed deny-list.** A malformed added regex makes command-guard
  block everything. Mitigation: patterns copied verbatim from a validated
  candidate + compiled in the probe + the suite runs the real hook.
- **Low — doctor latency.** The subprocess runs `gh auth status` (tool timeout
  20s). Mitigation: best-effort, gh-unavailable → exit 0; doctor is infrequent
  (not per-session). 
- **Informational — check is advisory.** It warns, does not prevent. Prevention
  is the deny-list + the token lacking delete_repo (currently the case).

## State Log

- 2026-06-03: draft created by core agent (P-0097)
- 2026-06-03: draft → pending (submit for review)
- 2026-06-03: pending → approved (user: '我们需要做一些防御' + AskUserQuestion 'doctor 集成' (explicit defense directive + integration choice))
- 2026-06-03: approved → implemented
