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


def refine_skill(name: str, additional_steps: list[str]) -> Path:
    """Append refinement steps to an existing learned skill.

    Hermes-inspired: skills self-improve during use. When a skill is
    invoked and the agent discovers additional useful steps, call this
    to append them.

    Args:
        name: Skill name (will be sanitized).
        additional_steps: New steps or notes to append.

    Returns:
        Path to the updated skill file.

    Raises:
        FileNotFoundError: If the skill does not exist.
    """
    safe_name = sanitize_name(name)
    target = _learned_dir() / f"{safe_name}.md"

    if not target.exists():
        raise FileNotFoundError(f"Skill not found: {target}")

    content = target.read_text(encoding="utf-8")

    # Update the 'updated' date in frontmatter
    today = date.today().isoformat()
    content = re.sub(r"updated: \d{4}-\d{2}-\d{2}", f"updated: {today}", content)

    # Append refinement section
    refinement = f"\n## Refinement ({today})\n\n"
    for i, step in enumerate(additional_steps, 1):
        refinement += f"{i}. {step}\n"

    content += refinement
    target.write_text(content, encoding="utf-8")
    logger.info("Skill refined: %s", safe_name)
    return target


def diff_and_refine(name: str) -> Optional[Path]:
    """Compare recorded session steps against a skill's documented workflow.

    Reads the skill document's Workflow section, compares it against
    the steps recorded in the tracker for this session, and auto-appends
    any new steps that aren't covered by the existing document.

    This is the Hermes "auto-diff" mechanism: skills self-improve during
    use by learning from the actual execution path.

    Args:
        name: Skill name to refine.

    Returns:
        Path to the updated skill file, or None if no refinement needed.
    """
    safe_name = sanitize_name(name)
    target = _learned_dir() / f"{safe_name}.md"

    if not target.exists():
        logger.info("Skill %s not in learned/ — skipping auto-refine", name)
        return None

    content = target.read_text(encoding="utf-8")

    # Extract existing workflow steps from the document
    existing_steps = _extract_workflow_steps(content)
    if not existing_steps:
        logger.info("No workflow section found in %s", name)
        return None

    # Get actual steps from tracker
    from governance_core.discovery.tracker import SkillTracker
    tracker = SkillTracker()
    session_steps = tracker.steps_taken_this_session()

    if not session_steps:
        return None

    actual_steps = [s["step"] for s in session_steps]

    # Find novel steps not covered by existing workflow
    novel = _find_novel_steps(existing_steps, actual_steps)

    if not novel:
        logger.info("No novel steps detected for %s — skill is up to date", name)
        return None

    # Append refinement
    logger.info("Auto-refining %s with %d novel steps", name, len(novel))
    result = refine_skill(name, novel)

    # Record refinement in tracker
    tracker.record_refinement(name)

    return result


def _extract_workflow_steps(content: str) -> list[str]:
    """Extract numbered workflow steps from a skill document.

    Args:
        content: Full Markdown content.

    Returns:
        List of step descriptions (without numbering).
    """
    steps = []
    in_workflow = False

    for line in content.split("\n"):
        stripped = line.strip()

        if stripped.startswith("## Workflow"):
            in_workflow = True
            continue
        if in_workflow and stripped.startswith("##"):
            break  # next section
        if in_workflow and re.match(r"^\d+\.\s+", stripped):
            step_text = re.sub(r"^\d+\.\s+", "", stripped)
            steps.append(step_text)

    return steps


def _find_novel_steps(existing: list[str], actual: list[str]) -> list[str]:
    """Find steps in actual execution not covered by existing workflow.

    Uses fuzzy matching: an actual step is "covered" if any existing
    step shares >= 50% of its significant words.

    Args:
        existing: Steps documented in the skill.
        actual: Steps recorded during execution.

    Returns:
        List of novel steps not covered by existing documentation.
    """
    def _significant_words(text: str) -> set[str]:
        """Extract significant words (length >= 3) from text."""
        return {
            w.lower()
            for w in re.findall(r"[a-zA-Z0-9_]+", text)
            if len(w) >= 3
        }

    existing_word_sets = [_significant_words(s) for s in existing]
    novel = []

    for step in actual:
        step_words = _significant_words(step)
        if not step_words:
            continue

        covered = False
        for ex_words in existing_word_sets:
            if not ex_words:
                continue
            overlap = len(step_words & ex_words) / max(len(step_words), 1)
            if overlap >= 0.5:
                covered = True
                break

        if not covered:
            novel.append(step)

    return novel


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
        "--auto-refine",
        type=str,
        default=None,
        metavar="SKILL_NAME",
        help="Auto-diff session steps against a skill and refine it",
    )
    args = parser.parse_args()

    if args.auto_refine:
        result = diff_and_refine(args.auto_refine)
        if result:
            print(f"[OK] Skill auto-refined: {result}")
        else:
            print(f"[SKIP] No refinement needed for: {args.auto_refine}")
        return

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
    )
    print(f"[OK] Skill extracted: {path}")


if __name__ == "__main__":
    main()
