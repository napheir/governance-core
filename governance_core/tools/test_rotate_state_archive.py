"""rotate_state: the archive it creates belongs to the consuming project.

The first rotation of a project wrote STATE_ARCHIVE.md under a fixed
upstream title ("# Trade Agent 项目状态文档 — Archive"), and the new file is
untracked -- committing only STATE.md then drops the rotated entries from git
(deva-vani, 0.48.3). The title now comes from STATE.md's own H1, and the
rotation reports (stats + a warning) that it created the archive. A per-day
cap rotation into an existing, tracked archive was silent and lost entries
the same way (deva-vani, 0.51.0), so every rotation now warns.

Run from repo root:
    python -m pytest tools/test_rotate_state_archive.py -q
"""
from __future__ import annotations

import importlib.util
from datetime import date, timedelta
from pathlib import Path

_TOOL = Path(__file__).resolve().parent / "rotate_state.py"


def _load():
    """Load rotate_state by path (it is a tool script, not a package module)."""
    spec = importlib.util.spec_from_file_location("_rotate_state_under_test", _TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _state(root: Path, h1: str) -> None:
    old = (date.today() - timedelta(days=30)).isoformat()
    new = date.today().isoformat()
    (root / "STATE.md").write_text(
        f"{h1}\n\n## 1. Updates in This Session\n\n"
        f"### {new} -- recent\n- kept\n\n"
        f"### {old} -- old\n- rotated\n",
        encoding="utf-8")


def test_first_archive_titled_from_state_h1(tmp_path: Path) -> None:
    _state(tmp_path, "# STATE -- deva-vani")
    stats = _load().rotate(execute=True, root=tmp_path)
    archive = (tmp_path / "STATE_ARCHIVE.md").read_text(encoding="utf-8")
    assert archive.startswith("# STATE -- deva-vani -- archive\n"), archive
    assert "Trade" not in archive
    assert "- rotated" in archive
    assert stats["archive_created"] is True


def test_existing_archive_header_kept_and_not_reported_created(tmp_path: Path) -> None:
    _state(tmp_path, "# STATE -- proj")
    (tmp_path / "STATE_ARCHIVE.md").write_text(
        "# Owner title\n\n---\n\n### 2020-01-01 -- ancient\n- a\n", encoding="utf-8")
    stats = _load().rotate(execute=True, root=tmp_path)
    archive = (tmp_path / "STATE_ARCHIVE.md").read_text(encoding="utf-8")
    assert archive.startswith("# Owner title\n")
    assert "- rotated" in archive
    assert stats["archive_created"] is False


def test_state_without_h1_gets_generic_title(tmp_path: Path) -> None:
    _state(tmp_path, "Session log")
    _load().rotate(execute=True, root=tmp_path)
    archive = (tmp_path / "STATE_ARCHIVE.md").read_text(encoding="utf-8")
    assert archive.startswith("# STATE archive\n"), archive


def test_every_rotation_warns_to_stage_the_archive(tmp_path: Path, caplog) -> None:
    tool = _load()
    _state(tmp_path, "# STATE -- proj")
    tool.rotate(execute=True, root=tmp_path)
    assert "created" in caplog.text and "stage it together" in caplog.text
    caplog.clear()
    _state(tmp_path, "# STATE -- proj")
    tool.rotate(execute=True, root=tmp_path)
    assert "changed (1 entries moved in)" in caplog.text, caplog.text
    assert "stage it together with STATE.md" in caplog.text


def test_no_warning_when_nothing_rotates_or_dry_run(tmp_path: Path, caplog) -> None:
    tool = _load()
    _state(tmp_path, "# STATE -- proj")
    tool.rotate(execute=False, root=tmp_path)
    (tmp_path / "STATE.md").write_text(
        f"# S\n\n### {date.today().isoformat()} -- only\n- kept\n", encoding="utf-8")
    tool.rotate(execute=True, root=tmp_path)
    assert "stage it together" not in caplog.text, caplog.text
