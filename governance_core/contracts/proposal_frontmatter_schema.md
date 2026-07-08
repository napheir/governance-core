# Contract: proposals/**/*.md Frontmatter Schema

**Version**: 1.2.0
**Status**: active
**Owner**: core
**Consumers**: all agents (write proposals, read status), `tools/audit_proposals.py` (validation), `.claude/hooks/session-context.py` (filter pending list), `.claude/commands/proposal.md` (skill that mutates status)

Defines the YAML frontmatter that proposals/**/*.md files must carry so
that the proposal state machine + `/proposal` skill can drive lifecycle
transitions consistently. Companion to
`proposals/p-0001-proposal_skill_v2_gate_template_statelog.md` (skill v2
design source) and total constitution Art.4之一 + Art.5.1 (storage
location semantics).

## Version history

- **1.2.0** (2026-07-08, P-0119 Phase 0): Add optional `execution` field
  (§4.7) marking an execution-class proposal whose `### Phase` gates are
  machine-run by `/proposal run`. Backward-compatible (absent = a normal
  proposal). Gate/check grammar in `contracts/proposal_gate_schema.md`.
- **1.1.0** (2026-05-12, P-0001 Phase 0): Add required `id` field
  (`P-NNNN` format, must match filename prefix + body H1 title) and
  required `agent` field (owner short-name enum). Backward-compatible
  for non-renumbered legacy proposals (see §6 Exemptions).
- **1.0.0** (initial): status / created / state-conditional fields.

---

## 1. Frontmatter shape

```markdown
---
id: P-0001
agent: core
status: pending
created: 2026-04-28
implemented_in: d7bb0d9
implemented_at: 2026-04-28
---

# Proposal P-0001: <title>
...
```

Constraints:
- Frontmatter MUST be the first content (no BOM, no leading blank lines).
- Opening `---` MUST be on line 1.
- Frontmatter ends with the next standalone `---` line.
- Body begins on the line immediately after the closing `---`.

---

## 2. Required fields

| Field | Type | Semantics |
|-------|------|-----------|
| `id` | string | `P-NNNN` (uppercase P, hyphen, 4-digit zero-padded monotonic). Must equal filename `p-NNNN-` prefix (lowercased) and body H1 `# Proposal P-NNNN:` token (three-way consistency, see §5.4). Allocated by `/proposal create` under filelock. **Required since v1.1.0.** Legacy proposals without `id` are grandfathered (see §6). |
| `agent` | enum | Owner agent. One of `core`, `rules`, `trade`, `data`, `research`. Determines `shared_state/proposals/<agent>/` write path. **Required since v1.1.0.** Legacy grandfathered. |
| `status` | enum | See §3.1 |
| `created` | ISO date | `YYYY-MM-DD`; date the proposal was first written |

Missing any required field is a hard audit failure (`tools/audit_proposals.py`
exit non-zero) — except for legacy proposals matched by §6 exemption rules.

---

## 3. Enumerations

### 3.1 `status`

| Value | Meaning | Usually transitioned to |
|-------|---------|------------------------|
| `draft` | being written, not submitted for review | `pending` |
| `pending` | submitted, awaiting user approval (default) | `approved` or `rejected` |
| `approved` | user-approved, ready to implement | `in-progress` or `implemented` |
| `in-progress` | implementation underway (optional, short tasks may skip) | `implemented` |
| `implemented` | landed, commit recorded; terminal | `superseded` (rare) |
| `superseded` | replaced by a newer proposal; terminal | — |
| `rejected` | user rejected with reason; terminal | — |

Unknown values are a hard audit failure.

**Default**: a proposal with no `status` field is treated as `pending`
by `session-context.py` (backward-compat for un-backfilled files), but
audit reports it as a missing-field error.

---

## 4. State-conditional fields

Each terminal / intermediate state has companion fields that capture
the transition's evidence. These are **required when the corresponding
status is set**, otherwise omitted.

### 4.1 `approved`

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `approved_at` | ISO date | yes | when user approved |

### 4.2 `in-progress`

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `started_at` | ISO date | yes | implementation start date |

### 4.3 `implemented`

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `implemented_in` | string | yes | short git commit hash (≥ 7 chars), must `git rev-parse` resolve |
| `implemented_at` | ISO date | yes | landed date |

### 4.4 `superseded`

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `superseded_by` | string | yes | relative path to replacement proposal (e.g., `proposals/new_design.md`) |

### 4.5 `rejected`

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `rejected_at` | ISO date | yes | rejection date |
| `rejection_reason` | string | yes | one-line user-supplied reason |

### 4.6 Optional cross-references

| Field | Type | Notes |
|-------|------|-------|
| `supersedes` | list[string] | relative paths to proposals this one replaces (mirror of others' `superseded_by`) |
| `related` | list[string] | conceptually linked proposals or knowledge entries |

### 4.7 Execution class (added v1.2.0, P-0119)

| Field | Type | Notes |
|-------|------|-------|
| `execution` | string (runner id) | **Optional.** Present marks an *execution-class* proposal whose `### Phase` entries carry machine-run `gate:` + `calibration:` lines (see `contracts/proposal_gate_schema.md`). gc ships one runner id, `gates`, executed by `/proposal run <id>`. Absent = a normal proposal (no per-phase gate machinery; the field never fires). When present, `transition --to approved` hard-gates each phase's gate calibration (exemption `--allow-uncalibrated-gate`, justify in `--note`). |

---

## 5. Format rules

### 5.1 Dates

- `YYYY-MM-DD` (ISO 8601 calendar date).
- All `*_at` fields ≥ `created`.

### 5.2 Commit hashes

- Format: lowercase hex, 7-12 characters (short hash range).
- Validated by `git rev-parse <hash>` succeeding.

### 5.3 Cross-reference paths

- Relative to repo root, including the `proposals/` prefix:
  ```yaml
  superseded_by: proposals/new_proposal.md
  ```
- Forbidden: bare basename (`new_proposal.md`), absolute paths
  (`/proposals/...`), no extension.

### 5.4 Three-way ID consistency (v1.1.0+)

For proposals carrying `id: P-NNNN`, the audit tool enforces that the
following three locations agree:

1. Frontmatter `id` field: `P-NNNN`
2. Filename prefix: `p-NNNN-<slug>.md` (lowercased `p`, same number)
3. Body H1 first line: `# Proposal P-NNNN:<rest>` (within first 50 body lines)

Mismatch in any of the three is a hard audit failure (Check 8). This
prevents rename drift between filename / id / title.

### 5.5 Storage path constraint (v1.1.0+)

In-flight proposals (status ∈ {draft, pending, approved, in-progress})
SHOULD physically live in `shared_state/proposals/<agent>/p-NNNN-*.md`
where `<agent>` matches the frontmatter `agent` field. Terminal proposals
(status ∈ {implemented, rejected, superseded}) SHOULD live in
`agent-core/proposals/_archive/<YYYY>/p-NNNN-*.md` where `<YYYY>` is the
year of the terminal transition.

The audit tool enforces mutual exclusion (Check 9): the same `id` MUST
NOT exist in both in-flight and archive paths simultaneously. Legacy
proposals in `agent-core/proposals/*.md` (top level) are exempt during
the v1.1.0 transition window (see §6).

---

## 6. Exemptions

The following files are NOT subject to this schema:

- `proposals/templates/*.md` — template files for new proposals
- `proposals/archived/**` — archived proposals retain their schema-time
  frontmatter; new edits to archived files NOT required to upgrade
- `proposals/**/_*.md` — files whose basename starts with `_` are
  discussion / review artifacts (e.g. `_review_<date>_<topic>.md`),
  not proposals; they may carry arbitrary frontmatter or none at all,
  and are skipped by `tools/audit_proposals.py`
- **Legacy non-`p-NNNN-*` proposals at `agent-core/proposals/*.md`
  top level**: pre-v1.1.0 proposals (filename without `p-NNNN-` prefix)
  are grandfathered. The audit tool requires only v1.0.0 fields
  (`status` + `created` + state-conditional) for these; `id` and `agent`
  are not required. Once a legacy proposal is migrated to the new
  storage scheme (renamed to `p-NNNN-*` + moved to `shared_state/proposals/`
  or `_archive/`), v1.1.0 rules fully apply. P-0001 Phase 4 plans the
  bulk migration; until then both schemas coexist.

---

## 7. Lifecycle invariants

- `implemented`, `superseded`, `rejected` are terminal — only a NEW
  proposal can effectively reverse the decision (no direct status
  rewind)
- `implemented_in` is immutable once set (records a fact)
- A proposal with `superseded_by: X` requires `X` to exist with
  `supersedes: [<this proposal>]` in its own frontmatter (auditor
  Check 6 — bidirectional consistency)

---

## 8. Versioning

This contract follows SemVer.

- **Patch** — typo / clarification, no validator change
- **Minor** — new optional fields, new enum values (backward compatible);
  new required fields permitted **only with grandfathering rule for
  pre-bump files** (see §6 legacy exemption pattern)
- **Major** — removed/renamed required fields without grandfathering,
  breaking enum changes; requires `proposals/` migration plan

**v1.1.0 rationale**: `id` and `agent` are new required fields, but the
§6 grandfathering rule preserves backward compatibility for the 76 legacy
proposals during the P-0001 Phase 4 migration window. New proposals
created via `/proposal create` after v1.1.0 are subject to all v1.1.0
rules immediately.
