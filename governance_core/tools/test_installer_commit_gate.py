"""Commit-time scope gate installed by install (P-0129 Phase F, F9).

Before, install shipped no per-agent allow list and no pre-commit hook, and
check_scope.py had no notion of the core agent (`--agent core` was FATAL
without core.allow.txt): the constitution's commit-time scope layer did not
exist in any consumer. install now seeds an empty (deny-all) allow list per
non-core agent, installs a pre-commit stub running
`tools/check_scope.py --staged-only` (identity resolved from config; the core
agent always passes), and never overwrites a foreign hook.

The end-to-end cases run real `git commit`s through the installed hook.
Only the auth-code signature check is stubbed.

Run from repo root:
    python -m pytest tools/test_installer_commit_gate.py -q
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from governance_core import installer

AGENTS = [
    {"name": "core", "branch": "master", "clone_dir": "agent-core"},
    {"name": "platform", "branch": "feature/platform", "clone_dir": "agent-platform"},
]


@pytest.fixture(autouse=True)
def _stub_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub only the auth-code signature check."""
    monkeypatch.setattr(installer.codec, "verify_auth_code",
                        lambda code, key: {"consumer_id": "test-consumer"})


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    """Run git in `repo` with a throwaway identity."""
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com",
         "-C", str(repo), *args],
        capture_output=True, encoding="utf-8", errors="replace", timeout=60)


def _clone(tmp_path: Path, name: str, git: bool = True) -> Path:
    """Create <tmp>/proj/<name>/, optionally as a git repo on master."""
    clone = tmp_path / "proj" / name
    clone.mkdir(parents=True)
    if git:
        assert _git(clone, "init", "-q", "-b", "master").returncode == 0
    return clone


def _install(clone: Path) -> int:
    """Run a real install with the 2-agent topology."""
    return installer.install(clone, config_overrides={
        "project_name": "proj", "core_agent_name": "core", "agents": AGENTS,
        "shared_state_root": str(clone.parent / "shared_state"),
    }, auth_code="stub", accept_candidate_uplink=True)


def _hook(clone: Path) -> Path:
    return clone / ".git" / "hooks" / "pre-commit"


def test_allow_lists_seeded_for_non_core_only(tmp_path: Path) -> None:
    clone = _clone(tmp_path, "agent-core")
    assert _install(clone) == 0
    seed = clone / "agent_rules" / "platform.allow.txt"
    assert seed.is_file()
    assert installer._allow_rule_count(clone, "platform") == 0
    assert not (clone / "agent_rules" / "core.allow.txt").exists()


def test_seeded_allow_list_edits_survive_reinstall(tmp_path: Path) -> None:
    clone = _clone(tmp_path, "agent-core")
    assert _install(clone) == 0
    seed = clone / "agent_rules" / "platform.allow.txt"
    seed.write_text("services/\n", encoding="utf-8")
    assert _install(clone) == 0
    assert seed.read_text(encoding="utf-8") == "services/\n"


def test_pre_commit_installed_lf_and_idempotent(tmp_path: Path) -> None:
    clone = _clone(tmp_path, "agent-core")
    assert _install(clone) == 0
    data = _hook(clone).read_bytes()
    assert installer.PRE_COMMIT_MARKER.encode() in data
    assert b"\r\n" not in data
    assert _install(clone) == 0
    assert _hook(clone).read_bytes() == data


def test_foreign_pre_commit_left_alone(tmp_path: Path) -> None:
    clone = _clone(tmp_path, "agent-core")
    _hook(clone).parent.mkdir(parents=True, exist_ok=True)
    _hook(clone).write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
    assert _install(clone) == 0
    assert _hook(clone).read_text(encoding="utf-8") == "#!/bin/sh\necho mine\n"


def test_hooks_path_owner_gets_no_stub(tmp_path: Path) -> None:
    clone = _clone(tmp_path, "agent-core")
    assert _git(clone, "config", "core.hooksPath", ".husky").returncode == 0
    assert _install(clone) == 0
    assert not _hook(clone).exists()


def test_non_git_dir_installs_without_hook(tmp_path: Path) -> None:
    clone = _clone(tmp_path, "agent-core", git=False)
    assert _install(clone) == 0
    assert not (clone / ".git").exists()


def _commit_file(clone: Path, rel: str) -> subprocess.CompletedProcess:
    """Stage one new file and attempt a commit through the installed hook."""
    target = clone / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x\n", encoding="utf-8")
    assert _git(clone, "add", "--", rel).returncode == 0
    return _git(clone, "commit", "-q", "-m", f"add {rel}")


def test_business_commit_outside_scope_rejected(tmp_path: Path) -> None:
    clone = _clone(tmp_path, "agent-platform")
    assert _install(clone) == 0
    res = _commit_file(clone, "services/api/app.py")
    assert res.returncode != 0, res.stdout + res.stderr
    assert "OUT_OF_SCOPE" in res.stdout + res.stderr


def test_business_commit_inside_scope_passes(tmp_path: Path) -> None:
    clone = _clone(tmp_path, "agent-platform")
    assert _install(clone) == 0
    (clone / "agent_rules" / "platform.allow.txt").write_text(
        "# platform scope\nservices/\n", encoding="utf-8")
    res = _commit_file(clone, "services/api/app.py")
    assert res.returncode == 0, res.stdout + res.stderr


def test_core_commit_anything_passes(tmp_path: Path) -> None:
    clone = _clone(tmp_path, "agent-core")
    assert _install(clone) == 0
    res = _commit_file(clone, "anywhere/file.txt")
    assert res.returncode == 0, res.stdout + res.stderr
