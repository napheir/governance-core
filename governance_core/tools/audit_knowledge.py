"""
knowledge/ health audit — contract-driven (v1.0.0+).

Derives required fields, enum values, and category -> owner map from:
  - contracts/knowledge_frontmatter_schema.md
  - contracts/knowledge_index_schema.md
  - knowledge/INDEX.md (Subdirectory Overview table)

Checks run (severity in brackets):
  1. Frontmatter required fields present         [fail]
  2. status enum valid                           [fail]
  3. owner enum valid                            [fail]
  4. owner matches category owner map            [fail]
  5. dates well-formed and updated >= created    [fail]
  6. File size < 100 lines                       [warn]
  7. INDEX.md references entry                   [warn]
  8. Staleness (>30 days since update)           [warn]
  9. Cross-reference link integrity              [fail]
 10. briefing enum valid (optional field)        [fail]
 11. Skill tier bijection + INDEX.md freshness   [fail / warn]
 12. carrier_class present                       [warn — transitional v1.2.0]
 13. carrier_class enum valid                    [warn — transitional v1.2.0]
 14. carrier_class matches expected path         [warn — transitional v1.2.0]
 15. current-state has autogen placeholder       [warn — transitional v1.2.0]
 16. Skill scenario-surface coverage             [fail — P-0103, gated on clusters]

Checks 12-15 enforce P-0053 / schema v1.2.0's transitional `carrier_class`
field per `contracts/knowledge_frontmatter_schema.md` §2.5 + §8.2 — they
emit warnings (never failures) so the broader knowledge base can migrate
gradually. Schema v1.3.0 will flip them to failures.

Exits 0 if no failures, 1 otherwise.

Usage:
    python tools/audit_knowledge.py                           # audit core's knowledge/
    python tools/audit_knowledge.py --root ../agent-rules     # audit another clone
"""

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
STALE_DAYS = 30
LINE_LIMIT = 100
SKIP_FILENAMES = {"INDEX.md", "_TEMPLATE.md", "_template.md", "VALIDATION_TEST.md"}

# Path prefixes (relative to knowledge/) skipped entirely by all checks.
# `assets/` holds vendored runtimes (Mermaid) and CSS/JS rendering
# infrastructure introduced by P-0054 Phase 2; not authored knowledge
# content, so frontmatter contract does not apply.
SKIP_PATH_PREFIXES = ("assets/",)

# Carrier-class path map (P-0053 §3) — top-level knowledge/ subdirectory ->
# expected `carrier_class` value. `models/` is the only subdirectory that
# mixes classes (see _expected_carrier_class below); everything else is
# 1:1. Semantic source: `knowledge/governance/knowledge-carrier-classes.md`.
CARRIER_CLASS_PATH_MAP = {
    "decisions": "decision-record",
    "domain": "reference",
    "governance": "reference",
    "methodology": "reference",
    "operations": "runbook",
    "experiments": "experiment-record",
    "datasets": "experiment-record",
    "features": "reference",
    "research": "reference",
    "data-quality": "reference",
    "trading": "reference",
    "skills": "reference",
    "design": "reference",  # added P-0053 Phase 4 after Phase 3 report surfaced gap
    "lessons": "derived-lesson",
    # "models" handled specially: *_current.md -> current-state,
    # *_evolution.md / production_changelog.md -> reference
}

# Marker for `current-state` files awaiting P-0054 autogen-block migration.
# Files holding production-drifting numbers must contain at least one of
# these placeholders so Check 15 confirms the author acknowledged the
# autogen requirement. P-0054 will replace the marker with structured
# autogen sections.
AUTOGEN_PLACEHOLDER_MARKERS = (
    "<!-- autogen-placeholder -->",
    'class="autogen-block"',  # P-0054 HTML form, accepted ahead of migration
)

# For Check 11 (skill tier bijection) we import the registry and the
# index builder. Both live under the project root, not as installed
# packages, so we widen sys.path explicitly.
if str(DEFAULT_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULT_ROOT))
if str(DEFAULT_ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(DEFAULT_ROOT / "tools"))

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
# Deliberately uses [ \t] rather than \s to avoid the colon's trailing
# whitespace eating the newline and absorbing the first block-list item
# as the field's value. Block-list form (`key:\n  - item`) is handled by
# parse_frontmatter's post-pass.
FIELD_LINE_RE = re.compile(r"^(\w+)[ \t]*:[ \t]*(.*)$", re.MULTILINE)
BLOCK_ITEM_RE = re.compile(r"^\s+-\s+(.+?)\s*$")

# Optional cross-reference fields per knowledge_frontmatter_schema §4.1.
# Values may be a single relative path or a list; either way, every
# listed path must resolve under knowledge/ or the link is broken.
LINK_FIELDS = ["supersedes", "superseded_by", "related", "blocks", "blocked_by"]


# -------------- contract parsing --------------

def parse_required_fields(contract_path: Path) -> list[str]:
    """Extract required-field names from frontmatter_schema §2 Required fields table."""
    text = contract_path.read_text(encoding="utf-8")
    marker = text.find("## 2. Required fields")
    if marker < 0:
        raise ValueError("contract missing §2 Required fields section")
    section = text[marker:]
    fields: list[str] = []
    header_seen = False
    for line in section.splitlines()[1:]:
        match = TABLE_ROW_RE.match(line)
        if not match:
            if header_seen:
                break
            continue
        cells = [c.strip() for c in match.group(1).split("|")]
        if not header_seen:
            if any("field" == c.lower() for c in cells):
                header_seen = True
            continue
        if all(set(c) <= set("-: ") for c in cells):
            continue
        first = cells[0].strip("`")
        if first:
            fields.append(first)
    if not fields:
        raise ValueError("contract §2 has no required-field rows")
    return fields


def parse_enum(contract_path: Path, heading: str) -> set[str]:
    """Extract enum values from a `### <heading>` markdown sub-section's first table."""
    text = contract_path.read_text(encoding="utf-8")
    marker = text.find(heading)
    if marker < 0:
        raise ValueError(f"contract missing heading {heading!r}")
    section = text[marker:]
    values: set[str] = set()
    header_seen = False
    for line in section.splitlines()[1:]:
        match = TABLE_ROW_RE.match(line)
        if not match:
            if header_seen:
                break
            continue
        cells = [c.strip() for c in match.group(1).split("|")]
        if not header_seen:
            if any("value" == c.lower() for c in cells):
                header_seen = True
            continue
        if all(set(c) <= set("-: ") for c in cells):
            continue
        v = cells[0].strip("`")
        if v:
            values.add(v)
    if not values:
        raise ValueError(f"contract {heading!r} has no enum rows")
    return values


def _expected_carrier_class(rel_path: Path) -> str | None:
    """Return the expected `carrier_class` for a knowledge-relative path.

    `rel_path` is relative to `knowledge/`. Returns None when the path's
    top-level subdirectory has no mapping (Check 14 then emits a "no
    mapping" warning for the file).

    `knowledge/models/` is the only directory that mixes classes:
        *_current.md             -> current-state
        production_changelog.md  -> reference
        *_evolution.md           -> reference
    """
    parts = rel_path.parts
    if not parts:
        return None
    top = parts[0]
    if top == "models":
        name = rel_path.name
        if name.endswith("_current.md"):
            return "current-state"
        # production_changelog.md and *_evolution.md are reference;
        # any future *.md additions to models/ default to reference until
        # the proposal/governance review reclassifies them.
        return "reference"
    return CARRIER_CLASS_PATH_MAP.get(top)


def parse_category_owner_map(knowledge_root: Path) -> dict[str, list[str]]:
    """Parse top INDEX.md -> {category: [allowed_owners]} (list for multi-owner).

    Returns an empty map when ``knowledge/INDEX.md`` is absent (defensive: a
    single-agent / pre-index project legitimately has no top-level index, and a
    missing optional input must never crash the validator). main() additionally
    gates Check 4 on the file's presence so the empty map is not mistaken for
    "every category unowned" (P-0112 / gc #114 sibling).
    """
    index_md = knowledge_root / "INDEX.md"
    if not index_md.is_file():
        return {}
    text = index_md.read_text(encoding="utf-8")
    result: dict[str, list[str]] = {}
    header_cols: list[str] | None = None
    for line in text.splitlines():
        match = TABLE_ROW_RE.match(line)
        if not match:
            if header_cols is not None:
                break
            continue
        cells = [c.strip() for c in match.group(1).split("|")]
        if header_cols is None:
            normalized = [c.lower() for c in cells]
            if "subdirectory" in normalized and "owner" in normalized:
                header_cols = normalized
            continue
        if all(set(c) <= set("-: ") for c in cells):
            continue
        row = dict(zip(header_cols, cells))
        cat = ""
        if "subdirectory" in row:
            cat = row["subdirectory"].strip("`/ ")
        owner_cell = ""
        if "owner" in row:
            owner_cell = row["owner"]
        if not cat or not owner_cell:
            continue
        owners = [o.strip().lower() for o in owner_cell.split("+")]
        result[cat] = owners
    return result


# -------------- frontmatter extraction --------------

def parse_frontmatter(text: str) -> dict[str, str] | None:
    """Return {field: raw_value} for the file's YAML frontmatter, or None.

    Scalar form:       `key: value`          -> result[key] = "value"
    Inline list:       `key: [a, b]`         -> result[key] = "[a, b]"
    Block list:        `key:\n  - a\n  - b`  -> result[key] = "[a, b]" (normalized)
    """
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    fm_body = parts[1]
    lines = fm_body.splitlines()
    result: dict[str, str] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        match = FIELD_LINE_RE.match(line)
        if not match:
            i += 1
            continue
        key = match.group(1)
        value = match.group(2).strip()
        if not value:
            # Look ahead for block-list items (lines beginning with whitespace + `-`)
            items: list[str] = []
            j = i + 1
            while j < len(lines):
                bm = BLOCK_ITEM_RE.match(lines[j])
                if not bm:
                    break
                items.append(bm.group(1).strip("\"'"))
                j += 1
            if items:
                value = "[" + ", ".join(items) + "]"
                i = j
            else:
                i += 1
        else:
            i += 1
        result[key] = value
    return result


def _parse_link_value(raw: str) -> list[str]:
    """Split a cross-reference value into individual path strings.

    Accepts three YAML surface forms:
      single path:   `supersedes: experiments/EXP-2026-0001.md`
      inline list:   `related: [a.md, decisions/adr-001.md]`
      (block-list form like `- item` is not in-scope for the tiny parser
       used here; the field schema permits it but entries in this repo
       use the two forms above.)
    Empty strings / placeholder "(none)" / "[]" are ignored.
    """
    raw = raw.strip()
    if not raw or raw in {"[]", "(none)", "null", "~"}:
        return []
    if raw.startswith("[") and raw.endswith("]"):
        items = [x.strip().strip("\"'") for x in raw[1:-1].split(",")]
        return [x for x in items if x]
    return [raw.strip("\"'")]


# -------------- skill tier bijection --------------

def _detect_non_hub(root: Path) -> bool:
    """Default-strict non-hub detection for audit relaxations (gc #101 / P-0104).

    Returns True only when the config for ``root`` positively identifies a
    downstream consumer clone. Any ambiguity (config absent / unreadable / no
    consumer_id, or the hub itself) returns False, so the strict FAIL behavior
    is the default and a relaxation can never silently weaken the hub.
    """
    try:
        from governance_core.config import is_non_hub_clone
        return is_non_hub_clone(root)
    except Exception:
        return False


def _audit_skill_tiers(root: Path, tiers_path: Path) -> tuple[int, int]:
    """Audit knowledge/skills/_tiers.json against the live registry.

    Three independent checks:
      11a. Bijection registry → tiers  (FAIL) — every md-skill must be
           classified into exactly one tier.
      11b. Bijection tiers → registry  (FAIL) — every tier entry must
           correspond to an existing md-skill (no phantoms).
      11c. INDEX.md freshness          (WARN) — generated INDEX.md must
           match what build_skill_index.render() would produce now.

    Python modules (source_type='module') are excluded — they are
    library code, not workflows; not in scope for tier classification.

    Returns:
        (failed_count, warned_count).
    """
    failed = 0
    warned = 0

    try:
        from governance_core.discovery.registry import SkillRegistry
    except Exception as exc:
        logger.warning("  WARN: skill registry import failed: %s", exc)
        return 0, 1

    try:
        tiers_data = json.loads(tiers_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("  FAIL: cannot parse _tiers.json: %s", exc)
        return 1, 0

    # project_root=root so --root and isolated test fixtures scan the audited
    # clone's skills (consistent with Check 16); at the hub this coincides with
    # the git-toplevel default.
    registry = SkillRegistry(track_usage=False, project_root=root)
    registry.scan()
    manifest = registry.manifest()
    md_skills = {
        s["name"] for s in manifest
        if s["source_type"] != "module"
    }
    # Learned skills (source_type='learned') are the only ones a non-hub clone
    # can produce locally; _tiers.json is hub-owned, so a freshly-extracted
    # learned skill is legitimately catalog-pending in a consumer (gc #101).
    learned_skills = {
        s["name"] for s in manifest if s["source_type"] == "learned"
    }
    non_hub = _detect_non_hub(root)

    tier_to_skills: dict[str, set[str]] = {}
    for tier_id, tier_body in tiers_data.get("tiers", {}).items():
        tier_to_skills[tier_id] = set(tier_body.get("skills", []))

    classified = set()
    duplicates: list[tuple[str, list[str]]] = []
    for name in md_skills:
        homes = [t for t, names in tier_to_skills.items() if name in names]
        if len(homes) > 1:
            duplicates.append((name, homes))
        if homes:
            classified.add(name)

    # 11a. registry → tiers
    unclassified = md_skills - classified
    for name in sorted(unclassified):
        if non_hub and name in learned_skills:
            # Non-hub clone: _tiers.json is hub-owned / out of this clone's
            # scope, so a just-extracted learned skill is legitimately pending
            # the hub's cataloging sweep (gc #101 / P-0104). WARN, don't FAIL.
            logger.warning(
                "  WARN: learned skill %r not yet in _tiers.json — pending "
                "hub catalog (non-hub clone)", name
            )
            warned += 1
        else:
            logger.warning(
                "  FAIL: skill %r not classified in _tiers.json", name
            )
            failed += 1

    # Duplicate classification is also a fail (each skill must live in one tier)
    for name, homes in duplicates:
        logger.warning(
            "  FAIL: skill %r appears in multiple tiers: %s", name, homes
        )
        failed += 1

    # 11b. tiers → registry
    all_tier_entries: set[str] = set()
    for names in tier_to_skills.values():
        all_tier_entries.update(names)
    phantoms = all_tier_entries - md_skills
    for name in sorted(phantoms):
        home_tiers = {t for t, names in tier_to_skills.items() if name in names}
        if non_hub and home_tiers == {"branch"}:
            # Non-hub clone: branch-tier skill *files* are branch-local (present
            # in exactly one clone) while _tiers.json is a single globally-synced
            # hub-owned file. A branch entry owned by another clone is therefore a
            # legitimate phantom here, unresolvable by any local action (deleting
            # the file can't touch the synced list). Mirror the 11a / 16a non-hub
            # carve-outs (gc #101/P-0104, #102/P-0105): WARN, don't FAIL (gc #114
            # / P-0111). Narrow to home_tiers == {"branch"} so a phantom that also
            # lives in universal/project (a real, fixable gap) still FAILs.
            logger.warning(
                "  WARN: branch-tier entry %r absent in this clone — "
                "branch-local file lives in its owning clone; _tiers.json is "
                "hub-owned (non-hub clone)", name
            )
            warned += 1
        else:
            logger.warning(
                "  FAIL: _tiers.json entry %r not found in skill registry "
                "(phantom)", name
            )
            failed += 1

    # 11c. unclassified bucket non-empty → warn
    pending = tier_to_skills.get("unclassified", set())
    if pending:
        logger.warning(
            "  WARN: %d skill(s) in unclassified bucket awaiting tier "
            "assignment: %s",
            len(pending), sorted(pending),
        )
        warned += 1

    # 11d. INDEX.md freshness — compare against builder output
    index_path = root / "knowledge" / "skills" / "INDEX.md"
    try:
        from build_skill_index import render as render_index
    except Exception as exc:
        logger.warning("  WARN: build_skill_index import failed: %s", exc)
        return failed, warned + 1

    if not index_path.is_file():
        logger.warning("  WARN: knowledge/skills/INDEX.md missing — run "
                       "`python tools/build_skill_index.py`")
        warned += 1
    else:
        expected = render_index(tiers_data, [
            s for s in registry.manifest() if s["source_type"] != "module"
        ])
        actual = index_path.read_text(encoding="utf-8")
        if actual != expected:
            logger.warning(
                "  WARN: knowledge/skills/INDEX.md is stale (does not match "
                "builder output) — run `python tools/build_skill_index.py`"
            )
            warned += 1
        else:
            logger.info(
                "  [OK] %d md-skills classified across %d tier(s); "
                "INDEX.md up to date",
                len(md_skills),
                sum(1 for n in tier_to_skills.values() if n),
            )

    return failed, warned


def _audit_scenario_coverage(root: Path, clusters_path: Path,
                             tiers_path: Path) -> tuple[int, int]:
    """Audit scenario-surface coverage (P-0103 part C, gc #100).

    Once a project authors ``knowledge/skills/_scenario_clusters.json``, every
    md-skill must ENTER the SessionStart surface -- be in the ``universal``
    tier (``_tiers.json``) OR a member of >=1 scenario cluster -- otherwise it
    can never be consulted, the very gap that left ~50 skills at use_count=0.

      16a. Coverage (FAIL) -- every md-skill is universal or clustered.
      16b. Phantom  (FAIL) -- every cluster member resolves to a real md-skill.

    Library modules (source_type='module') are excluded, mirroring Check 11.
    Gated on ``_scenario_clusters.json`` existence by the caller, so a project
    that has not adopted scenario clusters is never penalized.
    """
    failed = 0
    warned = 0
    try:
        from governance_core.discovery.registry import SkillRegistry
    except Exception as exc:
        logger.warning("  WARN: skill registry import failed: %s", exc)
        return 0, 1
    try:
        clusters_data = json.loads(clusters_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("  FAIL: cannot parse _scenario_clusters.json: %s", exc)
        return 1, 0

    def _field(d, key, default):
        # Membership test, not a defaulted dict lookup (Art.4): data file.
        return d[key] if isinstance(d, dict) and key in d else default

    # Scan the AUDITED project's skills (project_root=root), so this works
    # under --root and is isolatable in tests -- unlike Check 11's registry.
    registry = SkillRegistry(track_usage=False, project_root=root)
    registry.scan()
    manifest = registry.manifest()
    md_skills = {
        s["name"] for s in manifest if s["source_type"] != "module"
    }
    learned_skills = {
        s["name"] for s in manifest if s["source_type"] == "learned"
    }
    command_skills = {
        s["name"] for s in manifest if s["source_type"] == "command"
    }
    non_hub = _detect_non_hub(root)

    universal: set = set()
    if tiers_path.is_file():
        try:
            td = json.loads(tiers_path.read_text(encoding="utf-8"))
            universal = set(
                _field(_field(_field(td, "tiers", {}), "universal", {}),
                       "skills", [])
            )
        except (json.JSONDecodeError, OSError):
            universal = set()

    clustered: set = set()
    for body in _field(clusters_data, "clusters", {}).values():
        clustered.update(_field(body, "members", []))

    surfaced = universal | clustered

    # 16a. coverage
    for name in sorted(md_skills - surfaced):
        if name in command_skills:
            # Slash commands are always listed in the harness Skill-tool menu
            # and invoked by name, so their discoverability never depends on
            # SessionStart cluster surfacing -- the use_count=0 gap (P-0113)
            # this gate closes is about consult-only learned/guide skills.
            # Exempt commands from FAIL (gc #102 / P-0105); this is additive to
            # the #101 non-hub-learned WARN carve-out below, not a replacement.
            continue
        if non_hub and name in learned_skills:
            # Non-hub clone: surfacing catalog (universal tier / clusters) is
            # hub-owned, so a freshly-extracted learned skill is legitimately
            # pending the hub's cataloging sweep (gc #101 / P-0104).
            logger.warning(
                "  WARN: learned skill %r not yet surfaced — pending hub "
                "catalog (non-hub clone)", name)
            warned += 1
        else:
            logger.warning(
                "  FAIL: skill %r is neither universal nor in any scenario "
                "cluster -- it will never be surfaced (add it to the universal "
                "tier or a _scenario_clusters.json cluster)", name)
            failed += 1

    # 16b. phantom
    for name in sorted(clustered - md_skills):
        logger.warning(
            "  FAIL: _scenario_clusters.json member %r not found in skill "
            "registry (phantom)", name)
        failed += 1

    if failed == 0:
        logger.info(
            "  [OK] %d md-skills all surfaced (universal or clustered)",
            len(md_skills))
    return failed, warned


# -------------- main audit --------------

def main(root: Path | None = None) -> int:
    """Run all checks; return 0 (healthy) or 1 (failures)."""
    if root is None:
        root = DEFAULT_ROOT
    knowledge_dir = root / "knowledge"
    if not knowledge_dir.is_dir():
        logger.error("[FATAL] knowledge/ directory not found at %s", knowledge_dir)
        return 1

    contract_fm = root / "contracts" / "knowledge_frontmatter_schema.md"
    if not contract_fm.is_file():
        logger.error("[FATAL] frontmatter contract not found at %s", contract_fm)
        return 1

    required_fields = parse_required_fields(contract_fm)
    status_enum = parse_enum(contract_fm, "### 3.1 `status`")
    owner_enum = parse_enum(contract_fm, "### 3.2 `owner`")
    briefing_enum = parse_enum(contract_fm, "### 3.3 `briefing`")
    # Schema v1.2.0+: `carrier_class` enum (transitional required field).
    # Auditor Checks 12-15 emit warnings only; v1.3.0 will flip to fail.
    try:
        carrier_class_enum = parse_enum(contract_fm, "### 3.4 `carrier_class`")
    except ValueError:
        carrier_class_enum = set()
    # Check 4 (owner-matches-category) needs the top INDEX.md owner map. A
    # single-agent / pre-index project legitimately has no top-level INDEX.md
    # (owner-category is a multi-agent ownership concept). When it is absent,
    # WARN and SKIP Check 4 rather than FATAL (which would permanently fail a
    # legitimate single-agent self-audit) or fail-all (an empty map would flag
    # every file's category as "unowned"). All other checks still run. P-0112.
    index_present = (knowledge_dir / "INDEX.md").is_file()
    if index_present:
        category_owners = parse_category_owner_map(knowledge_dir)
    else:
        logger.warning(
            "[WARN] knowledge/INDEX.md absent -- owner/category check "
            "(Check 4) skipped (single-agent or pre-index project)"
        )
        category_owners = {}

    logger.info(
        "Contract v1.2.0 loaded: required=%s status_enum=%s owner_enum=%s "
        "briefing_enum=%s carrier_class_enum=%s",
        required_fields, sorted(status_enum), sorted(owner_enum),
        sorted(briefing_enum), sorted(carrier_class_enum),
    )
    logger.info("Category owner map: %s\n", category_owners)

    md_files = sorted(
        p for p in knowledge_dir.rglob("*.md")
        if p.name not in SKIP_FILENAMES
        and not any(
            p.relative_to(knowledge_dir).as_posix().startswith(pre)
            for pre in SKIP_PATH_PREFIXES
        )
    )
    logger.info("Auditing %d entries in %s/\n", len(md_files), knowledge_dir.name)

    passed = 0
    failed = 0
    warnings = 0

    def fail(path: Path, msg: str) -> None:
        nonlocal failed
        logger.warning("  FAIL: %s -- %s", path.relative_to(root), msg)
        failed += 1

    def warn(path: Path, msg: str) -> None:
        nonlocal warnings
        logger.warning("  WARN: %s -- %s", path.relative_to(root), msg)
        warnings += 1

    # --- Check 1-5: frontmatter-driven checks ---
    logger.info("=== Checks 1-5: Contract compliance ===")
    for f in md_files:
        text = f.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        if fm is None:
            fail(f, "missing or malformed frontmatter")
            continue

        # Check 1: required fields
        missing = [field for field in required_fields if field not in fm]
        if missing:
            fail(f, f"missing required fields: {missing}")
            continue

        # Check 2: status enum
        status_val = fm["status"]
        if status_val not in status_enum:
            fail(f, f"status {status_val!r} not in enum {sorted(status_enum)}")
            continue

        # Check 3: owner enum
        owner_val = fm["owner"]
        if owner_val not in owner_enum:
            fail(f, f"owner {owner_val!r} not in enum {sorted(owner_enum)}")
            continue

        # Check 4: owner matches category (only when a top INDEX.md owner map
        # exists; absent -> skipped with a WARN at load time, see main(). P-0112)
        if index_present:
            rel = f.relative_to(knowledge_dir)
            category = rel.parts[0] if rel.parts else ""
            allowed = category_owners.get(category) if category in category_owners else None
            if allowed is None:
                fail(f, f"category {category!r} not found in top INDEX.md owner map")
                continue
            if owner_val not in allowed:
                fail(f, f"owner {owner_val!r} not permitted for category {category!r} (allowed: {allowed})")
                continue

        # Check 5: date format + updated >= created
        created_raw = fm["created"]
        updated_raw = fm["updated"]
        if not DATE_RE.match(created_raw):
            if created_raw != "unknown":
                fail(f, f"created {created_raw!r} not YYYY-MM-DD")
                continue
        if not DATE_RE.match(updated_raw):
            if updated_raw != "unknown":
                fail(f, f"updated {updated_raw!r} not YYYY-MM-DD")
                continue
        if DATE_RE.match(created_raw) and DATE_RE.match(updated_raw):
            if updated_raw < created_raw:
                fail(f, f"updated {updated_raw} < created {created_raw}")
                continue

        # Check 10: briefing enum (added v1.1.0; field is optional —
        # absence is valid and means "not in any Briefing-mode panel")
        if "briefing" in fm:
            briefing_val = fm["briefing"]
            if briefing_val not in briefing_enum:
                fail(f, f"briefing {briefing_val!r} not in enum {sorted(briefing_enum)}")
                continue

        passed += 1

    # --- Check 9: cross-reference link integrity (fail-level) ---
    # Every path referenced in supersedes / superseded_by / related /
    # blocks / blocked_by must resolve to an existing file. Targets are
    # tried at two locations, passing if EITHER exists:
    #   1. knowledge/<target> — inter-knowledge cross-ref (the common case)
    #   2. <repo_root>/<target> — implementation pointer (ADRs and domain
    #      docs naturally point to code / config paths like contracts/,
    #      tools/, .claude/ that describe the thing being documented)
    # Broken links silently rot until a reader follows them and 404s.
    logger.info("\n=== Check 9: Link integrity (cross-references) ===")
    known_paths = {str(f.relative_to(knowledge_dir).as_posix()) for f in md_files}
    for f in md_files:
        text = f.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        if fm is None:
            continue
        for field in LINK_FIELDS:
            if field not in fm:
                continue
            raw = fm[field]
            targets = _parse_link_value(raw)
            for target in targets:
                target_clean = target.rstrip("/")  # tolerate trailing slash on dir refs
                if target in known_paths or target_clean in known_paths:
                    continue
                # Fall back to repo-relative (implementation pointer)
                repo_target = root / target_clean
                if repo_target.exists():
                    continue
                fail(f, f"{field} references non-existent path {target!r}")

    # --- Check 6: file size ---
    logger.info("\n=== Check 6: File size (<%d lines) ===", LINE_LIMIT)
    for f in md_files:
        lines = len(f.read_text(encoding="utf-8").splitlines())
        if lines >= LINE_LIMIT:
            warn(f, f"{lines} lines (>={LINE_LIMIT})")

    # --- Check 7: INDEX.md sync ---
    logger.info("\n=== Check 7: INDEX.md sync (warn) ===")
    for subdir in sorted(knowledge_dir.iterdir()):
        if not subdir.is_dir():
            continue
        index_path = subdir / "INDEX.md"
        if not index_path.exists():
            continue
        index_content = index_path.read_text(encoding="utf-8")
        for f in md_files:
            if f.parent != subdir and not str(f.relative_to(knowledge_dir)).startswith(subdir.name + "/"):
                continue
            rel = f.relative_to(subdir).as_posix()
            if rel not in index_content and f.name not in index_content:
                warn(f, f"not referenced in {subdir.name}/INDEX.md")

    # --- Check 8: staleness ---
    logger.info("\n=== Check 8: Staleness (>%d days) ===", STALE_DAYS)
    today = datetime.now()
    stale_cutoff = today - timedelta(days=STALE_DAYS)
    for f in md_files:
        text = f.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        if fm is None or "updated" not in fm or not DATE_RE.match(fm["updated"]):
            continue
        updated = datetime.strptime(fm["updated"], "%Y-%m-%d")
        if updated < stale_cutoff:
            age = (today - updated).days
            warn(f, f"{age} days since update")

    # --- Check 11: skill tier bijection + INDEX.md freshness ---
    tiers_path = root / "knowledge" / "skills" / "_tiers.json"
    if tiers_path.is_file():
        logger.info("\n=== Check 11: Skill tier classification ===")
        tier_failed, tier_warned = _audit_skill_tiers(root, tiers_path)
        failed += tier_failed
        warnings += tier_warned

    # --- Check 16: skill scenario-surface coverage (P-0103 C, gc #100) ---
    clusters_path = root / "knowledge" / "skills" / "_scenario_clusters.json"
    if clusters_path.is_file():
        logger.info("\n=== Check 16: Skill scenario-surface coverage ===")
        sc_failed, sc_warned = _audit_scenario_coverage(
            root, clusters_path, tiers_path)
        failed += sc_failed
        warnings += sc_warned

    # --- Checks 12-15: carrier_class transitional (warn-only, P-0053 Phase 2) ---
    # Schema v1.2.0 introduced `carrier_class` as a transitional required
    # field. All four checks below emit WARN (never FAIL) until v1.3.0
    # flips them per `contracts/knowledge_frontmatter_schema.md` §8.2.
    if carrier_class_enum:
        logger.info("\n=== Checks 12-15: carrier_class (warn-only, v1.2.0 transitional) ===")
        cc_missing = 0
        cc_invalid = 0
        cc_path_mismatch = 0
        cc_autogen_missing = 0
        for f in md_files:
            text = f.read_text(encoding="utf-8")
            fm = parse_frontmatter(text)
            if fm is None:
                continue
            rel = f.relative_to(knowledge_dir)

            # Check 12: field present
            if "carrier_class" not in fm:
                warn(f, "carrier_class field missing (transitional v1.2.0)")
                cc_missing += 1
                continue

            cls = fm["carrier_class"]

            # Check 13: enum valid
            if cls not in carrier_class_enum:
                warn(f, f"carrier_class {cls!r} not in enum {sorted(carrier_class_enum)}")
                cc_invalid += 1
                continue

            # Check 14: path matches expected class
            expected = _expected_carrier_class(rel)
            if expected is None:
                warn(f, f"no carrier_class path mapping for top-dir {rel.parts[0]!r}")
                cc_path_mismatch += 1
            elif cls != expected:
                warn(f, f"carrier_class {cls!r} does not match expected {expected!r} for path {rel.as_posix()}")
                cc_path_mismatch += 1

            # Check 15: current-state files must contain autogen placeholder
            if cls == "current-state":
                if not any(marker in text for marker in AUTOGEN_PLACEHOLDER_MARKERS):
                    warn(f, "carrier_class=current-state but no autogen placeholder marker found")
                    cc_autogen_missing += 1

        logger.info(
            "  carrier_class transitional summary: missing=%d invalid=%d "
            "path_mismatch=%d autogen_missing=%d",
            cc_missing, cc_invalid, cc_path_mismatch, cc_autogen_missing,
        )

    # --- Summary ---
    logger.info("\n" + "=" * 50)
    logger.info("  Passed:   %d", passed)
    logger.info("  Failed:   %d", failed)
    logger.info("  Warnings: %d", warnings)
    logger.info("=" * 50)

    if failed > 0:
        logger.error("\nACTION REQUIRED: resolve %d failure(s) before proceeding.", failed)
        return 1
    logger.info("\nKnowledge base is healthy.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Knowledge base health audit (contract-driven)")
    parser.add_argument(
        "--root",
        type=str,
        default=None,
        help="Project root directory (default: this script's repo root)",
    )
    args = parser.parse_args()
    root_path = Path(args.root).resolve() if args.root else None
    sys.exit(main(root_path))
