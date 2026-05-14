---
theme: universal
name: contract-driven-validator
description: Design principle for any validator or audit tool that enforces a schema — derive required fields, enum values, and structural rules by parsing the contract document at runtime, not by duplicating them as constants in the validator code. Duplication causes silent drift the moment the contract evolves (rename, add enum value, tighten required set). The validator and the contract must share exactly one source of truth. Applies to audit scripts, test fixtures, dashboard renderers, type generators — any consumer of a schema.
type: guide
tags: [contracts, validation, audit, governance, drift-prevention]
created: 2026-04-24
updated: 2026-05-06
---

# Contract-Driven Validator

When a tool enforces or consumes a schema contract (`contracts/*.md`, `contracts/*.json`), it MUST derive the schema details by parsing the contract at runtime. Hardcoding field names, enum values, or structural rules inside the validator is a silent-drift antipattern.

## Why this matters

A validator with hardcoded rules looks fine on day one. On day ninety, when the contract gains a new enum value or renames a required field, you have two problems:

1. The validator still reads the old rules → false failures or false passes
2. There's nothing mechanical telling you the two are out of sync

The failure mode is quiet. Nobody notices until a downstream consumer breaks, at which point "why didn't the audit catch this?" becomes the question. Because the audit was reading 90-day-old rules copied from the contract.

## The pattern

```python
# BAD — hardcoded
REQUIRED_FIELDS = {"title", "status", "created", "updated", "tags"}
STATUS_ENUM = {"active", "archived", "draft"}

def audit(file):
    fm = parse_frontmatter(file)
    for field in REQUIRED_FIELDS:
        if field not in fm: fail(...)
    if fm["status"] not in STATUS_ENUM: fail(...)

# GOOD — contract-derived
def audit(file, contract_path):
    required = parse_required_fields(contract_path)   # parses §2 table
    status_enum = parse_enum(contract_path, "### 3.1 `status`")  # parses table rows
    fm = parse_frontmatter(file)
    for field in required:
        if field not in fm: fail(...)
    if fm["status"] not in status_enum: fail(...)
```

The validator becomes a thin parser of the contract plus the check loop. When the contract gains a field or enum value, the validator picks it up on the next run — no code change needed.

## When to apply

Apply this pattern whenever you have:

- A schema contract that lists required fields, enum values, or structural rules in a structured way (markdown tables, JSON arrays, YAML lists)
- A tool that needs to enforce or consume those rules

Examples of applicable tools:
- Auditors (`audit_knowledge.py`, `audit_settings.py`, `check_scope.py`)
- Linters that enforce project-specific conventions
- Dashboard renderers that key off schema fields
- Test fixtures that generate compliant sample data
- Type / stub generators

## When NOT to apply

- The "contract" is English prose with no structured tables — parsing is too fragile; use a structured section or a JSON sidecar.
- The validator has performance constraints that preclude runtime parsing — cache the parsed contract, or generate code from the contract at build time (still contract-derived, just pre-processed).
- The contract itself is machine-generated from the validator (reverse direction) — then the validator IS the source of truth.

## Parsing shape conventions

When designing a contract with the expectation that validators will parse it:

1. **Required fields in a table**: put them in one markdown table with a predictable column header ("Field" / "Type" / "Semantics"). Validators grep by header name.
2. **Enums in sub-section tables**: each enum gets its own `### 3.x <field-name>` sub-heading with a `Value | Meaning` table. Validators find the heading, parse the table.
3. **Stable headings**: `## 2. Required fields`, `### 3.1 status`, etc. Section numbers change less often than wording; validators key off numbers.
4. **Mark exemptions explicitly**: `§6 Exemptions` listing files/paths that don't get validated. Parser treats these as a denylist.

See `contracts/knowledge_frontmatter_schema.md` + `tools/audit_knowledge.py` for a worked example where the audit parses §2 (required fields) and §3.1/§3.2 (enums) at startup.

## Versioning

The validator should print which contract version it loaded at startup:

```
Contract v1.0.0 loaded: required=[title, status, ...] status_enum=[active, archived, ...]
```

This gives a one-line debugging handle when behavior differs from expectation: "what version of the contract are you running against?"

## Single parser, not two implementations

When **multiple tools** consume the same contract, they MUST share a single parser implementation — either by importing a common module, or by one tool importing the other's parser. Two independent implementations of "parse this frontmatter" / "parse this JSON config" / "extract this section" will drift the moment either side accepts a YAML form, edge case, or format extension that the other doesn't.

The corollary to "single source of truth for the contract" is "single source of truth for **how the contract is parsed**". Each independent reader is a place where reality and contract can diverge silently — and the more readers, the harder the divergence is to detect, because you can't easily tell from the outside which reader is wrong.

```python
# BAD — two independent parsers
# tools/audit_knowledge.py
def parse_frontmatter(text):  # supports inline + block-list
    ...

# tools/build_knowledge_dashboard.py
def _parse_frontmatter(text):  # supports inline only — drifted!
    ...

# GOOD — shared
# tools/_frontmatter.py
def parse_frontmatter(text): ...

# audit_knowledge.py
from _frontmatter import parse_frontmatter

# build_knowledge_dashboard.py
from _frontmatter import parse_frontmatter
```

Detection heuristics: when two tools claim to read the same artifact, grep for `def parse_*` / `def _parse_*` in both. If you find two definitions — that's the smell. Either consolidate, or document why they're allowed to diverge (rare; usually a YAGNI claim that ages badly).

## Anti-patterns observed in this project's history

**Pre-2026-04-24** (`tools/audit_knowledge.py` rewrite): the audit hardcoded a set of required fields that gradually diverged from what entries actually used. When `owner` was added as required in frontmatter_schema v1.0.0, the old audit wouldn't have caught files missing it — because the old hardcoded set didn't mention owner. The rewrite that fixed this is the reference implementation for the contract-derived pattern above.

**2026-04-24 → 2026-05-06** (`tools/build_knowledge_dashboard.py` parser drift): the dashboard had its own `_parse_frontmatter` that only handled inline-list (`[a, b]`) and scalar values; multi-line block-list (`key:\n  - a\n  - b`) silently collapsed. Meanwhile `audit_knowledge.py` (rewritten 2026-04-24, commit `db0b830c`) supported all three forms via lookahead. **The two parsers drifted for ~12 days.**

Symptom: dashboard's knowledge graph view showed only **3 edges across 114 entries** even though `audit_knowledge.py` was correctly resolving 200+ cross-references behind the scenes. User noticed graph was suspiciously sparse. Root cause was identified in 7 diagnostic steps:

1. Hypothesize migration stripped link fields → **disproved** (`bdb00294` only added `owner:`)
2. Direct count: 76/115 entries have `related:` field → "metadata sparse" hypothesis falsified
3. Classify `related` targets → looks like 75/76 point to repo-relative impl pointers
4. Sample initial entry (`b4a5aa77` ADR-001) → uses multi-line YAML list form
5. Read dashboard's `_parse_frontmatter` docstring → self-confessed: "Multi-line list form collapses to string"
6. Compare to `audit_knowledge.py:parse_frontmatter` → it does block-list lookahead correctly
7. Quantify: 62 block-list link fields holding 204 targets / 181 of which point to other knowledge entries

Fix (commit `8e30fed3`): align dashboard's parser with audit's (lookahead block-list items, normalize to in-memory list). Edges 3 → 159; connected nodes 5 → 69.

The "new view exposes old bug" pattern: the cytoscape graph (commit `fb5e8efd`) didn't introduce the parser bug — it visualized data the table-view chips had also been quietly missing for 12 days. Adding richer visualization is sometimes the cheapest way to surface long-running silent bugs in shared parsers.

## Cross-reference

- `contracts/knowledge_frontmatter_schema.md` — contract structured for parsing
- `tools/audit_knowledge.py` — reference implementation parsing §2 + §3.1 + §3.2
- `tools/build_knowledge_dashboard.py` — alternate consumer; parser aligned with audit as of `8e30fed3` (was drifted pre-2026-05-06)
