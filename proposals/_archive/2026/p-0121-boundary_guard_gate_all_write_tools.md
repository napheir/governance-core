---
id: P-0121
agent: core
status: implemented
created: 2026-07-10
approved_at: 2026-07-10
implemented_in: 7457ae9
implemented_at: 2026-07-10
owner: core
---

# Proposal P-0121: session-boundary-guard: gate all write-capable tools (shape-based), not just Bash/Edit/Write

## Trigger

agent-core handoff `artifacts/gc-handoff/issue-boundary-guard-tool-coverage.md`
plus the user directive "优化一下防御机制". The handoff reports a coverage gap:
`session-boundary-guard` only gates `{Bash, Edit, Write}`, so every other
write-capable tool bypasses the boundary check entirely. This is a
**security-sensitive change to a hook source** that **tightens** enforcement
(blocks more) with consumer-visible breaking impact → `classify =
PROPOSAL_REQUIRED` (hook source + security-sensitive + breaking). It continues
the boundary-guard lineage of P-0087 (read-only fast-exit vs write-redirect)
and P-0116 (UTF-8 decode + fail-closed).

## Current State (read, not assumed)

- `governance_core/tools/session-boundary-guard.py:442-444` — the gate is an
  allowlist of THREE tool names; every other tool fast-exits unscanned:
  ```python
  tool_name = hook_input.get("tool_name", "")
  if tool_name not in {"Bash", "Edit", "Write"}:
      sys.exit(0)
  ```
- `session-boundary-guard.py:460-493` — routing today: Edit/Write →
  `tool_input.file_path` → `check_target`; Bash → `tool_input.command` →
  `is_read_only_bash` / `extract_bash_paths`.
- `~/.claude/settings.json` PreToolUse registers this hook with `matcher=""` —
  an empty matcher fires for **ALL** tools (confirmed). So the hook already
  *receives* PowerShell / NotebookEdit / Monitor calls; the in-script allowlist
  is the only thing letting them through. The fix is purely in-script; no
  settings/matcher change is required.
- Precedent for shape routing already in the codebase:
  `governance_core/hooks/proposal-classify-fast.py:79` extracts the path from
  `("file_path", "path", "notebook_path")`, and its manifest matcher is
  `Edit|Write|MultiEdit|NotebookEdit` (`hooks/hooks_manifest.json:12`).
- Harness facts verified this session:
  - PowerShell tool → `tool_name="PowerShell"`, input field `command` (confirmed
    via Claude Code tools reference + guide agent).
  - NotebookEdit → `tool_name="NotebookEdit"`, path field `notebook_path`
    (confirmed directly from the NotebookEdit tool JSONSchema — required
    absolute-path field).
  - Monitor → Bash-like `command` (flagged write-capable by the guide agent).
  - MultiEdit → not in the current tool set, but harmless to include defensively.
- `session-boundary-guard.py:117-118` already has `Set-Content` / `Out-File`
  regexes (added for `pwsh -Command`); `DEVICE_SINKS` (this session, v0.40.3)
  covers `/dev/null` family + `nul` but NOT PowerShell `$null`.

## Scope

`governance_core/` package source only (autonomy layer is a derived snapshot):

- `governance_core/tools/session-boundary-guard.py` — replace the 3-name
  allowlist in `main()` with shape-based routing (below); add PowerShell write
  verbs + `$null` device sink.
- `governance_core/tools/test_session_boundary_guard.py` — add PowerShell /
  NotebookEdit block+allow cases, device-sink `$null`/`NUL` allow cases, and a
  read-not-blocked regression case.

## Design & Contract

### Interfaces, I/O & Realization

**Realizer**: the hook script itself — `session-boundary-guard.py` as a
PreToolUse hook (stdin JSON → exit 0 allow / exit 2 block). No new process.

`main()` routing changes from a tool-NAME allowlist to **shape-based** routing:

1. **Command tools** — `tool_input` has a non-empty `command` (str) → scan via
   `is_read_only_bash` / `extract_bash_paths`. This is fully shape-based and
   covers Bash, PowerShell, Monitor, future shells, and command-shaped MCP
   tools with NO tool-name list. Only write-capable tools carry `command`; the
   scanner only flags real write patterns, so read subcommands pass.
2. **Path-write tools** — an explicit `WRITE_PATH_TOOLS` map
   `{"Edit":"file_path", "Write":"file_path", "NotebookEdit":"notebook_path",
   "MultiEdit":"file_path"}` → `check_target` on that field. This CANNOT be
   pure shape-based, because `file_path`/`path` are also carried by READ tools
   (Read → `file_path`; Glob/Grep → `path`); gating on field-presence alone
   would block legitimate cross-boundary READS. An explicit writer set is the
   correct realization of "gate-all" for the path shape.
3. Neither `command` nor a WRITE_PATH_TOOLS field → `sys.exit(0)`.

New write patterns appended to the command-scan pattern list (harmless on
non-matching input, so they can share one list): `Remove-Item`, `New-Item`,
`Copy-Item`, `Move-Item`, `Add-Content` (reuse existing `Set-Content`/`Out-File`
+ the `>`/`>>` redirect regex). `DEVICE_SINKS += {"$null"}` so PowerShell
`> $null` / `2>$null` is not false-blocked (mirrors the v0.40.3 device-sink fix).

### Field Dictionary

All fields consumed here are the **Claude Code PreToolUse hook payload** — an
EXTERNAL harness schema, not gc-persisted and not cross-agent, so no gc
`contracts/` file governs them (N/A — external harness contract).

| field | type | meaning | producer | consumer | constraints / allowed values |
|-------|------|---------|----------|----------|------------------------------|
| `tool_name` | str | invoked tool | CC harness | hook `main()` | any; used only for WRITE_PATH_TOOLS lookup |
| `tool_input.command` | str | shell command | CC harness | command-scan | present ⇒ command tool (Bash/PowerShell/Monitor/…) |
| `tool_input.file_path` | str | write target | CC harness | `check_target` | checked only for Edit/Write/MultiEdit |
| `tool_input.notebook_path` | str | .ipynb write target | CC harness | `check_target` | checked only for NotebookEdit |

### Flow

```
CC harness (PreToolUse, matcher="") → hook stdin {tool_name, tool_input}
  → repo-health alarm gate → derive_boundary(cwd)
  → shape route:
       command present         → is_read_only_bash / extract_bash_paths → check_target*
       WRITE_PATH_TOOLS field  → check_target
       else                    → exit 0
  → exit 0 (allow) | exit 2 (block)
```

## Non-Goals

- **Subprocess / script-internal writes** (handoff "Gap B"): the guard is a
  PreToolUse command/path scanner, not a sandbox. Writes inside a spawned child
  (`python -c "...open(outside,'w')"`, an external `.ps1`, `claude -p`,
  variable-indirected paths) are unseeable here. A hard guarantee needs
  OS-level enforcement (FS ACLs / AppContainer / Job Object / container) —
  resource-layer track, per machine. This hook stays defense-in-depth +
  accidental-write prevention + speed bump.
- **Write-capable MCP tools that carry a path field** (not `command`): cannot be
  distinguished from read MCP tools by field-shape alone; deferred to a
  follow-up (a consumer-maintained MCP allow/deny set, or a write-signal
  heuristic). Command-shaped MCP tools ARE covered by rule 1.
- **Exhaustive PowerShell write coverage**: `[System.IO.File]::WriteAllText`,
  `.NET` reflection, string-concat / variable-indirected paths — same residual
  class the guard already cannot catch for Bash.

## Open Questions

- Path-tool routing: field-shape vs explicit writer set? **Resolved** — explicit
  `WRITE_PATH_TOOLS` set, because Read/Glob/Grep share `file_path`/`path` and a
  shape-only rule would block cross-boundary READS (a bad, novel false positive).
  Command tools stay fully shape-based. If silence: ship the hybrid.

## Alternatives & Rationale

- **(A) Pure tool-name allowlist** (the handoff's literal `PATH_TOOLS` +
  `COMMAND_TOOLS`): simple, low over-block risk, but Monitor + write-capable MCP
  + future tools keep bypassing, and it depends on every tool_name string being
  exactly right (the guide agent could not confirm NotebookEdit's field name and
  surfaced a tool — Monitor — not on the list; brittle).
- **(B) Pure field-shape for both command AND path**: maximally robust but
  **wrong** — blocks cross-boundary READS (Read/Glob/Grep carry `file_path`/
  `path`).
- **(C, chosen) Hybrid**: shape-based for the `command` shape (robust, closes
  the scary PowerShell/Monitor/future gap with no name list) + explicit writer
  set for the path shape (correct; no read false-positives). Delivers the
  robustness intent of (B) exactly where it is safe, and the correctness of (A)
  where field-shape is ambiguous.

## Guardrails

- This proposal MODIFIES `session-boundary-guard` itself; validation must prove
  no regression to the existing Bash/Edit/Write + critical-path + override paths
  (full existing suite must stay green).
- `edit-write-guard` governs the source Edit; `command-guard` governs the test
  runs. No contract/constitution file touched → no `/iterate-constitution`.

## Phases

### Phase 1: shape-based routing + PowerShell/NotebookEdit coverage

- Deliverables:
  - `main()` shape-based routing (command-shape scan + `WRITE_PATH_TOOLS`
    explicit set + else-exit).
  - PowerShell write verbs (`Remove-Item`/`New-Item`/`Copy-Item`/`Move-Item`/
    `Add-Content`) + `$null` in `DEVICE_SINKS`.
  - Test cases: PowerShell write outside→block / inside→allow; PowerShell
    device-sink (`> $null`, `2>$null`, `>NUL`)→allow; PowerShell critical
    (`~/.ssh`)→block CRITICAL; NotebookEdit outside→block / inside→allow;
    **Read/Glob/Grep cross-boundary READ→allow (no regression)**; all existing
    Bash/Edit/Write + device-sink cases unchanged.
- Validation: `python governance_core/tools/test_session_boundary_guard.py`
  exit 0; `governance-core upgrade --project-root .` dogfood; manual
  PowerShell-tool write attempt to an out-of-boundary path observed to block.
- Exit criteria: full suite green incl. new cases; dogfood reinstall clean.

## Approval Criteria

- [ ] Every Field Dictionary entry names its governing `contracts/` file (or is N/A) — human-verify: all rows are the external PreToolUse payload, marked N/A with reason
- [ ] Every user-facing capability / mutation has a named realizer — human-verify: the hook script itself is the sole realizer; no implied-but-unbuilt component
- [ ] All Open Questions are resolved or explicitly deferred — human-verify: the single Open Question is resolved (hybrid)
- [ ] A PowerShell-tool write to an out-of-boundary path blocks (rc 2) and a critical path blocks CRITICAL — cmd: python governance_core/tools/test_session_boundary_guard.py
- [ ] PowerShell device-sink discards (`> $null`, `2>$null`, `>NUL`) are allowed — cmd: python governance_core/tools/test_session_boundary_guard.py
- [ ] NotebookEdit outside boundary blocks, inside allows — cmd: python governance_core/tools/test_session_boundary_guard.py
- [ ] Cross-boundary READS (Read/Glob/Grep-shaped path/command) remain allowed — no read regression — cmd: python governance_core/tools/test_session_boundary_guard.py
- [ ] Existing Bash/Edit/Write + device-sink + critical-path + override cases unchanged — cmd: python governance_core/tools/test_session_boundary_guard.py

## Validation Plan

1. `python governance_core/tools/test_session_boundary_guard.py` — full suite
   (existing 31 + new PowerShell/NotebookEdit/read-regression cases) exit 0.
2. `python governance_core/tools/test_derive_session_boundary.py` — peer green.
3. `governance-core upgrade --project-root .` — dogfood reinstall; diff the
   user-global enforcing copy per
   [[session-boundary-guard-enforced-from-user-global]] (upgrade won't touch it;
   note the deployment path).
4. Manual: a PowerShell-tool `Out-File`/`Remove-Item` to an out-of-boundary path
   is observed to block; a device-sink discard is observed to pass.

## Rollback / Recovery

Single-commit change to one hook + its test. Revert the commit and
`governance-core upgrade --project-root .` to restore prior behavior. No state
migration, no contract change. `CLAUDE_BOUNDARY_OVERRIDE=1` remains the runtime
escape hatch if a legitimate cross-boundary op is over-blocked before a revert.

## Risks

- **Over-blocking legitimate cross-boundary ops** (prob: medium; impact: low) —
  ops that silently succeeded via the un-gated PowerShell tool now require
  `CLAUDE_BOUNDARY_OVERRIDE=1` (audited; critical paths still never exempt).
  This is the intended, better posture, not a defect. Mitigation: the override
  valve; clear block message.
- **Blocking a cross-boundary READ** (prob: low; impact: medium — bad UX) —
  mitigated by routing path tools through an explicit WRITER set (Read/Glob/Grep
  never gated) and command tools only flagging real write patterns. Covered by
  the explicit read-regression test case.
- **Wrong PowerShell `tool_name`** silently disabling the gate (prob: low;
  impact: high) — mitigated by design: the command shape routes on the
  `command` FIELD, not the tool name, so even a renamed PowerShell tool is
  gated as long as it carries `command`.

## State Log

- 2026-07-10: draft created by core agent (P-0121)
- 2026-07-10: draft → pending (submit for review: gate-all write-capable tools via shape-based routing)
- 2026-07-10: pending → approved (user approved: 批准 (explicit approval signal, 2026-07-10))
- 2026-07-10: approved → implemented
