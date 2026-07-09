---
id: P-0120
agent: core
status: implemented
created: 2026-07-09
approved_at: 2026-07-09
implemented_in: e2993fd
implemented_at: 2026-07-09
owner: core
---

# Proposal P-0120: publish-knowledge Step 4: gate M-fm-only collection by frontmatter diff direction (issue #132)

## Trigger

Consumer trade-agent filed bug #132: `/publish-knowledge` Step 4 (core-only
cross-clone knowledge collection) collects every file classified `M-fm-only`
and checks out the clone's version (`git checkout FETCH_HEAD -- <path>`),
**without checking the direction of the frontmatter diff**. When hub/master is
*ahead* on frontmatter (the normal state right after core mass-backfills a
required field), a behind clone's file still classifies as `M-fm-only`
(`added_in_fm:0, removed_in_fm:1`, where the "removed" line is the field master
just added) — and Step 4.3, followed literally, **silently reverts the
hub-authored field**. `publish-knowledge.md` is a shipped governance skill
(ships to all consumers via `upgrade`) and this is a cross-clone data-correctness
change, so the fix is proposal-governed (Art.11 skill-system change).

## Current State (read, not assumed)

- `governance_core/commands/publish-knowledge.md:98-110` — Step 4.2 status
  table maps `M-fm-only` → "收" (collect) **unconditionally**; Step 4.3 does
  `git checkout FETCH_HEAD -- <path>` for every `A` / `M-fm-only` file.
- `governance_core/tools/diff_classify.py:154-155,228-229,241-242` — the
  classifier **already emits** `added_in_fm` / `removed_in_fm` per `M-*` file.
  `diff_classify --base HEAD(master) --head FETCH_HEAD(clone)` reports the
  master→clone delta, so a behind clone yields
  `{status: M-fm-only, added_in_fm: 0, removed_in_fm: >0}`. The direction
  signal exists; Step 4 just ignores it.
- No test covers `diff_classify.py`: `grep -rln classify_knowledge_diff`
  over `tools/test_*.py` + `governance_core/tools/test_*.py` = **0 hits**. The
  direction semantics are currently unverified.
- Reported real-run impact (#132): after a ~12-file frontmatter backfill on
  master, a Step 4 collect reported **20 / 114 / 114 / 118** `M-fm-only` files
  across four clones — **all** removed-only (`added_in_fm == 0`), i.e. 0 genuine
  net-new, yet literal Step 4.3 would have reverted the just-added field.

## Scope

- `governance_core/tools/diff_classify.py`: emit a derived `direction` field on
  each `M-*` record — `ahead` (`added_in_fm > 0`, clone has an fm line the hub
  lacks), `behind` (`added_in_fm == 0 and removed_in_fm > 0`, clone is simply
  behind), `mixed` (both > 0); `na` for `A` / `D` / `?`.
- `governance_core/commands/publish-knowledge.md`: Step 4.2 status table + Step
  4.3 — collect `M-fm-only` **only when `direction != behind`**; a `behind`
  file is skipped (the clone catches up when it merges master). `A` /
  `M-mixed` / `D` / `?` handling is unchanged.
- New `governance_core/tools/test_diff_classify.py`: script-style test asserting
  `ahead`→collect / `behind`→skip direction on synthetic frontmatter diffs
  (first coverage for `diff_classify.py`).

## Design & Contract

> Proportionate. Trivial change: one line "implementation self-evident; no interface
> or data-flow change." Otherwise fill all three sub-parts; use "N/A — <reason>" for
> any that genuinely doesn't apply — never leave a placeholder.

### Interfaces, I/O & Realization
- **`classify_knowledge_diff(...)` → `diff_classify.py` CLI** (realizer: the
  CLI, run by the core agent as Step 4.2 of the `/publish-knowledge` skill —
  no daemon; a maintainer-invoked CLI step). INPUT: git diff between `--base`
  (master `HEAD`) and `--head` (clone `FETCH_HEAD`) over `--paths knowledge/`;
  per changed file it counts added/removed lines inside vs outside the YAML
  frontmatter region. OUTPUT (JSONL record per file): the existing fields
  (`path`, `status`, `reason`, `added_in_fm`, `removed_in_fm`, ...) **plus a new
  derived `direction`** for `status ∈ {M-fm-only, M-mixed}` (`ahead|behind|mixed`);
  `na` for `A`/`D`/`?`. Additive — existing consumers that ignore the field are
  unaffected.
- **`/publish-knowledge` Step 4.2/4.3** (realizer: the core agent executing the
  skill). Reads the JSONL and branches on `(status, direction)`: `M-fm-only` +
  `behind` → skip; `M-fm-only` + `ahead`/`mixed` → `git checkout FETCH_HEAD --
  <path>` (collect). No new executable component — the skill is agent-executed
  instruction, already the realizer for Step 4.

### Field Dictionary
`direction` is **ephemeral tool output** — one JSONL stream consumed within a
single `/publish-knowledge` run, not persisted and not a cross-agent artifact.
No `contracts/` file governs it (N/A — not persisted/cross-agent); its meaning
lives in the `diff_classify.py` docstring + the Step 4.2 table.

| field | type | meaning | producer | consumer | constraints / allowed values |
|-------|------|---------|----------|----------|------------------------------|
| `direction` | str | frontmatter diff direction for `M-*` files | `diff_classify.py` | `/publish-knowledge` Step 4 agent | `ahead` \| `behind` \| `mixed` \| `na`; `behind` ⇒ skip collect |
| `added_in_fm` | int | `+` lines inside the fm region (existing) | `diff_classify.py` | `direction` derivation | ≥ 0 |
| `removed_in_fm` | int | `-` lines inside the fm region (existing) | `diff_classify.py` | `direction` derivation | ≥ 0 |

### Flow
```
git diff (base=master HEAD, head=clone FETCH_HEAD, paths=knowledge/)
  → diff_classify.py  (classify status + derive `direction`)
  → JSONL (one record/file)
  → /publish-knowledge Step 4.2 agent  (branch on status+direction)
  → Step 4.3: git checkout FETCH_HEAD -- <path>   [only ahead|mixed; behind skipped]
  → master working tree → commit → push
```

## Non-Goals

- Not changing `M-mixed` / `D` / `?` handling — they remain skip+WARN / skip as
  today (P-0055 semantics preserved).
- Not adding auto-conflict-resolution for a file that is genuinely ahead on one
  clone and behind on another — each file is classified independently per clone.
- Not touching the push / PR flow (Step 4.7 unchanged; still no auto-PR).
- Not changing the frontmatter-region detection logic (reused verbatim — only
  the direction *derivation* on top of it is new).

## Open Questions

> Known-undecided design points to resolve (or explicitly defer) BEFORE approval.
> Lightweight — NOT gated; the approver decides each. Write "None" rather than leaving
> the placeholder.

- ~~`M-fm-only` + `direction: mixed` (both an added and a removed fm line) —
  collect or WARN?~~ **RESOLVED (approver, 2026-07-09): collect** (treat like
  `ahead`) — it carries net-new fm content the hub lacks; the separately-removed
  line is caught up when the clone merges master. Gate: collect `M-fm-only`
  unless `direction == behind`.

## Alternatives & Rationale

- **Chosen — derive a `direction` field in `diff_classify.py` + gate in the
  skill.** The raw counts already exist; a derived field makes the skill-doc
  gate unambiguous *and* unit-testable, and gives a `cmd:` acceptance signal.
- **Alternative — gate purely in the skill doc using raw `added_in_fm` /
  `removed_in_fm`, no tool change.** Rejected: leaves the direction logic in
  prose only, with no test surface; a maintainer eyeballing two raw counts is
  error-prone. The derived field costs ~5 lines and closes the untested-tool
  gap in the same change.

## Guardrails

- **edit-write-guard**: edits target `governance_core/` package source (skill +
  tool + test) — allowed; the root autonomy-layer copy is never touched
  (Art.11.2).
- **command-guard / boundary-guard / sensitive-data-guard**: no interaction —
  no destructive commands, no cross-boundary writes, no secrets.
- **Art.11.3 dogfood**: after editing source, run
  `governance-core upgrade --project-root .` so this repo's own session picks up
  the new tool behavior.
- **Package-data / wheel (Art.11.4)**: all edits are `.py` + `.md` under
  already-globbed dirs (`tools/`, `commands/`) — no new `pyproject.toml`
  package-data glob needed.

## Phases

### Phase 0: Governance bootstrap — N/A

Not a constitution / contract change; no `/iterate-constitution` bootstrap.

### Phase 1: Direction gate + test

- Deliverables:
  - (a) `diff_classify.py` emits `direction` on each `M-*` record.
  - (b) `publish-knowledge.md` Step 4.2 table + 4.3 gate by direction
    (`behind` → skip).
  - (c) `test_diff_classify.py` asserts `ahead`→collect / `behind`→skip.
- Validation: `python governance_core/tools/test_diff_classify.py` exit 0; full
  suite green; `governance-core upgrade --project-root .` + `doctor` exit 0.
- Exit criteria: a behind-clone frontmatter file is no longer collected by the
  Step 4 gate; test green; Step 4.2/4.3 wording unambiguous.

## Approval Criteria

> Each item pairs a plain-language acceptance with ONE discriminating check token
> (`cmd: <exit 0 = pass>` / `agent-rubric: <ref>` / `human-verify: <sentence>`; see
> contracts/proposal_gate_schema.md). An item with no check token is prose, not an
> acceptance signal.

- [ ] `diff_classify` emits `direction` and `behind` (removed-only) is distinguishable from `ahead` — cmd: python governance_core/tools/test_diff_classify.py
- [ ] `publish-knowledge` Step 4.2 table + 4.3 skip `M-fm-only` + `direction: behind` — human-verify: the 4.2 row for behind says skip and 4.3 checks out only non-behind files
- [ ] `direction` field is additive / does not break existing diff_classify callers — human-verify: no consumer reads a removed field; JSONL keys are a superset
- [ ] Open Question (mixed-direction disposition) resolved or explicitly deferred — human-verify: decided in Open Questions before approve

## Validation Plan

- `python governance_core/tools/test_diff_classify.py` (run from repo root per
  the package-source test convention) — new direction test.
- Full test suite, both styles (script-style + pytest-style) — the new test is
  script-style.
- `governance-core upgrade --project-root .` then `governance-core doctor`
  (exit 0) — dogfood the new tool/skill into this repo's own session.
- Manual: synthesize a behind-clone diff (fm field removed vs master) and
  confirm `diff_classify` reports `direction: behind` and the Step 4 gate skips
  it.

## Rollback / Recovery

Revert the single commit. The `direction` field is additive (callers ignoring
it are unaffected) and the skill-doc gate reverts to the prior "collect all
`M-fm-only`" wording. No data migration, no state to unwind.

## Risks

- **A genuinely-ahead file misclassified as `behind`** (missed collect). Prob:
  low — the direction derivation is a pure function of the existing
  `added_in_fm`/`removed_in_fm` counts, and the fm-region logic is unchanged.
  Impact: medium (clone re-offers the entry next round — no data loss). Mitigation:
  the new test pins `ahead`/`behind`/`mixed` cases.
- **The reverse bug persisting elsewhere** — Step 4 is the only place that
  checks out clone versions of hub files; no other collect path. Low.

## State Log

- 2026-07-09: draft created by core agent (P-0120)
- 2026-07-09: draft → pending (submit bug #132 fix for review)
- 2026-07-09: pending → approved (User approved 2026-07-09: '批准，mixed 收' — mixed direction resolved to collect)
- 2026-07-09: approved → implemented
