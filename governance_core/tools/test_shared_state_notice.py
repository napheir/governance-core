"""Telling an agent and its owner about changes others made (P-0135 Phase 3).

Nothing used to tell an agent that someone else changed its shared_state
content: State Log lines had no actor, snapshots stayed in the acting clone,
and SessionStart showed status only. Now lib writes are journaled
(hash-chained), core's audit and foreign lib writes create notices, and at
SessionStart every change to the agent's partitions that it did not make
becomes a notice -- attributed via the journal, or "actor unknown" -- before
the last-seen manifest moves. The hook shows notices to the owner
(`systemMessage`) and the agent (`additionalContext`); alerts repeat until
acked, info notices are acked once shown. contracts/shared_state_ownership.md.

Run from repo root:
    python -m pytest tools/test_shared_state_notice.py -q
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
sys.path.insert(0, str(_HERE))
import notices  # noqa: E402
import proposal_lib as pl  # noqa: E402


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
        for f in ("_guard_common.py", "foreign-change-notice.py"):
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


def _lib_write(p: dict, actor: str, rel: str, text: str) -> None:
    """A lib write by `actor`: change the file, then record it."""
    path = p["shared"] / rel
    before = ownership.file_sha(path)
    _put(p, rel, text)
    ownership.record_write(p[actor], "test", rel, before, ownership.file_sha(path))


def _hook(clone: Path) -> dict | None:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    res = subprocess.run([sys.executable, str(clone / ".claude" / "hooks" / "foreign-change-notice.py")],
                         input="{}", capture_output=True, encoding="utf-8", env=env, timeout=60)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout) if res.stdout.strip() else None


REL = "proposals/platform/p-0001-x.md"


def test_first_scan_is_a_baseline(project: dict) -> None:
    _put(project, REL, "v1\n")
    result = ownership.scan(project["platform"])
    assert result["first_run"] and result["new"] == [] and result["notices"] == []
    assert ownership.load_manifest(project["platform"]) == {REL: ownership.file_sha(project["shared"] / REL)}


def test_core_lib_write_is_an_info_notice_once(project: dict) -> None:
    _put(project, REL, "v1\n")
    ownership.scan(project["platform"])
    _lib_write(project, "core", REL, "v2 by core\n")
    result = ownership.scan(project["platform"])
    assert result["new"] == []  # record_write already told platform
    (n,) = result["notices"]
    assert (n["severity"], n["from"], n["paths"]) == ("info", "core", [REL])


def test_raw_write_is_an_unknown_actor_alert_until_acked(project: dict) -> None:
    _put(project, REL, "v1\n")
    ownership.scan(project["platform"])
    _put(project, REL, "tampered\n")  # no lib, no journal line
    first = ownership.scan(project["platform"])
    assert len(first["new"]) == 1
    (n,) = first["notices"]
    assert (n["severity"], n["from"]) == ("alert", "unknown")
    assert "actor unknown" in n["detail"]
    again = ownership.scan(project["platform"])
    assert again["new"] == [] and len(again["notices"]) == 1  # repeats, no duplicate
    ownership.ack_notice(project["shared"], "platform", n["id"], "platform")
    assert ownership.scan(project["platform"])["notices"] == []


def test_non_core_lib_write_is_an_alert(project: dict) -> None:
    _put(project, REL, "v1\n")
    ownership.scan(project["platform"])
    _lib_write(project, "content", REL, "content edited it\n")
    (n,) = ownership.scan(project["platform"])["notices"]
    assert (n["severity"], n["from"]) == ("alert", "content")


def test_own_lib_write_is_not_news(project: dict) -> None:
    _put(project, REL, "v1\n")
    ownership.scan(project["platform"])
    _lib_write(project, "platform", REL, "my own edit\n")
    result = ownership.scan(project["platform"])
    assert result["new"] == [] and result["notices"] == []


def test_raw_deletion_is_reported(project: dict) -> None:
    path = _put(project, REL, "v1\n")
    ownership.scan(project["platform"])
    path.unlink()
    (n,) = ownership.scan(project["platform"])["notices"]
    assert n["from"] == "unknown" and n["detail"].startswith("deleted")


def test_journal_chain_detects_tampering(project: dict) -> None:
    _lib_write(project, "core", REL, "a\n")
    _lib_write(project, "core", REL, "b\n")
    assert ownership.verify_chain(project["shared"]) == (True, "")
    journal = project["shared"] / ownership.JOURNAL_NAME
    lines = journal.read_text(encoding="utf-8").split("\n")
    lines[0] = lines[0].replace('"op": "test"', '"op": "edited"')
    journal.write_text("\n".join(lines), encoding="utf-8")
    ok, detail = ownership.verify_chain(project["shared"])
    assert not ok and "line 2" in detail


def test_journal_chain_survives_rotation(project: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ownership, "JOURNAL_ROTATE_BYTES", 10)
    for i in range(3):
        _lib_write(project, "core", REL, f"v{i}\n")
    assert list(project["shared"].glob("_journal.*.jsonl"))
    assert ownership.verify_chain(project["shared"]) == (True, "")


def test_single_agent_project_is_silent(tmp_path: Path) -> None:
    p = _project(tmp_path, agents=("core",))
    ownership.record_write(p["core"], "test", "proposals/core/x.md", None, "0" * 64)
    assert not (p["shared"] / ownership.JOURNAL_NAME).exists()
    assert ownership.scan(p["core"])["notices"] == []
    assert _hook(p["core"]) is None


def test_hook_reaches_owner_and_agent(project: dict) -> None:
    _put(project, REL, "v1\n")
    assert _hook(project["platform"]) is None  # baseline, nothing to say
    _lib_write(project, "core", REL, "v2 by core\n")
    _put(project, "proposals/platform/p-0002-y.md", "dropped in raw\n")
    out = _hook(project["platform"])
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    owner = out["systemMessage"]
    assert "[ALERT]" in owner and "from unknown" in owner and "[info]" in owner
    assert "Report these to the owner" in out["hookSpecificOutput"]["additionalContext"]
    left = ownership.list_notices(project["shared"], "platform")
    assert [n["severity"] for n in left] == ["alert"]  # info acked once shown
    acked = list((project["shared"] / "notices" / "platform" / "acked").glob("*.json"))
    assert json.loads(acked[0].read_text(encoding="utf-8"))["acked_by"] == "shown"


def test_every_clone_sees_project_wide_count(project: dict) -> None:
    _put(project, REL, "v1\n")
    ownership.scan(project["platform"])
    _put(project, REL, "tampered\n")
    ownership.scan(project["platform"])
    out = _hook(project["content"])
    assert "[Notices pending] platform: 1" in out["systemMessage"]


def test_broken_chain_is_shown(project: dict) -> None:
    _lib_write(project, "core", REL, "a\n")
    _lib_write(project, "core", REL, "b\n")
    journal = project["shared"] / ownership.JOURNAL_NAME
    journal.write_text(journal.read_text(encoding="utf-8").split("\n", 1)[1], encoding="utf-8")
    out = _hook(project["platform"])
    assert "journal chain is broken" in out["systemMessage"]


def test_ack_rules(project: dict, capsys: pytest.CaptureFixture) -> None:
    nid = ownership.write_notice(project["shared"], "platform", kind="foreign-write",
                                 severity="alert", frm="unknown", paths=[REL])
    assert notices.main(["--project-root", str(project["content"]),
                         "ack", nid, "--agent", "platform"]) == 1
    assert notices.main(["--project-root", str(project["platform"]), "ack", nid]) == 0
    assert ownership.list_notices(project["shared"], "platform") == []
    nid2 = ownership.write_notice(project["shared"], "platform", kind="foreign-write",
                                  severity="alert", frm="unknown", paths=[REL])
    assert notices.main(["--project-root", str(project["core"]),
                         "ack", nid2, "--agent", "platform"]) == 0


def test_proposal_lib_journals_its_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list = []
    monkeypatch.setattr(ownership, "shared_rel", lambda root, path: "proposals/content/p.md")
    monkeypatch.setattr(ownership, "record_write",
                        lambda root, op, rel, before, after: calls.append((op, rel, before is None, after is None)))
    path = tmp_path / "p-9400-x.md"
    path.write_text("---\nid: P-9400\nagent: content\nstatus: pending\ncreated: 2026-11-06\n---\n\n"
                    "# Proposal P-9400: x\n\n## Current State (read, not assumed)\n\nRead `a.py:1`.\n\n"
                    "## State Log\n\n- x\n", encoding="utf-8")
    monkeypatch.setattr(pl, "detect_agent", lambda: "core")
    monkeypatch.setattr(pl, "_core_agent", lambda: "core")
    monkeypatch.setattr(pl, "find_by_id", lambda pid: path)
    monkeypatch.setattr(pl, "_lock_path", lambda: tmp_path / ".lock")
    monkeypatch.setattr(pl, "_lock_timeout", lambda: 5)
    monkeypatch.setattr(pl, "_write_snapshot", lambda *a, **k: None)
    pl.transition_proposal("P-9400", "approved", note="core")
    pl.link_proposal("P-9400", ["notes/x.md"])
    assert calls == [("transition pending->approved", "proposals/content/p.md", False, False),
                     ("link", "proposals/content/p.md", False, False)]
