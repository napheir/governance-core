# -*- coding: utf-8 -*-
"""Skill registry with progressive loading (Hermes-inspired).

Scans all skill sources (Python modules, slash commands, skill guides,
learned skills) and builds a two-level index:

  Level 0 (L0): name + description + type + tags  (always loaded)
  Level 1 (L1): full content                       (loaded on demand)

This keeps token budgets low when agents need to browse available skills,
while still allowing deep access when a specific skill is invoked.

Usage:
    from governance_core.discovery.registry import SkillRegistry

    registry = SkillRegistry()
    registry.scan()

    # L0: list all skills with metadata
    manifest = registry.manifest()

    # L1: load full content for a specific skill
    content = registry.load("futu-check")

    # Save manifest to disk
    registry.save_manifest("artifacts/tests/skill_manifest.json")

CLI:
    python -m governance_core.discovery.registry [--format json|table] [--output PATH]
"""
import json
import logging
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from governance_core.discovery import resolve_project_root

logger = logging.getLogger(__name__)

# Frontmatter regex: matches YAML between --- delimiters
_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(.*?)\n---\s*\n",
    re.DOTALL,
)


@dataclass
class SkillEntry:
    """Level 0 metadata for a single skill."""

    name: str
    description: str
    source_type: str  # "command", "guide", "learned", "module"
    file_path: str
    tags: list = field(default_factory=list)
    trigger: str = ""  # e.g. "/audit", "python -m skills.start_futu_opend"
    score: float = 0.0  # weighted score from tracker (frequency + recency)
    theme: str = ""  # sync/reuse breadth: "universal"|"core-only"|"<agent>"|""; P-0118 also feeds injection

    def to_dict(self) -> dict:
        """Serialize to dict for JSON output."""
        return asdict(self)


class SkillRegistry:
    """Two-level skill registry with progressive loading and weighted scoring."""

    def __init__(
        self,
        project_root: Optional[Path] = None,
        track_usage: bool = True,
    ) -> None:
        """Initialize registry.

        Args:
            project_root: Override project root (for testing).
            track_usage: If True, auto-record L1 loads in tracker.
        """
        self._root = project_root or resolve_project_root(__file__)
        self._entries: dict[str, SkillEntry] = {}
        self._track_usage = track_usage
        self._tracker = None  # lazy-loaded
        # P-0069: all skill sources are install-managed under the consuming
        # project's .claude/. The machinery ships in the governance-core
        # package; the skills it scans are per-project (no shared sibling
        # clone, no CODE_ROOT).
        self._sources = {
            "command": self._root / ".claude" / "commands",
            "guide": self._root / ".claude" / "skills",
            "learned": self._root / ".claude" / "skills" / "learned",
            "module": self._root / ".claude" / "skills",
        }

    def _get_tracker(self):
        """Lazy-load the tracker to avoid circular imports.

        Returns:
            SkillTracker instance.
        """
        if self._tracker is None:
            from governance_core.discovery.tracker import SkillTracker
            # Bind the tracker to THIS registry's root so the usage funnel
            # (record_surfaced/use) lands at the project being scanned, not
            # wherever resolve_project_root(__file__) happens to point. For the
            # default registry (no project_root) this is identical to before;
            # for an explicit project_root (hook/consumer/tests) it is correct.
            self._tracker = SkillTracker(
                tracker_path=self._root / ".claude" / "skills"
                / "learned" / ".usage.json"
            )
        return self._tracker

    def scan(self) -> int:
        """Scan all skill sources and build L0 index with weighted scores.

        Returns:
            Number of skills discovered.
        """
        self._entries.clear()
        self._scan_markdown_skills("command")
        self._scan_markdown_skills("guide")
        self._scan_markdown_skills("learned")
        self._scan_python_modules()

        # Apply weighted scores from tracker
        if self._track_usage:
            try:
                scores = self._get_tracker().weighted_scores()
                for name, score in scores.items():
                    if name in self._entries:
                        self._entries[name].score = round(score, 3)
            except Exception as e:
                logger.debug("Tracker scoring unavailable: %s", e)

        logger.info("Skill registry: %d skills discovered", len(self._entries))
        return len(self._entries)

    def manifest(self) -> list[dict]:
        """Return L0 manifest sorted by weighted score (desc), then name.

        Skills with usage history float to the top. Unused skills
        are sorted alphabetically within their score tier.

        Returns:
            List of skill metadata dicts.
        """
        return [
            e.to_dict()
            for e in sorted(
                self._entries.values(),
                key=lambda e: (-e.score, e.name),
            )
        ]

    def load(self, name: str) -> Optional[str]:
        """Load L1 content for a specific skill (full file content).

        Automatically records the usage in the tracker for weighted
        scoring and session-level skill tracking.

        Args:
            name: Skill name.

        Returns:
            Full file content, or None if not found.
        """
        entry = self._entries.get(name)
        if entry is None:
            logger.warning("Skill not found: %s", name)
            return None
        path = Path(entry.file_path)
        if not path.exists():
            logger.error("Skill file missing: %s", path)
            return None

        # Auto-track L1 load
        if self._track_usage:
            try:
                self._get_tracker().record_use(name)
            except Exception as e:
                logger.debug("Usage tracking failed: %s", e)

        return path.read_text(encoding="utf-8")

    def get(self, name: str) -> Optional[SkillEntry]:
        """Get L0 entry for a skill.

        Args:
            name: Skill name.

        Returns:
            SkillEntry or None.
        """
        return self._entries.get(name)

    def save_manifest(self, output_path: str) -> None:
        """Write L0 manifest to a JSON file.

        Args:
            output_path: File path for JSON output.
        """
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(self.manifest(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Manifest written to %s", out)

    def manifest_for_injection(self, source_types: list) -> list[dict]:
        """Return L0 entries filtered by source_type, sorted by score then name.

        Used by SessionStart hooks to inject only skill classes that the
        Claude Code harness does NOT auto-list (learned + guide). Commands
        are excluded — harness already injects them via system-reminder
        and re-injecting wastes tokens (see skill-injection-tiers.md).
        """
        return [
            e.to_dict()
            for e in sorted(
                (e for e in self._entries.values() if e.source_type in source_types),
                key=lambda e: (-e.score, e.name),
            )
        ]

    def summary_table(self) -> str:
        """Return a formatted table of all skills (for CLI output).

        Returns:
            ASCII table string.
        """
        lines = [
            f"{'Name':<30} {'Type':<10} {'Score':>5}  {'Description'}",
            f"{'-'*30} {'-'*10} {'-'*5}  {'-'*44}",
        ]
        for entry in sorted(self._entries.values(), key=lambda e: (-e.score, e.source_type, e.name)):
            desc = entry.description[:44] if entry.description else "(no description)"
            score_str = f"{entry.score:.1f}" if entry.score > 0 else "  -"
            lines.append(f"{entry.name:<30} {entry.source_type:<10} {score_str:>5}  {desc}")
        lines.append(f"\nTotal: {len(self._entries)} skills")
        return "\n".join(lines)

    # -- internal scanning methods --

    def _scan_markdown_skills(self, source_type: str) -> None:
        """Scan a directory of markdown skill files.

        Args:
            source_type: One of "command", "guide", "learned".
        """
        source_dir = self._sources[source_type]
        if not source_dir.exists():
            return

        for md_file in sorted(source_dir.glob("*.md")):
            if md_file.name.startswith("_"):
                continue  # skip templates
            name = md_file.stem
            content = md_file.read_text(encoding="utf-8")
            desc, tags, theme = self._extract_metadata(content)

            if not desc:
                # Fallback: use first non-empty, non-heading line
                desc = self._extract_first_line_desc(content)

            trigger = f"/{name}" if source_type == "command" else ""

            self._entries[name] = SkillEntry(
                name=name,
                description=desc,
                source_type=source_type,
                file_path=str(md_file),
                tags=tags,
                trigger=trigger,
                theme=theme,
            )

    def _scan_python_modules(self) -> None:
        """Scan Python skill modules for docstrings."""
        module_dir = self._sources["module"]
        if not module_dir.exists():
            return

        for py_file in sorted(module_dir.rglob("*.py")):
            if py_file.name == "__init__.py":
                continue
            # Skip the discovery module itself
            if "discovery" in py_file.parts:
                continue

            rel = py_file.relative_to(module_dir)
            # Module name: skills.concurrency.task_partitioner -> concurrency/task_partitioner
            name = str(rel.with_suffix("")).replace("\\", "/")
            desc = self._extract_py_docstring(py_file)
            trigger = f"python -m skills.{str(rel.with_suffix('')).replace(chr(92), '.').replace('/', '.')}"

            self._entries[name] = SkillEntry(
                name=name,
                description=desc,
                source_type="module",
                file_path=str(py_file),
                tags=["python"],
                trigger=trigger,
            )

    @staticmethod
    def _extract_metadata(content: str) -> tuple[str, list, str]:
        """Extract description, tags and theme from YAML frontmatter.

        Args:
            content: Full markdown content.

        Returns:
            Tuple of (description, tags, theme). `theme` is the raw
            sync/reuse-breadth value ("universal"|"core-only"|"<agent>") that
            sync_infra already enforces on shared skills, or "" when absent
            (e.g. a learned skill). P-0118 also reads it to derive the
            SessionStart universal-injection pool; enum validation stays with
            sync_infra / the auditor, not this reader.
        """
        match = _FRONTMATTER_RE.match(content)
        if not match:
            return "", [], ""

        frontmatter = match.group(1)
        desc = ""
        tags = []
        theme = ""

        for line in frontmatter.split("\n"):
            line = line.strip()
            if line.startswith("description:"):
                desc = line.split(":", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("tags:"):
                tag_str = line.split(":", 1)[1].strip()
                # Handle [tag1, tag2] format
                tag_str = tag_str.strip("[]")
                tags = [t.strip().strip('"').strip("'") for t in tag_str.split(",") if t.strip()]
            elif line.startswith("theme:"):
                theme = line.split(":", 1)[1].strip().strip('"').strip("'")

        return desc, tags, theme

    @staticmethod
    def _extract_first_line_desc(content: str) -> str:
        """Extract description from first meaningful line of content.

        Args:
            content: Full file content.

        Returns:
            First non-heading, non-empty line (truncated to 120 chars).
        """
        # Skip frontmatter
        body = _FRONTMATTER_RE.sub("", content)
        for line in body.split("\n"):
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("---"):
                continue
            return line[:120]
        return ""

    @staticmethod
    def _extract_py_docstring(py_file: Path) -> str:
        """Extract module-level docstring from a Python file.

        Args:
            py_file: Path to Python file.

        Returns:
            First line of docstring, or empty string.
        """
        try:
            content = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return ""

        # Find first triple-quoted string
        for marker in ('"""', "'''"):
            idx = content.find(marker)
            if idx == -1:
                continue
            end = content.find(marker, idx + 3)
            if end == -1:
                continue
            docstring = content[idx + 3:end].strip()
            # Return first line only
            first_line = docstring.split("\n")[0].strip()
            return first_line

        return ""


def _emit_injection(registry: "SkillRegistry") -> None:
    """Write Tier A (learned) + Tier B (guide) skill manifest to stdout.

    Used by SessionStart hooks. Commands are deliberately excluded —
    Claude Code harness already lists them via system-reminder, so
    re-injecting them is a redundant token cost (see
    .claude/skills/skill-injection-tiers.md for the design rationale).
    """
    import sys as _sys
    learned = registry.manifest_for_injection(["learned"])
    guides = registry.manifest_for_injection(["guide"])
    if not learned and not guides:
        return
    # Record path-A surfacing (best-effort; must never break injection output).
    try:
        names = [e["name"] for e in learned] + [e["name"] for e in guides]
        registry._get_tracker().record_surfaced(names)
    except Exception:  # noqa: BLE001 - tracking is a diagnostic, not critical
        pass
    lines = [
        "[Skills (L0)] Auto-discovered learned + guide skills "
        "(body lazy via Skill tool):"
    ]
    if learned:
        lines.append("  Learned (this agent's session extractions):")
        for e in learned:
            desc = (e["description"] or "(no description)")[:80]
            lines.append(f"    {e['name']:<40}  {desc}")
    if guides:
        lines.append("  Guides (cross-agent design principles):")
        for e in guides:
            desc = (e["description"] or "(no description)")[:80]
            lines.append(f"    {e['name']:<40}  {desc}")
    lines.append(
        "  Full manifest: python -m governance_core.discovery.registry --format table"
    )
    _sys.stdout.write("\n".join(lines) + "\n")


# Bounded universal-tier injection limit (re-balances prefix_cost C3 without
# re-introducing the full manifest dump). Scenario-cluster bodies stay lazy.
_UNIVERSAL_INJECTION_LIMIT = 10


def emit_bounded_injection(registry: "SkillRegistry") -> Optional[str]:
    """Return a bounded SessionStart skill menu, or None if nothing to surface.

    Issue #100 / P-0103 part A; universal derivation reworked by P-0118 to read
    the pre-existing per-skill ``theme:`` frontmatter (sync_infra's breadth
    field) instead of a central ``_tiers.json``. Re-balances
    prefix_cost_optimization.md C3 (counts-only) with a BOUNDED names menu so an
    agent can actually consult learned skills:

      - the universal-injection pool = every ``learned`` skill (this agent's own
        session extractions) plus every ``guide`` whose frontmatter
        ``theme == "universal"`` (cross-agent shared design principles present on
        every clone). Rendered as ``name + 1-line desc``, capped at
        ``_UNIVERSAL_INJECTION_LIMIT``. ``theme: core-only`` / ``theme: <agent>``
        guides are niche and reach the surface via a scenario cluster, not the
        every-session pool;
      - a compact scenario-cluster map (``knowledge/skills/_scenario_clusters.json``)
        ``cluster -> member names``; cluster BODIES stay lazy (Skill tool).

    Records path-A surfacing via the usage funnel (``record_surfaced``).
    Returns ``None`` when neither a universal pool nor any cluster is authored
    (e.g. a hub with 0 learned + 0 theme:universal skills) so the caller falls
    back to the counts-only summary. gc ships this reader + the schema doc
    (``knowledge/governance/skill-scenario-clusters.md``); P-0118 retires the
    central ``_tiers.json`` authoring in favour of ``theme``.
    """
    skills_dir = registry._root / "knowledge" / "skills"
    clusters_path = skills_dir / "_scenario_clusters.json"

    def _load(path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return {}

    def _field(d, key, default):
        # Membership test, not a defaulted dict lookup (Art.4): this parses a
        # consumer-authored data file, not config, but the guard is textual.
        return d[key] if isinstance(d, dict) and key in d else default

    # learned + guide entries carry per-skill `theme` + description;
    # manifest_for_injection is already sorted by (-score, name). Every entry
    # dict carries source_type + theme (asdict), so `e[...]` is a plain lookup,
    # not a defaulted `.get` (Art.4).
    inject_entries = registry.manifest_for_injection(["learned", "guide"])
    by_name = {e["name"]: (e["description"] or "") for e in inject_entries}

    # Universal pool from the pre-existing `theme` field (P-0118): a learned
    # skill is always this agent's own; a guide is shared-universal when
    # sync_infra themed it `universal`. No central `_tiers.json` read.
    universal = [e["name"] for e in inject_entries
                 if e["source_type"] == "learned" or e["theme"] == "universal"]

    clusters: dict = {}
    if clusters_path.exists():
        clusters = _field(_load(clusters_path), "clusters", {})

    if not universal and not clusters:
        return None

    surfaced: list = []
    lines = [
        "[Skills (L0)] Consult before re-deriving "
        "(bodies lazy via Skill tool):"
    ]
    if universal:
        lines.append("  Universal (every session):")
        for name in universal[:_UNIVERSAL_INJECTION_LIMIT]:
            desc = (by_name[name] if name in by_name else "")[:80] \
                or "(no description)"
            lines.append(f"    {name:<36}  {desc}")
            surfaced.append(name)
        extra = len(universal) - _UNIVERSAL_INJECTION_LIMIT
        if extra > 0:
            lines.append(
                f"    (+{extra} more universal -- registry --format table)"
            )
    if clusters:
        lines.append(
            "  Scenario clusters (load the matching one on entry):"
        )
        for cid, body in clusters.items():
            members = _field(body, "members", [])
            cdesc = _field(body, "description", "")
            head = f"    {cid} ({len(members)})"
            if cdesc:
                head += f" -- {cdesc[:60]}"
            lines.append(head)
            if members:
                lines.append(f"      {', '.join(members)}")
            surfaced.extend(members)
    lines.append(
        "  Full manifest: python -m governance_core.discovery.registry "
        "--format table"
    )

    # Record path-A surfacing (best-effort; never break injection output).
    try:
        registry._get_tracker().record_surfaced(sorted(set(surfaced)))
    except Exception:  # noqa: BLE001 - tracking is diagnostic, not critical
        pass
    return "\n".join(lines)


def _emit_funnel(registry: "SkillRegistry") -> None:
    """Print the Surfaced->Triggered->Loaded usage funnel for learned+guide skills.

    use_count alone scores 0 for skills designed to act from the SessionStart
    summary (path A) or the router-injected head (path B) without ever loading
    the body, so it cannot tell "applied via summary" from "dead weight". The
    funnel adds the two missing layers and classifies each skill:

      - retire candidate: surfaced > 0 but never triggered or loaded
      - slim candidate:   triggered > 0 but never loaded (head suffices)
      - star skill:       loaded repeatedly

    Lives on the registry CLI (not the tracker) because the registry knows the
    full learned+guide universe, so it can show 0/0/0 rows for skills the
    tracker never recorded -- and avoids a registry<-tracker circular import.
    """
    import sys as _sys
    tracker = registry._get_tracker()
    universe = (registry.manifest_for_injection(["learned"])
                + registry.manifest_for_injection(["guide"]))
    rows = []
    for e in universe:
        row = tracker.funnel_row(e["name"])
        surf, trig = row["surfaced_count"], row["triggered_count"]
        # load = both body-load paths: Skill-tool (use_count) + a Read of the
        # .md body (loaded_count, P-0113 WS-D). Learned/guide skills are Read,
        # not Skill-tool loaded, so loaded_count is the previously-missing half
        # that kept this column pinned at 0. The two counters are disjoint
        # event sources (Skill tool vs Read tool), so summing never double-counts.
        load = row["use_count"] + row["loaded_count"]
        last = (row["last_triggered"] or row["last_loaded"]
                or row["last_used"] or "-")
        rows.append((e["name"], e["source_type"], surf, trig, load, last))
    # retire candidates (surfaced, never triggered/loaded) sort to the top,
    # then by engagement (triggered+loaded) desc, then surfaced desc.
    rows.sort(key=lambda r: (
        0 if (r[2] > 0 and r[3] == 0 and r[4] == 0) else 1,
        -(r[3] + r[4]), -r[2]))
    hdr = (f"{'skill':<40} {'type':<8} {'surf':>5} {'trig':>5} "
           f"{'load':>5}  last")
    _sys.stdout.write(hdr + "\n" + "-" * len(hdr) + "\n")
    for name, st, surf, trig, load, last in rows:
        _sys.stdout.write(f"{name:<40} {st:<8} {surf:>5} {trig:>5} "
                          f"{load:>5}  {last}\n")
    retire = [r for r in rows if r[2] > 0 and r[3] == 0 and r[4] == 0]
    slim = [r for r in rows if r[3] > 0 and r[4] == 0]
    _sys.stdout.write(
        f"\nretire candidates (surfaced, never triggered/loaded): "
        f"{len(retire)}\n")
    _sys.stdout.write(
        f"slim candidates   (triggered, never loaded):          "
        f"{len(slim)}\n")


def main() -> None:
    """CLI entry point for skill registry."""
    import argparse

    parser = argparse.ArgumentParser(description="Skill Registry - Progressive Loading")
    parser.add_argument(
        "--format",
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Write manifest to file (JSON format)",
    )
    parser.add_argument(
        "--load",
        type=str,
        default=None,
        help="Load L1 content for a specific skill",
    )
    parser.add_argument(
        "--inject",
        action="store_true",
        help="Emit SessionStart injection text (Tier A learned + Tier B guides)",
    )
    parser.add_argument(
        "--funnel",
        action="store_true",
        help="Show the Surfaced->Triggered->Loaded skill-usage funnel",
    )
    args = parser.parse_args()

    registry = SkillRegistry()
    count = registry.scan()

    if args.inject:
        _emit_injection(registry)
        return

    if args.funnel:
        _emit_funnel(registry)
        return

    if args.load:
        content = registry.load(args.load)
        if content:
            print(content)
        else:
            print(f"[FAIL] Skill not found: {args.load}")
            raise SystemExit(1)
        return

    if args.output:
        registry.save_manifest(args.output)
        print(f"[OK] Manifest written to {args.output} ({count} skills)")
        return

    if args.format == "json":
        print(json.dumps(registry.manifest(), indent=2, ensure_ascii=False))
    else:
        print(registry.summary_table())


if __name__ == "__main__":
    main()
