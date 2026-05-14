# Contract: knowledge/**/INDEX.md Structure

**Version**: 1.0.0
**Status**: active
**Owner**: core
**Consumers**: `tools/build_knowledge_dashboard.py` (top-level parsing),
`tools/audit_knowledge.py` (structural checks)

Defines the format of `knowledge/INDEX.md` (top) and `knowledge/<cat>/INDEX.md`
(per-category) files so downstream tools can navigate the federated knowledge
base without hardcoded category lists.

---

## 1. Two INDEX levels

| Level | Path | Role | Owner |
|-------|------|------|-------|
| Top | `knowledge/INDEX.md` | Lists all subdirectory categories + their owners | `core` |
| Category | `knowledge/<cat>/INDEX.md` | Lists all entries within a category | the category's owner agent (per top INDEX) |

Nested INDEX (e.g., `knowledge/research/inspiration/INDEX.md`) is permitted
when a category organizes its entries by secondary axes (themes, sub-domains).
Nested INDEX conforms to the same category-level schema.

---

## 2. Top `knowledge/INDEX.md`

### 2.1 Required section: `## Subdirectory Overview`

A markdown H2 with the heading `Subdirectory Overview` containing exactly one
markdown table whose header row includes the columns `Subdirectory`, `Owner`,
`Content`, and optionally `Sub-Index`. The table is the authoritative source
for:

- The set of valid categories (determines scope of `audit_knowledge.py`).
- Each category's primary owner (cross-checked against each entry's `owner`
  frontmatter).
- Human-readable description used by `build_knowledge_dashboard.py`.

Example:

```markdown
## Subdirectory Overview

| Subdirectory | Owner | Content | Sub-Index |
|-------------|-------|---------|-----------|
| decisions/ | rules + core | Architecture Decision Records (ADR) | [INDEX](decisions/INDEX.md) |
| domain/ | rules + core | Cross-agent domain knowledge | [INDEX](domain/INDEX.md) |
| models/ | rules | Model evolution records | [INDEX](models/INDEX.md) |
| trading/ | trade | Trading domain knowledge | (pending) |
| data-quality/ | data | Data quality knowledge | (pending) |
| research/ | research | Tool research conclusions | [INDEX](research/INDEX.md) |
```

Cell rules:
- `Subdirectory`: path of the child directory, trailing `/` optional. Values
  MUST match `[a-z0-9][a-z0-9-]*`.
- `Owner`: one enum value from `knowledge_frontmatter_schema.md` §3.2, OR a
  combination joined by ` + ` (e.g., `rules + core` — order matters: first
  listed is the default primary owner). Permitted combinations are documented
  below.
- `Content`: one-line description; used verbatim as the dashboard subtitle.
- `Sub-Index`: optional markdown link to the category's INDEX.md, or
  `(pending)` when the category exists but has no entries.

Permitted multi-owner combinations: `rules + core`, `core + rules`. Other
combinations require a proposal.

### 2.2 Optional: contextual sections

The top INDEX MAY include additional sections above the subdirectory table
(introduction, governance reminder, quick-query cookbook). These are ignored
by parsers.

### 2.3 Frontmatter

Top INDEX.md does not require frontmatter. If present, only the following
fields are recognized:

| Field | Purpose |
|-------|---------|
| `version` | Semver of the top INDEX layout (currently `1.0.0`) |
| `updated` | Last material revision date |

---

## 3. Per-category `knowledge/<cat>/INDEX.md`

### 3.1 Structural flexibility

A category INDEX MAY organize entries in any of the following forms:

1. **Single table**: one markdown table with entry rows.
2. **Sectioned tables**: multiple `## Section` H2s, each containing one table.
3. **Thematic grouping**: H3 `### Theme` sub-headings with bullet lists of
   entries (used by `research/inspiration/INDEX.md`).

The dashboard generator's fallback — rglob the directory for `*.md` files when
it cannot parse the INDEX — makes structural flexibility safe. The audit tool
only checks that entries in the directory are referenced *somewhere* in the
INDEX.md body (substring match), not that a specific table format is used.

### 3.2 Optional frontmatter

Category INDEX.md MAY carry frontmatter to affect dashboard rendering:

| Field | Type | Effect |
|-------|------|--------|
| `display_title` | string | Overrides the directory name in the dashboard header |
| `display_order` | integer | Sort key for category ordering (ascending; default: table order in top INDEX) |
| `extends` | list[string] | Names of additional optional frontmatter fields this category accepts on its entries (documented here, enforced by auditor) |

Example:

```markdown
---
display_title: "Models — Production Evolution"
display_order: 10
extends: [strategy_family, production_since]
---

# knowledge/models/INDEX.md

...
```

### 3.3 Entry references

Each entry file (except `INDEX.md`, `_TEMPLATE.md`, `VALIDATION_TEST.md`) in
the category directory tree MUST be referenced by filename in the INDEX.md
body (transitively — nested subdirectory entries may be referenced in their
nested INDEX only).

Referencing form is flexible — any of these satisfy the check:

```markdown
- [EXP-2026-0009: V7 Boost Derivation](experiments/EXP-2026-0009.md)
| EXP-2026-0010 | active | `experiments/EXP-2026-0010.md` |
See `adr-005-hybrid-over-xgboost.md` for background.
```

---

## 4. Audit rules

`audit_knowledge.py` enforces the following INDEX-related checks:

| Check | Rule | Failure severity |
|-------|------|------------------|
| Top INDEX has Subdirectory Overview | H2 heading present; table parseable | **fail** |
| Top INDEX owners are valid enum values | Each `Owner` cell matches §2.1 rules | **fail** |
| Category dir has INDEX.md | Any directory listed in top INDEX must have an INDEX.md file | **fail** (grace period for `(pending)` cell) |
| Entry referenced in INDEX | Each non-exempt `*.md` file under a category is mentioned by name in that category's INDEX.md (or a nested INDEX.md) | **warn** |
| Owner frontmatter matches category | Each entry's `owner` frontmatter is either the category's primary owner OR (for multi-owner categories) any of the listed owners | **fail** |
| Nested INDEX consistency | If nested INDEX.md exists, entries in the nested directory are referenced in the nested (not parent) INDEX | **warn** |

---

## 5. Versioning

This contract follows SemVer:
- **Patch** — typo / clarification, no behavioral change to parsers
- **Minor** — new optional frontmatter fields, additional recognized section
  headings, new recognized multi-owner combinations
- **Major** — renamed/removed required sections, removed permitted layouts

Major bumps require a `proposals/` entry. Auditor declares target version at
the top of its output for troubleshooting version-skew.

---

## 6. Known quirks

- `knowledge/INDEX.md` is tolerant of leading content (quick-query blocks,
  governance reminders) above the `Subdirectory Overview` section.
- Empty categories: a category with only `INDEX.md` (no entries yet) is valid;
  the dashboard renders an empty section. Top INDEX should mark such rows as
  `(pending)` in the Sub-Index cell.
- `research/inspiration/`: the only currently-sanctioned nested-INDEX
  organization, grouped by `### Theme`. Future nested organizations require a
  proposal.
