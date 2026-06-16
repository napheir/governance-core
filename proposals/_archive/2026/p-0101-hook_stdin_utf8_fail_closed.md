---
id: P-0101
agent: core
status: implemented
created: 2026-06-16
approved_at: 2026-06-16
started_at: 2026-06-16
implemented_in: f0fda81
implemented_at: 2026-06-16
owner: core
---

# Proposal P-0101: Read hook stdin as UTF-8 bytes to stop classify gate fail-open on Win GBK + PYTHONUTF8 settings default

## Trigger

GitHub issue #98 (reporter: consumer trade-agent, against 0.28.0). All
stdin-reading governance hooks decode stdin in **locale text mode**. On a
Windows GBK/cp936 locale a payload containing Chinese (or any non-cp936)
bytes raises `UnicodeDecodeError` when the hook reads stdin; the hook's
`except` swallows it and **fails open** — silently allowing the action it
was meant to gate. Evidence: `audit/proposal_classify_fast_errors.jsonl` on
the consumer logged **313 fail-open entries, all `reason: "stdin parse
failed"`** (2026-05-26 → 2026-06-12). The most consequential case is the
proposal-classify gate (`proposal-classify-fast.py`), which is supposed to
block Edits to high-sensitivity paths until a classify entry exists but exits
0 (allow) on a mis-decoded payload.

Proposal governance applies (classify → PROPOSAL_REQUIRED): touches hook
sources (global governance), security-sensitive (a core governance gate
fails open), multi-phase (sweep across ~19 hooks + installer settings
template), and changes installer-generated state (`settings.local.json`).

## Scope

1. **Hook stdin decode (primary fix)** — replace every locale-text-mode
   stdin read (`json.load(sys.stdin)` / `json.loads(sys.stdin.read())` /
   `raw = sys.stdin.read()`) with a locale-independent UTF-8 byte read:
   `json.loads(sys.stdin.buffer.read().decode("utf-8"))`. Affected source
   files (19, under `governance_core/hooks/`): auth-guard, cache-watchdog,
   candidate-reminder, command-guard, constitution-reminder,
   constitutional-review, data-source-guard, direction-guard,
   edit-write-guard, merge-audit, prompt-context-router,
   proposal-classify-fast, renewal-reminder, repo-health, scope-guard,
   sensitive-data-guard, session-context, skill-usage-tracker,
   update-reminder.
2. **Fail posture on genuine decode/parse failure** — add `UnicodeDecodeError`
   to each hook's caught exceptions so a malformed payload is handled on a
   *known* branch, not the catch-all. Preserve each hook's existing posture:
   **gate hooks** (classify, command-guard, scope-guard, edit-write-guard,
   data-source-guard, sensitive-data-guard, auth-guard, direction-guard)
   fail **closed/known**; **advisory/reminder hooks** (reminders, routers,
   trackers, session-context, repo-health, merge-audit) stay exit 0
   (fail-safe) — but now only after an explicit UTF-8 decode, so the common
   Chinese-payload path no longer hits the swallow at all.
3. **Settings template (defense-in-depth)** — `installer.py`
   `_write_settings_local_json` natively sets `env.PYTHONUTF8 = "1"` on fresh
   installs and merges it in (without clobbering an existing `env` block) on
   re-install, so the runtime mitigation is guaranteed present rather than
   only *preserved* when a consumer happened to set it earlier.

## Non-Goals

- **Not** converting the 15 non-`_guard_common` hooks to import a shared
  module. Hooks are standalone scripts; adding sys.path bootstrap + a shared
  import to 15 more risks the in-process-import stdout-rebind class of bug.
  The per-hook one-line byte-decode is minimal and coupling-free. (A small
  `read_stdin_json()` helper in `_guard_common.py` MAY be added for the 4
  hooks that already import it; optional, not required for correctness.)
- **Not** changing stdout/stderr wrapping (several hooks already wrap output
  in a UTF-8 `TextIOWrapper`; the input side is the bug).
- **Not** altering any hook's allow/block *decision logic* — only how the
  payload bytes become a dict, and the fail branch on undecodable input.
- **Not** touching the constitution / contracts / classify-paths globs
  (P-0084 already governs the path set; this is a decode fix, different root).

## Guardrails

- **edit-write-guard**: edits are to `governance_core/hooks/*.py` and
  `governance_core/installer.py` (package source, in-boundary, core-writable).
  No constitution/`agent.core.md`/`CLAUDE.md` edits → no Art.13 block.
- **command-guard**: running `governance-core upgrade` and `tools/test_*.py`;
  avoid denied `rm -rf`/redirect literals (use `2>$null`, `-F` body files).
- **boundary-guard**: all targets inside the repo; no cross-boundary writes.
- **Art.11 (source/autonomy)**: edit package source `governance_core/` only,
  then `upgrade --project-root .` to re-materialize the autonomy layer —
  never hand-edit root `.claude/hooks/` copies.

## Phases

### Phase 0: Governance bootstrap

- Deliverables: this proposal approved; no constitution change required
  (decode-discipline is an implementation rule, not a new clause). If review
  decides the UTF-8-stdin rule should be codified, defer to a follow-up
  `/iterate-constitution` — out of scope here.
- Validation: proposal `submit` → user `approve`.
- Exit criteria: status `approved`.

### Phase 1: Shared pattern + security-critical gate first

- Deliverables: fix `proposal-classify-fast.py` (the gate with 313 logged
  fail-opens) to UTF-8 byte read + `UnicodeDecodeError`-aware fail-closed;
  add a regression test (`governance_core/tools/test_*`) that feeds a
  PreToolUse JSON containing Chinese bytes with `PYTHONUTF8` *unset* and
  asserts the gate does NOT exit 0 (no fail-open), and that a truly malformed
  payload fails on the known branch.
- Validation: new test green; existing classify-gate tests green.
- Exit criteria: classify gate no longer fails open on Chinese payloads.

### Phase 2: Sweep remaining stdin-reading hooks

- Deliverables: apply the UTF-8 byte read + `UnicodeDecodeError` handling to
  the other 18 hooks, preserving each one's gate-vs-advisory fail posture
  (see Scope §2).
- Validation: per-file hook test suites green (pytest-style + script-style,
  run per-file per memory `gc-test-suite-two-styles`); a grep confirms zero
  remaining `json.load(sys.stdin)` / `sys.stdin.read()` text-mode reads in
  `governance_core/hooks/`.
- Exit criteria: all 19 hooks decode stdin UTF-8-explicitly.

### Phase 3: Installer settings env default

- Deliverables: `_write_settings_local_json` sets `env.PYTHONUTF8="1"` on
  fresh install (in the new-file `data` dict) and merge-if-absent on
  re-install (preserve any existing `env` keys); update/extend installer
  tests to assert the env key is present after a fresh write and preserved on
  merge.
- Validation: installer test suite green; inspect a freshly generated
  `settings.local.json` shows `"env": {"PYTHONUTF8": "1"}`.
- Exit criteria: fresh consumer install ships the mitigation natively.

### Phase 4: Dogfood reinstall + close-out

- Deliverables: `governance-core upgrade --project-root .` to re-materialize
  this repo's autonomy layer; run the full hook + installer test suites from
  repo root; manual classify-gate check with a Chinese payload.
- Validation: all suites green; STATE.md updated before the phase commit
  (per memory `phase-commit-state-first`); version bump per release norms.
- Exit criteria: implemented + issue #98 closed referencing the commit.

## Approval Criteria

- Reviewer agrees the primary fix is the locale-independent
  `sys.stdin.buffer.read().decode("utf-8")` (not relying on `PYTHONUTF8`).
- Reviewer agrees gate hooks fail **closed/known** and advisory hooks stay
  fail-safe (exit 0) on genuinely undecodable input — no gate is loosened.
- Reviewer agrees the settings `env.PYTHONUTF8` is additive defense-in-depth
  and merge-if-absent (won't clobber a consumer's existing `env`).
- Scope is limited to decode plumbing; no decision logic changes.

## Validation Plan

- New regression test: feed `proposal-classify-fast.py` a PreToolUse JSON with
  Chinese characters via stdin, `PYTHONUTF8` unset, assert non-zero/blocking
  exit (was exit 0 fail-open).
- `grep -rn "json.load(sys.stdin)\|sys.stdin.read()" governance_core/hooks` →
  empty after Phase 2.
- Run `tools/test_*.py` for the touched hooks (per-file, both styles) and the
  installer suite from repo root (per memory `gc-test-suite-run-from-autonomy-layer`).
- After `upgrade --project-root .`, drive `proposal-classify-fast.py` via
  subprocess with a Chinese payload and confirm fail-closed (per memory
  `hook-stdout-rebind-breaks-inprocess-import`, drive via subprocess not import).

## Rollback / Recovery

- Per-phase: changes are isolated to hook sources + installer; `git revert`
  the package-source commit then `upgrade --project-root .` restores prior
  behavior.
- The settings `env.PYTHONUTF8` entry is additive and harmless; removing it
  only drops the secondary mitigation, the code fix stands alone.
- No data migration / no irreversible state; classify ledger untouched.

## Risks

- **Per-hook fail-posture regression** (med prob, high impact if wrong): a
  gate accidentally turned fail-open, or an advisory hook accidentally turned
  blocking. Mitigation: per-hook review of the `except` branch; gate-vs-
  advisory matrix in Scope §2; regression test on the classify gate.
- **Settings env merge clobbers consumer env** (low prob, med impact).
  Mitigation: merge-if-absent, preserve existing keys; installer test.
- **Stale build cache hides a dropped file** (low): none added/removed here,
  but if a test file is added under `governance_core/`, confirm wheel
  package-data (memory `wheel-package-data-nonpy`) and `rm -r build` before
  any `python -m build` (memory `stale-build-lib-cache-masks-file-removal`).
- **Text-mode newline reliance** (very low): all 19 reads feed a JSON parser
  that is newline-agnostic; byte read changes nothing semantically.

## State Log

- 2026-06-16: draft created by core agent (P-0101)
- 2026-06-16: draft → pending (submit for review: UTF-8 stdin decode fix for classify gate fail-open (issue #98))
- 2026-06-16: pending → approved (user approval signal: 批准)
- 2026-06-16: approved → in-progress (begin Phase 1: classify gate UTF-8 fix + regression test)
- 2026-06-16: in-progress → implemented
