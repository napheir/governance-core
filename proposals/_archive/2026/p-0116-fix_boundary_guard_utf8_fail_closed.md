---
id: P-0116
agent: core
status: implemented
created: 2026-07-01
approved_at: 2026-07-01
implemented_in: 372be21
implemented_at: 2026-07-01
owner: core
---

# Proposal P-0116: Fix session-boundary-guard.py: restore UTF-8 byte-decode (T-0015) + fail-closed on unparseable payload (#123)

## Trigger

Issue #123 (governance-core internal, not a `candidate`): the user-global
`session-boundary-guard.py` template regresses two hardenings a consumer had
applied — it uses text-mode `json.load(sys.stdin)` (mis-decodes CJK paths under a
GBK/cp936 locale) and fails **open** (`exit 0`) on an unparseable payload. Surfaced
in a consumer's 0.38.4->0.38.7 upgrade review. Owner directive (2026-07-01): fix
**fail-closed** (restore BOTH the UTF-8 byte-decode and the fail-closed posture).
Touches a security-backstop hook source → classify PROPOSAL_REQUIRED.

## Current State (read, not assumed)

- `governance_core/tools/session-boundary-guard.py:424-429` `main()`:
  ```python
  try:
      hook_input = json.load(sys.stdin)      # text mode, ambient locale
  except Exception:
      sys.exit(0)                             # fail OPEN
  ```
- **Every** other shipped hook reads bytes + explicit UTF-8 (T-0015): all 20
  `governance_core/hooks/*.py` use `json.loads(sys.stdin.buffer.read().decode("utf-8"))`
  (verified by grep). `session-boundary-guard.py` is the **lone outlier** still on
  text-mode `json.load`.
- `governance_core/hooks/edit-write-guard.py:627-630` shows the sibling pattern:
  byte-read + UTF-8, but `except Exception: sys.exit(0)` (fail **open**). So the
  UTF-8 decode is family-consistent; fail-**closed** is a boundary-guard-specific
  hardening (its role as the primary backstop under global `bypassPermissions`).
- Precedent: **P-0101** (archived) applied this exact byte-read UTF-8 fix to
  `proposal-classify-fast.py` to stop a Win-GBK fail-open; **P-0087** is a prior
  boundary-guard correctness fix. `governance_core/tools/test_session_boundary_guard.py`
  exists (25 subprocess-driven cases) — no CJK-decode or parse-error case yet.

## Scope

- `governance_core/tools/session-boundary-guard.py` `main()`: replace
  `json.load(sys.stdin)` with `json.loads(sys.stdin.buffer.read().decode("utf-8"))`;
  change the `except` branch from `sys.exit(0)` to a stderr BLOCKED message +
  `sys.exit(2)` (fail-closed).
- `test_session_boundary_guard.py`: add (a) a CJK-path-outside-boundary case under a
  non-UTF-8 stdio locale that must still BLOCK, and (b) a malformed-payload case that
  must BLOCK.
- Version bump; close #123.

## Design & Contract

### Interfaces, I/O & Realization
- `main()` (`session-boundary-guard.py`), a PreToolUse `Bash|Edit|Write` hook
  (user-global). INPUT: the PreToolUse payload on **stdin as raw bytes** →
  `.decode("utf-8")` → `json.loads` → dict (`tool_name`, `tool_input.file_path` /
  `tool_input.command`). OUTPUT: process exit code — `0` allow/delegate, `2` block
  (+ stderr reason). On decode/parse failure: stderr "BLOCKED: could not parse tool
  payload (failing closed)" + `exit 2`. Realizer: the hook process itself; no other
  component. The boundary-decision logic (`check_target`, critical paths, override)
  is unchanged.
- **Field Dictionary**: N/A — the only data crossing a boundary is the hook's own
  stdin payload (a Claude Code event schema owned by the harness, not a `contracts/`
  file); no persisted/cross-agent field is added or changed.

### Flow
Claude Code PreToolUse event (UTF-8 bytes on stdin) -> `sys.stdin.buffer.read()`
-> `.decode("utf-8")` -> `json.loads` -> boundary decision -> exit 0 (allow) / exit 2
(block). Parse failure -> exit 2 (block).

## Non-Goals

- **No change to the boundary-decision logic** (`check_target`, critical-path set,
  override, read-only fast-exit, redirect handling) — only the stdin parse + the
  parse-error posture change.
- **No auto-update of the live user-global `~/.claude/hooks/session-boundary-guard.py`**:
  `governance-core upgrade --project-root .` installs to the *project* `tools/`, not
  `~/.claude/hooks/`. Consumers re-install/refresh their user-global hook separately;
  this proposal only fixes the package-source template. (This is also why the fix
  cannot self-lock the current hub session.)
- No propagation to the fail-open posture of sibling PreToolUse guards — their
  fail-open is intentional (availability); only the primary backstop hardens.

## Open Questions

- Parse-error posture: fail-open (issue's stated minimum) vs fail-closed.
  **Resolved: fail-closed** (owner directive). A security backstop under global
  `bypassPermissions` must not silently allow a cross-boundary write when it cannot
  read its own input. Availability tradeoff (an unparseable payload now blocks) is
  accepted: Claude Code always sends a JSON payload for PreToolUse, and the decode is
  now robust UTF-8, so the failure surface is near-empty.

## Alternatives & Rationale

- **UTF-8 decode only, keep fail-open** (issue's stated minimum): rejected per owner
  directive — leaves the backstop silently allowing on any future parse failure.
- **UTF-8 decode + fail-closed** (chosen): restores both hardenings; matches the
  consumer's already-running version and retires the per-consumer drift.
- **Do nothing / per-consumer drift**: rejected — the consumer must re-harden on every
  upgrade; the correctness bug (CJK mis-decode) ships to every consumer.

## Guardrails

- `edit-write-guard`: edits are package source under `governance_core/tools/` — not
  the constitution trio; allowed. `constitutional-review` skips `tools/` paths.
- `boundary-guard`: this IS that guard; the edit is in-boundary (repo). The live
  user-global hook is untouched by the project upgrade, so no self-lock risk.
- Package isolation (Art.11.4): both files already ship under `governance_core/tools/`;
  wheel-content check confirms no leakage regression.

## Phases

### Phase 1: Fix parse + posture, add regression tests

- Deliverables:
  - `session-boundary-guard.py` `main()`: byte-read UTF-8 decode + fail-closed.
  - `test_session_boundary_guard.py`: CJK-under-non-UTF-8-stdio BLOCK case +
    malformed-payload BLOCK case.
  - Version bump; #123 closed.
- Validation:
  - `python tools/test_session_boundary_guard.py` — all cases pass (25 existing + new).
  - The CJK case FAILS against the old code (ascii stdio -> old `json.load` raises ->
    old fail-open exit 0 != expected block), proving the regression is covered.
  - `governance-core upgrade --project-root .` + `doctor` exit 0.
  - Wheel isolation: top-level `governance_core*` only, `maintainer/` absent.
- Exit criteria: all validation green; #123 closed.

## Approval Criteria

- [ ] `main()` reads `sys.stdin.buffer.read().decode("utf-8")` (aligns with all 20
      sibling hooks, T-0015).
- [ ] Parse/decode failure -> stderr BLOCKED + `sys.exit(2)` (fail-closed).
- [ ] Boundary-decision logic unchanged (no scope creep into check_target/criticals).
- [ ] Regression test: CJK path outside boundary under non-UTF-8 stdio still BLOCKS.
- [ ] Regression test: malformed payload BLOCKS (fail-closed).
- [ ] Field Dictionary N/A justified (harness-owned stdin schema, no contracts/ field).
- [ ] upgrade + doctor exit 0; wheel isolation clean.

## Validation Plan

1. `python tools/test_session_boundary_guard.py` (run after `upgrade` copies the fix
   to `tools/`) — existing 25 + new cases green.
2. Confirm the CJK regression case would fail on the pre-fix code (documented in the
   test comment; the ascii-stdio env forces the old text-mode read to raise).
3. `governance-core upgrade --project-root .` then `governance-core doctor` -> exit 0.
4. `python -m build --wheel` -> top-level `governance_core*` only, `maintainer/` absent.

## Rollback / Recovery

Revert `main()` to `json.load(sys.stdin)` + `sys.exit(0)` and drop the two test cases.
Single-function change; no state migration. (Reverting reintroduces the CJK mis-decode
and fail-open, so rollback is only for an unforeseen availability regression.)

## Risks

- **Fail-closed availability** (low): an unparseable PreToolUse payload now BLOCKS the
  Bash/Edit/Write instead of delegating. Mitigation: Claude Code always sends a JSON
  payload; the decode is robust UTF-8; a backstop that cannot read its input must not
  silently allow. Matches the consumer's already-running hardened version.
- **Self-lock during rollout** (none): the project `upgrade` does not touch the live
  `~/.claude/hooks/` copy; the hub session's guard is unaffected until the user-global
  hook is refreshed out-of-band.

## State Log

- 2026-07-01: draft created by core agent (P-0116)
- 2026-07-01: draft → pending (submit for review: boundary-guard UTF-8 byte-decode + fail-closed (#123))
- 2026-07-01: pending → approved (user approval: 批准实施 (AskUserQuestion 2026-07-01))
- 2026-07-01: approved → implemented
