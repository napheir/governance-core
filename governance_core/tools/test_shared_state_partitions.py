"""shared_state is partitioned per agent (P-0135 Phase 2).

edit-write-guard used to let every role write anything under shared_state,
scope-guard did not look at shell writes there, and proposal_lib had no
owner check, so one agent could rewrite another agent's proposals. Now a
business agent writes only its partitions (proposals/<self>/** plus config
`shared_state_partitions`); ledger, lock, journal and notices (plus config
`shared_state_lib_only`) are written only by the libs; proposal_lib
mutations need the owner or core. contracts/shared_state_ownership.md §2-3.

The guards run as Claude Code runs them: a subprocess fed hook JSON.

Run from repo root:
    python -m pytest tools/test_shared_state_partitions.py -q
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_HOOKS = next(p for p in (_HERE.parent / "hooks", _HERE.parent / ".claude" / "hooks")
              if (p / "_guard_common.py").is_file())
sys.path.insert(0, str(_HERE))
import proposal_lib as pl  # noqa: E402


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"),
                                                  _HOOKS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def project(tmp_path: Path) -> dict:
    """A three-agent project: core + platform + content clones and shared_state."""
    proj = tmp_path / "proj"
    shared = proj / "shared_state"
    cfg = {
        "project_name": "proj", "install_root": str(tmp_path),
        "shared_state_root": str(shared), "core_agent_name": "core",
        "core_branches": ["master"], "ritual_phrase": "OK",
        "agents": [
            {"name": "core", "branch": "master", "clone_dir": "agent-core"},
            {"name": "platform", "branch": "feature/platform",
             "clone_dir": "agent-platform"},
            {"name": "content", "branch": "feature/content",
             "clone_dir": "agent-content"}],
        "shared_state_partitions": ["todos/{agent}/**"],
        "shared_state_lib_only": ["todos/_ledger.json*"],
    }
    clones = {}
    for name in ("core", "platform", "content"):
        clone = proj / f"agent-{name}"
        (clone / ".governance").mkdir(parents=True)
        (clone / ".governance" / "config.json").write_text(json.dumps(cfg),
                                                           encoding="utf-8")
        hooks = clone / ".claude" / "hooks"
        hooks.mkdir(parents=True)
        for f in ("_guard_common.py", "edit-write-guard.py", "scope-guard.py"):
            shutil.copy2(_HOOKS / f, hooks / f)
        (clone / "agent_rules").mkdir()
        (clone / "agent_rules" / f"{name}.allow.txt").write_text(
            f"services/{name}/\n", encoding="utf-8")
        clones[name] = clone
    for rel in ("proposals/platform", "proposals/content", "todos/platform",
                "todos/content", "todos/active"):
        (shared / rel).mkdir(parents=True)
    return {"shared": shared, **clones}


def _hook(clone: Path, name: str, payload: dict) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, str(clone / ".claude" / "hooks" / f"{name}.py")],
                          input=json.dumps(payload), capture_output=True,
                          encoding="utf-8", errors="replace", env=env, timeout=60)


def _write(clone: Path, target: Path) -> subprocess.CompletedProcess:
    return _hook(clone, "edit-write-guard", {
        "tool_name": "Write",
        "tool_input": {"file_path": str(target), "content": "x\n"}})


def _bash(clone: Path, command: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return _hook(clone, "scope-guard", {
        "tool_name": "Bash", "tool_input": {"command": command},
        "cwd": str(cwd or clone)})


# --- classification (_guard_common.shared_state_access) ---------------------

@pytest.mark.parametrize("rel,kind", [
    ("proposals/platform/p-0001-x.md", "own"),
    ("todos/platform/t-1.md", "own"),
    ("proposals/content/p-0002-y.md", "foreign"),
    ("todos/content/t-2.md", "foreign"),
    ("proposals/_id_ledger.json", "lib-only"),
    ("proposals/_id_ledger.json.lock", "lib-only"),
    ("_journal.jsonl", "lib-only"),
    ("notices/platform/n.json", "lib-only"),
    ("todos/_ledger.json", "lib-only"),
    ("todos/active/t-3.md", "other"),
    ("knowledge/dashboard.html", "other"),
])
def test_classification(project: dict, rel: str, kind: str) -> None:
    gc = _load("_guard_common")
    got, got_rel = gc.shared_state_access(str(project["shared"] / rel), "platform",
                                          str(project["platform"]))
    assert (got, got_rel) == (kind, rel)


def test_outside_shared_state(project: dict) -> None:
    gc = _load("_guard_common")
    kind, _ = gc.shared_state_access(str(project["platform"] / "x.py"), "platform",
                                     str(project["platform"]))
    assert kind == "outside"


@pytest.mark.skipif(os.name != "nt", reason="Windows path forms")
def test_git_bash_and_case_forms_on_windows(project: dict) -> None:
    gc = _load("_guard_common")
    target = str(project["shared"] / "proposals" / "content" / "p.md")
    drive, rest = target[0].lower(), target[2:].replace("\\", "/")
    assert gc.shared_state_access(f"/{drive}{rest}", "platform",
                                  str(project["platform"]))[0] == "foreign"
    assert gc.shared_state_access(target.upper(), "platform",
                                  str(project["platform"]))[0] == "foreign"


# --- edit-write-guard ----------------------------------------------------------

def test_edit_own_proposal_allowed(project: dict) -> None:
    res = _write(project["platform"], project["shared"] / "proposals/platform/p-1.md")
    assert res.returncode == 0, res.stderr


def test_edit_other_agents_proposal_blocked(project: dict) -> None:
    res = _write(project["platform"], project["shared"] / "proposals/content/p-2.md")
    assert res.returncode == 2 and "another agent's shared_state partition" in res.stderr


@pytest.mark.parametrize("rel", ["proposals/_id_ledger.json", "_journal.jsonl",
                                 "notices/content/n.json", "todos/active/t.md"])
def test_edit_lib_only_and_unpartitioned_blocked(project: dict, rel: str) -> None:
    res = _write(project["platform"], project["shared"] / rel)
    assert res.returncode == 2, res.stderr


def test_edit_configured_partition_allowed(project: dict) -> None:
    res = _write(project["platform"], project["shared"] / "todos/platform/t.md")
    assert res.returncode == 0, res.stderr


def test_core_may_write_anywhere(project: dict) -> None:
    res = _write(project["core"], project["shared"] / "proposals/content/p-2.md")
    assert res.returncode == 0, res.stderr


# --- scope-guard -----------------------------------------------------------------

@pytest.mark.parametrize("command", [
    "echo x > ../shared_state/proposals/content/p.md",
    "echo x >> ../shared_state/proposals/content/p.md",
    "cp /tmp/a ../shared_state/proposals/_id_ledger.json",
    "cd ../shared_state && rm proposals/content/p.md",
    "sed -i 's/a/b/' ../shared_state/todos/active/t.md",
    "mv ../shared_state/proposals/content/p.md /tmp/x",
    "tee ../shared_state/_journal.jsonl < /dev/null",
    'touch "../shared_state/proposals/content/with space.md"',
])
def test_bash_foreign_writes_blocked(project: dict, command: str) -> None:
    res = _bash(project["platform"], command)
    assert res.returncode == 2 and "not one of your partitions" in res.stderr, \
        (command, res.stderr)


@pytest.mark.parametrize("command", [
    "echo x > ../shared_state/proposals/platform/p.md",
    "cat ../shared_state/proposals/content/p.md",
    "cp ../shared_state/proposals/content/p.md /tmp/copy.md",
    "grep -r foo ../shared_state/",
    "python tools/proposal_lib.py list",
    "echo '> ../shared_state/proposals/content/p.md'",
    "git status 2>/dev/null",
])
def test_bash_reads_and_own_writes_allowed(project: dict, command: str) -> None:
    res = _bash(project["platform"], command)
    assert res.returncode == 0, (command, res.stderr)


def test_bash_absolute_git_bash_path_blocked(project: dict) -> None:
    target = str(project["shared"] / "proposals" / "content" / "p.md")
    if os.name == "nt":
        target = "/" + target[0].lower() + target[2:].replace("\\", "/")
    res = _bash(project["platform"], f"echo x > {target}")
    assert res.returncode == 2, res.stderr


# --- proposal_lib owner checks -------------------------------------------------

def _proposal(tmp_path: Path, owner: str, status: str = "pending") -> Path:
    path = tmp_path / f"p-9300-{owner}.md"
    path.write_text(
        f"---\nid: P-9300\nagent: {owner}\nstatus: {status}\ncreated: 2026-11-06\n---\n\n"
        "# Proposal P-9300: x\n\n## Current State (read, not assumed)\n\n"
        "Read `tools/x.py:1`.\n\n## Approval Criteria\n\n"
        "- [ ] ok — human-verify: yes\n\n## State Log\n\n- 2026-11-06: draft created\n",
        encoding="utf-8")
    return path


@pytest.fixture()
def lib(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """proposal_lib against one temp file, with a chosen calling agent."""
    state = {"caller": "platform"}
    monkeypatch.setattr(pl, "detect_agent", lambda: state["caller"])
    monkeypatch.setattr(pl, "_core_agent", lambda: "core")
    monkeypatch.setattr(pl, "_lock_path", lambda: tmp_path / ".lock")
    monkeypatch.setattr(pl, "_lock_timeout", lambda: 5)
    monkeypatch.setattr(pl, "_write_snapshot", lambda *a, **k: None)
    monkeypatch.setattr(pl, "_agents", lambda: ["core", "platform", "content"])
    monkeypatch.setattr(pl, "find_by_id", lambda pid: state["path"])
    return state


def test_lib_owner_may_transition_and_is_logged(tmp_path: Path, lib: dict) -> None:
    lib["path"] = _proposal(tmp_path, "platform")
    pl.transition_proposal("P-9300", "approved", note="owner: ok")
    assert "pending → approved (owner: ok) by platform" in lib["path"].read_text(encoding="utf-8")


def test_lib_other_agent_may_not_transition(tmp_path: Path, lib: dict) -> None:
    lib["path"] = _proposal(tmp_path, "content")
    before = lib["path"].read_bytes()
    with pytest.raises(PermissionError, match="belongs to 'content'"):
        pl.transition_proposal("P-9300", "approved", note="x")
    assert lib["path"].read_bytes() == before


def test_lib_core_may_transition_any(tmp_path: Path, lib: dict) -> None:
    lib["caller"] = "core"
    lib["path"] = _proposal(tmp_path, "content")
    pl.transition_proposal("P-9300", "approved", note="core curation")
    assert "by core" in lib["path"].read_text(encoding="utf-8")


@pytest.mark.parametrize("call", [
    lambda: pl.link_proposal("P-9300", ["notes/x.md"]),
    lambda: pl.set_handoff_to("P-9300", None),
])
def test_lib_other_mutations_need_owner(tmp_path: Path, lib: dict, call) -> None:
    lib["path"] = _proposal(tmp_path, "content")
    with pytest.raises(PermissionError):
        call()


def test_lib_orchestrate_needs_owner(tmp_path: Path, lib: dict) -> None:
    lib["path"] = _proposal(tmp_path, "content", status="draft")
    with pytest.raises(PermissionError):
        pl.set_orchestration("P-9300", "workflow")


def test_lib_force_agent_archive_is_core_only(tmp_path: Path, lib: dict,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    lib["path"] = _proposal(tmp_path, "content", status="rejected")
    monkeypatch.setattr(pl, "_in_flight_root", lambda: tmp_path)
    with pytest.raises(PermissionError, match="only the core agent"):
        pl.archive_proposal("P-9300", force_agent=True)


def test_lib_create_under_another_agent_needs_core(lib: dict) -> None:
    with pytest.raises(PermissionError, match="only the core"):
        pl.create_proposal(slug="x", title="x", agent="content")
