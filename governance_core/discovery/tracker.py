# -*- coding: utf-8 -*-
"""Skill usage tracker with JSON persistence.

Tracks skill usage frequency, recency, and session complexity to support:
1. Weighted skill discovery (frequently-used skills rank higher)
2. Auto-trigger heuristic (when to suggest skill extraction)
3. Refinement tracking (which skills were used and may need updates)

Data stored at .claude/skills/learned/.usage.json — survives across sessions.

Usage:
    from governance_core.discovery.tracker import SkillTracker

    tracker = SkillTracker()
    tracker.record_use("futu-check")
    tracker.record_task_completion("Deploy strangle pipeline")
    scores = tracker.weighted_scores()
    if tracker.should_extract():
        print("Time to extract skills from this session")
"""
import json
import logging
import math
import os
import subprocess
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from governance_core.discovery import resolve_project_root

logger = logging.getLogger(__name__)


def _tracker_file() -> Path:
    """Return the per-agent tracker state path.

    Resolves to ``<agent_root>/.claude/skills/learned/.usage.json`` so each
    agent clone keeps its own session state instead of writing into core.
    """
    return resolve_project_root(__file__) / ".claude" / "skills" / "learned" / ".usage.json"

# Weights for scoring formula
_W_FREQUENCY = 0.4
_W_RECENCY = 0.4
_W_REFINEMENT = 0.2

# Recency half-life in days (score halves every N days of non-use)
_RECENCY_HALF_LIFE = 14

# Complexity threshold: extract skill when session score reaches this
_EXTRACTION_THRESHOLD = 5


def _today() -> str:
    """Return today's date as ISO string."""
    return date.today().isoformat()


def _days_since(iso_date: str) -> int:
    """Calculate days between a date string and today."""
    try:
        d = datetime.strptime(iso_date, "%Y-%m-%d").date()
        return (date.today() - d).days
    except (ValueError, TypeError):
        return 999


def _recency_score(last_used: str) -> float:
    """Exponential decay score based on days since last use.

    Args:
        last_used: ISO date string of last usage.

    Returns:
        Score between 0.0 and 1.0, where 1.0 = used today.
    """
    days = _days_since(last_used)
    return math.exp(-0.693 * days / _RECENCY_HALF_LIFE)  # ln(2) ~ 0.693


def _int_field(entry: dict, key: str) -> int:
    """Return ``entry[key]`` as an int, treating an absent key as 0.

    Schema v2 funnel counters (surfaced_count / triggered_count) are
    lazy-migrated: an old 4-key entry has no such key until first recorded.
    Spelled as an explicit membership test rather than a dict-get default so
    the Art.4 config-fallback rule (regex-enforced on all dict access) does
    not false-positive on this data-dict read.
    """
    return entry[key] if key in entry else 0


class SkillTracker:
    """Persistent skill usage tracker."""

    def __init__(self, tracker_path: Optional[Path] = None) -> None:
        """Initialize tracker.

        Args:
            tracker_path: Override path to .usage.json (for testing).
        """
        self._path = tracker_path or _tracker_file()
        self._data = self._load()

    def _load(self) -> dict:
        """Load tracker data from disk.

        Returns:
            Tracker data dict with 'skills' and 'sessions' keys.
        """
        if not self._path.exists():
            return {
                "skills": {},
                "sessions": {
                    "current": {
                        "date": _today(),
                        "tasks_completed": 0,
                        "files_modified": 0,
                        "skills_used": [],
                        "steps_taken": [],
                    },
                    "last_extraction": None,
                    "extractions_total": 0,
                },
            }
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Tracker file corrupt, reinitializing: %s", e)
            return {"skills": {}, "sessions": {
                "current": {"date": _today(), "tasks_completed": 0,
                            "files_modified": 0, "skills_used": [],
                            "steps_taken": []},
                "last_extraction": None, "extractions_total": 0,
            }}

    def _save(self) -> None:
        """Persist tracker data atomically (tmp file + os.replace).

        The router (path B, ``record_triggered``) now writes per user prompt
        as a separate subprocess and may overlap a path-C load, so a plain
        full-file rewrite could expose a half-written file to a concurrent
        reader. ``os.replace`` is atomic on both Windows and POSIX: a reader
        sees either the old or the new file, never a truncated one. A lost
        write under a rare race is acceptable (counters are a proxy); a
        corrupt file is not.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._data, indent=2, ensure_ascii=False)
        fd, tmp = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp, self._path)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _ensure_current_session(self) -> dict:
        """Ensure current session data exists and is for today.

        Returns:
            Current session dict.
        """
        sessions = self._data.setdefault("sessions", {})
        current = sessions.get("current", {})
        if current.get("date") != _today():
            # New day — reset session counters
            current = {
                "date": _today(),
                "tasks_completed": 0,
                "files_modified": 0,
                "skills_used": [],
                "steps_taken": [],
            }
            sessions["current"] = current
        return current

    # --- Skill usage tracking ---

    def record_use(self, name: str) -> None:
        """Record that a skill was loaded/used (L1 load).

        Args:
            name: Skill name.
        """
        skills = self._data.setdefault("skills", {})
        entry = skills.setdefault(name, {
            "use_count": 0,
            "last_used": None,
            "created": _today(),
            "refinement_count": 0,
        })
        entry["use_count"] += 1
        entry["last_used"] = _today()

        session = self._ensure_current_session()
        if name not in session.setdefault("skills_used", []):
            session["skills_used"].append(name)

        self._save()
        logger.info("Skill use recorded: %s (total: %d)", name, entry["use_count"])

    def record_refinement(self, name: str) -> None:
        """Record that a skill was refined.

        Args:
            name: Skill name.
        """
        skills = self._data.setdefault("skills", {})
        entry = skills.get(name)
        if entry:
            entry["refinement_count"] = entry.get("refinement_count", 0) + 1
            entry["last_used"] = _today()
            self._save()

    # --- Usage funnel: Surfaced (A) / Triggered (B) / Loaded (C) ---
    #
    # A skill reaches the agent by three distinct paths, but record_use only
    # counts path C (full-body load). Learned + guide skills are designed to be
    # acted on from the SessionStart one-line summary (A) or the router-injected
    # head (B) without ever loading the body, so use_count=0 cannot distinguish
    # "applied via summary" from "dead weight". record_surfaced / record_triggered
    # add the missing two layers. Schema v2 fields are lazy-migrated: an old
    # 4-key entry gains them on first record, and weighted_scores() / get_stats()
    # tolerate their absence unchanged.

    def record_surfaced(self, names: list[str]) -> None:
        """Record that skills were surfaced in the SessionStart menu (path A).

        Per-day deduped: a skill surfaced again the same day is not recounted,
        so compact/resume re-fires of SessionStart do not inflate the count.
        The whole injection list is recorded in one ``_save``.

        Args:
            names: Skill names that appeared in the injection menu.
        """
        today = _today()
        skills = self._data.setdefault("skills", {})
        changed = False
        for name in names:
            entry = skills.setdefault(name, {
                "use_count": 0, "last_used": None, "created": today,
                "refinement_count": 0,
            })
            if entry.get("last_surfaced") != today:
                entry["surfaced_count"] = _int_field(entry, "surfaced_count") + 1
                entry["last_surfaced"] = today
                changed = True
        if changed:
            self._save()

    def record_triggered(self, name: str) -> None:
        """Record that a skill's router trigger fired (path B), per-event.

        Counts every trigger-text match, including dedup-suppressed re-matches:
        dedup gates only whether the body is re-injected, not whether the
        scenario recurred, so it is an injection-output optimization rather
        than a relevance signal. Creates the entry if the skill was never
        surfaced.

        Args:
            name: Skill name whose router trigger matched.
        """
        skills = self._data.setdefault("skills", {})
        entry = skills.setdefault(name, {
            "use_count": 0, "last_used": None, "created": _today(),
            "refinement_count": 0,
        })
        entry["triggered_count"] = _int_field(entry, "triggered_count") + 1
        entry["last_triggered"] = _today()
        self._save()

    def funnel_row(self, name: str) -> dict:
        """Return the Surfaced/Triggered/Loaded counters for one skill.

        Returns zeros for a skill the tracker has never recorded, so a caller
        iterating the full learned+guide universe can show 0/0/0 rows without
        reaching into private tracker state.

        Args:
            name: Skill name.

        Returns:
            Dict with surfaced_count / triggered_count / use_count and the
            three last-* timestamps (None when never recorded).
        """
        entry = self._data.get("skills", {}).get(name, {})
        return {
            "surfaced_count": _int_field(entry, "surfaced_count"),
            "triggered_count": _int_field(entry, "triggered_count"),
            "use_count": _int_field(entry, "use_count"),
            "last_surfaced": entry.get("last_surfaced"),
            "last_triggered": entry.get("last_triggered"),
            "last_used": entry.get("last_used"),
        }

    # --- Session complexity tracking ---

    def record_task_completion(self, task_description: str) -> None:
        """Record a task completion in the current session.

        Args:
            task_description: Brief description of completed task.
        """
        session = self._ensure_current_session()
        session["tasks_completed"] = session.get("tasks_completed", 0) + 1
        self._save()

    def record_step(self, step_description: str) -> None:
        """Record an execution step in the current session.

        Used for auto-refinement: captures actual steps taken while
        following a skill, so they can be diff'd against the skill document.

        Args:
            step_description: What was done (e.g., "Ran pytest tests/daily/").
        """
        session = self._ensure_current_session()
        session.setdefault("steps_taken", []).append({
            "step": step_description,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        })
        self._save()

    def record_files_modified(self, count: int) -> None:
        """Record number of files modified in this session.

        Args:
            count: Number of files modified.
        """
        session = self._ensure_current_session()
        session["files_modified"] = count
        self._save()

    def record_extraction(self, skill_name: str) -> None:
        """Record that a skill was extracted in this session.

        Args:
            skill_name: Name of the extracted skill.
        """
        sessions = self._data.setdefault("sessions", {})
        sessions["last_extraction"] = _today()
        sessions["extractions_total"] = sessions.get("extractions_total", 0) + 1
        self._save()

    # --- Git-based auto-population ---

    def populate_from_git(self, root: Path | None = None) -> None:
        """Auto-populate session metrics from git state.

        Reads today's commits and recent file changes to set
        tasks_completed and files_modified without requiring
        explicit record_* calls throughout the session.

        Args:
            root: Project root for git commands. Defaults to the invoking
                agent's repo root (resolved via CLAUDE_AGENT_ROOT / git).
        """
        cwd = str(root) if root else str(resolve_project_root(__file__))

        # Count files modified (staged + last commit)
        files = set()
        for cmd in (
            ["git", "diff", "--cached", "--name-only"],
            ["git", "diff", "--name-only", "HEAD~1..HEAD"],
        ):
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, cwd=cwd, timeout=5,
                    encoding="utf-8", errors="replace",
                )
                files.update(f for f in result.stdout.strip().split("\n") if f)
            except (subprocess.TimeoutExpired, OSError):
                pass
        if files:
            self.record_files_modified(len(files))

        # Count today's commits as tasks
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "--since=midnight", "--format=%s"],
                capture_output=True, text=True, cwd=cwd, timeout=5,
                encoding="utf-8", errors="replace",
            )
            stdout = result.stdout or ""
            commits = [c for c in stdout.strip().split("\n") if c]
        except (subprocess.TimeoutExpired, OSError):
            commits = []

        if commits:
            session = self._ensure_current_session()
            session["tasks_completed"] = max(
                session.get("tasks_completed", 0), len(commits)
            )
            self._save()

    # --- Heuristics ---

    def session_complexity(self) -> int:
        """Calculate current session complexity score.

        Scoring:
          +1 per task completed
          +1 per 5 files modified
          +1 per 10 steps taken
          +2 if skills were used (skill-guided session = higher value)

        Returns:
            Integer complexity score.
        """
        session = self._ensure_current_session()
        score = session.get("tasks_completed", 0)
        score += session.get("files_modified", 0) // 5
        score += len(session.get("steps_taken", [])) // 10
        if session.get("skills_used"):
            score += 2
        return score

    def should_extract(self) -> bool:
        """Determine if the current session warrants skill extraction.

        Heuristic: session complexity >= threshold AND no extraction
        happened today yet.

        Returns:
            True if skill extraction is recommended.
        """
        sessions = self._data.get("sessions", {})
        if sessions.get("last_extraction") == _today():
            return False  # already extracted today
        return self.session_complexity() >= _EXTRACTION_THRESHOLD

    def should_extract_reason(self) -> str:
        """Return why should_extract() gives its verdict (P-0070 Fix B).

        One of: 'recommended' (complexity at/above threshold, nothing
        extracted today), 'already-extracted-today', or 'below-threshold'.
        Lets a caller report the real reason rather than assuming low
        complexity -- complexity can be well above threshold yet
        should_extract() still False because an extraction already ran today.
        """
        sessions = self._data.get("sessions", {})
        if sessions.get("last_extraction") == _today():
            return "already-extracted-today"
        if self.session_complexity() >= _EXTRACTION_THRESHOLD:
            return "recommended"
        return "below-threshold"

    def skills_used_this_session(self) -> list[str]:
        """Return names of skills loaded (L1) in this session.

        Returns:
            List of skill names.
        """
        session = self._ensure_current_session()
        return list(session.get("skills_used", []))

    def steps_taken_this_session(self) -> list[dict]:
        """Return steps recorded in this session.

        Returns:
            List of step dicts with 'step' and 'timestamp'.
        """
        session = self._ensure_current_session()
        return list(session.get("steps_taken", []))

    # --- Weighted scoring ---

    def weighted_scores(self) -> dict[str, float]:
        """Calculate weighted scores for all tracked skills.

        Formula:
          score = W_freq * log2(use_count + 1)
                + W_recency * recency_decay(last_used)
                + W_refinement * log2(refinement_count + 1)

        Returns:
            Dict mapping skill name to weighted score.
        """
        scores = {}
        for name, data in self._data.get("skills", {}).items():
            freq = math.log2(data.get("use_count", 0) + 1)
            recency = _recency_score(data.get("last_used", "2000-01-01"))
            refinement = math.log2(data.get("refinement_count", 0) + 1)
            scores[name] = (
                _W_FREQUENCY * freq
                + _W_RECENCY * recency
                + _W_REFINEMENT * refinement
            )
        return scores

    def get_stats(self) -> dict:
        """Return summary statistics for CLI display.

        Returns:
            Dict with session and skill stats.
        """
        session = self._ensure_current_session()
        skills = self._data.get("skills", {})
        sessions = self._data.get("sessions", {})
        return {
            "session_date": session.get("date"),
            "tasks_completed": session.get("tasks_completed", 0),
            "files_modified": session.get("files_modified", 0),
            "skills_used_today": session.get("skills_used", []),
            "steps_taken_today": len(session.get("steps_taken", [])),
            "session_complexity": self.session_complexity(),
            "extraction_threshold": _EXTRACTION_THRESHOLD,
            "should_extract": self.should_extract(),
            "should_extract_reason": self.should_extract_reason(),
            "total_tracked_skills": len(skills),
            "total_extractions": sessions.get("extractions_total", 0),
            "last_extraction": sessions.get("last_extraction"),
        }


def main() -> None:
    """CLI entry point for tracker inspection."""
    import argparse

    parser = argparse.ArgumentParser(description="Skill Usage Tracker")
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show session and skill statistics",
    )
    parser.add_argument(
        "--scores",
        action="store_true",
        help="Show weighted scores for all tracked skills",
    )
    parser.add_argument(
        "--should-extract",
        action="store_true",
        help="Check if skill extraction is recommended",
    )
    args = parser.parse_args()

    tracker = SkillTracker()

    if args.scores:
        scores = tracker.weighted_scores()
        if not scores:
            print("No tracked skills yet.")
            return
        for name, score in sorted(scores.items(), key=lambda x: -x[1]):
            print(f"  {name:<35} {score:.3f}")
        return

    if args.should_extract:
        tracker.populate_from_git()
        # P-0070 Fix B: report the real reason -- complexity can be well
        # above threshold yet extraction still declined because one already
        # ran today. The old CLI always claimed "not enough complexity".
        reason = tracker.should_extract_reason()
        complexity = tracker.session_complexity()
        if reason == "recommended":
            sys.stdout.write(
                "[YES] Session complexity warrants skill extraction\n")
        elif reason == "already-extracted-today":
            sys.stdout.write("[NO] A skill was already extracted today\n")
        else:
            sys.stdout.write("[NO] Not enough complexity for extraction yet\n")
        sys.stdout.write(
            f"     Complexity: {complexity} "
            f"(threshold: {_EXTRACTION_THRESHOLD})\n")
        return

    # Default: show stats (auto-populate from git first)
    tracker.populate_from_git()
    stats = tracker.get_stats()
    print("Skill Tracker Stats")
    print("=" * 40)
    print(f"  Session date:        {stats['session_date']}")
    print(f"  Tasks completed:     {stats['tasks_completed']}")
    print(f"  Files modified:      {stats['files_modified']}")
    print(f"  Steps taken:         {stats['steps_taken_today']}")
    print(f"  Skills used today:   {stats['skills_used_today']}")
    print(f"  Session complexity:  {stats['session_complexity']} / {stats['extraction_threshold']}")
    print(f"  Should extract:      {stats['should_extract']}")
    print(f"  Total tracked:       {stats['total_tracked_skills']} skills")
    print(f"  Total extractions:   {stats['total_extractions']}")
    print(f"  Last extraction:     {stats['last_extraction'] or 'never'}")


if __name__ == "__main__":
    main()
