---
id: P-0093
agent: core
status: implemented
created: 2026-06-02
approved_at: 2026-06-02
implemented_in: 7e5835b
implemented_at: 2026-06-02
owner: core
---

# Proposal P-0093: promote upgrade-review drift pre-pass (gc #22)

## Trigger

Curation of GitHub candidate **#22** (`mechanism`, from trade-agent): a
deterministic, read-only **upgrade drift-risk pre-pass**. Proposal governance
applies: it adds a shipped tool **and** modifies a shipped hook source
(`update-reminder.py`, SessionStart) — a capability that ships to all
consumers via `upgrade` (classify → PROPOSAL_REQUIRED). Owner chose to include
the hook wiring (not tool-only).

## Scope

- `tools/upgrade_review.py` (new): runs `governance-core upgrade --dry-run`,
  mechanically classifies drift risk **NONE / GREEN / YELLOW / RED**, writes a
  report under `audit/upgrade_review/` (gitignored, Art.10), and **never
  applies** (exit 0 always). A `protected_drift.json` ({"paths": [...]})
  convention flags RED when an upgrade would *revert* a deliberately-kept local
  fix.
- `hooks/update-reminder.py`: when an update is already detected, run the tool
  best-effort (`_drift_verdict`, 25s timeout) and append a one-line verdict to
  the existing banner (`_verdict_line`); any failure → plain banner.
- Tests: `tools/test_upgrade_review.py` (13 cases) + 2 new wiring cases in
  `tools/test_update_reminder.py`. Version 0.22.0 → 0.23.0 (shared release).

Curation fix to the contributed payload: `classify()` aligned to its own
documented verdict contract (cross-minor + drift now → RED; cross-minor alone
→ YELLOW; the old code discarded the cross-minor reason). Docstring genericized
(consumer-internal proposal ids stripped); mechanism otherwise verbatim.

## Non-Goals

- The tool **never applies** an upgrade — apply stays a human action via
  `/upgrade`. This is a surfacing/pre-pass tool only.
- No LLM semantic review in the tool itself (a consumer's scheduled routine can
  layer that on YELLOW/RED).
- The hub (governance-core) does not run the wiring — `update-reminder`
  early-exits for `consumer_id == governance-core` (editable install). The
  wiring is consumer-facing.

## Guardrails

- `edit-write-guard`: not triggered.
- `constitutional-review`: `upgrade_review.py` lives under `tools/`
  (skip-listed); `update-reminder.py` edits use no new `.get(k, default)` /
  `print`.
- `runtime-import-discipline`: `update-reminder.py` was already a registered
  fail-open gc-importer; the wiring subprocesses the tool (no new gc import).

## Phases

### Phase 1: Promote tool + wire hook + validate (single phase)

- Deliverables: the Scope edits + tests; version bump.
- Validation: see Validation Plan.
- Exit criteria: full suite green, doctor exit 0, wheel isolated, tool
  dogfooded on the hub, archived.

## Approval Criteria

- Mechanism is a generic gc-consumer capability; no domain coupling
  (genericized).
- `parse()` regexes verified against the real `installer._dry_run_report`
  output format (`version: X -> Y`, `crosses N minor`, `--- drift diff: P ---`).
- Wiring is best-effort + timeout-bounded; never breaks session start.
- `governance_core/` edited only (Art.11.2).

## Validation Plan

- `python tools/test_upgrade_review.py` → 13/13 (parse against a real-format
  sample incl. diff-body `---` noise; NONE/GREEN/YELLOW/RED contract;
  `load_protected` tolerance).
- `python tools/test_update_reminder.py` → 11/11 (incl. 2 new: stub tool →
  verdict line appended; no tool → plain banner fallback).
- Dogfood: `python tools/upgrade_review.py` on the hub → verdict NONE,
  report written, exit 0 (tool runs end-to-end against the real CLI).
- `doctor` exit 0; wheel top-level only `governance_core*`, `upgrade_review.py`
  present, no `maintainer/` leak.

## Rollback / Recovery

Single commit; `git revert` removes the tool + wiring. The wiring is purely
additive to the banner and best-effort; reverting only the `update-reminder.py`
hunk keeps the standalone tool while removing the session-start integration.

## Risks

- SessionStart latency: the wiring spawns a dry-run subprocess when an update
  is available. **Mitigated**: gated on update-available (rare), 25s timeout,
  best-effort fallback to the plain banner.
- Cannot be dogfooded on the hub (early-exit gate): **mitigated** by a unit
  test exercising the consumer path with a stub tool.
- dry-run output-format drift could silence the verdict: **mitigated** — parse
  regexes are tested against the real format; a non-match degrades to NONE
  (no false alarm), and the tool is read-only so a wrong verdict never applies.

## State Log

- 2026-06-02: draft created by core agent (P-0093)
- 2026-06-02: draft → pending (submit for review: curate gc #22 upgrade-review)
- 2026-06-02: pending → approved (user: 批准 (approve, archive and close both issues))
- 2026-06-02: approved → implemented
