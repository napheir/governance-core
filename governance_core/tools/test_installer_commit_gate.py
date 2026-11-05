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


def _git_nohooks(repo: Path, *args: str) -> subprocess.CompletedProcess:
    """Fixture-setup git call with hooks disabled (not an agent action)."""
    return _git(repo, "-c", "core.hooksPath=.no-hooks", *args)


def _merge_fixture(tmp_path: Path) -> Path:
    """Business clone: feature/platform behind a master core-infra change,
    merged with --no-commit so the final `git commit` runs pre-commit (the
    path a conflicted /sync-repos merge takes)."""
    clone = _clone(tmp_path, "agent-platform")
    assert _install(clone) == 0
    (clone / "agent_rules" / "platform.allow.txt").write_text("services/\n",
                                                              encoding="utf-8")
    assert _git_nohooks(clone, "add", "-A").returncode == 0
    assert _git_nohooks(clone, "commit", "-q", "-m", "base").returncode == 0
    assert _git(clone, "checkout", "-q", "-b", "feature/platform").returncode == 0
    (clone / "services").mkdir()
    (clone / "services" / "app.py").write_text("x = 1\n", encoding="utf-8")
    assert _git_nohooks(clone, "add", "-A").returncode == 0
    assert _git_nohooks(clone, "commit", "-q", "-m", "platform").returncode == 0
    assert _git(clone, "checkout", "-q", "master").returncode == 0
    tool = clone / "tools" / "rotate_state.py"
    tool.write_text(tool.read_text(encoding="utf-8") + "\n# core change\n",
                    encoding="utf-8")
    assert _git_nohooks(clone, "commit", "-q", "-am", "core infra").returncode == 0
    assert _git(clone, "checkout", "-q", "feature/platform").returncode == 0
    assert _git(clone, "merge", "--no-commit", "--no-ff", "master").returncode == 0
    return clone


def test_merge_commit_importing_core_changes_passes(tmp_path: Path) -> None:
    """Files staged exactly as MERGE_HEAD has them are merge imports."""
    clone = _merge_fixture(tmp_path)
    res = _git(clone, "commit", "-q", "-m", "merge master")
    assert res.returncode == 0, res.stdout + res.stderr


def test_merge_commit_with_agent_edit_to_core_file_rejected(tmp_path: Path) -> None:
    """An out-of-scope edit slipped into the merge resolution is still caught."""
    clone = _merge_fixture(tmp_path)
    other = clone / "tools" / "check_scope.py"
    other.write_text(other.read_text(encoding="utf-8") + "\n# sneaky\n",
                     encoding="utf-8")
    assert _git(clone, "add", "--", "tools/check_scope.py").returncode == 0
    res = _git(clone, "commit", "-q", "-m", "merge master")
    assert res.returncode != 0, res.stdout + res.stderr
    assert "tools/check_scope.py" in res.stdout + res.stderr


def test_business_commit_widening_own_allow_list_rejected(tmp_path: Path) -> None:
    """The agent_rules/ master-equality skip compares STAGED content: an
    agent cannot widen its own scope through the commit under check."""
    clone = _clone(tmp_path, "agent-platform")
    assert _install(clone) == 0
    allow = clone / "agent_rules" / "platform.allow.txt"
    allow.write_text("services/\n", encoding="utf-8")
    assert _git_nohooks(clone, "add", "-A").returncode == 0
    assert _git_nohooks(clone, "commit", "-q", "-m", "base").returncode == 0
    assert _git(clone, "checkout", "-q", "-b", "feature/platform").returncode == 0
    allow.write_text("services/\ntools/\n", encoding="utf-8")
    assert _git(clone, "add", "--", "agent_rules/platform.allow.txt").returncode == 0
    res = _git(clone, "commit", "-q", "-m", "widen my scope")
    assert res.returncode != 0, res.stdout + res.stderr
    assert "agent_rules/platform.allow.txt" in res.stdout + res.stderr


def test_pre_merge_commit_installed_lf_and_idempotent(tmp_path: Path) -> None:
    clone = _clone(tmp_path, "agent-core")
    assert _install(clone) == 0
    hook = clone / ".git" / "hooks" / "pre-merge-commit"
    data = hook.read_bytes()
    assert installer.PRE_MERGE_COMMIT_MARKER.encode() in data
    assert b"--merge-commit" in data
    assert b"\r\n" not in data
    assert _install(clone) == 0
    assert hook.read_bytes() == data


def _auto_merge_fixture(tmp_path: Path, name: str = "agent-platform",
                        agent_edit: bool = False) -> Path:
    """Clone on feature/platform (own commit), local master stale at base.
    core-next carries a core infra change; core-tip changes that file again
    and is the fetched upstream (refs/remotes/origin/master = config
    upstream_branch), so core-next is core history whose content differs
    from the core ref. agent_edit: feature/platform also changed that core
    file (committed before the gate), in a region git merges cleanly."""
    clone = _clone(tmp_path, name)
    assert _install(clone) == 0
    (clone / "agent_rules" / "platform.allow.txt").write_text("services/\n",
                                                              encoding="utf-8")
    tool = clone / "tools" / "rotate_state.py"
    tool.write_text(tool.read_text(encoding="utf-8") + "\n# core section\n\n"
                    + "\n" * 20 + "# end\n", encoding="utf-8")
    assert _git_nohooks(clone, "add", "-A").returncode == 0
    assert _git_nohooks(clone, "commit", "-q", "-m", "base").returncode == 0
    assert _git(clone, "checkout", "-q", "-b", "feature/platform").returncode == 0
    (clone / "services").mkdir()
    (clone / "services" / "app.py").write_text("x = 1\n", encoding="utf-8")
    assert _git_nohooks(clone, "add", "-A").returncode == 0
    assert _git_nohooks(clone, "commit", "-q", "-m", "platform").returncode == 0
    if agent_edit:
        text = tool.read_text(encoding="utf-8")
        tool.write_text(text.replace("# end\n", "# end\n# agent edit\n"),
                        encoding="utf-8")
        assert _git_nohooks(clone, "commit", "-q", "-am", "agent").returncode == 0
    assert _git(clone, "checkout", "-q", "-b", "core-next", "master").returncode == 0
    text = tool.read_text(encoding="utf-8")
    tool.write_text(text.replace("# core section\n", "# core section v2\n"),
                    encoding="utf-8")
    assert _git_nohooks(clone, "commit", "-q", "-am", "core infra").returncode == 0
    assert _git(clone, "checkout", "-q", "-b", "core-tip").returncode == 0
    text = tool.read_text(encoding="utf-8")
    tool.write_text(text.replace("# core section v2\n", "# core section v3\n"),
                    encoding="utf-8")
    assert _git_nohooks(clone, "commit", "-q", "-am", "core infra 2").returncode == 0
    assert _git(clone, "update-ref", "refs/remotes/origin/master",
                "core-tip").returncode == 0
    target = "core-next" if name == "agent-core" else "feature/platform"
    assert _git(clone, "checkout", "-q", target).returncode == 0
    return clone


def _merge_head(clone: Path) -> bool:
    return _git(clone, "rev-parse", "-q", "--verify", "MERGE_HEAD").returncode == 0


def test_auto_merge_of_core_changes_deferred_then_concluded(tmp_path: Path) -> None:
    """A conflict-free merge runs pre-merge-commit, not pre-commit. Imports it
    cannot attribute (MERGE_HEAD not written yet) defer the commit; `git
    commit` then concludes it through the MERGE_HEAD-aware pre-commit gate."""
    clone = _auto_merge_fixture(tmp_path)
    res = _git(clone, "merge", "--no-edit", "core-next")
    assert res.returncode != 0, res.stdout + res.stderr
    assert "[DEFER]" in res.stdout + res.stderr
    assert _merge_head(clone)
    res = _git(clone, "commit", "--no-edit")
    assert res.returncode == 0, res.stdout + res.stderr
    assert not _merge_head(clone)


def test_auto_merge_carrying_agent_edit_to_core_file_rejected(tmp_path: Path) -> None:
    """The clean 3-way result of a core file the agent also changed equals
    neither side: no longer committed unchecked by an automatic merge."""
    clone = _auto_merge_fixture(tmp_path, agent_edit=True)
    res = _git(clone, "merge", "--no-edit", "core-next")
    assert res.returncode != 0, res.stdout + res.stderr
    res = _git(clone, "commit", "--no-edit")
    assert res.returncode != 0, res.stdout + res.stderr
    assert "tools/rotate_state.py" in res.stdout + res.stderr


def test_auto_merge_from_upstream_ahead_of_stale_master_commits(tmp_path: Path) -> None:
    """Imports identical to the core ref are recognized without MERGE_HEAD.
    The core ref is config upstream_branch (origin/master), not a hard-coded
    local master -- which /sync-repos leaves stale in business clones."""
    clone = _auto_merge_fixture(tmp_path)
    res = _git(clone, "merge", "--no-edit", "origin/master")
    assert res.returncode == 0, res.stdout + res.stderr
    assert not _merge_head(clone)


def test_core_auto_merge_commits(tmp_path: Path) -> None:
    clone = _auto_merge_fixture(tmp_path, name="agent-core")
    assert _git(clone, "checkout", "-q", "-b", "side", "master").returncode == 0
    assert _commit_file(clone, "anywhere/file.txt").returncode == 0
    res = _git(clone, "merge", "--no-edit", "core-next")
    assert res.returncode == 0, res.stdout + res.stderr


# --- P-0131: merge imports are attributed to their source commits ---------

def _conclude(clone: Path, ref: str) -> subprocess.CompletedProcess:
    """Merge `ref` with --no-ff --no-commit, then conclude via pre-commit."""
    res = _git(clone, "merge", "--no-ff", "--no-commit", ref)
    assert res.returncode == 0, res.stdout + res.stderr
    return _git(clone, "commit", "--no-edit")


def test_merge_from_upstream_core_history_passes(tmp_path: Path) -> None:
    """The /sync-repos path: merging the fetched upstream imports core files."""
    clone = _auto_merge_fixture(tmp_path)
    res = _conclude(clone, "origin/master")
    assert res.returncode == 0, res.stdout + res.stderr


def test_merge_of_foreign_agent_branch_out_of_scope_commit_rejected(tmp_path: Path) -> None:
    """Another business agent's branch: its out-of-scope commit is no longer
    passed as a merge import just because it is staged as MERGE_HEAD."""
    clone = _auto_merge_fixture(tmp_path)
    assert _git(clone, "checkout", "-q", "-b", "feature/content", "master").returncode == 0
    (clone / "content").mkdir()
    (clone / "content" / "page.md").write_text("# page\n", encoding="utf-8")
    assert _git_nohooks(clone, "add", "-A").returncode == 0
    assert _git_nohooks(clone, "commit", "-q", "-m", "content: add page").returncode == 0
    assert _git(clone, "checkout", "-q", "feature/platform").returncode == 0
    res = _conclude(clone, "feature/content")
    out = res.stdout + res.stderr
    assert res.returncode != 0, out
    assert "IMPORTED_OUT_OF_SCOPE" in out and "content: add page" in out, out


def test_merge_of_foreign_agent_branch_evil_merge_resolution_rejected(tmp_path: Path) -> None:
    """A file slipped into a merge commit on the other branch (differs from
    both of its parents) is attributed to that merge commit."""
    clone = _auto_merge_fixture(tmp_path)
    assert _git(clone, "checkout", "-q", "-b", "feature/content", "master").returncode == 0
    assert _git(clone, "merge", "--no-ff", "--no-commit", "core-next").returncode == 0
    (clone / "tools" / "evil.py").write_text("x = 1\n", encoding="utf-8")
    assert _git_nohooks(clone, "add", "-A").returncode == 0
    assert _git_nohooks(clone, "commit", "-q", "-m", "content: sync core").returncode == 0
    assert _git(clone, "checkout", "-q", "feature/platform").returncode == 0
    res = _conclude(clone, "feature/content")
    out = res.stdout + res.stderr
    assert res.returncode != 0, out
    assert "tools/evil.py" in out and "IMPORTED_OUT_OF_SCOPE" in out, out
    assert "tools/rotate_state.py" not in out, out  # core history still passes


def test_own_branch_pull_merge_with_core_history_passes(tmp_path: Path) -> None:
    """Pulling the agent's own diverged remote branch, which itself merged
    core history, is not mistaken for a foreign import."""
    clone = _auto_merge_fixture(tmp_path)
    assert _git(clone, "checkout", "-q", "-b", "remote-side").returncode == 0
    (clone / "services" / "b.py").write_text("b = 1\n", encoding="utf-8")
    assert _git_nohooks(clone, "add", "-A").returncode == 0
    assert _git_nohooks(clone, "commit", "-q", "-m", "platform b").returncode == 0
    assert _git_nohooks(clone, "merge", "-q", "--no-ff", "-m", "sync",
                        "core-next").returncode == 0
    assert _git(clone, "update-ref", "refs/remotes/origin/feature/platform",
                "remote-side").returncode == 0
    assert _git(clone, "checkout", "-q", "feature/platform").returncode == 0
    (clone / "services" / "c.py").write_text("c = 1\n", encoding="utf-8")
    assert _git_nohooks(clone, "add", "-A").returncode == 0
    assert _git_nohooks(clone, "commit", "-q", "-m", "platform c").returncode == 0
    res = _conclude(clone, "origin/feature/platform")
    assert res.returncode == 0, res.stdout + res.stderr


def test_merge_from_upstream_with_in_scope_conflict_resolution_passes(tmp_path: Path) -> None:
    """deva-vani's first sync with real branch commits: a STATE.md conflict
    (both sides prepended an entry) resolved by keeping both; in scope."""
    clone = _auto_merge_fixture(tmp_path)
    allow = clone / "agent_rules" / "platform.allow.txt"
    allow.write_text("services/\nSTATE.md\n", encoding="utf-8")
    assert _git_nohooks(clone, "commit", "-q", "-am", "scope").returncode == 0
    state = clone / "STATE.md"
    base = state.read_text(encoding="utf-8")
    state.write_text("### platform entry\n" + base, encoding="utf-8")
    assert _git_nohooks(clone, "commit", "-q", "-am", "platform state").returncode == 0
    assert _git(clone, "checkout", "-q", "core-tip").returncode == 0
    state.write_text("### core entry\n" + base, encoding="utf-8")
    assert _git_nohooks(clone, "commit", "-q", "-am", "core state").returncode == 0
    assert _git(clone, "update-ref", "refs/remotes/origin/master", "core-tip").returncode == 0
    assert _git(clone, "checkout", "-q", "feature/platform").returncode == 0
    res = _git(clone, "merge", "--no-ff", "--no-commit", "origin/master")
    assert res.returncode != 0  # STATE.md conflict
    state.write_text("### core entry\n### platform entry\n" + base, encoding="utf-8")
    assert _git(clone, "add", "STATE.md").returncode == 0
    res = _git(clone, "commit", "--no-edit")
    assert res.returncode == 0, res.stdout + res.stderr
