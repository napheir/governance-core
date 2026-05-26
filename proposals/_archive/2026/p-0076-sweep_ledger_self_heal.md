---
id: P-0076
agent: core
status: implemented
created: 2026-05-26
approved_at: 2026-05-26
started_at: 2026-05-26
implemented_in: 3125f2d
implemented_at: 2026-05-26
owner: core
---

# Proposal P-0076: candidate pipeline robustness — ledger self-heal + reject feedback

## Trigger

Hub-side audit 2026-05-26 of `/proposal P-0075` aftermath surfaced two
separate failure modes in the P-0072 candidate sweep flow. Both produced
the same observable symptom (duplicate candidate issues from trade-agent
flooding the hub queue), but the root causes are distinct and require
distinct fixes:

### Failure mode A — ledger loss (Phase 1)

Four GitHub candidate issues from trade-agent paired into duplicates:
- #4 / #6: `p4-scenario-fixture-construction` (sha256 `ee67474d...`,
  byte-for-byte equal payload)
- #5 / #7: `cross-agent-gate-spec-mock` (sha256 `279def21...`,
  byte-for-byte equal payload)

The candidate ids differ only by the date stamp baked into
`envelope.make_candidate_id`. P-0072's dedup is built on payload SHA-256
(`ledger.payload_digest`), not the id, so once `_uplinked.json` contains
the digest, subsequent sweeps of the same payload skip silently.

The duplicates therefore prove the consumer-side ledger lost the prior
entries. The candidate outbox (`.governance/candidate-outbox/`) is
gitignored and transient — a manual `rm -rf`, a wiped clone, a failed
write, or an across-machine clone all leave the consumer with a learned
skill that was already uplinked but no record proving so. The next sweep
treats it as net-new and uplinks again, flooding the hub queue with
duplicates the maintainer must hand-curate.

The four #4-#7 issues have been closed as not-planned (business-layer
content). Underlying P-0072 dedup logic remains correct. Phase 1 hardens
that logic against ledger loss by attempting to *recover* the ledger from
the hub's issue history before declaring envelopes net-new.

### Failure mode B — no hub→consumer reject feedback (Phase 2)

Ledger self-heal solves *digest-equal* duplicates, but a deeper failure
mode remains: a consumer authors a skill, hub rejects it, consumer edits
the skill (or its frontmatter, or any single byte), payload digest
changes, the ledger considers it net-new, sweep uplinks the *new* digest
as a fresh candidate, and the maintainer rejects it again — manually, for
the same underlying reason.

There is currently **no channel** carrying a hub reject back to the
consumer:
- Closing a GitHub issue as not-planned is invisible to the consumer's
  sweep — `cmd_sweep` never queries hub state.
- The reject comment text the maintainer writes lives on GitHub only; the
  consumer never sees it unless their human owner reads the issue.
- A consumer can in good faith re-uplink an iterating-but-still-business
  payload N times before the owner figures out the hub keeps rejecting it
  for the same structural reason.

This is the same pattern as P-0071's revocation feed solved for the
authorization layer: the hub maintains a signed feed of revoked
consumer_ids; auth-guard pulls it; consumer learns it's revoked without
the maintainer reaching out individually. Phase 2 applies that pattern to
candidate rejections.

**Why proposal governance applies**: changes consumer-side wrap-up
behavior + crosses package source (`governance_core/candidates/`) + adds
a GitHub-network dependency to sweep + introduces a new hub-side
authoritative artifact (rejected registry) shipped in the wheel + touches
the candidate pipeline every authorized consumer runs.

## Scope

Two-phase change touching `governance_core/candidates/*`,
`governance_core/tools/candidate.py`, a new
`governance_core/candidates/rejected_registry.json` shipped artifact,
and a new `maintainer/reject_candidate.py` tool.

### Phase 1 — sweep ledger self-heal (Failure mode A)

1. **Add `discover_uplinked_from_hub(origin, repo)`** in
   `governance_core.candidates.ledger` (or sibling module if the
   network dep does not belong in `ledger.py`). Queries the hub via
   `gh issue list --state all --json number,title,body,url
   --search "[candidate] (from <origin>)"`, parses each body's
   `### payload/<name>.md` fenced block, computes
   `_hash_payload([(name, bytes)])`, returns
   `[{digest, candidate_id, issue_url}]`.

   The fenced block is the exact bytes that originally fed the digest
   (the consumer's source payload, transported verbatim), so rehashing
   reproduces the digest. No schema change to the issue body required.

2. **Modify `cmd_sweep`** to call recovery once *before* the `pending`
   selection loop, gated on:
   - ledger file missing OR ledger has zero entries, AND
   - outbox has at least one envelope, AND
   - `gh` is available + project is authorized (consent + auth code).

   Recovery writes rebuilt entries to `_uplinked.json` via
   `record_uplink` (idempotent).

3. **Stay fail-safe**: any network or `gh` failure during recovery
   falls back to the current behavior (no recovery, sweep continues
   with whatever ledger is on disk).

4. **Add `test_candidate_recovery.py`** (new): 4 unit cases using a
   `subprocess.run` shim with canned `gh issue list` JSON.

### Phase 2 — reject feedback registry (Failure mode B)

5. **New shipped artifact `governance_core/candidates/rejected_registry.json`**
   (committed in package source, packaged in wheel, downloaded with
   every `pip install governance-core`). Schema 1:

   ```json
   {
     "schema": 1,
     "updated": "2026-05-26T...",
     "rejected": [
       {
         "rejected_at": "2026-05-26",
         "skill_name": "p4-scenario-fixture-construction",
         "payload_sha256": "ee67474d...",
         "origin": "trade-agent",
         "issue_urls": ["https://github.com/.../issues/4",
                        "https://github.com/.../issues/6"],
         "reason": "business-layer content — strangle50 / o2_score /...",
         "advice": "keep as local learned skill; remove `layer: candidate-common`"
       },
       ...
     ]
   }
   ```

6. **New hub-side tool `maintainer/reject_candidate.py`** (excluded
   from wheel by the `governance_core*` packages whitelist, hub-only).
   Args: `--issue <N> --reason "..." --advice "..." [--also-close]`.
   Actions:
   - `gh issue view N --json title,body,url` fetch the issue
   - Parse `### payload/<name>.md` fenced block (same parser as
     Phase 1 recovery — shared code)
   - Compute `_hash_payload([(name, bytes)])`
   - Append entry to `rejected_registry.json` (idempotent on
     `(skill_name, payload_sha256)`)
   - If `--also-close` → `gh issue close N --reason "not planned"`
     + post a comment with the reason/advice text
   - Print the registry diff for maintainer review

   Maintainer workflow becomes: examine candidate issue → run
   `python maintainer/reject_candidate.py --issue 4 --reason "..."
   --advice "..." --also-close`, all-in-one.

7. **New module `governance_core.candidates.rejected`** with:
   - `load_rejected_registry()` — reads the wheel-shipped JSON
   - `is_rejected(skill_name, payload_sha256)` — returns one of:
     - `None` — not in registry
     - `{match: "exact", entry: <dict>}` — sha matches (same content
       previously rejected); **blocks uplink**
     - `{match: "name", entry: <dict>}` — name matches but sha
       differs (consumer rewrote a previously-rejected skill);
       **warns but allows uplink** (hub re-evaluates the new content)

8. **Modify `collect.collect_netnew_skills` and `cmd_sweep`** to
   consult the registry:
   - For each `layer: candidate-common` skill, compute its
     `skill_digest`.
   - `is_rejected(...)`:
     - `exact` → don't collect/uplink; print structured advisory:
       ```
       [candidate] sweep: SKIPPED <skill> -- previously rejected by hub
         reason:   business-layer content -- strangle50 / o2_score / ...
         advice:   keep as local learned skill; remove `layer: candidate-common`
         issues:   https://github.com/.../issues/4
                   https://github.com/.../issues/6
       ```
     - `name` → still collect/uplink, but print warning to stderr:
       ```
       [candidate] sweep: NOTE <skill> -- a previously-rejected skill with
       the same name exists (different content). Uplinking the new content
       for hub re-evaluation. Prior reason: ...
       ```
     - `None` → normal path.

9. **Extend SessionStart `candidate-reminder.py` hook** to also report
   rejected-but-still-tagged skills:
   ```
   [Candidate] N learned skill(s) tagged candidate-common; 1 was
   previously rejected by hub (<name>): remove `layer: candidate-common`
   or rename to avoid auto-uplink noise.
   ```
   Surfaces the situation at session start so the owner notices without
   waiting for the next wrap-up.

10. **Tests `test_rejected_registry.py`** (new): 6+ cases:
    - exact sha match → block + correct advisory text;
    - name-only match → allow + warning text;
    - no match → normal collect path;
    - empty registry → normal collect path;
    - malformed registry JSON → log + treat as empty (fail-safe);
    - maintainer tool round-trip: build registry from issue → consumer
      reads + blocks.

11. **Docs**:
    - `docs/core-manual.md` §11 — Phase 1 self-healing paragraph
      + Phase 2 reject feedback subsection (reject flow,
      registry semantics, how to write a good reason+advice pair).
    - `docs/core-manual.md` §12 or new section — maintainer side:
      how to use `reject_candidate.py`.

Version: 0.7.0 → 0.7.1 (Phase 1 alone could be patch; Phase 2 adds a
new public file in the wheel + a new module + a new hub tool → minor
is more honest). **Bump 0.7.0 → 0.8.0**, single bump for both phases
following the P-0074 / P-0075 once-per-proposal pattern.

## Non-Goals

- **Not** repairing trade-agent's specific situation. The four #4-#7
  issues are already closed by hand. After this proposal lands, the
  maintainer can backfill them into `rejected_registry.json` using
  `reject_candidate.py --issue N` (post-close, the tool can still
  fetch the body and rebuild the entry). The trade owner can then
  let the new mechanism prevent recurrence without intervention.
- **Not** removing `make_candidate_id`'s date stamp. The date stamp is
  useful for chronology / debuggability; dedup correctness comes from
  the content digest, not the id.
- **Not** changing the candidate issue-body schema. Phase 1 rehashes
  the embedded fenced payload bytes; Phase 2's
  `reject_candidate.py` does the same. No new field to write.
- **Not** centralizing the ledger on the hub. The ledger stays
  consumer-side; the hub remains the durable record of *issues* +
  rejected_registry, and recovery uses them to rebuild consumer state
  when needed.
- **Not** auto-editing a consumer's skill frontmatter. When sweep
  detects a previously-rejected skill (Phase 2), it prints the
  advisory but never touches the file — the owner decides whether to
  remove `layer: candidate-common`, rename, or delete the skill.
  Auto-modification of authored skills would violate the autonomy
  carve-out invariant.
- **Not** building an "unreject" workflow. A rejected entry stays in
  `rejected_registry.json` indefinitely. A consumer who genuinely
  generalizes a previously-rejected skill should pick a **new name**
  to signal the semantic shift; the maintainer can add an "obsolete"
  marker in `rejected_registry.json` if a rejection is later judged
  invalid, but this is out of scope here.
- **Not** introducing GitHub API rate-limit accounting. Phase 1
  recovery is one-shot per sweep when ledger empty (one `gh issue
  list`). Phase 2 registry is local (no network at sweep time, only
  at maintainer-tool time). Net impact on sweep API budget: zero in
  the healthy path.
- **Not** moving `rejected_registry.json` outside the wheel. Shipping
  it inside the wheel is the right semantic — every consumer that
  upgrades the package also learns of new rejections. A separate
  signed feed (like the revocation feed) is heavier than needed
  because: (a) the registry is not security-critical (rejection is
  advisory, not enforced), (b) wheel signature already proves origin.

## Guardrails

- `edit-write-guard` — not triggered: no `CLAUDE.md` /
  `constitution/*.md` changes.
- `command-guard` — recovery uses `gh issue list --search "..."`;
  args are constructed from a fixed format and a sanitized origin
  slug; no user-controlled shell input.
- `scope-guard` / `boundary-guard` — all changes within
  `governance_core/` package source.
- `sensitive-data-guard` — issue body parsed contains payload text
  (the skill markdown the consumer authored); already public via the
  open issue, so no new exposure.
- `constitutional-review` — Art. 4 (no `.get(k, default)` fallback):
  the recovery function uses explicit `if key in d` membership and
  raises on malformed responses rather than silent default.

## Phases

### Phase 1: ledger self-heal + tests

- Deliverables:
  - `governance_core/candidates/ledger.py`: add
    `discover_uplinked_from_hub(origin: str, repo: str) -> list[dict]`
    + a shared `parse_payload_from_issue_body(body: str)` helper
    (used again by `reject_candidate.py` in Phase 2).
  - `governance_core/tools/candidate.py`: `cmd_sweep` calls recovery
    when ledger empty + outbox non-empty + `gh` available; merges via
    `record_uplink` before the pending selection loop.
  - `governance_core/tools/test_candidate_recovery.py` (new): 4
    regression cases (rebuild OK / malformed body skipped / no gh
    graceful / mixed recovered + net-new).
- Validation:
  - `python governance_core/tools/test_candidate_recovery.py` -- all green.
  - Regression: `test_revocation` 24, `test_renewal` 13,
    `test_candidate_attribution` 9, `test_candidate_reminder` 7,
    `test_update_reminder` 9, `test_auth_guard` 9, `test_auth_codec` 11,
    `test_upgrade_dry_run` 14.
  - Dogfood: governance-core is the hub and short-circuits sweep
    (`[N/A -- hub project]`); Phase 1 path exercised by unit tests.
- Exit criteria: tests green; commit `feat: P-0076 Phase 1 - sweep
  ledger self-heal`. **No version bump yet** (single bump at end of
  Phase 2, per P-0074/P-0075 pattern).

### Phase 2: rejected registry + consumer skip + maintainer tool

- Deliverables:
  - `governance_core/candidates/rejected_registry.json` (new, shipped
    artifact). Initial content: backfill the four #4-#7 closed issues
    (two distinct rejected skills) so the mechanism activates immediately.
  - `governance_core/candidates/rejected.py` (new module):
    `load_rejected_registry`, `is_rejected(skill_name, sha)` returning
    `None` / `{match: "exact" | "name", entry: ...}`.
  - `governance_core/tools/candidate.py`: `cmd_sweep` consults
    `is_rejected` per pending envelope; `exact` blocks + prints
    advisory; `name` warns + uplinks; `None` normal.
  - `governance_core/hooks/candidate-reminder.py`: extend to surface
    rejected-but-still-tagged skills at SessionStart.
  - `maintainer/reject_candidate.py` (new, hub-only). CLI:
    `--issue <N> --reason "..." --advice "..." [--also-close]`.
    Uses the Phase 1 shared `parse_payload_from_issue_body` helper.
  - `governance_core/tools/test_rejected_registry.py` (new): 6+
    regression cases listed in Scope §10.
  - `docs/core-manual.md`: §11 Phase 2 reject feedback subsection +
    §13 (new) maintainer reject_candidate workflow.
  - `governance_core/__init__.py` + `pyproject.toml`: 0.7.0 → 0.8.0
    (single bump for the whole proposal).
- Validation:
  - `python governance_core/tools/test_rejected_registry.py` -- all green.
  - Wheel inspection: `python -c "import zipfile, glob; z=zipfile.ZipFile(glob.glob('dist/*.whl')[-1]); print([n for n in z.namelist() if 'rejected' in n])"` -- shows `rejected_registry.json` + `rejected.py`; does NOT show `maintainer/`.
  - End-to-end maintainer rehearsal (dogfood): in this repo, run
    `python maintainer/reject_candidate.py --issue 4 --reason "..."
    --advice "..."` against a fixture issue body; verify the
    registry diff; revert.
  - Regression: full suite as Phase 1 + `test_candidate_recovery`
    (post-Phase-1).
- Exit criteria: tests green; commit `feat: P-0076 Phase 2 - reject
  feedback registry`. Version 0.8.0.

## Approval Criteria

- User confirms **always-rehash** approach (vs. embedding a
  `payload_sha256:` line in the issue body), which keeps the
  issue-body schema unchanged and avoids trust questions about who
  wrote a digest line.
- User confirms recovery being **fail-safe** is the right shape: any
  recovery error falls back to current sweep behavior; wrap-up never
  blocks on it.
- User confirms **Phase 2 match semantics**: `exact` sha match blocks
  uplink (definitive); `name`-only match warns but allows uplink (gives
  the consumer room to genuinely rewrite, with hub re-evaluation). The
  alternative (always block on name match) is stricter but punishes
  legitimate iteration.
- User confirms **registry stays inside the wheel** (vs. a separate
  signed feed like P-0071's revocation feed). Rejection is advisory,
  not security-critical; wheel signature already attests provenance.
- User confirms **no auto-unreject**: a rejected entry stays
  indefinitely. A genuinely-generalized rewrite uses a new skill name.
- User confirms **no auto-modification of consumer's skill
  frontmatter** (sweep prints advisory; owner decides).
- User confirms version bump 0.7.0 → **0.8.0** (single minor bump
  across both phases, per P-0074/P-0075 once-per-proposal pattern).

## Validation Plan

### Phase 1
- Static: `grep -r "discover_uplinked_from_hub" governance_core/` —
  one definition + one call in `cmd_sweep` + one test file.
- Unit: `test_candidate_recovery` 4+ cases including the negative
  paths (no `gh`, malformed body).

### Phase 2
- Static:
  - `grep -r "is_rejected\|rejected_registry" governance_core/` —
    definitions in `rejected.py`, calls in `cmd_sweep` + reminder
    hook, test file.
  - `grep -r "rejected_registry" maintainer/` — `reject_candidate.py`
    writes/reads the registry.
- Unit: `test_rejected_registry` 6+ cases (exact / name / none /
  empty / malformed / maintainer round-trip).
- Wheel: 0.8.0 builds; `rejected_registry.json` + `rejected.py` are
  in the wheel; `maintainer/` is NOT in the wheel.
- Initial backfill: open `rejected_registry.json` after install,
  verify it lists the two skills from #4-#7 with sha256 hashes
  matching what was rebuilt this session.
- End-to-end smoke: in a scratch repo with a `candidate-common`
  learned skill whose payload sha matches an entry in
  `rejected_registry.json`, `python tools/candidate.py sweep
  --dry-run` prints the `SKIPPED ... previously rejected` advisory
  and does not include the skill in pending.

## Rollback / Recovery

- Two commits (one per phase); rollback = `git revert <phase-2-hash>`
  for Phase 2 alone, or both hashes to revert the whole proposal.
- Both phases are **additive**: existing dedup logic (`is_uplinked` on
  the on-disk ledger) is untouched. If Phase 1 recovery has a bug,
  worst case recovery raises and falls back to current behavior (pre-
  P-0076 state, duplicates possible but no regression). If Phase 2
  `is_rejected` has a bug, worst case the advisory is wrong or
  missing (sweep proceeds normally, hub rejects again — same as today).
- `rejected_registry.json` is data, not code; a wrong entry can be
  removed by editing the file in the package source + bumping the
  version + re-releasing. The maintainer tool's `--also-close` flag
  is optional (the close + comment can always be done manually if
  the tool malfunctions).

## Risks

### Phase 1
| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Issue body fenced block schema drifts (e.g. uplink.py changes the header) | Med | Med | recovery wraps body parse in try/except; unparseable issues skipped + INFO log; uplink.py and recovery share the parser, kept in sync via tests |
| Hub has many candidate issues from same origin → API rate limit | Low | Low | one `gh issue list` call regardless of N; gated on ledger empty + outbox non-empty |
| Recovery rebuilds digest no longer matching any envelope | Low | None | extra ledger line is harmless |
| `gh` not authenticated on consumer | Med | None | recovery returns empty, sweep continues unchanged |
| Recovery adds network into sweep happy path | Med | Low | gated on ledger empty + outbox non-empty; healthy consumers never trigger it |

### Phase 2
| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Consumer keeps editing a rejected skill, name match keeps warning but allowing → noise loop | Med | Low | the **warning** is per-sweep advisory only, not a block; if the owner ignores it, the maintainer can either re-reject the new variant (sha entry added) or note the name in `rejected_registry.json` with `block_name: true` (future extension; out of scope here) |
| `rejected_registry.json` grows unbounded over years | Low | Low | bounded by hand-curated rejections; even hundreds of entries are kilobytes. Future major version can compact / migrate if needed |
| Maintainer writes a poor `reason` / `advice` pair → consumer sees uninformative message | Med | Low | `reject_candidate.py` requires both args; doc has a "writing a good reason/advice" subsection. Phase 2 acceptance includes a maintainer dogfood pass on the existing four #4-#7 issues |
| Wheel rebuild required to ship a new rejection → delay between maintainer reject and consumer learning | Med | Low | consumers learn at next `pip install -U` / `governance-core upgrade`. The `update-reminder.py` SessionStart hook (P-0073) already prompts within 12h of a new release. Acceptable lag for advisory information |
| Auto-modification temptation — future contributor adds "sweep rewrites skill frontmatter to layer: local on exact match" | Low | High (violates autonomy carve-out) | Non-Goals + Approval Criteria explicitly forbid; `rejected.py` module has no Write access in its API |
| `rejected_registry.json` JSON malformed (typo in a maintainer edit) | Low | Low | `load_rejected_registry` catches `JSONDecodeError`, logs, returns empty registry; sweep falls back to pre-P-0076 Phase 2 behavior |
| Consumer cheats by renaming the rejected skill | Med | None — by design | rename = new skill name = hub re-evaluates. If still business-layer, hub rejects again under new name. Friction is intended; the registry is advisory, not adversarial. The aim is owner awareness, not control |
| Test `test_rejected_registry` becomes coupled to specific real entries in the shipped registry → flaky as the registry grows | Low | Low | tests load a fixture registry, not the shipped one; the shipped file is validated separately via a smoke test that asserts schema-1 shape + non-empty `rejected` array |

## State Log

- 2026-05-26: draft created by core agent (P-0076)
- 2026-05-26: draft → pending (submit for review: sweep ledger self-heal)
- 2026-05-26: pending → approved (user signal: '批准执行')
- 2026-05-26: approved → in-progress (Phase 1 start)
- 2026-05-26: in-progress → implemented
