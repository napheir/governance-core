"""session-context lists only dated STATE.md entries (P-0129 Phase E, F6).

The installer seeds STATE.md with an HTML-comment format example
"### YYYY-MM-DD -- <short title>"; a bare "### " split surfaced that example
as the most recent entry. Entries now use rotate_state's definition: a
"### YYYY-MM-DD" header.

The hook rewraps sys.stdout at import time, so it is loaded in a child
process (see memory hook-stdout-rebind-breaks-inprocess-import).

Run from repo root:
    python -m pytest tools/test_session_context_state.py -q
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
TEMPLATE = (
    "# STATE -- proj\n\n"
    "## 1. Updates in This Session\n\n"
    "<!-- Newest entry on top. Format:\n"
    "### YYYY-MM-DD -- <short title>\n"
    "- summary / files / key decisions / test results\n"
    "-->\n"
)


def _hook() -> Path:
    """session-context.py in the package-source or the installed layout."""
    for candidate in (_HERE.parent / "hooks" / "session-context.py",
                      _HERE.parent / ".claude" / "hooks" / "session-context.py"):
        if candidate.is_file():
            return candidate
    pytest.skip("session-context.py not found next to tools/")


def _recent_state(root: Path) -> str:
    """Call the hook's _read_recent_state(root) in a child process."""
    code = (
        "import importlib.util, sys\n"
        "spec = importlib.util.spec_from_file_location('sc', sys.argv[1])\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
        "sys.stdout.write(mod._read_recent_state(sys.argv[2]))\n"
    )
    res = subprocess.run([sys.executable, "-c", code, str(_hook()), str(root)],
                         input="", capture_output=True, encoding="utf-8",
                         timeout=30, check=True)
    return res.stdout


def test_template_only_has_no_entries(tmp_path: Path) -> None:
    (tmp_path / "STATE.md").write_text(TEMPLATE, encoding="utf-8")
    out = _recent_state(tmp_path)
    assert "YYYY-MM-DD" not in out
    assert "(no recent entries)" in out


def test_real_entries_listed_template_skipped(tmp_path: Path) -> None:
    (tmp_path / "STATE.md").write_text(
        TEMPLATE
        + "\n### 2026-11-05 -- newest\n- a\n"
        + "\n### 2026-11-04 -- older\n- b\n",
        encoding="utf-8")
    out = _recent_state(tmp_path)
    assert "YYYY-MM-DD" not in out
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    assert lines == ["### 2026-11-05 -- newest", "### 2026-11-04 -- older"]
