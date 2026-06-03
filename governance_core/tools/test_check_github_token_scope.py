"""Unit tests for check_github_token_scope.py (P-0097, gc #85).

Monkeypatches `gh auth status` so the delete_repo-scope verdict is exercised
without the network. The security-relevant contract: exit 1 IFF the active
token carries `delete_repo`; otherwise exit 0, and FAIL-SAFE to 0 when gh is
unavailable / unparseable (a check that cannot run must not block).

Run from repo root:
    python -m pytest tools/test_check_github_token_scope.py -q
"""
import importlib.util
import subprocess as _subprocess
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_github_token_scope",
    _REPO / "tools" / "check_github_token_scope.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


class _FakeProc:
    def __init__(self, stdout: str = "", stderr: str = "") -> None:
        self.stdout = stdout
        self.stderr = stderr


def _patch_gh(monkeypatch, *, stdout: str = "", stderr: str = "",
              exc: BaseException | None = None) -> None:
    def fake_run(*_a, **_k):
        if exc is not None:
            raise exc
        return _FakeProc(stdout, stderr)
    monkeypatch.setattr(mod.subprocess, "run", fake_run)


def test_delete_repo_present_exits_1(monkeypatch):
    _patch_gh(monkeypatch,
              stderr="  - Token scopes: 'repo', 'delete_repo', 'workflow'\n")
    assert mod.main() == 1


def test_delete_repo_absent_exits_0(monkeypatch):
    _patch_gh(monkeypatch,
              stderr="  - Token scopes: 'gist', 'read:org', 'repo', 'workflow'\n")
    assert mod.main() == 0


def test_gh_not_installed_fails_safe_0(monkeypatch):
    _patch_gh(monkeypatch, exc=FileNotFoundError())
    assert mod.main() == 0


def test_gh_timeout_fails_safe_0(monkeypatch):
    _patch_gh(monkeypatch,
              exc=_subprocess.TimeoutExpired(cmd="gh", timeout=20))
    assert mod.main() == 0


def test_unparseable_status_fails_safe_0(monkeypatch):
    _patch_gh(monkeypatch, stdout="not logged in to any hosts\n")
    assert mod.main() == 0


def test_scopes_on_stdout_also_parsed(monkeypatch):
    # gh has emitted the status block to stdout in some versions; the tool
    # concatenates both streams, so a delete_repo on stdout still trips.
    _patch_gh(monkeypatch,
              stdout="Token scopes: 'repo', 'delete_repo'\n")
    assert mod.main() == 1
