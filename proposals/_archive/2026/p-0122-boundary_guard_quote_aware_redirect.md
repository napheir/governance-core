---
id: P-0122
agent: core
status: implemented
created: 2026-07-10
approved_at: 2026-07-10
implemented_in: d20a8b8
implemented_at: 2026-07-10
owner: core
---

# Proposal P-0122: session-boundary-guard: quote-aware redirect detection (stop false-blocking > inside quoted strings)

## Trigger

The `>`-inside-a-quoted-string false positive is a documented residual of both
#134 (device-sink fix) and P-0121 (tool coverage): a `>`/`>>` that appears
inside a quoted string or inline script is captured by the naive redirect regex
and can false-block. It bit repeatedly THIS session — every commit message
containing `> /path` or `2>$null` had to be routed through a `-F` message file to
avoid the guard blocking `git commit`. The user asked to fix it (loose-end item
1). This CHANGES what a security hook catches (redirect detection) →
`classify = PROPOSAL_REQUIRED` (security-sensitive). Boundary-guard lineage:
P-0087 (read-only fast-exit vs write-redirect), P-0121 (tool coverage), P-0116
(decode/fail-closed).

## Current State (read, not assumed)

- `governance_core/tools/session-boundary-guard.py:114-115` — the redirect
  pattern treats ANY `>` as a redirect operator:
  ```python
  (re.compile(r">>?\s*([^\s&|;<>]+)"), 1, "redirect"),
  ```
  A `>` inside a quoted data string (`git commit -m "use x > /outside"`) or an
  inline-script regex literal (`python -c "re.match(r'>>?', s)"`) is captured as
  a write target and checked → false block when the captured token resolves
  outside the boundary (or hits a critical pattern like `/.ssh/`).
- `session-boundary-guard.py:257-289` — `extract_bash_paths`: the pattern loop;
  each match's captured token is quote-stripped, device-sink-filtered, then
  `check_target`-ed. There is no notion of whether the `>` operator itself was
  inside quotes.
- `session-boundary-guard.py:194` — `is_read_only_bash` treats any `>` as
  "not read-only" (so a quoted-`>` command falls through to `extract_bash_paths`
  rather than fast-exiting; correctness then depends entirely on the extractor).
- The residual is already recorded as out-of-scope in the archived P-0121
  Non-Goals and the #134 scope note ("needs a shell-aware tokenizer — larger and
  riskier").

## Scope

`governance_core/` package source only:

- `governance_core/tools/session-boundary-guard.py` — add a quote-mask helper;
  in `extract_bash_paths`, for the `redirect` label, skip a match whose `>`
  operator falls inside a balanced quoted span.
- `governance_core/tools/test_session_boundary_guard.py` — add quoted-`>` allow
  cases + real-redirect-still-blocks + quoted-target-still-blocks +
  unbalanced-quote fail-safe cases.

## Design & Contract

### Interfaces, I/O & Realization

**Realizer**: the hook script itself (PreToolUse, exit 0/2). No new process.

- New pure helper `_quoted_char_mask(command: str) -> tuple[list[bool], bool]`:
  left-to-right scan tracking single/double quote state (single quotes are
  literal inside double and vice-versa; non-nesting). Returns `(mask, balanced)`
  where `mask[i]` is True iff char `i` is inside a quote, and `balanced` is True
  iff quotes closed cleanly (final state not inside any quote).
- In `extract_bash_paths`: compute `(mask, balanced)` once. For the `redirect`
  pattern ONLY, skip a match when `balanced and mask[m.start()]` is True — i.e.
  the `>` operator itself is inside a quoted string, so it is literal data, not a
  shell redirect. All other patterns (cp/mv/Set-Content/Remove-Item/…) are
  unchanged (they require a verb, so they do not false-positive on arbitrary
  quoted `>`).
- **Fail-safe**: when `balanced` is False (unbalanced/odd quotes, ambiguous
  parse), the mask is NOT trusted — the `>` is treated as a redirect (current
  behavior), preserving over-blocking rather than risking an under-block.

### Field Dictionary

N/A — the only inputs are the external Claude Code PreToolUse payload
(`tool_input.command`), an external harness schema, not gc-persisted and not
governed by a gc `contracts/` file (same as P-0121).

### Flow

```
command string → _quoted_char_mask → (mask, balanced)
  → redirect regex matches
       for each match m:
         if balanced and mask[m.start()]  → drop (quoted '>' = literal)
         else                             → extract target → check_target
  → exit 0 (allow) | exit 2 (block)
```

## Non-Goals

- **Full shell tokenizer + recursion into `-c` / `-Command` / `-e` arguments**:
  the "correct" way to catch a redirect INSIDE a spawned subshell script
  (`bash -c 'echo x > /outside'`) is to tokenize and recurse. Larger, riskier
  for a security hook; deferred.
- **Quoted-subshell redirects stop being caught** (`bash -c 'echo > /outside'`):
  this is the accepted trade-off — the `>` is inside quotes, so this change drops
  it. That write is a **subprocess-internal write**, which is ALREADY a
  documented non-goal of this guard (#135 / P-0121 Gap B: the guard cannot see
  writes inside a spawned subprocess/script). So this change removes an
  incidental, inconsistent catch — it opens no path the guard ever GUARANTEED to
  close. The top-level redirect (`cmd > /outside`, unquoted `>`) is unchanged.

## Open Questions

- Accept losing the incidental catch of quoted-subshell redirects
  (`bash -c 'echo > /out'`) to fix the high-frequency quoted-`>` false positive?
  **Resolved — yes.** Subprocess-internal writes are already a documented
  non-goal (guard is defense-in-depth, not a sandbox), and the false positive is
  frequent + blocks routine `git commit`. If silence: ship the quote-mask.

## Alternatives & Rationale

- **(A) Full shlex tokenizer + recurse into `-c`/`-Command`**: correct for both
  the false positive AND quoted-subshell redirects, but a large, higher-risk
  rewrite of a security hook's core scan (shlex raises on unbalanced quotes /
  Windows backslash paths; needs careful fallback). Deferred.
- **(B, chosen) Quote-mask skip for the redirect operator, fail-safe on
  unbalanced quotes**: small, surgical, provably scoped to the `redirect` label;
  fixes the frequent false positive; opens no guaranteed-covered write path
  (loses only the already-non-goal quoted-subshell catch); over-blocks (current
  behavior) when the parse is ambiguous.
- **(C) Do nothing / keep the `-F` message-file workaround**: rejected — the
  false positive recurs on routine commits and inline scripts; the workaround is
  friction, not a fix.

## Guardrails

- Modifies `session-boundary-guard` itself: validation must prove no regression
  to real top-level redirect catching (existing block cases 22/23/36) and to the
  device-sink / critical-path / override paths (full 46-case suite green).
- `edit-write-guard` governs the source Edit; `command-guard` the test runs. No
  contract/constitution file touched → no `/iterate-constitution`.

## Phases

### Phase 1: quote-aware redirect detection

- Deliverables:
  - `_quoted_char_mask` helper + redirect-label skip in `extract_bash_paths`
    (fail-safe on unbalanced quotes).
  - Test cases: quoted-`>` in a commit-message-style command → allow; inline
    `python -c` regex-literal `>>?` → allow; real `cmd > /outside` (unquoted `>`)
    → still block; `cmd > "/outside"` (quoted TARGET, unquoted `>`) → still
    block; unbalanced-quote command → still scanned (fail-safe); all existing 46
    cases unchanged.
- Validation: `python governance_core/tools/test_session_boundary_guard.py`
  exit 0; dogfood `governance-core upgrade --project-root .`; deploy to
  user-global enforcing copy; live-check that a `git commit -m` containing
  `> /path` no longer blocks.
- Exit criteria: full suite green incl. new cases; live commit-message check
  passes.

## Approval Criteria

- [ ] Every Field Dictionary entry names its governing `contracts/` file (or is N/A) — human-verify: N/A (external PreToolUse payload), reason given
- [ ] Every user-facing capability / mutation has a named realizer — human-verify: the hook script itself; no implied-but-unbuilt component
- [ ] All Open Questions are resolved or explicitly deferred — human-verify: the single Open Question is resolved (accept trade-off)
- [ ] A quoted `>` (commit-message / inline-script style) no longer false-blocks — cmd: python governance_core/tools/test_session_boundary_guard.py
- [ ] A real top-level redirect `cmd > /outside` (unquoted `>`) STILL blocks — cmd: python governance_core/tools/test_session_boundary_guard.py
- [ ] A quoted redirect TARGET `cmd > "/outside"` (unquoted `>`) STILL blocks — cmd: python governance_core/tools/test_session_boundary_guard.py
- [ ] An unbalanced-quote command is still scanned (fail-safe, not skipped) — cmd: python governance_core/tools/test_session_boundary_guard.py
- [ ] All existing 46 boundary-guard cases pass unchanged — cmd: python governance_core/tools/test_session_boundary_guard.py

## Validation Plan

1. `python governance_core/tools/test_session_boundary_guard.py` — full suite
   (existing 46 + new quoted-`>` / real-redirect / quoted-target / unbalanced
   cases) exit 0.
2. `python governance_core/tools/test_derive_session_boundary.py` — peer green.
3. Dogfood `governance-core upgrade --project-root .`; deploy to user-global
   enforcing copy (per [[session-boundary-guard-enforced-from-user-global]]).
4. Live: a `git commit -m "... > /some/path ..."` no longer blocks (the very
   friction this session hit); a real `echo x > <outside>` still blocks.

## Rollback / Recovery

Single-commit change to one hook + its test. Revert the commit and
`governance-core upgrade --project-root .` (+ re-copy to user-global) to restore
prior behavior. No state migration, no contract change.

## Risks

- **Losing the incidental quoted-subshell redirect catch** (prob: n/a — by
  design; impact: low) — already a documented non-goal (subprocess-internal
  writes); the guard is defense-in-depth, not a sandbox. Mitigation: documented;
  top-level redirects unchanged.
- **Quote-parse edge cases** (escaped quotes `\"`, `$'...'`, nested) (prob: low;
  impact: low) — mitigated by the `balanced` fail-safe: any ambiguous parse
  reverts to current (over-blocking) behavior, never under-blocks.
- **Accidentally skipping a real redirect** (prob: very low; impact: medium) —
  a real redirect operator is unquoted, so `mask[m.start()]` is False and it is
  NOT skipped; only a `>` genuinely inside balanced quotes is dropped. Covered by
  the real-redirect + quoted-target regression cases.

## State Log

- 2026-07-10: draft created by core agent (P-0122)
- 2026-07-10: draft → pending (submit for review: quote-aware redirect detection)
- 2026-07-10: pending → approved (user approved: 批准 (explicit approval signal, 2026-07-10))
- 2026-07-10: approved → implemented
