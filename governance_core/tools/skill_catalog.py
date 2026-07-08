# -*- coding: utf-8 -*-
"""User-friendly CLI for browsing the skill catalog by theme.

Reads the same data as tools/build_skill_index.py (the registry, grouped by each
skill's `theme:` frontmatter -- universal | core-only | <agent>) but formats for
terminal consumption rather than markdown. Use this when you want to know "what
skills can I use here?" without leaving the shell.

Examples:
    python tools/skill_catalog.py                      # all groups, all types
    python tools/skill_catalog.py --group universal
    python tools/skill_catalog.py --group core-only --type command
    python tools/skill_catalog.py --grep wrap          # filter by name substring

This is read-only and side-effect free; for the markdown view consumed by
knowledge/ tooling, see tools/build_skill_index.py.
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

_HEAD_GROUPS = ("universal", "core-only")
_TAIL_GROUPS = ("learned", "unclassified")
_GROUP_TITLES = {
    "universal": "Universal",
    "core-only": "Core-only",
    "learned": "Learned (per-agent extractions)",
    "unclassified": "Unclassified (missing theme)",
}


def _load_manifest() -> list[dict]:
    reg = SkillRegistry(track_usage=False)
    reg.scan()
    return [s for s in reg.manifest() if s["source_type"] != "module"]


def _theme_group(entry: dict) -> str:
    """Index group of a skill, derived from its theme (see build_skill_index)."""
    if entry["source_type"] == "learned":
        return "learned"
    return entry["theme"] or "unclassified"


def _group_title(group: str) -> str:
    """Human title; per-agent themes render as 'Agent: <name>'."""
    return _GROUP_TITLES[group] if group in _GROUP_TITLES else f"Agent: {group}"


def _ordered_groups(present: set) -> list:
    """universal, core-only, <agents...>, learned, unclassified (present only)."""
    order = [g for g in _HEAD_GROUPS if g in present]
    agents = sorted(g for g in present
                    if g not in _HEAD_GROUPS and g not in _TAIL_GROUPS)
    order.extend(agents)
    order.extend(g for g in _TAIL_GROUPS if g in present)
    return order


def _print_skill(entry: dict, indent: int = 2) -> None:
    """Print a single skill row in a 2-line block."""
    name = entry["name"]
    stype = entry["source_type"]
    desc = entry["description"].strip().rstrip(".")
    if len(desc) > 92:
        desc = desc[:89] + "..."
    print(f"{' ' * indent}{name:<55} [{stype}]")
    print(f"{' ' * indent}  {desc}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Browse the skill catalog by theme."
    )
    parser.add_argument(
        "--group",
        default=None,
        help="Filter to a single theme group "
             "(universal | core-only | <agent> | learned | unclassified).",
    )
    parser.add_argument(
        "--type",
        choices=["command", "guide", "learned"],
        default=None,
        help="Filter to a single source type (default: all).",
    )
    parser.add_argument(
        "--grep",
        type=str,
        default=None,
        help="Filter by case-insensitive substring match on skill name.",
    )
    parser.add_argument(
        "--names-only",
        action="store_true",
        help="Print one skill name per line (no descriptions); useful for piping.",
    )
    args = parser.parse_args()

    manifest = _load_manifest()
    grouped: dict[str, list[dict]] = {}
    for entry in manifest:
        grouped.setdefault(_theme_group(entry), []).append(entry)

    grep_lower = args.grep.lower() if args.grep else None
    groups_to_show = ([args.group] if args.group
                      else _ordered_groups(set(grouped)))

    total = 0
    for group in groups_to_show:
        entries = grouped[group] if group in grouped else []
        filtered = []
        for entry in sorted(entries, key=lambda e: e["name"]):
            if args.type and entry["source_type"] != args.type:
                continue
            if grep_lower and grep_lower not in entry["name"].lower():
                continue
            filtered.append(entry)

        if not filtered:
            if args.group:  # explicit ask for an empty / unknown group
                print(f"[{_group_title(group)}]  (empty)")
            continue

        if not args.names_only:
            print(f"\n[{_group_title(group)}]  ({len(filtered)})")
            print()

        for entry in filtered:
            if args.names_only:
                print(entry["name"])
            else:
                _print_skill(entry)
        total += len(filtered)

    if not args.names_only:
        print(f"\n{total} skill(s) matched.")
        print(
            "For usage stats: python -m governance_core.discovery.tracker --stats\n"
            "For full registry incl modules: "
            "python -m governance_core.discovery.registry --format table"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
