"""Journaling an agent's own Edit/Write, and changes a write must not absorb (P-0136).

0.51.0 journaled lib writes only. An agent's own body Edit of its own
proposal -- the way /proposal says to fill a proposal -- therefore surfaced as
an "actor unknown" alert. And a change was taken as explained when any
journal line merely ended at the current sha, while an own write moved the
last-seen manifest without checking where the file had been: a raw change
just before an own write was absorbed. Now the own-write hooks journal
Edit/Write (via "edit"), a change is explained only by a run of journal
lines from the last-seen sha, and an own write checks that run first.
contracts/shared_state_ownership.md §4-5 (1.1.0).

Run from repo root:
    python -m pytest tools/test_ownership_own_edits.py -q
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from governance_core import ownership

_HERE = Path(__file__).resolve().parent
_HOOKS = next(p for p in (_HERE.parent / "hooks", _HERE.parent / ".claude" / "hooks")
              if (p / "_guard_common.py").is_file())
_COPIED = ("_guard_common.py", "foreign-change-notice.py", "own-write-capture.py",
           "own-write-journal.py")
REL = "proposals/platform/p-0001-x.md"


def _project(tmp_path: Path, agents=("core", "platform", "content")) -> dict:
    proj = tmp_path / "proj"
    shared = proj / "shared_state"
    cfg = {
        "project_name": "proj", "install_root": str(tmp_path),
        "shared_state_root": str(shared), "core_agent_name": "core",
        "core_branches": ["master"], "ritual_phrase": "OK",
        "agents": [{"name": a, "branch": "master" if a == "core" else f"feature/{a}",
                    "clone_dir": f"agent-{a}"} for a in agents],
    }
    out = {"shared": shared}
    for name in agents:
        clone = proj / f"agent-{name}"
        (clone / ".governance").mkdir(parents=True)
        (clone / ".governance" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
        hooks = clone / ".claude" / "hooks"
        hooks.mkdir(parents=True)
        for f in _COPIED:
            shutil.copy2(_HOOKS / f, hooks / f)
        out[name] = clone
    (shared / "proposals" / "platform").mkdir(parents=True)
    return out


@pytest.fixture()
def project(tmp_path: Path) -> dict:
    return _project(tmp_path)


def _put(p: dict, rel: str, text: str) -> Path:
    path = p["shared"] / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def _run(clone: Path, hook: str, payload: dict) -> None:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    res = subprocess.run([sys.executable, str(clone / ".claude" / "hooks" / f"{hook}.py")],
                         input=json.dumps(payload), capture_output=True,
                         encoding="utf-8", env=env, timeout=60)
    assert res.returncode == 0 and res.stdout == "", (res.stdout, res.stderr)


def _edit(p: dict, actor: str, rel: str, text: str, *, tool: str = "Edit",
          payload_extra: dict | None = None, capture: bool = True) -> None:
    """An Edit/Write as Claude Code runs it: Pre hook, the write, Post hook."""
    path = p["shared"] / rel
    target = {"notebook_path": str(path)} if tool == "NotebookEdit" else {"file_path": str(path)}
    payload = {"tool_name": tool, "tool_input": target, "session_id": "sess-1",
               "tool_use_id": f"toolu_{actor}_{len(text)}"}
    payload.update(payload_extra or {})
    if capture:
        _run(p[actor], "own-write-capture", payload)
    _put(p, rel, text)
    _run(p[actor], "own-write-journal", payload)


def _lib_write(p: dict, actor: str, rel: str, text: str) -> None:
    path = p["shared"] / rel
    before = ownership.file_sha(path)
    _put(p, rel, text)
    ownership.record_write(p[actor], "test", rel, before, ownership.file_sha(path))


def _journal(p: dict) -> list:
    return [r for r in ownership.journal_records(p["shared"], rotated=True) if "path" in r]


def test_own_edit_is_journaled_and_not_news(project: dict) -> None:
    _put(project, REL, "v1\n")
    ownership.scan(project["platform"])
    _edit(project, "platform", REL, "body section filled in\n")
    (rec,) = _journal(project)
    assert (rec["actor"], rec["op"], rec["via"]) == ("platform", "edit:Edit", "edit")
    result = ownership.scan(project["platform"])
    assert result["new"] == [] and result["notices"] == []


def test_raw_write_then_own_edit_still_alerts(project: dict) -> None:
    _put(project, REL, "v1\n")
    ownership.scan(project["platform"])
    _put(project, REL, "tampered\n")  # no journal line
    _edit(project, "platform", REL, "owner edits on top\n")
    (n,) = ownership.list_notices(project["shared"], "platform")
    assert (n["severity"], n["from"]) == ("alert", "unknown")
    assert "before edit:Edit by platform" in n["detail"]
    assert ownership.scan(project["platform"])["new"] == []  # told once, not twice


def test_raw_write_then_own_lib_write_still_alerts(project: dict) -> None:
    _put(project, REL, "v1\n")
    ownership.scan(project["platform"])
    _put(project, REL, "tampered\n")
    _lib_write(project, "platform", REL, "lib transition on top\n")
    (n,) = ownership.list_notices(project["shared"], "platform")
    assert (n["severity"], n["from"]) == ("alert", "unknown")
    assert "before test by platform" in n["detail"]


def test_change_needs_a_run_of_lines_not_just_an_end(project: dict) -> None:
    _put(project, REL, "v1\n")
    ownership.scan(project["platform"])
    _put(project, REL, "tampered\n")
    _lib_write(project, "core", REL, "core writes on top\n")  # info to platform
    ownership.scan(project["platform"])
    notices = ownership.list_notices(project["shared"], "platform")
    assert sorted((n["severity"], n["from"]) for n in notices) == [
        ("alert", "unknown"), ("info", "core")]
    (alert,) = [n for n in notices if n["severity"] == "alert"]
    assert "before test by core" in alert["detail"]


def test_core_edit_of_another_partition_is_an_alert(project: dict) -> None:
    _put(project, REL, "v1\n")
    ownership.scan(project["platform"])
    _edit(project, "core", REL, "core hand-edits platform's proposal\n")
    (n,) = ownership.list_notices(project["shared"], "platform")
    assert (n["severity"], n["from"], n["detail"]) == ("alert", "core", "edit:Edit by core")
    assert ownership.scan(project["platform"])["new"] == []


def test_core_lib_write_stays_info_and_says_lib(project: dict) -> None:
    _put(project, REL, "v1\n")
    ownership.scan(project["platform"])
    _lib_write(project, "core", REL, "core dispatches\n")
    (rec,) = _journal(project)
    assert rec["via"] == "lib"
    (n,) = ownership.list_notices(project["shared"], "platform")
    assert n["severity"] == "info"


def test_chain_reads_rotated_journal(project: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ownership, "JOURNAL_ROTATE_BYTES", 10)
    _put(project, REL, "v0\n")
    ownership.scan(project["platform"])
    for i in range(3):
        _lib_write(project, "core", REL, f"v{i + 1}\n")
    assert list(project["shared"].glob("_journal.*.jsonl"))
    assert ownership.scan(project["platform"])["new"] == []  # explained across files


def test_missing_capture_surfaces_as_unknown(project: dict) -> None:
    _put(project, REL, "v1\n")
    ownership.scan(project["platform"])
    _edit(project, "platform", REL, "pre hook never ran\n", capture=False)
    assert _journal(project) == []
    (nid,) = ownership.scan(project["platform"])["new"]
    (n,) = ownership.list_notices(project["shared"], "platform")
    assert n["id"] == nid and n["from"] == "unknown"


def test_fallback_key_without_tool_use_id(project: dict) -> None:
    _put(project, REL, "v1\n")
    ownership.scan(project["platform"])
    _edit(project, "platform", REL, "no tool_use_id\n", payload_extra={"tool_use_id": ""})
    (rec,) = _journal(project)
    assert rec["actor"] == "platform"
    assert not list((project["platform"] / ownership.PENDING_REL).glob("*.json"))


def test_notebook_edit_uses_notebook_path(project: dict) -> None:
    rel = "proposals/platform/n.ipynb"
    _put(project, rel, "{}\n")
    ownership.scan(project["platform"])
    _edit(project, "platform", rel, '{"cells": []}\n', tool="NotebookEdit")
    (rec,) = _journal(project)
    assert rec["op"] == "edit:NotebookEdit"


def test_files_outside_partitions_and_single_agent_are_ignored(tmp_path: Path) -> None:
    p = _project(tmp_path)
    _edit(p, "platform", "todos/active/t.md", "unpartitioned\n")
    assert _journal(p) == []
    solo = _project(tmp_path / "solo", agents=("core",))
    _edit(solo, "core", "proposals/core/p.md", "single agent\n")
    assert not (solo["shared"] / ownership.JOURNAL_NAME).exists()
    assert not (solo["core"] / ownership.PENDING_REL).exists()


def test_stale_captures_are_pruned(project: dict) -> None:
    folder = project["platform"] / ownership.PENDING_REL
    folder.mkdir(parents=True)
    stale = folder / "old.json"
    stale.write_text("{}", encoding="utf-8")
    old = ownership.datetime.datetime.now().timestamp() - ownership.PENDING_TTL_SECONDS - 60
    os.utime(stale, (old, old))
    _put(project, REL, "v1\n")
    _run(project["platform"], "own-write-capture", {
        "tool_name": "Edit", "tool_input": {"file_path": str(project["shared"] / REL)},
        "tool_use_id": "toolu_new"})
    assert not stale.exists() and (folder / "toolu_new.json").is_file()


def test_record_write_rejects_unknown_via(project: dict) -> None:
    with pytest.raises(ownership.OwnershipError):
        ownership.record_write(project["platform"], "x", REL, None, None, via="shell")
