# -*- coding: utf-8 -*-
"""User-friendly CLI for browsing the skill catalog by organizational tier.

Reads the same data as tools/build_skill_index.py (registry × _tiers.json)
but formats for terminal consumption rather than markdown. Use this when
you want to know "what skills can I use here?" without leaving the shell.

Examples:
    python tools/skill_catalog.py                 # all tiers, all types
    python tools/skill_catalog.py --tier universal
    python tools/skill_catalog.py --tier branch --type command
    python tools/skill_catalog.py --unclassified  # only the T0 bucket
    python tools/skill_catalog.py --grep wrap     # filter by name substring

This is read-only and side-effect free; for the markdown view consumed by
knowledge/ tooling, see tools/build_skill_index.py.
"""
import argparse
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from skills.discovery.registry import SkillRegistry  # noqa: E402

logger = logging.getLogger(__name__)

TIERS_PATH = PROJECT_ROOT / "knowledge" / "skills" / "_tiers.json"
TIER_ORDER = ["universal", "project", "branch", "unclassified"]
TIER_TITLES = {
    "universal": "Tier 1 — Universal",
    "project": "Tier 2 — Project-Universal (Trade Agent)",
    "branch": "Tier 3 — Branch / Business",
    "unclassified": "Unclassified",
}


def _load_tiers() -> dict:
    if not TIERS_PATH.is_file():
        raise FileNotFoundError(f"Missing tier map: {TIERS_PATH}")
    return json.loads(TIERS_PATH.read_text(encoding="utf-8"))


def _load_manifest() -> dict[str, dict]:
    reg = SkillRegistry(track_usage=False)
    reg.scan()
    return {
        s["name"]: s for s in reg.manifest()
        if s["source_type"] != "module"
    }


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
        description="Browse the skill catalog by organizational tier."
    )
    parser.add_argument(
        "--tier",
        choices=TIER_ORDER,
        default=None,
        help="Filter to a single tier (default: all).",
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
        "--unclassified",
        action="store_true",
        help="Shortcut: --tier=unclassified (show only awaiting-review).",
    )
    parser.add_argument(
        "--names-only",
        action="store_true",
        help="Print one skill name per line (no descriptions); useful for piping.",
    )
    args = parser.parse_args()

    tiers_data = _load_tiers()
    manifest = _load_manifest()

    selected_tier = "unclassified" if args.unclassified else args.tier
    tiers_to_show = [selected_tier] if selected_tier else TIER_ORDER

    grep_lower = args.grep.lower() if args.grep else None

    total = 0
    for tier_id in tiers_to_show:
        tier = tiers_data["tiers"].get(tier_id, {})
        names = sorted(tier.get("skills", []))
        if not names:
            if selected_tier:  # explicit ask for empty tier
                print(f"[{TIER_TITLES[tier_id]}]  (empty)")
            continue

        # Apply filters
        filtered = []
        for name in names:
            entry = manifest.get(name)
            if entry is None:
                # Phantom: print explicit marker so the bug is visible
                if not args.type and not grep_lower:
                    filtered.append({"name": name, "_phantom": True})
                continue
            if args.type and entry["source_type"] != args.type:
                continue
            if grep_lower and grep_lower not in name.lower():
                continue
            filtered.append(entry)

        if not filtered:
            continue

        if not args.names_only:
            desc = tier.get("description", "")
            print(f"\n[{TIER_TITLES[tier_id]}]  ({len(filtered)})")
            if desc:
                print(f"  {desc}")
            print()

        for entry in filtered:
            if args.names_only:
                print(entry["name"])
            elif entry.get("_phantom"):
                print(f"  ⚠ {entry['name']:<55} [PHANTOM — not in registry]")
            else:
                _print_skill(entry)
        total += len(filtered)

    if not args.names_only:
        print(f"\n{total} skill(s) matched.")
        print(
            "For usage stats: python -m skills.discovery.tracker --stats\n"
            "For full registry incl modules: "
            "python -m skills.discovery.registry --format table"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
