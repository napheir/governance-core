---
id: P-0117
agent: core
status: implemented
created: 2026-07-01
approved_at: 2026-07-01
implemented_in: 4d6f87a
implemented_at: 2026-07-01
owner: core
---

# Proposal P-0117: Let consumers declare intentional drift so _capture_drift stamps it layer:business (#119)

## Trigger

Issue #119 (governance-core internal, not a `candidate`): `installer.py::_capture_drift`
packages **every** install-managed file whose content differs from its
`installed_files.json` baseline as a `layer: candidate-common` drift envelope, so a
consumer's `/wrap-up` sweep re-uplinks the SAME intentional (permanent) drift on every
upgrade. Owner directive (2026-07-01): implement via `/proposal`, ADR **option 1**
(stamp `layer:business` at emission). Changes install/automation behavior + adds a
consumer-facing config file → classify PROPOSAL_REQUIRED.

## Current State (read, not assumed)

- `governance_core/installer.py:366-414` `_capture_drift`: for each manifest entry
  whose `_content_sha256` != baseline, calls `envelope.build_envelope(...)` **without
  a `layer=` argument** (`installer.py:400-410`).
- `governance_core/candidates/envelope.py:105-152`: `build_envelope(..., layer: str =
  "candidate-common", ...)`; `LAYERS = ("candidate-common", "business")` (`envelope.py:38`).
  So every captured drift defaults to `candidate-common`.
- Consumer sweep (`candidate.py sweep`) acts only on `candidate-common` envelopes; the
  digest ledger re-mints a fresh digest per date-stamped drift so `is_uplinked()` misses
  and re-sends; `rejected_registry.json` is reactive + name-global — none suppress
  recurring *intentional* drift at the source.
- Incident (issue #119): consumer `trade-agent` sweep uplinked 4 todo<->proposal bridge
  drift candidates that had to be deleted; recurs every upgrade.
- Cross-repo: trade-agent P-0125 already ships a consumer-side interim
  (`restore_todo_bridges.py`) that reads `.governance/intentional_drift.json`
  (`{"schema":1,"drift_targets":[...]}`) and prunes matching outbox envelopes pre-sweep.
- `_capture_drift` tests live in `governance_core/tools/test_installer_drift_eol.py`
  (pytest-style, `dry_run` path); no layer/intentional-drift case yet.

## Scope

- ADD `installer._load_intentional_drift(project_root) -> set[str]`: parse consumer-owned
  `.governance/intentional_drift.json` (`{"schema":1,"drift_targets":["<repo-rel path>",...]}`),
  fail-safe -> empty set on missing/malformed/wrong-schema, paths normalized to `/`.
- `_capture_drift`: load the set once; per drifted entry pass
  `layer="business" if norm(entry_path) in intentional else "candidate-common"` to
  `build_envelope`. (Still captures the file -- safety net preserved; ADR option 1.)
- Tests in `test_installer_drift_eol.py`: `_load_intentional_drift` parsing + `_capture_drift`
  stamps `business` for a declared target and `candidate-common` for an undeclared one.
- Version bump; close #119.

## Design & Contract

### Interfaces, I/O & Realization
- `installer._load_intentional_drift(project_root: Path) -> set[str]`: INPUT
  `.governance/intentional_drift.json` (consumer-owned). Returns the set of declared
  repo-relative paths (forward-slash normalized). Missing/malformed/wrong-schema ->
  `set()` (advisory noise-suppression, never a correctness gate; fail-safe). Avoids
  `.get(k, default)` (Art.4). Realizer: the installer module.
- `installer._capture_drift(...)` (modified): for each drifted manifest entry, choose
  `layer` = `business` iff its path is in the declared set, else `candidate-common`
  (unchanged default), and pass it to `envelope.build_envelope(..., layer=...)`. The
  envelope is STILL built (safety capture intact). Realizer: `governance-core upgrade`
  -> `_capture_drift` -> `build_envelope`.
- Downstream, unchanged: `candidate.py collect/sweep` already act only on
  `candidate-common`, so a `business`-stamped drift is skipped natively -- no new sweep
  logic, no `rejected_registry` round-trip, no hub issue.

### Field Dictionary
| field | type | meaning | producer | consumer | constraints |
|-------|------|---------|----------|----------|-------------|
| `schema` | int | drift-declaration schema version | consumer (hand-authored) | `_load_intentional_drift` | must == `1` |
| `drift_targets` | list[str] | repo-relative paths of intentional permanent drift | consumer | `_load_intentional_drift` -> `_capture_drift` | forward-slash repo-relative |
| `layer` (envelope) | str | candidate layer stamped on the drift envelope | `_capture_drift` | `candidate.py collect/sweep` | one of `LAYERS` (`envelope.py:38`) |

Governing store: `.governance/intentional_drift.json`, schema owned by
`_load_intentional_drift` (the single parser) -- **not** a `contracts/` file, consistent
with P-0115's per-agent `.usage.json` precedent (consumer-local runtime declaration, not
a cross-agent contract). The **file name + schema are locked to trade-agent P-0125's
already-shipped interim** so the consumer prune retires with zero churn once gc adopts this.

### Flow
consumer authors `.governance/intentional_drift.json` -> `governance-core upgrade` ->
`_capture_drift` reads it via `_load_intentional_drift` -> declared drift ->
`build_envelope(layer="business")` -> `sweep` skips it (business != candidate-common) ->
no hub issue. Undeclared drift -> `candidate-common` -> normal uplink (unchanged).

## Non-Goals

- **No skip-emission** (ADR option 2): the file is still captured (safety net; no silent
  fork) -- only its `layer` changes.
- **No `cmd_sweep` filter** (ADR option 3): stamping at emission is earlier + simpler and
  needs no new sweep-side logic.
- `.governance/intentional_drift.json` is **not** added to `installed_files.json` -- it is
  consumer-authored, so `upgrade` never clobbers it (nothing to wire; stated for clarity).
- No new `contracts/` file (schema lives with the parser; see Field Dictionary).
- No change to the digest ledger or `rejected_registry` semantics.

## Open Questions

- ADR choice (stamp-business / skip-emit / sweep-filter). **Resolved: option 1**
  (owner directive) -- preserves the safety capture with the least logic.
- File name / schema. **Resolved: `.governance/intentional_drift.json`,
  `{"schema":1,"drift_targets":[...]}`** -- locked to the consumer's shipped interim for
  forward-compat.

## Alternatives & Rationale

- **Option 1 -- stamp `layer:business` at emission (chosen)**: preserves capture-then-
  overwrite safety; one `layer=` argument; sweep already ignores non-common.
- **Option 2 -- skip emitting the envelope**: rejected -- loses the safety capture (a
  genuine mistake in a declared path would vanish silently).
- **Option 3 -- filter in `cmd_sweep` by drift_target**: rejected -- later in the pipeline,
  the envelope is still minted (outbox churn) and needs new sweep-side logic.
- **Keep `rejected_registry` as the guard**: rejected (issue) -- reactive, name-global,
  and semantically wrong (these were never "rejected candidates").

## Guardrails

- `edit-write-guard`: edit is `governance_core/installer.py` package source -- allowed.
- `constitutional-review` (Art.4): the new parser must NOT use `.get(k, default)` -- use
  explicit membership tests (installer.py is not in the hook's skip set).
- Package isolation (Art.11.4): no new shipped file; `.governance/intentional_drift.json`
  is consumer-authored, never in the wheel or the manifest.

## Phases

### Phase 1: Add parser + layer stamping + tests

- Deliverables:
  - `installer._load_intentional_drift`; `_capture_drift` layer selection.
  - Tests: parser (missing/valid/malformed/wrong-schema/backslash) + `_capture_drift`
    stamps business vs candidate-common.
  - Version bump; #119 closed.
- Validation:
  - `python -m pytest tools/test_installer_drift_eol.py -q` green (existing + new).
  - `governance-core upgrade --project-root .` + `doctor` exit 0.
  - Wheel isolation: top-level `governance_core*` only, `maintainer/` absent, no
    `intentional_drift.json` in the wheel.
- Exit criteria: all validation green; #119 closed.

## Approval Criteria

- [ ] `_load_intentional_drift` fail-safe (missing/malformed/wrong-schema -> empty set),
      no `.get(k, default)` (Art.4), forward-slash normalized.
- [ ] `_capture_drift` stamps `business` for declared paths, `candidate-common` otherwise,
      and STILL builds the envelope (safety capture preserved).
- [ ] File name + schema == trade-agent P-0125 (`.governance/intentional_drift.json`,
      `{"schema":1,"drift_targets":[...]}`).
- [ ] Field Dictionary store named (consumer-owned JSON, N/A for `contracts/`, per P-0115).
- [ ] Tests cover parser + both layer outcomes; upgrade + doctor exit 0; wheel clean.

## Validation Plan

1. `python -m pytest tools/test_installer_drift_eol.py -q` -- existing + new cases pass.
2. `governance-core upgrade --project-root .` then `governance-core doctor` -> exit 0.
3. `python -m build --wheel` -> top-level `governance_core*` only; `maintainer/` absent;
   no consumer `intentional_drift.json` leaked.

## Rollback / Recovery

Remove `_load_intentional_drift` and revert `_capture_drift` to the unconditional
default `layer`. Purely additive; a consumer with no `.governance/intentional_drift.json`
sees identical behavior to today (empty set -> all drift stays `candidate-common`).

## Risks

- **Over-broad declaration** (low): a consumer lists a path they did NOT actually intend
  to keep -> that drift is stamped business and not surfaced to the hub. Mitigation: the
  file is hand-authored + consumer-owned; the capture still happens locally (recoverable),
  and it only suppresses *hub uplink*, not local visibility.
- **Schema drift vs consumer interim** (low): mitigated by locking the exact file name +
  schema to P-0125; a mismatch would just mean the consumer prune keeps running (no harm).

## State Log

- 2026-07-01: draft created by core agent (P-0117)
- 2026-07-01: draft → pending (submit for review: intentional-drift layer:business (#119, ADR option 1))
- 2026-07-01: pending → approved (user approval: 批准实施(option 1) (AskUserQuestion 2026-07-01))
- 2026-07-01: approved → implemented
