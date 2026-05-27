---
id: P-0077
agent: core
status: implemented
created: 2026-05-27
approved_at: 2026-05-27
started_at: 2026-05-27
implemented_in: 74d283a
implemented_at: 2026-05-27
owner: core
---

# Proposal P-0077: uplink.py: send drift diff (not full file) + use --body-file (issue #15)

## Trigger

GitHub issue #15 (filed 2026-05-27 by napheir, the trade-agent owner)
reports three failure modes hit consecutively during a single
`/upgrade` flow 0.7.0 -> 0.8.0 on Windows:

| # | Symptom | Root cause |
|---|---------|-----------|
| 1 | `gh issue create failed: 'kind/mechanism' not found` | Hub repo missing `kind/<x>` labels for `mechanism` and `hook`. Patched on the hub during the upgrade (one-off `gh label create`) but worth surfacing as setup doc. |
| 2 | `gh CLI not found` (misleading) on 40-41 KB candidate bodies | `subprocess.run(['gh', ..., '--body', body])` exceeds Windows `CreateProcessW` cmdline cap (~32K UNICODE_STRING). Python surfaces this as `FileNotFoundError`, which `uplink.py:151` catches and re-raises as "`gh` CLI not found". |
| 3 | `candidate envelope too large for issue uplink (143KB > 60K)` | The `dashboard.py` drift envelope reships the **entire current file** as the issue body, even though the hub package already holds the `baseline_sha256` content of that exact path. |

Failure modes 2 and 3 share a deeper structural issue: **drift candidates
currently transmit the full current file, but the hub already ships the
baseline bytes**. The issue body should carry the *diff* against
baseline, not the full file. Once that shift is in:
- Failure 3 disappears (143KB current dashboard.py -> ~5KB diff, well
  under the 60K body cap).
- Failure 2 is unblocked for most realistic drift sizes (diff stays
  small enough to fit Windows cmdline) -- though the `--body-file` cmdline
  fix is still the right structural change for any consumer that uploads
  large net-new skill / hook payloads.
- Failure 1 is doc-only.

issue #15's author (napheir, same as trade-agent's owner and this
proposal's reviewer) explicitly proposes a **single coupled PR** rather
than three separate fixes; this proposal honors that intent.

**Why proposal governance applies**: changes consumer-side uplink wire
format (drift body schema) + hub-side parser must remain compatible
(`parse_payload_from_issue_body`, `discover_uplinked_from_hub` from
P-0076, `maintainer/reject_candidate.py`) + new Windows-cmdline fix
landing in same module + touches a path every authorized consumer runs.

## Scope

Single-phase change.

### 1. Windows cmdline fix (`--body` -> `--body-file`)

`uplink.uplink_envelope`: replace
```python
argv = ["gh", "issue", "create", "--repo", repo,
        "--title", title, "--body", body]
```
with
```python
with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                 encoding="utf-8") as tf:
    tf.write(body)
    body_path = tf.name
try:
    argv = ["gh", "issue", "create", "--repo", repo,
            "--title", title, "--body-file", body_path]
    ...
finally:
    Path(body_path).unlink(missing_ok=True)
```
No-op on Linux/macOS (ARG_MAX is high enough that `--body` never
triggers `CreateProcessW`-style truncation there) but the `--body-file`
path is the simpler artifact in either case.

### 2. drift candidates: send diff, not full file

`uplink.build_issue`: split on `"drift_target" in meta`:

- **net-new** (no `drift_target`): unchanged. The issue body keeps the
  `### payload/<name>` fenced full content, as 0.8.0 P-0076 Phase 1's
  round-trip rehash relies on it.
- **drift** (`drift_target` + `baseline_sha256` present): replace the
  full `### payload/<name>` fenced content with:
  - a `### drift diff` fenced block carrying the unified diff between
    the **upstream baseline** (read via `installer._pkg_source_path`)
    and the consumer's current file (read from `envelope_dir / source_paths[0]`)
  - a `### payload digest` line carrying the consumer's payload SHA-256
    (the digest the consumer's `payload_digest` already computed)
  - `payload_form: diff` metadata line so the hub-side parser can
    branch without guessing

Body schema for a drift issue (excerpt):
```
- drift_target: `tools/proposal_lib.py`
- baseline_sha256: `aabbcc...`
- payload_form: diff
- payload_sha256: `ddeeff...`

### drift diff (unified, against baseline)
```diff
--- baseline/tools/proposal_lib.py
+++ consumer/tools/proposal_lib.py
@@ ...
```
```

If `_pkg_source_path(meta["drift_target"])` returns None or the file is
missing (e.g. unfamiliar autonomy path, schema drift), `build_issue`
falls back to the legacy full-payload format so uplink never blocks the
consumer for a baseline-lookup failure.

### 3. hub-side parser tolerance for drift diff body

`governance_core.candidates.ledger.parse_payload_from_issue_body`
(P-0076 Phase 1 shared parser): when `payload_form: diff` is present in
the body's bullet list, **skip rehashing the fenced block**; return
the `payload_sha256` directly. Net-new bodies keep the rehash path.

`governance_core.candidates.ledger.discover_uplinked_from_hub`: no
change needed beyond the parser update -- it consumes the parser's
output directly.

`maintainer/reject_candidate.py`: same tolerance -- when fetching a
drift issue for a reject entry, it does not need to rehash either; the
sha-from-body is authoritative.

### 4. cap stays on body size (already correct)

Issue #15 §3 describes moving the cap from "payload size" to "body
size" in `candidate.py sweep`. Current code (`uplink.build_issue:95`)
already caps on **body** length, not payload, so this item is a no-op.
But the cap stays meaningful: drift body now (diff) is far below the
limit; net-new body can still hit it on a >60K skill (a code smell
that warrants a separate channel, out of scope).

### 5. setup doc: hub labels

The hub repo needs `kind/mechanism` and `kind/hook` labels for uplink
to succeed on those candidate kinds (`kind/skill` was already present).
Issue #15 reports this was hit live in the upgrade; the labels have
been created on `napheir/governance-core` as a one-off fix.

Add a `docs/core-manual.md` setup-section note: when standing up a
fresh hub repo, run

```bash
gh label create "kind/skill" --color C5DEF5 -R <repo>
gh label create "kind/hook" --color C5DEF5 -R <repo>
gh label create "kind/mechanism" --color C5DEF5 -R <repo>
gh label create candidate --color D4C5F9 -R <repo>
```

Also update the `governance_core.candidates.uplink.UplinkError` message
that catches `CalledProcessError` to hint at the labels case when stderr
matches the `not found` pattern.

### 6. tests

- `test_uplink_drift_diff.py` (new):
  - `build_issue` on a drift envelope -> body contains `### drift diff`,
    `payload_form: diff`, `payload_sha256:`; no `### payload/<name>`
    full fenced block.
  - `build_issue` on a net-new envelope -> behavior unchanged (full
    payload fence + no `payload_form` line).
  - `parse_payload_from_issue_body` on the drift body -> returns
    `(meta, {})` with `meta["payload_sha256"]` correctly populated; on
    net-new body -> behavior unchanged.
  - `discover_uplinked_from_hub` integration: mocked `gh issue list`
    returns one drift + one net-new issue -> ledger gets both digests
    correctly.
  - Windows cmdline regression: assert `uplink_envelope`'s `gh` argv
    uses `--body-file` not `--body`, with the body content matching
    the tempfile contents.

Version: 0.8.0 -> 0.9.0 (minor: drift issue body schema change; hub
parser still accepts both forms so a 0.8.0-issue and a 0.9.0-issue can
both be parsed by a 0.9.0 hub).

## Non-Goals

- **Not** raising GitHub's issue body cap beyond 65535 chars (platform
  limit; not in our control).
- **Not** introducing an alternate transport (gist, release artifact)
  for net-new skill / hook payloads that exceed 60K. Out of scope --
  a deferred follow-up if anyone files a legitimately huge candidate.
  Issue #15 explicitly marks this OOS.
- **Not** centralizing hub label management. The proposal's setup doc
  + improved error message is enough; a separate "hub bootstrap CLI"
  is overkill.
- **Not** removing the body-size cap. Net-new candidates still must
  fit; cap protects against accidents.
- **Not** unifying drift envelope handling vs. P-0076 Phase 2's
  rejected-registry workflow. These are different lanes (uplink vs.
  reject feedback); the registry's existing schema is fine.
- **Not** auto-rehashing drift content on the hub side as a
  consistency check. The consumer-reported `payload_sha256` is
  treated as authoritative (same trust model as net-new today;
  signed authorization at uplink-time binds the consumer to the
  payload).

## Guardrails

- `edit-write-guard` -- not triggered: no `CLAUDE.md` /
  `constitution/*.md` changes.
- `command-guard` -- `gh issue create --body-file <tempfile>`: tempfile
  is a controlled path produced by `tempfile.NamedTemporaryFile`, no
  user-controlled shell input.
- `scope-guard` / `boundary-guard` -- all changes within
  `governance_core/`.
- `sensitive-data-guard` -- secret scan still runs on envelope payload
  files **before** transport (existing P-0065 behavior). The diff
  rendering only narrows what's sent; if the scan had caught a secret
  in the full payload, it still does so before build_issue is called.
- `constitutional-review` -- Art. 4 (no `.get(k, default)`): the
  drift-branch reads explicit `if "drift_target" in meta`.

## Phases

### Phase 1: --body-file + drift diff + hub parser tolerance + label setup doc

- Deliverables:
  - `governance_core/candidates/uplink.py`:
    - `build_issue`: drift branch renders unified_diff + payload_sha256
      metadata; net-new branch unchanged.
    - `uplink_envelope`: switch to `--body-file <tempfile>` argv path
      (Windows cmdline fix).
    - Improve `UplinkError` text when stderr matches `label not found`
      pattern (label-setup hint).
  - `governance_core/candidates/ledger.py`:
    - `parse_payload_from_issue_body`: recognize `payload_form: diff`
      bullet, return sha from body line, skip rehash.
    - `discover_uplinked_from_hub`: no change beyond the parser pickup.
  - `maintainer/reject_candidate.py`: rebuilt parser tolerates drift
    body (no functional change for net-new).
  - `governance_core/tools/test_uplink_drift_diff.py` (new): 5+ unit
    cases from Scope §6.
  - `docs/core-manual.md`: add hub-bootstrap label setup subsection +
    drift-as-diff mechanism explanation.
  - `governance_core/__init__.py` + `pyproject.toml`: 0.8.0 -> 0.9.0.
- Validation:
  - `python governance_core/tools/test_uplink_drift_diff.py` -- all green.
  - Full regression: revocation 24, renewal 13, candidate-attribution
    9, candidate-reminder 7, update-reminder 9, auth-guard 9,
    auth-codec 11, upgrade-dry-run 14, candidate-recovery 14 (P-0076
    Phase 1; the drift body schema change must not break this),
    rejected-registry 21 (P-0076 Phase 2).
  - Build 0.9.0 wheel; verify `uplink.py` and `ledger.py` both ship the
    new branches; verify wheel still excludes `maintainer/`.
  - Dogfood: governance-core is the hub and does not uplink. Cannot
    fully repro the Windows cmdline path in this repo's CI, but the
    `--body-file` codepath is exercised by unit tests + Windows hosts
    on this repo as the developer environment.
  - End-to-end smoke (optional in this session, deferable to
    post-release real consumer): on trade-agent's remaining 143KB
    dashboard.py drift envelope still in outbox, run `tools/candidate.py
    uplink <env> --dry-run` and confirm the rendered body is small
    enough + carries the diff + sha. (Trade owner can do this after
    upgrading to 0.9.0.)
- Exit criteria: tests green; commit `feat: P-0077 - uplink drift
  diff + body-file (issue #15)`. Version 0.9.0.

## Approval Criteria

- User confirms **single phase** for all three #15 items per author's
  "single PR coupled changes" intent.
- User confirms `payload_form: diff` schema is reasonable (alternative
  considered: derive form from absence of `### payload/<name>` block,
  but explicit metadata is more robust to future body shape changes).
- User confirms version bump 0.8.0 -> **0.9.0** (minor: changes drift
  issue body schema, parser accepts both forms for compatibility).
- User confirms the **trade-agent owner can self-recover** the
  remaining 143KB dashboard.py drift after upgrading to 0.9.0 (no
  hub-side data migration needed; the existing drift envelope in
  trade's outbox can be re-uplinked under 0.9.0 transport).

## Validation Plan

- Static: `grep -rn "payload_form\|--body-file\|drift diff" governance_core/` -- definitions in uplink.py + ledger.py + tests.
- Unit: `test_uplink_drift_diff` 5+ cases (drift body shape / net-new
  body unchanged / parser branches / windows cmdline / hub recovery
  end-to-end).
- Wheel: 0.9.0 builds; new transport code shipped.
- Cross-platform: `--body-file` runs the same on Linux/macOS as on
  Windows (Python tempfile API).

## Rollback / Recovery

- Single-commit phase; rollback = `git revert`.
- Wire format is **forwards-only**: a 0.9.0 hub parser handles both
  0.8.0-shape full-payload bodies and 0.9.0-shape diff bodies. So a
  consumer on 0.9.0 sending diff bodies to a 0.8.0 hub would not parse
  cleanly -- but 0.9.0 ships as the *hub* upgrade, so by the time a
  consumer is on 0.9.0 the hub has already been updated (consumer
  upgrades follow `pip install -U` after the wheel publishes).
- `--body-file` rollback: trivially revert the argv change; pre-fix
  failure mode reappears only for Windows consumers with >32K bodies.

## Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Hub-side parser branch doesn't cover all 0.8.0-shape bodies + 0.9.0-shape bodies | Med | Med (P-0076 ledger self-heal partially breaks) | regression test_candidate_recovery (14 cases) + new test for drift body schema; parser explicitly branches on `payload_form` metadata |
| Consumer's `_pkg_source_path` returns None / baseline missing | Low | Low | `build_issue` falls back to legacy full-payload format on lookup failure; transport is best-effort |
| Tempfile cleanup failure leaks files | Low | Low | `Path.unlink(missing_ok=True)` in `finally` block; tempdir cleaned up by OS later anyway |
| Diff format differs across Python versions causing reviewers to see noisy diffs | Low | Low | `difflib.unified_diff` is stable across Python 3.11+ |
| 0.9.0 consumer talking to a still-0.8.0 hub | Low | Low | Hub-side change is in 0.9.0 wheel; if a maintainer somehow rolls back the hub to 0.8.0, they can still parse 0.9.0 issue bodies because the 0.8.0 parser ignores unknown bullet lines and the `### drift diff` block is well-formed |
| `--body-file` introduces filesystem race on Windows | Low | Low | `NamedTemporaryFile(delete=False)` writes synchronously then closes before `gh` invokes; `gh` reads the file at invocation time |
| Issue #15 label-setup doc gets stale (future labels added) | Low | Low | maintainer/reject_candidate.py error message provides a runtime hint; doc lists current labels with a "see hooks_manifest" cross-ref |
| Trade-agent's remaining 143KB dashboard.py drift envelope built under 0.8.0 cannot be uplinked under 0.9.0 transport | Low | Low | Existing envelope is just a drift envelope with `drift_target` + `baseline_sha256` -- 0.9.0 `build_issue` reads from the envelope and applies the new transport. No envelope migration needed |

## State Log

- 2026-05-27: draft created by core agent (P-0077)
- 2026-05-27: draft → pending (submit for review: issue #15 uplink drift diff + body-file)
- 2026-05-27: pending → approved (user signal: 'OK，做吧')
- 2026-05-27: approved → in-progress (Phase 1 start)
- 2026-05-27: in-progress → implemented
