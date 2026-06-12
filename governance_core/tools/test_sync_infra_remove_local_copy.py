"""Tests for sync_infra._remove_local_copy git-tracked guard (#91, P-0099).

A centralized hook whose local copy is git-tracked must be KEPT: settings.json
already points the hook at core's absolute path, and the 6 central hooks are
gc-managed + git-tracked in consumers, so git restores them on every
merge/checkout -- unlinking them only churns. Only a genuinely-orphan untracked
copy (the original one-time migration target) is removed.

Run: python -m pytest tools/test_sync_infra_remove_local_copy.py
"""
import subprocess
from pathlib import Path

from governance_core.tools import sync_infra


def _git(repo: Path, *args: str) -> None:
    """Run a git command in `repo`, raising on failure."""
    subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True)


def _init_repo(repo: Path) -> None:
    """Initialize a throwaway git repo with a committer identity."""
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@t.invalid")
    _git(repo, "config", "user.name", "t")


def _make(repo: Path, rel: str) -> Path:
    """Create a file at repo/rel and return its path."""
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# hook\n", encoding="utf-8")
    return target


def test_tracked_copy_is_kept(tmp_path):
    """A git-tracked local hook is left in place (not unlinked)."""
    _init_repo(tmp_path)
    rel = ".claude/hooks/session-context.py"
    target = _make(tmp_path, rel)
    _git(tmp_path, "add", rel)  # staged -> tracked (ls-files matches the index)

    msg = sync_infra._remove_local_copy(tmp_path, rel, dry_run=False)

    assert target.exists(), "tracked hook must NOT be unlinked (#91)"
    assert "[KEEP]" in msg


def test_untracked_orphan_is_removed(tmp_path):
    """An untracked orphan copy is still removed (original migration intent)."""
    _init_repo(tmp_path)
    rel = ".claude/hooks/orphan.py"
    target = _make(tmp_path, rel)  # never git-added -> untracked

    msg = sync_infra._remove_local_copy(tmp_path, rel, dry_run=False)

    assert not target.exists(), "untracked orphan must be removed"
    assert "[DEL]" in msg


def test_dry_run_keeps_tracked_and_does_not_delete_orphan(tmp_path):
    """Dry-run never unlinks: tracked -> [KEEP], untracked -> would-[DEL]."""
    _init_repo(tmp_path)
    tracked_rel = ".claude/hooks/repo-health.py"
    orphan_rel = ".claude/hooks/orphan.py"
    tracked = _make(tmp_path, tracked_rel)
    orphan = _make(tmp_path, orphan_rel)
    _git(tmp_path, "add", tracked_rel)

    keep_msg = sync_infra._remove_local_copy(tmp_path, tracked_rel, dry_run=True)
    del_msg = sync_infra._remove_local_copy(tmp_path, orphan_rel, dry_run=True)

    assert tracked.exists() and "[KEEP]" in keep_msg
    assert orphan.exists() and "would remove" in del_msg  # dry-run: not deleted


def test_is_git_tracked_non_repo_fails_safe(tmp_path):
    """Outside a git repo, _is_git_tracked returns False (fail safe to delete)."""
    assert sync_infra._is_git_tracked(tmp_path, "anything.py") is False
