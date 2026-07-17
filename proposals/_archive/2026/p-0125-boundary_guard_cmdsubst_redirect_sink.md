---
id: P-0125
agent: core
status: implemented
created: 2026-07-17
approved_at: 2026-07-17
implemented_in: e9a32b7
implemented_at: 2026-07-17
owner: core
---

# Proposal P-0125: session-boundary-guard: exclude cmdsubst/backtick closers from bare redirect capture (stop false-blocking device sinks in $(...))

## Trigger

Issue #137 (user-filed): the device-sink discard fix shipped in P-0121/P-0122
(#134/#135) has a **residual tail** — a stderr/stdout discard whose redirect sits
at the END of a command substitution `$(… 2>/dev/null)` or backtick
`` `… 2>/dev/null` `` is still false-blocked. The redirect capture class swallows
the closing `)` / `` ` `` into the target (`/dev/null)`), so the `DEVICE_SINKS`
exact-match misses and the discard is treated as a real cross-boundary write →
`exit 2`. `$(… 2>/dev/null)` is an extremely common shell shape (git plumbing in
`$(...)`, tool scripts, and — ironically — commit messages that quote the
pattern), so the false positive recurs constantly. The user asked to fix it:
"之前的升级优化不够干净" (the previous upgrade wasn't clean enough).

This CHANGES what a security hook catches (redirect capture) →
`classify = PROPOSAL_REQUIRED` (security-sensitive), same reasoning and lineage as
P-0122: P-0087 (read-only fast-exit vs write-redirect), P-0121 (tool coverage),
P-0116 (decode/fail-closed), P-0122 (quote-aware redirect). This is the strict
tail P-0122 left: P-0122 stopped a `>` *inside quotes* from being read as a
redirect; this stops a bare redirect target from swallowing the shell
metacharacter that *closes* a subshell/cmdsubst.

## Current State (read, not assumed)

- `governance_core/tools/session-boundary-guard.py:137` — the redirect pattern:
  ```python
  (re.compile(r">>?\s*([^\s&|;<>]+)"), 1, "redirect"),
  ```
  The negated class `[^\s&|;<>]+` excludes whitespace, `&`, `|`, `;`, `<`, `>` —
  but **not** `)`, `(`, or backtick. So a `>`/`2>` immediately before `)` /
  `` ` `` swallows that closer into the captured path.
- `session-boundary-guard.py:371` — device-sink membership is EXACT:
  `if p.lower() in DEVICE_SINKS:`. With the contaminated `/dev/null)` the
  exact-match fails, so the sink is not skipped and the (non-existent) path is
  boundary-checked and blocked.
- `DEVICE_SINKS` (`:103-107`) holds bare tokens (`/dev/null`, `$null`, `nul`, …) —
  no trailing metacharacters, so any closer contamination defeats it.
- The P-0122 quote-mask (`_quoted_char_mask`, `:294-330`) is orthogonal: it only
  suppresses a `>` operator that sits *inside quotes*. A `2>/dev/null` inside
  `$( … )` is UNQUOTED, so the quote-mask does not touch it — this residual is
  outside P-0122's scope by construction.
- **Reproduced** (harness driving the real hook via PreToolUse stdin, this
  session):
  - `y=$(echo hi 2>/dev/null)` → `exit 2`, `Target: /dev/null)` (BUG)
  - `` foo=`grep x f 2>/dev/null` `` → `exit 2`, `Target: /dev/null` + trailing
    backtick (BUG)
  - `echo hi 2>/dev/null` (bare) → `exit 0` (control, already correct)
  - `(cat a > /outside/real)` → `exit 2`, `Target: /outside/real)` (real write,
    correctly still blocks — only the displayed target is cosmetically wrong)

## Scope

`governance_core/` package source only (no contract / constitution file):

- `governance_core/tools/session-boundary-guard.py` — widen the negated character
  class of the `redirect` capture pattern (line 137) to also exclude `(`, `)`, and
  backtick, so a bare redirect target terminates on the shell metacharacters that
  open/close a subshell or command substitution.
- `governance_core/tools/test_session_boundary_guard.py` — add cmdsubst /
  backtick device-sink allow cases + a subshell real-write regression (still
  blocks) mirroring the existing 52-case harness.

After the source edit: `governance-core upgrade --project-root .` to dogfood into
the repo autonomy layer, plus re-copy to the user-global enforcing copy
(`~/.claude/hooks/session-boundary-guard.py`) per
[[session-boundary-guard-enforced-from-user-global]] — the autonomy `tools/` copy
is NOT the copy that enforces the current session.

## Design & Contract

> Proportionate. Trivial change: one line "implementation self-evident; no interface
> or data-flow change." Otherwise fill all three sub-parts; use "N/A — <reason>" for
> any that genuinely doesn't apply — never leave a placeholder.

### Interfaces, I/O & Realization

**Realizer**: the hook script itself (`session-boundary-guard.py`, PreToolUse,
exit 0/2). No new process, no new function, no signature change.

The only change is the regex literal of ONE existing pattern in
`BASH_PATH_PATTERNS`:

```python
# before
(re.compile(r">>?\s*([^\s&|;<>]+)"), 1, "redirect"),
# after
(re.compile(r">>?\s*([^\s&|;<>()`]+)"), 1, "redirect"),
```

INPUT consumed: the external Claude Code PreToolUse payload
(`tool_input.command` string). OUTPUT produced: exit code (0 allow / 2 block) +
stderr diagnostics. The captured `redirect` target (group 1) now terminates at a
subshell/cmdsubst boundary char instead of swallowing it; downstream
`DEVICE_SINKS` exact-match and `check_target` are unchanged and now receive the
clean token.

### Field Dictionary

N/A — the only input is the external Claude Code PreToolUse payload
(`tool_input.command`), a harness schema not gc-persisted and not governed by a gc
`contracts/` file (same as P-0121 / P-0122).

### Flow

```
command string → redirect regex `>>?\s*([^\s&|;<>()`]+)` (group 1)
   e.g. `2>/dev/null)`  → captures `/dev/null`  (closer ) NOT swallowed)
        `2>/dev/null` ` → captures `/dev/null`  (closer ` NOT swallowed)
        `> /outside/real)` → captures `/outside/real` (real path, closer dropped)
  → p.lower() in DEVICE_SINKS ?  yes → skip (allow)   no → check_target
  → exit 0 (allow) | exit 2 (block)
```

## Non-Goals

- **Full shell tokenizer / recursion into `-c` / `-Command` subshell scripts**:
  still deferred (same non-goal as P-0122). A redirect *inside* a spawned
  subprocess script (`bash -c 'echo x > /outside'`) remains uncaught — documented
  as defense-in-depth, not a sandbox.
- **Changing the `is_read_only_bash` redirect-presence probe** (`:245`,
  `re.search(r">>?\s*[^\s&|;<>]", command)`): NOT touched. It only decides whether
  a command has *some* file-write redirect (so it should not fast-exit as
  read-only); it extracts no path. A `$(cmd 2>/dev/null)` correctly falls through
  to `extract_bash_paths`, which then recognizes the sink. Widening it is
  unnecessary and out of scope.
- **The cosmetic `Target:` in a real subshell block** (`(cat a > /outside/real)`
  currently prints `/outside/real)`): the fix incidentally corrects this to
  `/outside/real`, but improving block diagnostics is not the goal — safety is
  (the real write still blocks either way).

## Open Questions

None. The grammar argument is decisive: a bare (unquoted) redirect target cannot
legitimately contain `)` / `(` / backtick in POSIX shell — those close a subshell
/ command substitution, and bash raises a syntax error on an unquoted `(`/`)` in a
filename. So excluding them from the *bare* capture is correct grammar, not a
heuristic, and it cannot cause an under-block of a real write. (Quoted targets are
already handled by the P-0122 quote-mask; this only tightens the bare class.)

## Alternatives & Rationale

- **(A, chosen) Widen the redirect capture class** to `[^\s&|;<>()`]+`. Fixes both
  the device-sink miss AND the cosmetically-wrong `Target:` on real subshell
  writes, in one grammatically-sound edit. A bare redirect target legitimately
  terminates at `(` / `)` / `` ` `` (they are shell metacharacters), so this
  tightening cannot drop a real path.
- **(B) Keep the broad class; strip a trailing `)` / `` ` `` / `;` / `&` from the
  captured target before the DEVICE_SINKS / boundary check.** Also works, but it is
  a post-hoc cleanup that has to enumerate every trailing metacharacter and leaves
  the capture semantically wrong (it captured too much, then trimmed). Rejected:
  the capture-class fix is the cause-level fix; stripping is symptom-level.
- **(C) Do nothing** — rejected: `$( … 2>/dev/null)` is a pervasive shape;
  false-blocking it recurs constantly (the user filed #137 precisely because the
  prior "optimization wasn't clean enough").

## Guardrails

- Modifies `session-boundary-guard` itself: validation must prove NO regression to
  real redirect catching (existing block cases 22/23/36/49/50/51) and to the
  device-sink / critical-path / override / quote-mask paths (full 52-case suite
  green + the new cmdsubst cases).
- `edit-write-guard` governs the source Edit; `command-guard` the test runs.
- No `contracts/` / constitution file touched → no `/iterate-constitution`, no
  Phase 0 governance bootstrap.
- Dogfood requires re-copy to the user-global enforcing copy (the autonomy
  `tools/` copy is not what enforces this session) —
  [[session-boundary-guard-enforced-from-user-global]].

## Phases

### Phase 1: exclude cmdsubst/backtick closers from bare redirect capture

- Deliverables:
  - Widen the `redirect` capture class to `[^\s&|;<>()`]+` in
    `session-boundary-guard.py:137`.
  - Test cases (mirroring the 52-case harness): `$(cmd 2>/dev/null)` → allow;
    `` `cmd 2>/dev/null` `` → allow; `$(cmd >$null)` / `$(cmd 2>NUL)` → allow
    (device sinks in cmdsubst); `(cmd > <outside>)` inside a subshell → still
    block (real-write regression guard).
- Validation: `python governance_core/tools/test_session_boundary_guard.py`
  exit 0; `python governance_core/tools/test_derive_session_boundary.py` green;
  dogfood `governance-core upgrade --project-root .`; re-copy to user-global
  enforcing copy; live-check that a `$(… 2>/dev/null)` Bash command no longer
  blocks.
- Exit criteria: full suite green incl. new cmdsubst cases; live cmdsubst
  device-sink check passes; a real subshell write still blocks.

## Approval Criteria

> Each item pairs a plain-language acceptance with ONE discriminating check token
> (`cmd: <exit 0 = pass>` / `agent-rubric: <ref>` / `human-verify: <sentence>`; see
> contracts/proposal_gate_schema.md). An item with no check token is prose, not an
> acceptance signal.

- [ ] Every Field Dictionary entry names its governing `contracts/` file (or is N/A) — human-verify: N/A (external PreToolUse payload), reason given
- [ ] Every user-facing capability / mutation has a named realizer — human-verify: the hook script itself; no implied-but-unbuilt component
- [ ] All Open Questions are resolved or explicitly deferred — human-verify: none (grammar argument decisive)
- [ ] A device sink in a command substitution `$(cmd 2>/dev/null)` no longer false-blocks — cmd: python governance_core/tools/test_session_boundary_guard.py
- [ ] A device sink in backticks `` `cmd 2>/dev/null` `` no longer false-blocks — cmd: python governance_core/tools/test_session_boundary_guard.py
- [ ] A real write inside a subshell `(cmd > <outside>)` STILL blocks — cmd: python governance_core/tools/test_session_boundary_guard.py
- [ ] All existing 52 boundary-guard cases pass unchanged — cmd: python governance_core/tools/test_session_boundary_guard.py

## Validation Plan

1. `python governance_core/tools/test_session_boundary_guard.py` — full suite
   (existing 52 + new cmdsubst / backtick device-sink allow + subshell real-write
   block) exit 0.
2. `python governance_core/tools/test_derive_session_boundary.py` — peer green.
3. Dogfood `governance-core upgrade --project-root .`; re-copy to the user-global
   enforcing copy `~/.claude/hooks/session-boundary-guard.py` (per
   [[session-boundary-guard-enforced-from-user-global]]); confirm the enforcing
   copy now matches the package source.
4. Live: a `y=$(echo hi 2>/dev/null)` Bash command no longer blocks; a real
   `echo x > <outside>` and a subshell `(echo x > <outside>)` still block.

## Rollback / Recovery

Single-commit change to one hook + its test. Revert the commit and
`governance-core upgrade --project-root .` (+ re-copy to user-global) to restore
prior behavior. No state migration, no contract change.

## Risks

- **Accidentally dropping a real redirect path that legitimately contains
  `(`/`)`/backtick** (prob: none; impact: n/a) — a bare unquoted redirect target
  cannot contain those in POSIX shell (they are metacharacters / syntax errors in
  a filename). Quoted targets are handled by the P-0122 quote-mask, which is
  unchanged. Covered by the subshell real-write regression case.
- **Regression to an existing case** (prob: very low; impact: medium) — the change
  only NARROWS the redirect capture (excludes 3 more chars); every existing case's
  target contains none of `(`/`)`/backtick, so captures are byte-identical.
  Verified by the unchanged full 52-case suite.

## State Log

- 2026-07-17: draft created by core agent (P-0125)
- 2026-07-17: draft → pending (submit for review: exclude cmdsubst/backtick closers from bare redirect capture (issue #137))
- 2026-07-17: pending → approved (user approved: 批准 (explicit approval signal, 2026-07-17))
- 2026-07-17: approved → implemented
