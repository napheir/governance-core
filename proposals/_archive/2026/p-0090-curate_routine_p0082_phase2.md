---
id: P-0090
agent: core
status: implemented
created: 2026-06-02
approved_at: 2026-06-02
implemented_in: 7818ba2
implemented_at: 2026-06-02
owner: core
---

# Proposal P-0090: P-0082 Phase 2: scheduled C-hybrid curation routine + deterministic auto-promote gate + kill-switch

## Trigger

P-0082 Phase 2, per core's handoff (`agent-core/artifacts/gc-phase2/HANDOFF.md`)
and the user's "做 phase2" + "连调度也一并建". This is the LLM-judgment layer that
actually reduces the operator's relay: it works the open candidate/feedback
queue daily, auto-promoting only deterministic-T0 candidates and advising on the
rest. It is the **most trust-sensitive** piece of the whole arc — a scheduled
remote routine that can autonomously commit + version-bump to the hub — so it
gets its own careful proposal (Art.13). Classify = PROPOSAL_REQUIRED
(autonomous write capability + scheduling + security gate).

## Scope

**1. Deterministic auto-promote gate (`maintainer/curate_gate.py`):**

The ONLY thing that may green-light an auto-promote. Pure deterministic; the
LLM routine calls it and may NEVER override a `False`. For an `auto-eligible`
issue it:

- **reconstructs the envelope from the issue body** (P-0089: the payload is not
  published; for net-new candidates `build_issue` embeds candidate.json + each
  `### <source_path>` fenced block in the body). Drift/diff-form bodies are not
  reconstructable here → not eligible (they are `mechanism` = non-T0 anyway).
- runs the FULL `envelope.validate_envelope` (metadata + payload on disk),
- `registry.is_consumer_revoked(origin)` must be False,
- secret scan via `uplink.scan_envelope` must be empty (the SAME gate — Art.8),
- not a previously-rejected digest (`rejected` registry + `ledger.payload_digest`),
- net-new (`git cat-file -e HEAD:<target>` — no overwrite),
- `kind in {skill}` (see doc-gap note) and `layer == candidate-common`,
- no security-surface hit (reuses `candidate_intake.touches_surface`),
- skill-theme ok: parse the skill `.md` frontmatter; hold if theme/tags
  intersect the governance/security hold-set from
  `auto_promote_security_surface.json`,
- **trial-apply**: in an isolated `git worktree` (NOT the live checkout), place
  the payload at its target (mirroring `candidate.py promote` placement) and run
  `pytest`; ALL green required. The worktree is removed afterward.

Returns `(eligible: bool, reasons: list[str])`. Any failure ⇒ `eligible=False`.

**2. Kill-switch (`maintainer/auto_curate_enabled`):** `{"enabled": false}` —
committed **disabled by default**. Absent/false ⇒ advise-only (no auto-promote
this run). Lets the operator turn the autonomous path on/off globally without
touching the routine.

**3. Routine spec (`maintainer/curate_routine.md`):** the C-hybrid logic +
the exact self-contained routine prompt:
- `auto-eligible` → `curate_gate.evaluate`; eligible ⇒ `candidate.py promote`
  (commit + version bump) + comment "auto-promoted (T0)"; not eligible ⇒
  relabel `needs-human` + comment why.
- `needs-human` / valid non-T0 → LLM semantic advice + label `advised`, NEVER
  promote.
- `feedback` → LLM triage (fix / wontfix / needs-info) + label `advised`.
- Honor the kill-switch; never promote a non-T0 or security-surface candidate;
  comment on every issue touched.

**4. Schedule (`/schedule` → `RemoteTrigger`):** a daily remote routine
(`0 0 * * *` UTC ≈ 09:00 Asia/Tokyo), gc repo, the spec's prompt, model
`claude-sonnet-4-6`, tools Bash/Read/Write/Edit/Glob/Grep.

**5. Tests + version bump.**

## Non-Goals

- **No schema change to add `kind: doc`** (see doc-gap). T0 stays `skill`-only in
  practice this round.
- No change to `candidate.py promote` placement logic (the gate mirrors it; the
  routine calls the real `promote`).
- No change to the deny-set surface config or intake (P-0088/P-0089 stand).
- The routine prompt is committed as spec; refining the LLM wording over time is
  out of scope here.

## Guardrails

- **Safety posture (defense in depth) — nothing auto-promotes unless ALL hold:**
  1. kill-switch `auto_curate_enabled.enabled == true` (default false),
  2. `curate_gate.evaluate` returns eligible (9 deterministic checks +
     trial-apply green),
  3. the candidate is T0 (skill / candidate-common / net-new / no surface),
  4. the remote agent actually has push creds (see blocker).
  The LLM can only DOWNGRADE (advise / relabel needs-human); it can never
  upgrade past a gate `False`.
- **GitHub-connection blocker (must flag):** `/schedule` reports GitHub is NOT
  connected for this repo. The remote agent cannot clone or push until the user
  runs `/web-setup` (or installs the Claude GitHub App). So the routine is
  **dormant** until that + the kill-switch are both done — an additional safety
  layer, but it means the schedule is created in a not-yet-functional state by
  design; documented, not hidden.
- **edit-write-guard / boundary-guard**: gate + kill-switch + spec are new files
  under `maintainer/` (in-boundary, not constitution). The remote routine runs
  in the cloud against its own checkout — out of this session's boundary entirely.
- **Art.11.4**: `maintainer/` stays wheel-excluded.
- **Art.8**: the gate reuses `uplink.scan_envelope` + the real
  `validate_envelope` + `candidate.py promote` — no parallel implementations.

## Phases

### Phase 0: Governance bootstrap

- Deliverables: this proposal (P-0090), draft → pending → approved.
- Validation: explicit user approval signal.
- Exit criteria: status = approved.

### Phase 1: Build the gate + kill-switch + spec (deterministic, tested)

- Deliverables: `curate_gate.py`, `auto_curate_enabled` (disabled),
  `curate_routine.md`, tests, version bump.
- Validation:
  - unit test: reconstruct-from-body round-trips; each gate check fails closed
    (revoked origin / secret / rejected / not-net-new / wrong kind / surface
    hit / theme hold / trial-apply red ⇒ eligible False); a clean net-new skill
    ⇒ eligible True; kill-switch disabled ⇒ gate-irrelevant advise-only.
  - full `pytest tools/` + standalone family green; upgrade + doctor exit 0;
    wheel isolation clean (`maintainer/` absent).
- Exit criteria: suite green; commit `Implements: P-0090`; pushed.

### Phase 2: Schedule the routine

- Deliverables: a daily `RemoteTrigger` routine on the gc repo with the spec
  prompt; the GitHub-connection + kill-switch prerequisites surfaced to the user.
- Validation: `RemoteTrigger {action:list}` shows the routine; the prompt is
  self-contained and honors the kill-switch.
- Exit criteria: routine created (dormant by design until creds + switch);
  routine URL returned.

## Approval Criteria

- The auto-promote path is gated by ALL of: kill-switch on, `curate_gate`
  eligible, T0, push creds — verifiable in `curate_gate.py` + the routine prompt.
- The LLM cannot override a gate `False` (the prompt + gate API make the
  deterministic verdict authoritative).
- Default state is SAFE: kill-switch shipped `false`; routine dormant until
  GitHub connected.
- Trial-apply runs in an isolated worktree, never the live checkout.

## Validation Plan

```bash
python tools/test_curate_gate.py                  # gate fail-closed matrix
python -m pytest tools/ -q                         # full suite
governance-core upgrade --project-root . && governance-core doctor
python -m build --wheel
python -m zipfile -l dist/governance_core-<v>-*.whl   # only governance_core*/
# Phase 2 (after push):
#   RemoteTrigger {action:"create", ...}  ; RemoteTrigger {action:"list"}
```

## Rollback / Recovery

- **Disable instantly**: set `auto_curate_enabled` to `{"enabled": false}` (or
  delete it) — advise-only, no code change, no redeploy.
- **Unschedule**: the routine is paused via `RemoteTrigger {action:"update",
  enabled:false}` or deleted at claude.ai/code/routines.
- **Undo a bad auto-promote**: each is a normal gc commit + version bump —
  `git revert <hash>`; `upgrade` re-derives the autonomy layer.
- Phase 1 code reverts as one commit; the gate/kill-switch/spec are inert
  without the routine.

## Risks

- **Autonomous write to the hub** (the headline risk): a scheduled agent commits
  + bumps version unattended. Mitigations: 4-layer defense (kill-switch off by
  default + deterministic gate + T0-only + push-creds-required); trial-apply in
  an isolated worktree + full pytest before any promote; every promote is a
  revertible commit; the gate reuses the real validators (no divergence).
- **LLM tries to over-promote** (low, fully mitigated): the prompt forbids it and
  the gate is authoritative — the LLM cannot bypass `evaluate()==False`.
- **doc-gap** (known limitation): the surface model says T0 = `{skill, doc}` but
  the envelope `KINDS` are `(skill, hook, mechanism)` — `doc` fails metadata
  validation upstream, so only `skill` is auto-promotable today. The gate gates
  on `{skill}` to match reality; adding `doc` is a schema/contract change tracked
  as a follow-up, not done here.
- **Trial-apply side effects** (low): worktree isolation + cleanup; a crashed run
  leaves a stray worktree at worst (prunable), never a dirty live checkout.
- **GitHub not connected** (operational, surfaced): the routine cannot function
  until `/web-setup`; created intentionally dormant so the machinery is in place,
  but the user must connect creds to make it live.

## State Log

- 2026-06-02: draft created by core agent (P-0090)
- 2026-06-02: draft → pending (submit for review: P-0082 Phase 2 curate routine + gate + kill-switch + schedule)
- 2026-06-02: pending → approved (user approval signal: 批准; noted GitHub local-vs-remote auth distinction)
- 2026-06-02: approved → implemented
