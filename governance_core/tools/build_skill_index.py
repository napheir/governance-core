# -*- coding: utf-8 -*-
"""Build knowledge/skills/INDEX.md from governance_core.discovery.registry × _tiers.json.

Joins the runtime skill registry with the organizational-tier classification
in knowledge/skills/_tiers.json and emits a deterministic markdown index.

Determinism: same registry + same _tiers.json → byte-identical output. We
sort within each tier by (source_type, name) — never by score, because
score is per-agent .usage.json state and would cause cross-clone diff
churn.

Python modules (source_type='module') are excluded; they are library code,
not workflows. INDEX.md links the registry CLI for the module view.

Usage:
    python tools/build_skill_index.py            # rebuild INDEX.md
    python tools/build_skill_index.py --check    # exit non-zero if stale
"""
import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from governance_core.discovery.registry import SkillRegistry  # noqa: E402

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")

TIERS_PATH = PROJECT_ROOT / "knowledge" / "skills" / "_tiers.json"
INDEX_PATH = PROJECT_ROOT / "knowledge" / "skills" / "INDEX.md"

TIER_ORDER = ["universal", "project", "branch", "unclassified"]
TIER_TITLES = {
    "universal": "Tier 1 — Universal",
    "project": "Tier 2 — Project-Universal (Trade Agent)",
    "branch": "Tier 3 — Branch / Business",
    "unclassified": "Unclassified",
}
SOURCE_TYPE_LABELS = {
    "command": "command",
    "guide": "guide",
    "learned": "learned",
}


def load_tiers() -> dict:
    """Load _tiers.json; fail loud if missing or malformed."""
    if not TIERS_PATH.is_file():
        raise FileNotFoundError(f"Missing tier map: {TIERS_PATH}")
    return json.loads(TIERS_PATH.read_text(encoding="utf-8"))


def load_registry() -> list[dict]:
    """Scan registry and return manifest, filtering out Python modules."""
    reg = SkillRegistry(track_usage=False)
    reg.scan()
    return [s for s in reg.manifest() if s["source_type"] != "module"]


def _rel_path(abs_path: str) -> str:
    """Convert absolute file_path to repo-relative POSIX path."""
    p = Path(abs_path)
    try:
        return p.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def render(tiers_data: dict, manifest: list[dict]) -> str:
    """Render INDEX.md content from tiers data + registry manifest.

    Args:
        tiers_data: Parsed _tiers.json content.
        manifest: Registry manifest, modules excluded.

    Returns:
        Full INDEX.md text.
    """
    by_name = {s["name"]: s for s in manifest}

    lines: list[str] = []
    lines.append("---")
    lines.append('display_title: "Skills — Organizational Tiers"')
    lines.append("display_order: 16")
    lines.append("generated_by: tools/build_skill_index.py")
    lines.append("---")
    lines.append("")
    lines.append("# Skill Index")
    lines.append("")
    lines.append(
        "> Auto-generated. **Do not edit by hand** — edit "
        "`knowledge/skills/_tiers.json` or the skill's source file instead, "
        "then re-run `python tools/build_skill_index.py`."
    )
    lines.append(">")
    lines.append(
        f"> Source: `governance_core.discovery.registry` × `_tiers.json` "
        f"(version {tiers_data.get('version', '?')}). "
        f"Total: {len(manifest)} workflow skills classified."
    )
    lines.append(">")
    lines.append(
        "> Live usage stats: `python -m governance_core.discovery.tracker --stats` "
        "(per-clone state, not in this file)."
    )
    lines.append(">")
    lines.append(
        "> Python skill modules (source_type=module) are library code, not "
        "workflows; not classified here. See "
        "`python -m governance_core.discovery.registry --format table` for the full "
        "registry including modules."
    )
    lines.append("")

    for tier_id in TIER_ORDER:
        tier = tiers_data["tiers"].get(tier_id, {})
        tier_skills = tier.get("skills", [])
        tier_desc = tier.get("description", "")

        if tier_id == "unclassified" and not tier_skills:
            continue  # skip empty unclassified to keep INDEX.md tidy

        lines.append(f"## {TIER_TITLES[tier_id]}")
        lines.append("")
        if tier_desc:
            lines.append(f"_{tier_desc}_")
            lines.append("")

        if not tier_skills:
            lines.append("*(no skills in this tier)*")
            lines.append("")
            continue

        # Within tier: group by source_type for clarity, sorted alpha by name.
        by_type: dict[str, list[dict]] = {}
        for name in sorted(tier_skills):
            entry = by_name.get(name)
            if entry is None:
                # Phantom entry in _tiers.json — let audit catch this; render
                # a visible placeholder so the bug is loud.
                lines.append(
                    f"- ⚠ `{name}` — **NOT FOUND in registry** "
                    f"(phantom entry in `_tiers.json`)"
                )
                continue
            by_type.setdefault(entry["source_type"], []).append(entry)

        for stype in ["command", "guide", "learned"]:
            if stype not in by_type:
                continue
            entries = by_type[stype]
            lines.append(f"### {SOURCE_TYPE_LABELS[stype].capitalize()}s "
                         f"({len(entries)})")
            lines.append("")
            for e in entries:
                rel = _rel_path(e["file_path"])
                desc = e["description"].strip().rstrip(".")
                # Truncate long descriptions for one-line bullet readability
                if len(desc) > 100:
                    desc = desc[:97] + "..."
                lines.append(f"- [`{e['name']}`]({rel}) — {desc}")
            lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append(f"_Last generated: {date.today().isoformat()}_")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build skill INDEX.md")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if INDEX.md is stale (do not write).",
    )
    args = parser.parse_args()

    tiers_data = load_tiers()
    manifest = load_registry()
    new_content = render(tiers_data, manifest)

    if args.check:
        if not INDEX_PATH.exists():
            logger.error("INDEX.md missing at %s", INDEX_PATH)
            return 1
        current = INDEX_PATH.read_text(encoding="utf-8")
        if current != new_content:
            logger.error(
                "INDEX.md is stale (does not match builder output). "
                "Run: python tools/build_skill_index.py"
            )
            return 1
        logger.info("[OK] INDEX.md is up to date")
        return 0

    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(new_content, encoding="utf-8")
    logger.info(
        "[OK] Wrote %s (%d skills across %d tiers)",
        INDEX_PATH.relative_to(PROJECT_ROOT),
        len(manifest),
        sum(1 for t in TIER_ORDER if tiers_data["tiers"].get(t, {}).get("skills")),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
