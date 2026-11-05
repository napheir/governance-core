"""Tests for config-derived agent identity + guard hardening (P-0129 Phase A).

Builds a deva-vani-shaped multi-clone layout in a temp dir:

    <tmp>/workshop/<project>/agent-{core,platform,experience,content}/
        .governance/config.json   (4 agents, install_root = <tmp>/workshop)
        .claude/hooks/{_guard_common,edit-write-guard,scope-guard}.py

and checks (1) _guard_common identity resolution, (2) the real guards run
as subprocesses against it -- the failure modes reported by deva-vani:
business clones resolved as core (F1), sibling-clone Bash refs never matched
in the nested layout (F7), a non-core agent able to edit its own guard (F8).

Runs from either layout: installed (tools/ next to .claude/hooks/) or
package source (governance_core/tools/ next to governance_core/hooks/).
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
AGENTS = [
    {"name": "core", "branch": "master", "clone_dir": "agent-core"},
    {"name": "platform", "branch": "feature/platform", "clone_dir": "agent-platform"},
    {"name": "experience", "branch": "feature/experience", "clone_dir": "agent-experience"},
    {"name": "content", "branch": "feature/content", "clone_dir": "agent-content"},
]
GUARD_FILES = ("_guard_common.py", "edit-write-guard.py", "scope-guard.py")


def _hooks_dir() -> Path:
    """Directory holding the guard sources in the current layout."""
    for candidate in (_HERE.parent / ".claude" / "hooks", _HERE.parent / "hooks"):
        if (candidate / "_guard_common.py").is_file():
            return candidate
    pytest.skip("_guard_common.py not found next to tools/")


def _load_guard_common():
    """Import _guard_common from the current layout by path."""
    spec = importlib.util.spec_from_file_location(
        "_gc_guard_common_test", _hooks_dir() / "_guard_common.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_config(clone: Path, agents: list, install_root: Path) -> None:
    """Write a minimal .governance/config.json into `clone`."""
    gov = clone / ".governance"
    gov.mkdir(parents=True, exist_ok=True)
    (gov / "config.json").write_text(json.dumps({
        "project_name": "deva-vani",
        "install_root": str(install_root),
        "core_agent_name": "core",
        "agents": agents,
    }), encoding="utf-8")


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """Build the nested 4-clone layout; return the project dir."""
    install_root = tmp_path / "workshop"
    proj = install_root / "deva-vani"
    src = _hooks_dir()
    for agent in AGENTS:
        clone = proj / agent["clone_dir"]
        _write_config(clone, AGENTS, install_root)
        hooks = clone / ".claude" / "hooks"
        hooks.mkdir(parents=True)
        for name in GUARD_FILES:
            shutil.copy2(src / name, hooks / name)
    return proj


# --- identity resolution ----------------------------------------------------


def test_each_clone_resolves_to_its_own_agent(project: Path) -> None:
    gc = _load_guard_common()
    for agent in AGENTS:
        assert gc.resolve_agent(str(project / agent["clone_dir"])) == agent["name"]


def test_detect_role_maps_core_agent_to_core_token(project: Path) -> None:
    gc = _load_guard_common()
    assert gc.detect_role(str(project / "agent-core")) == gc.CORE_ROLE
    assert gc.detect_role(str(project / "agent-platform")) == "platform"


def test_identity_ignores_checked_out_branch(project: Path) -> None:
    """A business clone on `master` is still that business agent (F1 bypass)."""
    gc = _load_guard_common()
    clone = project / "agent-platform"
    subprocess.run(["git", "init", "-q", "-b", "master", str(clone)], check=True)
    assert gc.detect_role(str(clone)) == "platform"


def test_unregistered_clone_is_unresolved_not_core(project: Path) -> None:
    gc = _load_guard_common()
    stray = project / "agent-unknown"
    _write_config(stray, AGENTS, project.parent)
    with pytest.raises(gc.TopologyError, match="not registered"):
        gc.resolve_agent(str(stray))
    assert gc.detect_role(str(stray)) == gc.UNRESOLVED_ROLE
    assert "not registered" in gc.identity_failure(str(stray))


def test_missing_config_is_unresolved(tmp_path: Path) -> None:
    gc = _load_guard_common()
    assert gc.detect_role(str(tmp_path)) == gc.UNRESOLVED_ROLE
    assert "config not found" in gc.identity_failure(str(tmp_path))


def test_core_agent_name_must_be_an_agent(tmp_path: Path) -> None:
    gc = _load_guard_common()
    clone = tmp_path / "agent-core"
    _write_config(clone, [{"name": "lead", "clone_dir": "agent-core"}], tmp_path)
    with pytest.raises(gc.TopologyError, match="core_agent_name"):
        gc.resolve_agent(str(clone))


def test_single_agent_config_resolves_regardless_of_dir_name(tmp_path: Path) -> None:
    """The hub layout: one agent whose clone_dir need not match."""
    gc = _load_guard_common()
    repo = tmp_path / "some-checkout"
    _write_config(repo, [{"name": "core", "branch": "master",
                          "clone_dir": "governance-core"}], tmp_path)
    assert gc.detect_role(str(repo)) == gc.CORE_ROLE


def test_sibling_patterns_match_nested_layout(project: Path) -> None:
    """F7: patterns derive from the real clone location, not install_root."""
    gc = _load_guard_common()
    pats = gc.sibling_clone_patterns(str(project / "agent-platform"))
    assert "deva-vani/agent-experience" in pats
    assert "../agent-content" in pats
    assert not any("agent-platform" in p for p in pats)  # not self
    assert not any("agent-core" in p for p in pats)      # core stays reachable


# --- guards as subprocesses ---------------------------------------------------


def _run_hook(clone: Path, hook: str, payload: dict) -> subprocess.CompletedProcess:
    """Run `clone`'s installed copy of `hook` with `payload` on stdin."""
    return subprocess.run(
        [sys.executable, str(clone / ".claude" / "hooks" / hook)],
        input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", timeout=30, cwd=str(clone),
    )


def _edit(clone: Path, target: Path) -> subprocess.CompletedProcess:
    """Simulate an Edit of `target` from a session in `clone`."""
    return _run_hook(clone, "edit-write-guard.py", {
        "tool_name": "Edit",
        "tool_input": {"file_path": str(target), "old_string": "a",
                       "new_string": "b"},
        "transcript_path": "",
    })


def _bash(clone: Path, command: str) -> subprocess.CompletedProcess:
    """Simulate a Bash call from a session in `clone`."""
    return _run_hook(clone, "scope-guard.py", {
        "tool_name": "Bash", "tool_input": {"command": command},
    })


def test_business_edit_outside_allow_list_is_blocked(project: Path) -> None:
    clone = project / "agent-platform"
    res = _edit(clone, clone / "services" / "api" / "app.py")
    assert res.returncode == 2, res.stderr
    assert "role=platform" in res.stderr


def test_business_edit_inside_allow_list_passes(project: Path) -> None:
    clone = project / "agent-platform"
    rules = clone / "agent_rules"
    rules.mkdir()
    (rules / "platform.allow.txt").write_text("services/\n", encoding="utf-8")
    res = _edit(clone, clone / "services" / "api" / "app.py")
    assert res.returncode == 0, res.stderr


def test_business_edit_of_sibling_clone_is_blocked(project: Path) -> None:
    clone = project / "agent-platform"
    res = _edit(clone, project / "agent-core" / "contracts" / "x.md")
    assert res.returncode == 2, res.stderr
    assert "cross-repo" in res.stderr


@pytest.mark.parametrize("rel", [
    ".claude/hooks/edit-write-guard.py",
    ".claude/hooks/_guard_common.py",
    ".claude/settings.json",
    ".claude/settings.local.json",
])
def test_business_cannot_edit_own_guard(project: Path, rel: str) -> None:
    """F8: enforcement files are not part of the agent's writable .claude/."""
    clone = project / "agent-platform"
    res = _edit(clone, clone / rel)
    assert res.returncode == 2, res.stderr
    assert "self-protection" in res.stderr


def test_business_can_edit_other_claude_files(project: Path) -> None:
    clone = project / "agent-platform"
    res = _edit(clone, clone / ".claude" / "skills" / "learned" / "x.md")
    assert res.returncode == 0, res.stderr


def test_core_edit_anywhere_in_repo_passes(project: Path) -> None:
    clone = project / "agent-core"
    res = _edit(clone, clone / ".claude" / "hooks" / "edit-write-guard.py")
    assert res.returncode == 0, res.stderr


def test_unresolved_identity_blocks_writes(project: Path) -> None:
    clone = project / "agent-platform"
    renamed = project / "agent-renamed"
    clone.rename(renamed)
    res = _edit(renamed, renamed / "services" / "x.py")
    assert res.returncode == 2, res.stderr
    assert "identity unresolved" in res.stderr


@pytest.mark.parametrize("command", [
    "echo hi > ../agent-content/notes.txt",
    "cp a.txt {proj}/agent-experience/a.txt",
    "ls {proj_posix}/agent-experience",
])
def test_business_bash_to_sibling_clone_is_blocked(project: Path, command: str) -> None:
    """F7: absolute (Windows and POSIX drive form) and relative refs all match."""
    proj = project.as_posix()
    proj_posix = "/" + proj[0].lower() + proj[2:] if proj[1:2] == ":" else proj
    clone = project / "agent-platform"
    res = _bash(clone, command.format(proj=proj, proj_posix=proj_posix))
    assert res.returncode == 2, res.stderr
    assert "role=platform" in res.stderr


def test_business_bash_referencing_core_clone_passes(project: Path) -> None:
    clone = project / "agent-platform"
    res = _bash(clone, "ls ../agent-core/tools")
    assert res.returncode == 0, res.stderr


def test_core_bash_to_sibling_clone_passes(project: Path) -> None:
    clone = project / "agent-core"
    res = _bash(clone, "ls ../agent-content")
    assert res.returncode == 0, res.stderr
