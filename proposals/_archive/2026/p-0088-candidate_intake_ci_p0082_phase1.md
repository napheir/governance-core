---
id: P-0088
agent: core
status: implemented
created: 2026-06-01
approved_at: 2026-06-01
implemented_in: ac861d3
implemented_at: 2026-06-01
owner: core
---

# Proposal P-0088: P-0082 Phase 1 gc-side: deterministic candidate-intake CI + uplink envelope publish (+ #21 de-drift)

## Trigger

User relayed a handoff from a trade-agent (consumer) session
(`agent-core/artifacts/gc-phase1/HANDOFF.md`) for the gc-side (hub) half of
the consumer-approved **P-0082** (candidate-pipeline layering: deterministic
intake in Phase 1, scheduled-LLM curation in Phase 2). The consumer's P-0082
governs the consumer repo; the gc hub needs its **own** governance record
(Art.13) because this lands CI, a security-surface config, and a
consumer-facing `uplink` behavior change. Classify = PROPOSAL_REQUIRED
(CI workflow + security-sensitive + multi-file + consumer-facing).

Bundled by the same request: "顺手按方案 1 收掉 #21" — issue #21 (shipped
common-layer docs hard-reference consumer-specific `proposals/<name>.md`
paths → consumer `audit_knowledge.py` Check 9 FAIL + perpetual drift); the
reporter's recommended **option 1** is to drop those provenance refs.

## Scope

**Phase 1 — candidate-intake CI (deterministic, NO LLM, NO promotion):**

- NEW `maintainer/auto_promote_security_surface.json` — verbatim from the
  handoff: a deterministic deny-set (8 categories, 41 globs) of paths that can
  never be auto-promoted (enforcement guards, auth/lease, scope rules,
  constitution/contracts, routing/classify, pipeline self-protection,
  settings, install/distribution) + a skill-theme supplement. Hot-editable.
- NEW `maintainer/candidate_intake.py` — deterministic intake run on
  `issues.opened`. Distinguishes candidate vs feedback; fetches + structurally
  validates the published envelope; secret-scans; dedups vs rejected registry;
  computes a deterministic T0-eligibility; applies labels + posts one ack
  comment. **Never promotes.** The handoff's GC-TODO placeholders are finalized
  against the real gc APIs:
  - `governance_core.candidates.envelope.validate_envelope` (structural)
  - `governance_core.candidates.uplink.scan_envelope` (the SAME HIGH+MEDIUM
    secret gate uplink uses — Art.8 unified path, no parallel scanner)
  - `governance_core.candidates.{rejected,ledger}` (dedup vs rejected digest)
  - `governance_core.tools._classify_match.match` (gitignore-glob surface hit)
  - net-new check: `git cat-file -e HEAD:<source_path>` — exists ⇒ not net-new
- NEW `.github/workflows/candidate-intake.yml` — the Action: `issues.opened`
  cheap pre-filter → checkout → `pip install -e .` → `python
  maintainer/candidate_intake.py`. Permissions: `issues: write`,
  `contents: read`.

**Phase 2 — uplink envelope publish (so CI can fetch the real envelope):**

- EDIT `governance_core/candidates/uplink.py` — after a successful
  `gh issue create`, idempotent + best-effort publish the envelope as an asset
  on a `candidates` prerelease (`<id>.tar.gz` via `shutil.make_archive` gztar;
  `gh release create --prerelease` ignore-exists; `gh release upload
  --clobber`). Reconcile the handoff's `.tgz`/`.tar.gz` mismatch to
  `.tar.gz` on BOTH ends (publish + `fetch_envelope`). A publish failure must
  NOT fail the uplink (issue already created) — logged, returns the issue URL.
- Version bump (consumer-facing behavior change ships via `upgrade`).

**Phase 3 — labels:** create the 5 missing labels (`feedback`, `valid`,
`auto-eligible`, `needs-human`, `dup-of-rejected`); `candidate` + `invalid`
already exist.

**Phase 4 — #21 de-drift (separate commit):** remove the stale
`proposals/<name>.md` entries from `related:` in
`governance_core/knowledge_governance/agent-least-privilege.md` (1 ref) and
`resource-layer-hardening.md` (3 refs); bump each `updated:`. Body prose
provenance mentions stay (not link-integrity-checked). Close #21.

## Non-Goals

- **No Phase 2 LLM curation** (the scheduled promote/advise routine) — that is
  P-0082 Phase 2, a separate proposal. This intake only labels + acks.
- **No auto-promotion.** The Action cannot promote; T0-eligibility is
  informational. Zero privilege-escalation surface in this phase.
- No change to `candidate.py review/promote` (hub curation stays manual).
- No new runtime hook (the intake is CI-only; runtime-import-discipline for
  per-call hooks does not apply to a CI script).
- #21 option 2/3 (auditor change / new frontmatter convention) are rejected in
  favor of option 1 per the reporter + user.

## Guardrails

- **edit-write-guard**: none of the targets are constitution files.
- **boundary-guard**: all edits in-boundary (cwd = gc repo). The handoff
  drafts live outside the boundary and are READ only; gc copies are authored
  fresh in-boundary (no cross-boundary write).
- **constitutional-review (Art.4)**: `candidate_intake.py` reads required env
  vars with `os.environ[...]` (fail-fast) and config with no silent
  `.get(k, default)` fallback for required keys; surface config is loaded
  strictly.
- **Art.11.4 package isolation**: `maintainer/` and `.github/` are NOT in the
  pip package — wheel must stay `governance_core*`-only. The intake script
  imports `governance_core` only at CI runtime (after `pip install -e .`),
  never shipped inside the wheel.
- **Art.7 code standards**: `logging` not `print`; ASCII-only log markers;
  docstrings + type hints.

## Phases

### Phase 0: Governance bootstrap

- Deliverables: this proposal (P-0088), draft → pending → approved before any
  edit.
- Validation: explicit user approval signal (agent cannot self-approve).
- Exit criteria: status = approved.

### Phase 1: Candidate-intake CI (3-piece set, GC-TODOs finalized)

- Deliverables: the 3 new files above, with the deterministic checks
  implemented (not placeholder), wired to the real gc module APIs.
- Validation: `python -c "import ast; ast.parse(...)"` parse-clean; a unit
  test driving `candidate_intake` decision logic with synthetic
  candidate/feedback/invalid bodies (mocking `gh` + fetch) → correct labels;
  surface config loads (41 globs, no dups).
- Exit criteria: tests green; commit references `Implements: P-0088`.

### Phase 2: Uplink envelope publish + version bump

- Deliverables: uplink publish step (idempotent, best-effort); version bump.
- Validation: existing uplink tests stay green; a test asserting a
  publish-step failure does NOT raise out of `uplink_envelope`; `--dry-run`
  unaffected.
- Exit criteria: suite green; bump shipped.

### Phase 3: Labels

- Deliverables: 5 labels created on the hub repo.
- Validation: `gh label list` shows all 7 intake labels.
- Exit criteria: labels present (idempotent — re-create is a no-op/ignored).

### Phase 4: #21 de-drift

- Deliverables: 4 stale `proposals/` refs removed from the 2 docs' `related:`;
  `updated:` bumped; #21 closed.
- Validation: `audit_knowledge.py` (Check 9 link integrity) clean; grep shows
  no `proposals/` ref left in either doc's frontmatter.
- Exit criteria: separate commit; #21 CLOSED.

## Approval Criteria

- The intake Action provably **cannot promote** (no promote call path); worst
  case it mislabels, which a human corrects.
- `maintainer/` + `.github/` remain excluded from the wheel (verified by the
  wheel-content check) — Art.11.4 intact.
- The secret re-scan reuses uplink's exact scanner (no second, divergent
  implementation) — Art.8.
- #21: only the 4 `proposals/` `related:` entries are removed; the non-proposal
  `related:` entries (`agent_rules/...`, `knowledge/...`) are preserved.

## Validation Plan

```bash
# Phase 1: intake logic
python -m pytest tools/test_candidate_intake.py -q     # new unit test
python -c "import json,collections; g=[x for c in json.load(open('maintainer/auto_promote_security_surface.json'))['categories'].values() for x in c['globs']]; assert len(g)==len(set(g)), 'dup glob'; print(len(g),'globs ok')"
# Phase 2: uplink unchanged on the happy path + publish best-effort
python -m pytest tools/ -q
# dogfood + isolation
governance-core upgrade --project-root .
governance-core doctor                                  # exit 0
python -m build --wheel
python -m zipfile -l dist/governance_core-<v>-*.whl     # only governance_core*/ ; no maintainer/ ; no .github/
# Phase 4: link integrity
python tools/audit_knowledge.py                         # Check 9 clean
```

## Rollback / Recovery

- Phase 1 is pure-additive + stateless: delete
  `.github/workflows/candidate-intake.yml` to disable the Action;
  `maintainer/{candidate_intake.py,auto_promote_security_surface.json}` are
  inert without the workflow.
- Phase 2 uplink publish reverts independently (`git revert` the uplink hunk);
  it only ADDS a release asset — removing it leaves issue-create untouched.
- Phase 3 labels: deletable via `gh label delete` (cosmetic).
- Phase 4: `git revert` restores the refs (but they were the bug; unlikely).
- Each phase = its own commit, so any single phase reverts cleanly.

## Risks

- **Wheel leak of `maintainer/`/`.github/`** (low prob / high impact): a
  packaging glob could accidentally include them. Mitigation: wheel-content
  assertion in the validation plan; `pyproject` `packages` already limited to
  `governance_core*`.
- **Intake imports break in CI** (med / low): wrong module path. Mitigation:
  finalized against real APIs this session + a local unit test that imports the
  same symbols.
- **Publish step slows / flakes uplink** (low / low): best-effort + logged;
  never raises; issue creation already succeeded before publish runs.
- **`.tar.gz` vs `.tgz` mismatch** (med / med if unfixed): reconciled to
  `.tar.gz` on both publish and fetch ends in this proposal.
- **net-new false-negative** (low / low): `git cat-file` against `HEAD` only
  flags overwrites of tracked files; informational only (Phase 2 routine
  re-checks before any promote) — no auto-promote in this phase regardless.

## State Log

- 2026-06-01: draft created by core agent (P-0088)
- 2026-06-01: draft → pending (submit for review: P-0082 Phase 1 gc-side candidate-intake CI + uplink publish + #21 de-drift)
- 2026-06-01: pending → approved (user approval signal: 批准; test scope = pure-logic unit test)
- 2026-06-01: approved → implemented
