# -*- coding: utf-8 -*-
"""Build knowledge/skills/INDEX.md from governance_core.discovery.registry, grouped by theme.

P-0118 retired the central knowledge/skills/_tiers.json: a skill's breadth now
lives in its own `theme:` frontmatter (universal | core-only | <agent>), the
field sync_infra already enforces for cross-clone routing. This builder derives
the index from that field -- no central tier file, no hand-authored taxonomy.

Determinism: same registry -> byte-identical output. We sort within each group
by name -- never by score, which is per-agent .usage.json state and would cause
cross-clone diff churn -- and emit no timestamp.

Python modules (source_type='module') are excluded; they are library code, not
workflows. INDEX.md links the registry CLI for the module view.

Usage:
    python tools/build_skill_index.py            # rebuild INDEX.md
    python tools/build_skill_index.py --check    # exit non-zero if stale
"""
import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from governance_core.discovery.registry import SkillRegistry  # noqa: E402

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")

INDEX_PATH = PROJECT_ROOT / "knowledge" / "skills" / "INDEX.md"

# Fixed groups render first (in this order); per-agent theme groups sort
# alphabetically between them and the trailing learned/unclassified buckets.
_HEAD_GROUPS = ("universal", "core-only")
_TAIL_GROUPS = ("learned", "unclassified")
_GROUP_TITLES = {
    "universal": "Universal",
    "core-only": "Core-only",
    "learned": "Learned (per-agent extractions)",
    "unclassified": "Unclassified (missing theme)",
}
SOURCE_TYPE_LABELS = {
    "command": "command",
    "guide": "guide",
    "learned": "learned",
}


def load_registry() -> list[dict]:
    """Scan registry and return manifest, filtering out Python modules."""
    reg = SkillRegistry(track_usage=False)
    reg.scan()
    return [s for s in reg.manifest() if s["source_type"] != "module"]


def _theme_group(entry: dict) -> str:
    """The index group a skill belongs to, derived from its theme.

    learned skills carry no theme (per-agent, not sync-routed) -> their own
    group; a non-learned skill with an empty theme is a defect -> 'unclassified'.
    """
    if entry["source_type"] == "learned":
        return "learned"
    return entry["theme"] or "unclassified"


def _group_title(group: str) -> str:
    """Human title for a theme group; per-agent themes render as 'Agent: <name>'."""
    return _GROUP_TITLES[group] if group in _GROUP_TITLES else f"Agent: {group}"


def _ordered_groups(present: set) -> list:
    """Deterministic group order: universal, core-only, <agents...>, learned, unclassified."""
    order = [g for g in _HEAD_GROUPS if g in present]
    agents = sorted(
        g for g in present
        if g not in _HEAD_GROUPS and g not in _TAIL_GROUPS
    )
    order.extend(agents)
    order.extend(g for g in _TAIL_GROUPS if g in present)
    return order


def _rel_path(abs_path: str) -> str:
    """Convert absolute file_path to repo-relative POSIX path."""
    p = Path(abs_path)
    try:
        return p.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def render(manifest: list[dict]) -> str:
    """Render INDEX.md content from the registry manifest, grouped by theme.

    Args:
        manifest: Registry manifest, modules excluded.

    Returns:
        Full INDEX.md text (deterministic: no timestamp, name-sorted).
    """
    grouped: dict[str, list[dict]] = {}
    for entry in manifest:
        grouped.setdefault(_theme_group(entry), []).append(entry)

    lines: list[str] = []
    lines.append("---")
    lines.append('display_title: "Skills - by theme"')
    lines.append("display_order: 16")
    lines.append("generated_by: tools/build_skill_index.py")
    lines.append("---")
    lines.append("")
    lines.append("# Skill Index")
    lines.append("")
    lines.append(
        "> Auto-generated. **Do not edit by hand** -- edit the skill's `theme:` "
        "frontmatter (universal | core-only | <agent>) or the skill body, then "
        "re-run `python tools/build_skill_index.py`."
    )
    lines.append(">")
    lines.append(
        f"> Source: `governance_core.discovery.registry` grouped by `theme`. "
        f"Total: {len(manifest)} workflow skills."
    )
    lines.append(">")
    lines.append(
        "> Live usage stats: `python -m governance_core.discovery.tracker --stats` "
        "(per-clone state, not in this file)."
    )
    lines.append(">")
    lines.append(
        "> Python skill modules (source_type=module) are library code, not "
        "workflows; not indexed here. See "
        "`python -m governance_core.discovery.registry --format table` for the full "
        "registry including modules."
    )
    lines.append("")

    for group in _ordered_groups(set(grouped)):
        lines.append(f"## {_group_title(group)}")
        lines.append("")

        by_type: dict[str, list[dict]] = {}
        for e in grouped[group]:
            by_type.setdefault(e["source_type"], []).append(e)

        for stype in ["command", "guide", "learned"]:
            if stype not in by_type:
                continue
            rows = sorted(by_type[stype], key=lambda e: e["name"])
            lines.append(f"### {SOURCE_TYPE_LABELS[stype].capitalize()}s "
                         f"({len(rows)})")
            lines.append("")
            for e in rows:
                rel = _rel_path(e["file_path"])
                desc = e["description"].strip().rstrip(".")
                # Truncate long descriptions for one-line bullet readability
                if len(desc) > 100:
                    desc = desc[:97] + "..."
                lines.append(f"- [`{e['name']}`]({rel}) - {desc}")
            lines.append("")

    lines.append("---")
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

    manifest = load_registry()
    new_content = render(manifest)

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
    n_groups = len({_theme_group(e) for e in manifest})
    logger.info(
        "[OK] Wrote %s (%d skills across %d theme group(s))",
        INDEX_PATH.relative_to(PROJECT_ROOT),
        len(manifest),
        n_groups,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
