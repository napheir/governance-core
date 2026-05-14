# Contract: knowledge/**/*.md Frontmatter Schema

**Version**: 1.2.0
**Status**: active
**Owner**: core
**Consumers**: all agents (read via `/learn`, write via `experiment-manager`)
**Tools**: `tools/audit_knowledge.py` (validation), `tools/build_knowledge_dashboard.py` (rendering)

Every file under `knowledge/**` (except `INDEX.md` and `_TEMPLATE.md`) must begin
with a YAML frontmatter block conforming to this schema. This contract is the
single source of truth — `audit_knowledge.py` derives its checks from this file
and `build_knowledge_dashboard.py` reads these fields.

---

## 1. Frontmatter shape

```markdown
---
title: <short human-readable title>
status: active
created: 2026-04-24
updated: 2026-04-24
owner: rules
tags: [w150, xgboost, hybrid]
# optional fields below
supersedes: experiments/EXP-2026-0009.md
related: [decisions/adr-005-hybrid-over-xgboost.md]
---

# <body starts here>
```

Constraints:
- Frontmatter MUST be the first content in the file (no BOM, no leading blank lines).
- Opening `---` MUST be on line 1.
- Frontmatter ends with the next standalone `---` line.
- Body begins on the line immediately after the closing `---`.

---

## 2. Required fields

All six fields below MUST be present on every `knowledge/**/*.md` file except
files explicitly excluded in §4. Missing any required field is a hard audit
failure (exit code 1 from `audit_knowledge.py`).

| Field | Type | Semantics |
|-------|------|-----------|
| `title` | string | One-line human-readable title; max 120 chars; no trailing period |
| `status` | enum | See §3.1 |
| `created` | ISO date | `YYYY-MM-DD`; date the entry was first committed |
| `updated` | ISO date | `YYYY-MM-DD`; date of last material revision (not reformat) |
| `owner` | enum | See §3.2 |
| `tags` | list[string] | ≥1 lowercase kebab-case tag; no spaces; used for dashboard faceting |

### 2.5 Transitional required fields

Fields scheduled to become required after one rotation period. The auditor
emits **warnings only** (not failures) during the transitional window so
existing knowledge entries can be migrated without breaking the build.

| Field | Type | Introduced | Becomes hard-required | Semantics |
|-------|------|------------|----------------------|-----------|
| `carrier_class` | enum | v1.2.0 | v1.3.0 (sealed when P-0054 implementation completes) | See §3.4 |

P-0053 Phase 2 (this version) introduces `carrier_class` as a transitional
required field. Phase 3 produces a read-only inference report mapping each
existing entry to its expected class without modifying files. Backfill is
governed by P-0054 or a separate proposal; only after backfill completes
does v1.3.0 promote the field to hard-required in §2.

---

## 3. Enumerations

### 3.1 `status`

| Value | Meaning |
|-------|---------|
| `active` | Current authoritative knowledge; freely referenced |
| `archived` | Kept for historical record; no longer the working truth (usually points forward via `superseded_by`) |
| `draft` | Work-in-progress; incomplete or unvalidated |
| `deprecated` | Officially retired; readers MUST prefer `superseded_by`; file kept only to preserve inbound links |

Unknown values are a hard audit failure.

### 3.2 `owner`

| Value | Meaning |
|-------|---------|
| `rules` | Written + maintained by rules agent (algorithms, experiments, model decisions) |
| `trade` | Written + maintained by trade agent (execution, strategy, risk) |
| `data` | Written + maintained by data agent (ingestion, quality, analytics) |
| `research` | Written + maintained by research agent (tool research, prototypes, inspiration) |
| `core` | Written + maintained by core agent (governance, shared infrastructure, cross-agent ADRs) |

`owner` determines write-authority under scope guards: only the owner agent may
materially change the entry's body; other agents may reference but must open a
proposal to edit. For multi-authorship ADRs in `knowledge/decisions/` and
`knowledge/domain/`, `owner` reflects the *primary* author; additional
collaborators go in the optional `contributors` list (§4.2).

### 3.3 `briefing` (added v1.1.0)

| Value | Meaning |
|-------|---------|
| `pinned` | Long-term high-priority entry; surfaced in the dashboard's Briefing-mode Pinned panel on every render (e.g. production-state docs, primary architecture ADRs) |
| `serendipity` | Worth occasionally re-reading but not urgent; entered into a rotating pool, two are surfaced per ISO calendar week via deterministic seed (e.g. inspiration material, deep research entries) |

The two values are mutually exclusive — a single entry MAY declare at most one.
The field itself is optional; absence means the entry does not appear in either
Briefing panel (default behavior; back-compat with v1.0.x).

Unknown values are a hard audit failure.

See `proposals/dashboard_briefing_mode.md` for the design rationale and
`config/briefing_config.json` for the runtime tuning surface (per-week count,
status / tag exclusions, stale-check categories).

### 3.4 `carrier_class` (added v1.2.0)

| Value | Meaning |
|-------|---------|
| `decision-record` | One-shot decision + context + tradeoff; immutable once implemented (ADRs in `knowledge/decisions/`) |
| `reference` | Non-drifting narrative / system structure / concept diagrams (`knowledge/{domain,governance,methodology,research,data-quality,trading,skills,features}/`) |
| `runbook` | Procedural operating steps / playbooks (`knowledge/operations/*-manual.md`) |
| `experiment-record` | Frozen experiment / dataset snapshot (`knowledge/experiments/`, `knowledge/datasets/`) |
| `current-state` | **Production-drifting** state snapshot; numbers must be autogen-backed (`knowledge/models/*_current.md`) |
| `derived-lesson` | Reusable causal pattern abstracted from incidents / decisions (`knowledge/lessons/`) |

Authoritative semantic source: `knowledge/governance/knowledge-carrier-classes.md`
(P-0053). This contract lists the enum values; the governance doc defines
each class's update triggers, autogen permissions, and lesson eligibility.

Unknown values are an audit warning during the v1.2.0 transitional window
(`tools/audit_knowledge.py` Check 12) and a hard failure from v1.3.0.

---

## 4. Optional fields

### 4.1 Lifecycle and cross-reference

| Field | Type | Semantics |
|-------|------|-----------|
| `supersedes` | string or list[string] | Relative path(s) to entries this one replaces |
| `superseded_by` | string | Relative path to the entry that replaced this (required when `status = deprecated`) |
| `related` | list[string] | Relative paths to conceptually linked entries |
| `blocks` | list[string] | Proposals / experiments that cannot proceed until this is resolved |
| `blocked_by` | list[string] | Reverse of `blocks` |

### 4.2 Attribution

| Field | Type | Semantics |
|-------|------|-----------|
| `contributors` | list[enum<owner>] | Other agents who authored substantive content |
| `decision_date` | ISO date | For ADRs: date the decision was made (may differ from `created`) |

### 4.3 Briefing surfacing (added v1.1.0)

| Field | Type | Semantics |
|-------|------|-----------|
| `briefing` | enum (`pinned` / `serendipity`) | See §3.3. Drives dashboard Briefing-mode panel inclusion |

### 4.4 Domain-specific extensions

Each subdirectory MAY define additional optional fields. Extensions are
documented in the subdirectory's `INDEX.md` frontmatter under an `extends:`
section. Extensions MUST NOT rename required fields or relax their constraints.

---

## 5. Field format rules

### 5.1 Dates
- Format: `YYYY-MM-DD` (ISO 8601 calendar date only; no time/timezone).
- `updated >= created` MUST hold.
- Rotation policy: `updated` is NOT bumped for pure reformat commits; agents
  must distinguish content revisions from cosmetic changes.

### 5.2 Tags
- Lowercase only.
- Kebab-case (`strangle50`, `per-stock`, `v7-boost`). Underscore is permitted
  but discouraged.
- Each tag ≤ 40 chars.
- Total tag count ≤ 12 per entry.
- No semantic duplication with `status` / `owner` (e.g., tag `archived` is
  redundant — `status: archived` carries that signal).

### 5.3 Path resolution for cross-references

Cross-references in `supersedes` / `superseded_by` / `related` / `blocks` /
`blocked_by` may target **either** another knowledge entry **or** an
implementation path elsewhere in the repo (e.g., an ADR in `knowledge/decisions/`
naturally points to the code / config / hook that implements the decision).

`audit_knowledge.py` Check 9 resolves each target by trying both locations in
order; a target passes if **either** resolves to an existing file/directory:

1. **Knowledge-relative** (the common case) — resolved against `knowledge/`:
   ```yaml
   supersedes: experiments/EXP-2026-0009.md          # → knowledge/experiments/EXP-2026-0009.md
   related: [domain/hk_market_regime.md]             # → knowledge/domain/hk_market_regime.md
   ```

2. **Repo-relative** (implementation pointer) — resolved against the repo root:
   ```yaml
   related:
     - contracts/knowledge_frontmatter_schema.md     # → <repo>/contracts/...
     - .claude/hooks/edit-write-guard.py             # → <repo>/.claude/hooks/...
     - tools/audit_knowledge.py                      # → <repo>/tools/...
   ```

Forbidden forms (unambiguous error):
```yaml
supersedes: /knowledge/experiments/EXP-X.md         # absolute path
supersedes: knowledge/experiments/EXP-X.md          # redundant knowledge/ prefix
supersedes: EXP-2026-0009                           # bare ID with no path
```

Trailing `/` is tolerated for directory references (e.g., `.claude/hooks/`).

---

## 6. Exemptions

The following files are NOT subject to this schema:

- `knowledge/INDEX.md` — top index, governed by `knowledge_index_schema.md`
- `knowledge/*/INDEX.md` — per-category indexes, governed by `knowledge_index_schema.md`
- `knowledge/*/_TEMPLATE.md` — templates (may carry exemplar frontmatter for
  copy-paste but are ignored by the auditor)
- `knowledge/*/VALIDATION_TEST.md` — legacy placeholders (pending removal)

---

## 7. Versioning

This contract follows SemVer:
- **Patch** — typo / clarification, no behavioral change to validators
- **Minor** — new optional fields, new status/owner enum values (backward compatible)
- **Major** — removed/renamed required fields, breaking enum changes

Consumers (auditors, dashboards, downstream tools) MUST declare compatibility
via their own schema header. Any major bump requires a `proposals/` entry
and staged migration (Art.3 of project constitution).

---

## 8. Migration policy

When this contract evolves:
1. Core publishes the updated contract + migration guide in `proposals/`.
2. Each agent migrates their own `knowledge/<owner-scope>/**` files in their
   feature branch.
3. Auditor runs in "transitional" mode for one rotation period (warn instead of
   fail on the new field) to give agents time to catch up.
4. After rotation, auditor flips to hard-fail.

Major-version changes NEVER auto-rewrite files. All migrations go through the
owning agent's review.

### 8.1 v1.1.0 release notes

`briefing` is a new **optional** field. v1.0.x entries are auto-compliant —
absent field means "does not appear in either Briefing panel" which matches
v1.0.x dashboard behavior (Briefing mode did not exist). No transitional
warn-only period needed; auditor goes straight to enum-validation hard-fail
since absence is valid.

Per-agent self-marking is async (`proposals/dashboard_briefing_mode.md`
Phase C) — each agent decides at their own pace which of their entries
warrant `pinned` / `serendipity`.

### 8.2 v1.2.0 release notes

`carrier_class` is a new **transitional required** field (§2.5). Unlike
v1.1.0's `briefing` (which was always optional), v1.2.0 declares intent to
make `carrier_class` mandatory but defers enforcement to allow migration:

- **v1.2.0 (P-0053 Phase 2, this release)**: field is documented; auditor
  Checks 12-15 emit `WARN` (never `FAIL`) on missing / invalid / path-mismatched
  values, or on `current-state` entries lacking an autogen placeholder.
  Existing entries are not auto-rewritten.
- **P-0053 Phase 3**: auditor `--infer` mode produces a read-only mapping
  report (`audit/knowledge_class_inference_report.md`) listing the inferred
  class for every existing entry without modifying files.
- **P-0054**: defines the autogen block protocol and migrates `current-state`
  exemplars; backfill of `carrier_class` frontmatter for the broader corpus
  is a separate downstream proposal.
- **v1.3.0**: once backfill is complete and Phase 4 ships, the field moves
  from §2.5 to §2 and the warnings become failures. v1.3.0 release notes
  will document the cutover commit.

Authoritative class semantics live in
`knowledge/governance/knowledge-carrier-classes.md`. This contract reserves
the enum values and the migration timeline; semantics (when to update each
class, which class allows autogen blocks, lesson eligibility) are owned by
the governance doc.
