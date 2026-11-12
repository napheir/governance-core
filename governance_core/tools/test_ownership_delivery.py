"""Getting ownership notices in front of the owner (P-0136).

0.51.0 acked an info notice the moment the SessionStart hook emitted it, and
one owner never saw that message, so the notice was gone unseen. Now an info
notice is acked only after two distinct sessions have shown it (a resume
keeps the session id and does not count twice), and acked notices can be
reviewed with `notices.py list --recent`. The 0.51.1 first-prompt gate
(notice-gate) was withdrawn in 0.51.2: the prompt it blocked could be a
peer's cross-session message, which was then lost.
contracts/shared_state_ownership.md §5 (1.1.1).

Run from repo root:
    python -m pytest tools/test_ownership_delivery.py -q
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

_COPIED = ("_guard_common.py", "foreign-change-notice.py")
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


def _put(p: dict, rel: str, text: str) -> None:
    path = p["shared"] / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _core_writes(p: dict, text: str) -> None:
    path = p["shared"] / REL
    before = ownership.file_sha(path)
    _put(p, REL, text)
    ownership.record_write(p["core"], "dispatch", REL, before, ownership.file_sha(path))


def _hook(clone: Path, hook: str, payload: dict) -> dict | None:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    res = subprocess.run([sys.executable, str(clone / ".claude" / "hooks" / f"{hook}.py")],
                         input=json.dumps(payload), capture_output=True,
                         encoding="utf-8", env=env, timeout=60)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout) if res.stdout.strip() else None


def _start(p: dict, session: str) -> dict | None:
    return _hook(p["platform"], "foreign-change-notice",
                 {"session_id": session, "source": "startup"})


def _info_ready(p: dict) -> None:
    _put(p, REL, "v1\n")
    ownership.scan(p["platform"])
    _core_writes(p, "core dispatches a todo\n")


def _alert_ready(p: dict) -> str:
    _put(p, REL, "v1\n")
    ownership.scan(p["platform"])
    _put(p, REL, "tampered\n")
    (nid,) = ownership.scan(p["platform"])["new"]
    return nid


def test_info_survives_one_session_and_acks_at_the_second(project: dict) -> None:
    _info_ready(project)
    out = _start(project, "s1")
    assert "[info]" in out["systemMessage"]
    (n,) = ownership.list_notices(project["shared"], "platform")
    assert n["shown"] == ["s1"]
    _start(project, "s1")  # resume / compact keeps the id
    assert len(ownership.list_notices(project["shared"], "platform")) == 1
    _start(project, "s2")
    assert ownership.list_notices(project["shared"], "platform") == []
    (acked,) = ownership.list_acked(project["shared"], "platform")
    assert acked["acked_by"] == "shown-2" and acked["shown"] == ["s1", "s2"]


def test_no_session_id_shows_but_marks_nothing(project: dict) -> None:
    _info_ready(project)
    out = _hook(project["platform"], "foreign-change-notice", {})
    assert "[info]" in out["systemMessage"]
    (n,) = ownership.list_notices(project["shared"], "platform")
    assert "shown" not in n


def test_alerts_are_never_acked_by_showing(project: dict) -> None:
    nid = _alert_ready(project)
    for session in ("s1", "s2", "s3"):
        _start(project, session)
    (n,) = ownership.list_notices(project["shared"], "platform")
    assert n["id"] == nid and "shown" not in n
    with pytest.raises(ownership.OwnershipError):
        ownership.mark_shown(project["shared"], "platform", nid, "s9")


def test_recent_lists_acked_notices_within_days(project: dict, capsys) -> None:
    nid = _alert_ready(project)
    ownership.ack_notice(project["shared"], "platform", nid, "platform")
    args = ["--project-root", str(project["platform"]), "list", "--recent"]
    assert notices.main(args) == 0
    out = capsys.readouterr().out
    assert nid in out and "by platform" in out
    acked = project["shared"] / "notices" / "platform" / "acked" / f"{nid}.json"
    data = json.loads(acked.read_text(encoding="utf-8"))
    data["acked_at"] = "2000-01-01T00:00:00Z"
    acked.write_text(json.dumps(data), encoding="utf-8")
    assert notices.main(args + ["--days", "3"]) == 0
    assert "no notices acked in the last 3 day(s)" in capsys.readouterr().out


def test_no_prompt_gate_is_shipped() -> None:
    """0.51.2 withdrew notice-gate: a blocked prompt is discarded, and the
    first prompt of a session can be a peer's cross-session message."""
    manifest = json.loads((_HOOKS / "hooks_manifest.json").read_text(encoding="utf-8"))
    assert "notice-gate.py" not in manifest["hooks"]
    assert not any(h["event"] == "UserPromptSubmit" and "notice" in name
                   for name, h in manifest["hooks"].items())
    assert not (_HOOKS / "notice-gate.py").exists()
