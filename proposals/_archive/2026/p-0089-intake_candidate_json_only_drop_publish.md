---
id: P-0089
agent: core
status: implemented
created: 2026-06-02
approved_at: 2026-06-02
implemented_in: 7e9a473
implemented_at: 2026-06-02
owner: core
---

# Proposal P-0089: P-0082 #23: intake validates embedded candidate.json only; drop consumer-side envelope publish

## Trigger

Issue #23 (architecture review after P-0088, confirmed with the user): the
P-0088 "consumer's `uplink` publishes the envelope so CI can run the real
validator" design has a structural flaw — publishing to the hub is a WRITE to
the hub, which breaks the consumer/hub trust separation the pipeline is built
on and is impossible for any non-owner consumer. The user agreed: consumers
must never hold hub write access. The simpler fix (#23): Phase-1 intake needs
only the metadata, which always embeds in the issue body; the payload is only
needed at promote-time (rare, hub-side, human/Phase-2-gated). This walks back
P-0088's option b. Classify = PROPOSAL_REQUIRED (revises the candidate
pipeline + a consumer-facing `uplink` behavior change + version bump).

## Scope

**1. Drop the consumer-side envelope publish (revert P-0088 option b):**

- `governance_core/candidates/uplink.py` — remove `publish_envelope()` and its
  call in `uplink_envelope()`; remove the now-unused `import logging`,
  `import shutil`, and module `log` (all three were added only for the publish
  step — verified no other use in this module). `uplink` returns to pure
  GitHub-issue transport: no write to the hub beyond creating the issue.
- Delete `governance_core/tools/test_candidate_uplink_publish.py` (tests the
  removed function).

**2. Intake validates the embedded candidate.json only:**

- `maintainer/candidate_intake.py` — remove `fetch_envelope()`. `main()` now
  validates the candidate.json parsed from the issue body via the EXISTING
  metadata-only validator `governance_core.candidates.envelope.validate_metadata`
  (schema / kind / layer / source_paths / drift-field consistency — no
  payload-on-disk check). The payload-dependent checks (secret re-scan via
  `scan_envelope`, rejected-digest dedup via `payload_digest`) are REMOVED from
  intake and deferred to promote-time (they belong in P-0082 Phase 2's
  `curate_gate.py`). The metadata-only checks stay: security-surface hit and
  net-new (both read `source_paths` only).
- `compute_eligibility(...)` simplifies to inputs `(metadata_valid, net_new,
  surface_hit, kind, layer)`. Decision: invalid metadata → `invalid`; else T0
  (`net_new and kind in {skill,doc} and layer==candidate-common and no surface
  hit`) → `auto-eligible`; else → `needs-human`. Still NEVER promotes.
- `.github/workflows/candidate-intake.yml` — drop the "fetch the published
  envelope" rationale from comments; `contents: read` stays (checkout +
  `pip install -e .` still need it). No release-download step existed in the
  yml; nothing functional to remove there.

**3. Tests + version:** rewrite `test_candidate_intake.py` for the new
candidate.json-only decision; bump `0.21.0 -> 0.21.1` (same-day correction of
the just-shipped uplink behavior). Close #23.

The existing split in `envelope.py` (`validate_metadata` dict-only vs
`validate_envelope` dir+payload) means #23's "split validate_candidate.py"
suggestion is already satisfied — intake calls `validate_metadata`; the full
`validate_envelope` stays for promote-time.

## Non-Goals

- **No P-0082 Phase 2** (the scheduled curation routine, `curate_gate.py`,
  kill-switch) — a separate proposal; this only corrects Phase 1.
- No change to `candidate.json` schema or the envelope format (`build_envelope`
  / `validate_envelope` / `validate_candidate.py` full check unchanged).
- No change to `candidate.py review/promote` (hub curation stays manual).
- Payload transport at promote-time is documented as a #23 follow-up concern,
  not implemented here (owner uses the local outbox; external consumer supplies
  the payload at promote via issue attachment / re-submit).

## Guardrails

- **edit-write-guard**: no constitution files touched.
- **boundary-guard**: all edits in-boundary; the Phase 2 handoff + #23 are READ
  from outside the boundary / GitHub only.
- **constitutional-review (Art.4)**: no new `.get(k, default)` in package code;
  intake env reads stay `os.environ[...]` fail-fast.
- **Art.11.4**: `maintainer/` + `.github/` remain wheel-excluded (unchanged).
- **Art.8**: intake no longer runs a payload secret scan at all (deferred), so
  there is no second/divergent scanner; the one true scanner stays in `uplink`
  (pre-send) and will be re-used by Phase 2's gate (promote-time).

## Phases

### Phase 0: Governance bootstrap

- Deliverables: this proposal (P-0089), draft -> pending -> approved.
- Validation: explicit user approval signal.
- Exit criteria: status = approved.

### Phase 1: Walk back option b + intake metadata-only

- Deliverables: the uplink revert, intake rework, workflow comment, test
  rewrite, version bump, #23 closed.
- Validation:
  - `python tools/test_candidate_intake.py` green (new metadata-only cases).
  - full `pytest tools/` + standalone candidate family green; the removed
    `test_candidate_uplink_publish.py` is gone (not failing).
  - `grep publish_envelope governance_core/` -> no hits.
  - `governance-core upgrade` + `doctor` exit 0; wheel isolation clean.
- Exit criteria: suite green; commit references `Implements: P-0089`; #23 closed.

## Approval Criteria

- `uplink_envelope` no longer writes anything to the hub except the issue
  itself (no release create/upload) — verifiable by reading the function.
- Intake decision is computable from candidate.json alone — no `fetch_envelope`,
  no payload on disk required.
- Intake still NEVER promotes; T0 stays a hint.
- `validate_metadata` (not the payload check) is what intake calls.

## Validation Plan

```bash
python tools/test_candidate_intake.py            # new candidate.json-only cases
python -m pytest tools/ -q                        # full suite
grep -rn "publish_envelope" governance_core/      # expect: no hits
grep -rn "fetch_envelope" maintainer/             # expect: no hits
governance-core upgrade --project-root . && governance-core doctor
python -m build --wheel
python -m zipfile -l dist/governance_core-0.21.1-*.whl   # only governance_core*/
```

## Rollback / Recovery

- Single self-contained commit; `git revert <hash>` restores P-0088's option b
  (not desired, but clean). The change only REMOVES code paths (publish +
  fetch) and simplifies a decision function — low blast radius.
- No data migration, no schema change, nothing stateful to undo.

## Risks

- **Intake weaker than P-0088 advertised** (expected / low): it no longer does a
  full structural + secret + dedup check. Mitigation: those were never sound at
  intake without the payload; they move to promote-time (Phase 2 gate), which is
  the only place they gate a real action. Documented in the ack comment + #23.
- **`auto-eligible` now rests on metadata only** (low / low): a T0 hint could be
  over-optimistic. Mitigation: it is ONLY a hint; Phase 2's deterministic gate
  re-verifies (secret/dedup/trial-apply) before any auto-promote, and Phase 2
  is not in this proposal — nothing auto-promotes today.
- **Removing a just-shipped public function** (`publish_envelope`) (low): it was
  shipped in 0.21.0 hours ago and never relied upon; 0.21.1 corrects it.

## State Log

- 2026-06-02: draft created by core agent (P-0089)
- 2026-06-02: draft → pending (submit for review: #23 walk-back intake candidate.json-only + drop publish)
- 2026-06-02: pending → approved (user approval signal: 批准)
- 2026-06-02: approved → implemented
