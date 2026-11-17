"""Journaling an agent's shell writes to shared_state partition files (P-0138).

Through 0.52.0 the own-write hooks journaled Edit/Write only. An agent's own
`sed -i` (or `>`, `mv` ...) on its own todo therefore surfaced as an "actor
unknown" alert at its next Edit or SessionStart (deva-vani, 2026-11-13). Now
the hooks also run for Bash: the capture stores the shas of the targets
scope-guard's parser finds, and the journal records each one that changed
(op/via "bash"). Writes the parser cannot see still alert.
contracts/shared_state_ownership.md §4 (1.3.0).

Run from repo root:
    python -m pytest tools/test_ownership_shell_writes.py -q
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
_COPIED = ("_guard_common.py", "own-write-capture.py", "own-write-journal.py",
           "own-write-journal-failure.py")
TODO = "todos/platform/active/t-0005-x.md"


def _project(tmp_path: Path) -> dict:
    proj = tmp_path / "proj"
    shared = proj / "shared_state"
    agents = ("core", "platform", "content")
    cfg = {
        "project_name": "proj", "install_root": str(tmp_path),
        "shared_state_root": str(shared), "core_agent_name": "core",
        "core_branches": ["master"], "ritual_phrase": "OK",
        "shared_state_partitions": ["todos/{agent}/**"],
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
    (shared / "todos" / "platform" / "active").mkdir(parents=True)
    (shared / "todos" / "platform" / "done").mkdir(parents=True)
    return out


@pytest.fixture()
def project(tmp_path: Path) -> dict:
    return _project(tmp_path)


def _put(p: dict, rel: str, text: str) -> Path:
    path = p["shared"] / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def _run(clone: Path, hook: str, payload: dict, env_extra: dict | None = None) -> None:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", **(env_extra or {}))
    res = subprocess.run([sys.executable, str(clone / ".claude" / "hooks" / f"{hook}.py")],
                         input=json.dumps(payload), capture_output=True,
                         encoding="utf-8", env=env, timeout=60)
    assert res.returncode == 0 and res.stdout == "", (res.stdout, res.stderr)


_CALLS = [0]


def _bash(p: dict, actor: str, command: str, effect, *, post: str | None = "own-write-journal",
          extra_input: dict | None = None) -> dict:
    """A Bash call as Claude Code runs it: Pre hook, the command's effect, Post hook."""
    _CALLS[0] += 1
    payload = {"tool_name": "Bash", "tool_input": dict({"command": command}, **(extra_input or {})),
               "cwd": str(p["shared"]), "session_id": "sess-1",
               "tool_use_id": f"toolu_bash_{_CALLS[0]}"}
    _run(p[actor], "own-write-capture", payload)
    effect()
    if post:
        _run(p[actor], post, payload)
    return payload


def _edit(p: dict, actor: str, rel: str, text: str) -> None:
    """An Edit as Claude Code runs it: Pre hook, the write, Post hook."""
    _CALLS[0] += 1
    payload = {"tool_name": "Edit", "tool_input": {"file_path": str(p["shared"] / rel)},
               "session_id": "sess-1", "tool_use_id": f"toolu_edit_{_CALLS[0]}"}
    _run(p[actor], "own-write-capture", payload)
    _put(p, rel, text)
    _run(p[actor], "own-write-journal", payload)


def _posix(path: Path) -> str:
    return path.as_posix()


def _pending(p: dict, actor: str) -> list:
    return sorted((p[actor] / ownership.PENDING_REL).glob("*.json"))


def test_field_case_edit_sed_edit_gives_no_alert(project: dict) -> None:
    path = _put(project, TODO, "experience confirmed; content pending\n")
    ownership.scan(project["platform"])
    _edit(project, "platform", TODO, "experience confirmed; content pending.\n")
    _bash(project, "platform", f"sed -i 's/content pending/content confirmed/' {_posix(path)}",
          lambda: _put(project, TODO, "experience confirmed; content confirmed.\n"))
    _edit(project, "platform", TODO, "all confirmed.\n")
    assert ownership.list_notices(project["shared"], "platform") == []
    assert ownership.scan(project["platform"])["new"] == []
    ops = [(r["op"], r["via"]) for r in ownership.journal_records(project["shared"]) if "path" in r]
    assert ops == [("edit:Edit", "edit"), ("bash", "bash"), ("edit:Edit", "edit")]


def test_without_bash_hooks_the_field_case_alerts(project: dict) -> None:
    """Calibration: 0.52.0 ran no hook for Bash, so the same sequence alerts."""
    _put(project, TODO, "v1\n")
    ownership.scan(project["platform"])
    _edit(project, "platform", TODO, "v2\n")
    _put(project, TODO, "v3 by sed\n")  # the shell write, no hook ran
    _edit(project, "platform", TODO, "v4\n")
    (n,) = ownership.list_notices(project["shared"], "platform")
    assert (n["severity"], n["from"]) == ("alert", "unknown")
    assert "before edit:Edit by platform" in n["detail"]


@pytest.mark.parametrize("make_cmd", [
    lambda t: f"echo hi > {t}",
    lambda t: f"echo hi | tee -a {t}",
    lambda t: f"cp /dev/null {t}",
])
def test_own_shell_writes_are_not_news(project: dict, make_cmd) -> None:
    path = _put(project, TODO, "v1\n")
    ownership.scan(project["platform"])
    _bash(project, "platform", make_cmd(_posix(path)), lambda: _put(project, TODO, "hi\n"))
    assert ownership.scan(project["platform"])["new"] == []
    assert ownership.list_notices(project["shared"], "platform") == []


def test_mv_into_a_directory_and_rm_are_journaled(project: dict) -> None:
    src = _put(project, TODO, "done now\n")
    other = _put(project, "todos/platform/active/t-0006-y.md", "drop me\n")
    ownership.scan(project["platform"])
    done = project["shared"] / "todos" / "platform" / "done"
    _bash(project, "platform", f"mv {_posix(src)} {_posix(done)}/",
          lambda: shutil.move(str(src), str(done / src.name)))
    _bash(project, "platform", f"rm {_posix(other)}", other.unlink)
    assert ownership.scan(project["platform"])["new"] == []
    recs = [(r["path"], r["sha_before"] is None, r["sha_after"] is None)
            for r in ownership.journal_records(project["shared"]) if "path" in r]
    assert sorted(recs) == sorted([
        ("todos/platform/active/t-0005-x.md", False, True),
        ("todos/platform/done/t-0005-x.md", True, False),
        ("todos/platform/active/t-0006-y.md", False, True)])


def test_core_shell_write_into_another_partition_is_an_attributed_alert(project: dict) -> None:
    path = _put(project, TODO, "v1\n")
    ownership.scan(project["platform"])
    _bash(project, "core", f"sed -i 's/v1/v2/' {_posix(path)}",
          lambda: _put(project, TODO, "v2\n"))
    (n,) = ownership.list_notices(project["shared"], "platform")
    assert (n["severity"], n["from"], n["detail"]) == ("alert", "core", "bash by core")
    assert ownership.scan(project["platform"])["new"] == []  # told once


def test_unparsed_script_write_still_alerts(project: dict) -> None:
    _put(project, TODO, "v1\n")
    ownership.scan(project["platform"])
    _bash(project, "platform", "python - <<'EOF'\nopen('t.md', 'w').write('x')\nEOF",
          lambda: _put(project, TODO, "written by a script\n"))
    assert len(ownership.scan(project["platform"])["new"]) == 1
    (n,) = ownership.list_notices(project["shared"], "platform")
    assert (n["severity"], n["from"]) == ("alert", "unknown")


def test_no_post_hook_means_the_write_still_alerts(project: dict) -> None:
    path = _put(project, TODO, "v1\n")
    ownership.scan(project["platform"])
    _bash(project, "platform", f"echo x > {_posix(path)}",
          lambda: _put(project, TODO, "x\n"), post=None)
    assert len(ownership.scan(project["platform"])["new"]) == 1
    (n,) = ownership.list_notices(project["shared"], "platform")
    assert (n["severity"], n["from"]) == ("alert", "unknown")


def test_failed_command_is_journaled_by_the_failure_hook(project: dict) -> None:
    path = _put(project, TODO, "v1\n")
    ownership.scan(project["platform"])
    _bash(project, "platform", f"echo x > {_posix(path)} && false",
          lambda: _put(project, TODO, "x\n"), post="own-write-journal-failure")
    assert ownership.scan(project["platform"])["new"] == []
    assert _pending(project, "platform") == []


def test_background_call_makes_no_capture(project: dict) -> None:
    path = _put(project, TODO, "v1\n")
    _bash(project, "platform", f"sleep 5; echo x > {_posix(path)}", lambda: None,
          post=None, extra_input={"run_in_background": True})
    assert _pending(project, "platform") == []


def test_bash_capture_records_every_target(project: dict) -> None:
    path = _put(project, TODO, "v1\n")
    done = project["shared"] / "todos" / "platform" / "done"
    _bash(project, "platform", f"cp {_posix(path)} {_posix(done)} && echo y > {_posix(path)}",
          lambda: None, post=None)
    (pending,) = _pending(project, "platform")
    data = json.loads(pending.read_text(encoding="utf-8"))
    assert data["tool"] == "Bash" and data["dirs"] == ["todos/platform/done"]
    assert data["files"] == {TODO: ownership.file_sha(path)}
    assert "ts" in data


def test_commands_without_a_shared_state_target_skip_the_package(project: dict,
                                                                  tmp_path: Path) -> None:
    fake = tmp_path / "fake_pkg" / "governance_core"
    fake.mkdir(parents=True)
    marker = tmp_path / "imported.txt"
    (fake / "__init__.py").write_text(
        f"open({str(marker)!r}, 'w').write('x')\nraise ImportError('fake')\n",
        encoding="utf-8")
    env = {"PYTHONPATH": str(fake.parent)}
    base = {"tool_name": "Bash", "cwd": str(project["platform"]), "session_id": "s",
            "tool_use_id": "toolu_fast"}
    _run(project["platform"], "own-write-capture",
         dict(base, tool_input={"command": "python -m pytest tools/ -q > out.txt 2>&1"}), env)
    assert not marker.exists()
    _run(project["platform"], "own-write-capture",
         dict(base, tool_input={"command": f"echo x > {_posix(project['shared'] / TODO)}"}), env)
    assert marker.exists()  # sanity: a shared_state target does import it


def test_one_parser_for_block_and_journal() -> None:
    scope_guard = (_HOOKS / "scope-guard.py").read_text(encoding="utf-8")
    assert "def _write_targets" not in scope_guard
    assert "shell_write_targets as _write_targets" in scope_guard


def test_manifest_runs_the_journal_for_bash_and_on_failure() -> None:
    manifest = json.loads((_HOOKS / "hooks_manifest.json").read_text(encoding="utf-8"))["hooks"]
    for name in ("own-write-capture.py", "own-write-journal.py", "own-write-journal-failure.py"):
        assert "Bash" in manifest[name]["matcher"].split("|")
    assert manifest["own-write-journal-failure.py"]["event"] == "PostToolUseFailure"
