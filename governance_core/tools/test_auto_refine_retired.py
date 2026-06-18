"""Regression tests for the auto-refine retirement (gc #103 / P-0106).

The dead Hermes auto-refine subsystem was removed: `diff_and_refine`,
`refine_skill`, `_extract_workflow_steps`, `_find_novel_steps`, the extractor
`--auto-refine` CLI, and the tracker `record_step` / `steps_taken_this_session`
/ `record_refinement` + `steps_taken` plumbing. These tests pin that:

  (i)   the removed symbols are gone (no dangling attribute);
  (ii)  the extractor CLI no longer accepts `--auto-refine`;
  (iii) the live extraction path `extract_skill` still works;
  (iv)  the live `session_complexity()` / `get_stats()` numbers are unchanged —
        the removed `steps_taken` score term was always 0 (no producer), so the
        complexity formula equals tasks + files//5 + (2 if skills) with no steps
        contribution.

Run from repo root:
    python -m pytest governance_core/tools/test_auto_refine_retired.py -q
"""
import os
import subprocess
import sys

from governance_core import discovery
from governance_core.discovery import extractor
from governance_core.discovery.tracker import SkillTracker


# (i) removed symbols are gone

def test_extractor_dead_symbols_removed():
    for sym in ("diff_and_refine", "refine_skill",
                "_extract_workflow_steps", "_find_novel_steps"):
        assert not hasattr(extractor, sym), f"{sym} should be removed"


def test_tracker_dead_symbols_removed():
    for sym in ("record_step", "steps_taken_this_session", "record_refinement"):
        assert not hasattr(SkillTracker, sym), f"{sym} should be removed"


# (ii) extractor CLI no longer accepts --auto-refine

def test_cli_rejects_auto_refine(tmp_path):
    # Supply the required extract args so the ONLY parse fault is the now-removed
    # --auto-refine flag (argparse reports required-missing before unrecognized,
    # so without these the message would be about --name, not --auto-refine).
    # The unrecognized-arg error fires at parse time, before extract_skill runs;
    # CLAUDE_AGENT_ROOT isolates state regardless. encoding="utf-8": child stdout
    # would otherwise decode as GBK on Windows.
    env = {**os.environ, "CLAUDE_AGENT_ROOT": str(tmp_path)}
    r = subprocess.run(
        [sys.executable, "-m", "governance_core.discovery.extractor",
         "--name", "x", "--description", "d", "--steps", "a|b",
         "--auto-refine", "some-skill"],
        capture_output=True, text=True, encoding="utf-8", env=env,
    )
    assert r.returncode != 0
    assert "auto-refine" in (r.stderr + r.stdout)  # argparse: unrecognized arg


# (iii) live extraction path still works (isolated via CLAUDE_AGENT_ROOT)

def test_extract_skill_still_works(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_AGENT_ROOT", str(tmp_path))
    discovery._reset_root_cache()
    try:
        path = extractor.extract_skill(
            name="demo-skill",
            description="a demo",
            steps=["step one", "step two"],
        )
        assert path.exists()
        assert path.name == "demo-skill.md"
        assert "demo-skill" in path.read_text(encoding="utf-8")
    finally:
        discovery._reset_root_cache()


# (iv) live complexity/stats numbers unchanged; no steps_taken term/field

def test_session_complexity_has_no_steps_term(tmp_path):
    tr = SkillTracker(tracker_path=tmp_path / ".usage.json")
    tr.record_task_completion("t1")
    tr.record_task_completion("t2")
    tr.record_files_modified(10)
    tr.record_use("some-skill")
    # 2 tasks + 10//5 + 2 (skills present) = 6; no steps_taken contribution.
    assert tr.session_complexity() == 6


def test_get_stats_drops_steps_taken_today(tmp_path):
    tr = SkillTracker(tracker_path=tmp_path / ".usage.json")
    tr.record_task_completion("t1")
    tr.record_task_completion("t2")
    tr.record_files_modified(10)
    tr.record_use("some-skill")
    stats = tr.get_stats()
    assert "steps_taken_today" not in stats
    assert stats["session_complexity"] == 6
