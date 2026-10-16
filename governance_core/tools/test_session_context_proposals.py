# -*- coding: utf-8 -*-
"""Tests for session-context's pending-proposal banner (`_check_proposals`).

Regression: the banner only scanned `../shared_state/proposals` (the
multi-clone layout), so a single-repo project that keeps `shared_state/`
inside the repo -- the governance-core hub itself -- never saw its own
pending proposals at SessionStart. Both layouts are now scanned.

The hook rewraps sys.stdout at import time, so it is loaded in a child
interpreter rather than inside the test process. Temp files only.

Run from repo root:
    python -m pytest tools/test_session_context_proposals.py -q
"""
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent


def _hook_path() -> Path:
    """session-context.py in the package-source or the installed layout."""
    for candidate in (_HERE.parent / "hooks" / "session-context.py",
                      _HERE.parent / ".claude" / "hooks" / "session-context.py"):
        if candidate.is_file():
            return candidate
    pytest.skip("session-context.py not found next to tools/")


def _banner(root: Path, role: str) -> str:
    """Call the hook's _check_proposals(root, role) in a subprocess."""
    code = (
        "import importlib.util, sys\n"
        "spec = importlib.util.spec_from_file_location('sc', sys.argv[1])\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
        "sys.stdout.write(mod._check_proposals(sys.argv[2], sys.argv[3]))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(_hook_path()), str(root), role],
        capture_output=True, timeout=60)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    return result.stdout.decode("utf-8", "replace")


def _write(d: Path, nnnn: str, agent: str, status: str) -> str:
    """Write a minimal proposal into `d`; return its filename."""
    d.mkdir(parents=True, exist_ok=True)
    name = f"p-{nnnn}-x.md"
    (d / name).write_text(
        f"---\nid: P-{nnnn}\nagent: {agent}\nstatus: {status}\n"
        f"created: 2030-01-01\nowner: {agent}\n---\n\n# Proposal P-{nnnn}: x\n",
        encoding="utf-8")
    return name


def test_in_repo_shared_state_is_listed(tmp_path):
    root = tmp_path / "repo"
    name = _write(root / "shared_state" / "proposals" / "core", "0001",
                  "core", "pending")
    assert name in _banner(root, "core")


def test_sibling_shared_state_is_still_listed(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    name = _write(tmp_path / "shared_state" / "proposals" / "alpha", "0001",
                  "alpha", "approved")
    assert name in _banner(root, "alpha")


def test_both_layouts_are_merged(tmp_path):
    root = tmp_path / "repo"
    inner = _write(root / "shared_state" / "proposals" / "alpha", "0001",
                   "alpha", "pending")
    outer = _write(tmp_path / "shared_state" / "proposals" / "alpha", "0002",
                   "alpha", "in-progress")
    out = _banner(root, "alpha")
    assert inner in out and outer in out


def test_same_file_in_both_layouts_listed_once(tmp_path):
    root = tmp_path / "repo"
    name = _write(root / "shared_state" / "proposals" / "alpha", "0001",
                  "alpha", "pending")
    _write(tmp_path / "shared_state" / "proposals" / "alpha", "0001",
           "alpha", "pending")
    assert _banner(root, "alpha").count(name) == 1


def test_other_agents_are_counted_not_listed(tmp_path):
    root = tmp_path / "repo"
    name = _write(root / "shared_state" / "proposals" / "beta", "0001",
                  "beta", "pending")
    out = _banner(root, "alpha")
    assert "Cross-agent pending: beta=1" in out and name not in out


@pytest.mark.parametrize("status", ["draft", "implemented", "rejected",
                                    "superseded", "upstreamed"])
def test_hidden_statuses_stay_hidden(tmp_path, status):
    root = tmp_path / "repo"
    _write(root / "shared_state" / "proposals" / "core", "0001", "core", status)
    assert _banner(root, "core") == ""


def test_no_shared_state_anywhere_is_silent(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    assert _banner(root, "core") == ""
