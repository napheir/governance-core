# -*- coding: utf-8 -*-
"""Skill auto-extractor (Hermes-inspired).

Analyzes a workflow description and generates a reusable skill document
in .claude/skills/learned/. The extracted skill follows the project's
skill template format and can be discovered by the SkillRegistry.

This module is invoked by the /extract-skill slash command or directly:

    python -m governance_core.discovery.extractor --name "strangle-pipeline" \\
        --description "End-to-end strangle signal generation" \\
        --steps "1. Check OpenD|2. Load config|3. Generate indicators|4. Train model"

The generated skill is written to .claude/skills/learned/<name>.md and
immediately discoverable by the SkillRegistry at L0.
"""
import logging
import re
from datetime import date
from pathlib import Path
from typing import Optional

from governance_core.discovery import resolve_project_root

logger = logging.getLogger(__name__)


def _learned_dir() -> Path:
    """Return the per-agent learned-skills directory.

    Each agent clone owns its own ``.claude/skills/learned/`` so extracted
    skills live next to the session they were produced from.
    """
    return resolve_project_root(__file__) / ".claude" / "skills" / "learned"


def sanitize_name(name: str) -> str:
    """Convert a human-friendly name to a valid kebab-case filename.

    Args:
        name: Human-readable skill name (e.g. "Strangle Pipeline Run").

    Returns:
        Kebab-case filename stem (e.g. "strangle-pipeline-run").
    """
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9\s-]", "", name)
    name = re.sub(r"[\s_]+", "-", name)
    name = re.sub(r"-+", "-", name)
    return name.strip("-")


def build_skill_document(
    name: str,
    description: str,
    steps: list[str],
    preconditions: Optional[list[str]] = None,
    outputs: Optional[list[str]] = None,
    tags: Optional[list[str]] = None,
    notes: Optional[list[str]] = None,
    layer: str = "candidate-common",
) -> str:
    """Build a skill document in project-standard Markdown format.

    Args:
        name: Skill name (kebab-case).
        description: One-line description.
        steps: Ordered list of workflow steps.
        preconditions: Optional pre-checks before running.
        outputs: Optional list of output artifacts/paths.
        tags: Optional tags for registry discovery.
        notes: Optional notes or caveats.
        layer: Common-layer classification (P-0065) -- "candidate-common"
            (generic, eligible for uplink to governance-core) or "business"
            (project-specific). Defaults to "candidate-common" when unsure.

    Returns:
        Complete Markdown skill document content.
    """
    tag_str = ", ".join(tags) if tags else "learned, workflow"
    today = date.today().isoformat()

    sections = []

    # Frontmatter
    sections.append(f"""---
name: {name}
description: "{description}"
type: learned
layer: {layer}
tags: [{tag_str}]
created: {today}
updated: {today}
---""")

    # Title
    sections.append(f"\n# {name}\n")
    sections.append(f"{description}\n")

    # Preconditions
    if preconditions:
        sections.append("## Preconditions\n")
        for i, pre in enumerate(preconditions, 1):
            sections.append(f"{i}. {pre}")
        sections.append("")

    # Workflow
    sections.append("## Workflow\n")
    for i, step in enumerate(steps, 1):
        sections.append(f"{i}. {step}")
    sections.append("")

    # Outputs
    if outputs:
        sections.append("## Outputs\n")
        for out in outputs:
            sections.append(f"- {out}")
        sections.append("")

    # Notes
    if notes:
        sections.append("## Notes\n")
        for note in notes:
            sections.append(f"- {note}")
        sections.append("")

    return "\n".join(sections)


def extract_skill(
    name: str,
    description: str,
    steps: list[str],
    preconditions: Optional[list[str]] = None,
    outputs: Optional[list[str]] = None,
    tags: Optional[list[str]] = None,
    notes: Optional[list[str]] = None,
    overwrite: bool = False,
    layer: str = "candidate-common",
) -> Path:
    """Extract a reusable skill document and write to learned/ directory.

    Args:
        name: Human-readable skill name.
        description: One-line description.
        steps: Ordered workflow steps.
        preconditions: Optional pre-checks.
        outputs: Optional output artifacts.
        tags: Optional tags.
        notes: Optional notes.
        overwrite: If True, overwrite existing skill with same name.
        layer: Common-layer classification (P-0065) -- "candidate-common"
            or "business". Written to the skill frontmatter.

    Returns:
        Path to the generated skill file.

    Raises:
        FileExistsError: If skill already exists and overwrite is False.
    """
    safe_name = sanitize_name(name)
    learned_dir = _learned_dir()
    learned_dir.mkdir(parents=True, exist_ok=True)
    target = learned_dir / f"{safe_name}.md"

    if target.exists() and not overwrite:
        raise FileExistsError(
            f"Skill already exists: {target}. Use --overwrite to replace."
        )

    content = build_skill_document(
        name=safe_name,
        description=description,
        steps=steps,
        preconditions=preconditions,
        outputs=outputs,
        tags=tags,
        notes=notes,
        layer=layer,
    )

    target.write_text(content, encoding="utf-8")
    logger.info("Skill extracted: %s -> %s", safe_name, target)

    # Close the loop with the tracker so should_extract()'s "already extracted
    # today" branch (tracker.py:319-322) becomes effective and extractions_total
    # reflects reality. Silent on failure — tracking is opportunistic, never
    # critical path (matches .claude/hooks/skill-usage-tracker.py contract).
    try:
        from governance_core.discovery.tracker import SkillTracker
        SkillTracker().record_extraction(safe_name)
    except Exception:
        logger.warning("record_extraction failed for %s — extraction itself succeeded", safe_name)

    return target


def main() -> None:
    """CLI entry point for skill extraction."""
    import argparse

    parser = argparse.ArgumentParser(description="Skill Auto-Extractor")
    parser.add_argument("--name", required=True, help="Skill name")
    parser.add_argument("--description", required=True, help="One-line description")
    parser.add_argument(
        "--steps",
        required=True,
        help="Workflow steps separated by '|'",
    )
    parser.add_argument(
        "--preconditions",
        default=None,
        help="Precondition checks separated by '|'",
    )
    parser.add_argument(
        "--outputs",
        default=None,
        help="Output artifacts separated by '|'",
    )
    parser.add_argument(
        "--tags",
        default=None,
        help="Tags separated by ','",
    )
    parser.add_argument(
        "--notes",
        default=None,
        help="Notes separated by '|'",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing skill",
    )
    parser.add_argument(
        "--layer",
        choices=["candidate-common", "business"],
        default="candidate-common",
        help="P-0065 common-layer classification (default: candidate-common)",
    )
    args = parser.parse_args()

    steps = [s.strip() for s in args.steps.split("|") if s.strip()]
    preconditions = (
        [s.strip() for s in args.preconditions.split("|") if s.strip()]
        if args.preconditions else None
    )
    outputs = (
        [s.strip() for s in args.outputs.split("|") if s.strip()]
        if args.outputs else None
    )
    tags = (
        [t.strip() for t in args.tags.split(",") if t.strip()]
        if args.tags else None
    )
    notes = (
        [s.strip() for s in args.notes.split("|") if s.strip()]
        if args.notes else None
    )

    path = extract_skill(
        name=args.name,
        description=args.description,
        steps=steps,
        preconditions=preconditions,
        outputs=outputs,
        tags=tags,
        notes=notes,
        overwrite=args.overwrite,
        layer=args.layer,
    )
    print(f"[OK] Skill extracted: {path}")


if __name__ == "__main__":
    main()
