"""Branch scope audit run from core (P-0135 Phase 1).

`check_scope.py --audit-branch --agent X --repo <clone>` fetches the clone's
checked-out commit into core's repo and audits its net change since the
merge-base with core's ref, against X's allow rules as committed on core's
ref. Before this there was only a baseline mode that needed a
`.baseline_commit` nothing wrote, so a branch change outside scope that
skipped the pre-commit gate (commit -n, plumbing, missing hooks) was never
found afterwards.

Real git repos: a core clone and two business clones of it.

Run from repo root:
    python -m pytest tools/test_check_scope_branch_audit.py -q
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
_TOOL = _HERE / "check_scope.py"
_GUARD_COMMON = next(p for p in (_HERE.parent / "hooks" / "_guard_common.py",
                                 _HERE.parent / ".claude" / "hooks" / "_guard_common.py")
                     if p.is_file())
_SCOPE_GUARD = _GUARD_COMMON.parent / "scope-guard.py"


def _git(repo: Path, *args: str) -> str:
    """Run a fixture git command with a throwaway identity and no hooks."""
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com",
         "-c", "core.hooksPath=.no-hooks", "-C", str(repo), *args],
        check=True, capture_output=True, encoding="utf-8").stdout


def _write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _commit(repo: Path, files: dict, msg: str, *flags: str) -> None:
    for rel, text in files.items():
        if text is None:
            _git(repo, "rm", "-q", rel)
        else:
            _write(repo, rel, text)
            _git(repo, "add", rel)
    _git(repo, "commit", "-q", *flags, "-m", msg)


@pytest.fixture()
def project(tmp_path: Path) -> dict:
    """core (master) plus a platform clone on feature/platform."""
    proj = tmp_path / "proj"
    core = proj / "agent-core"
    core.mkdir(parents=True)
    _git(core, "init", "-q", "-b", "master")
    cfg = {
        "project_name": "proj", "install_root": str(tmp_path),
        "shared_state_root": str(proj / "shared_state"),
        "core_agent_name": "core", "core_branches": ["master"],
        "upstream_branch": "origin/master", "ritual_phrase": "OK",
        "agents": [
            {"name": "core", "branch": "master", "clone_dir": "agent-core"},
            {"name": "platform", "branch": "feature/platform",
             "clone_dir": "agent-platform"},
            {"name": "content", "branch": "feature/content",
             "clone_dir": "agent-content"},
            {"name": "data", "branch": "feature/data", "clone_dir": "agent-data"},
        ],
    }
    _write(core, ".governance/config.json", json.dumps(cfg))
    _write(core, "agent_rules/platform.allow.txt", "services/platform/\n")
    _write(core, "agent_rules/content.allow.txt", "content/\n")
    _write(core, "agent_rules/shared.deny.txt", ".governance/auth_code\n")
    _write(core, "tools/shared.py", "v1\n")
    _write(core, "tools/old.py", "old\n")
    _write(core, "content/intro.md", "hello\n")
    _write(core, "services/platform/app.py", "a\n")
    (core / "tools").mkdir(exist_ok=True)
    shutil.copy2(_TOOL, core / "tools" / "check_scope.py")
    (core / ".claude" / "hooks").mkdir(parents=True)
    shutil.copy2(_GUARD_COMMON, core / ".claude" / "hooks" / "_guard_common.py")
    _git(core, "add", "-A")
    _git(core, "commit", "-q", "-m", "core: bootstrap")
    platform = proj / "agent-platform"
    subprocess.run(["git", "clone", "-q", str(core), str(platform)], check=True,
                   capture_output=True)
    _git(platform, "checkout", "-q", "-b", "feature/platform")
    return {"core": core, "platform": platform}


def _audit(cwd: Path, *args: str) -> tuple[int, dict | str]:
    """Run check_scope.py in `cwd`; return (exit code, report or text)."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    res = subprocess.run([sys.executable, str(cwd / "tools" / "check_scope.py"),
                          *args], cwd=cwd, capture_output=True, encoding="utf-8",
                         errors="replace", env=env, timeout=120)
    out = res.stdout + res.stderr
    if "--json" in args and res.returncode in (0, 1):
        return res.returncode, json.loads(res.stdout)
    return res.returncode, out


def _from_core(p: dict, agent: str = "platform") -> tuple[int, dict]:
    return _audit(p["core"], "--audit-branch", "--agent", agent,
                  "--repo", str(p["platform"]), "--json")


def _paths(report: dict) -> list:
    return sorted(v["path"] for v in report["violations"])


def test_own_scope_change_passes(project: dict) -> None:
    _commit(project["platform"], {"services/platform/app.py": "b\n"}, "own work")
    rc, report = _from_core(project)
    assert rc == 0 and report["violations"] == [], report
    assert report["ref"] == "refs/gc-audit/platform"


def test_other_agents_file_is_reported_with_owner(project: dict) -> None:
    _commit(project["platform"], {"content/intro.md": "rewritten\n"}, "touch content")
    rc, report = _from_core(project)
    assert rc == 1
    (v,) = report["violations"]
    assert v["path"] == "content/intro.md" and v["owners"] == ["content"]
    assert any("touch content" in c for c in v["commits"])


def test_widened_allow_file_on_branch_does_not_count(project: dict) -> None:
    _commit(project["platform"], {
        "agent_rules/platform.allow.txt": "services/platform/\ntools/\n",
        "tools/shared.py": "mine\n"}, "widen my scope")
    rc, report = _from_core(project)
    assert rc == 1
    assert _paths(report) == ["agent_rules/platform.allow.txt", "tools/shared.py"]


def test_commit_made_with_no_verify_is_still_reported(project: dict) -> None:
    _commit(project["platform"], {"tools/shared.py": "sneaky\n"}, "skip hooks", "-n")
    rc, report = _from_core(project)
    assert rc == 1 and _paths(report) == ["tools/shared.py"]


def test_core_merge_passes(project: dict) -> None:
    _commit(project["core"], {"tools/shared.py": "v2\n"}, "core: v2")
    _git(project["platform"], "fetch", "-q", "origin")
    _git(project["platform"], "merge", "-q", "--no-ff", "-m", "sync", "origin/master")
    _commit(project["platform"], {"services/platform/app.py": "c\n"}, "own work")
    rc, report = _from_core(project)
    assert rc == 0, report


def test_older_core_version_passes(project: dict) -> None:
    core = project["core"]
    _commit(core, {"tools/shared.py": "v2\n"}, "core: v2")
    v2 = _git(core, "rev-parse", "HEAD").strip()
    _commit(core, {"tools/shared.py": "v3\n"}, "core: v3")
    _git(project["platform"], "fetch", "-q", "origin")
    _git(project["platform"], "checkout", v2, "--", "tools/shared.py")
    _git(project["platform"], "commit", "-q", "-m", "take core v2")
    rc, report = _from_core(project)
    assert rc == 0, report


def test_change_hidden_in_merge_resolution_is_reported(project: dict) -> None:
    _commit(project["core"], {"tools/shared.py": "v2\n"}, "core: v2")
    platform = project["platform"]
    _git(platform, "fetch", "-q", "origin")
    _git(platform, "merge", "-q", "--no-ff", "--no-commit", "origin/master")
    _write(platform, "tools/shared.py", "v2 plus a backdoor\n")
    _git(platform, "add", "tools/shared.py")
    _git(platform, "commit", "-q", "--no-edit")
    rc, report = _from_core(project)
    assert rc == 1 and _paths(report) == ["tools/shared.py"]


def test_deleting_a_core_file_is_reported(project: dict) -> None:
    _commit(project["platform"], {"tools/shared.py": None}, "drop core file")
    rc, report = _from_core(project)
    assert rc == 1 and report["violations"][0]["status"] == "D"


def test_deletion_matching_core_passes(project: dict) -> None:
    _commit(project["core"], {"tools/old.py": None}, "core: drop old")
    _commit(project["platform"], {"tools/old.py": None}, "drop it too")
    rc, report = _from_core(project)
    assert rc == 0, report


def test_tampered_clone_refs_do_not_fool_core(project: dict) -> None:
    """The clone points its own origin/master at its tip and edits its local
    allow file; core's audit uses core's refs and core's rules."""
    platform = project["platform"]
    _commit(platform, {"content/intro.md": "rewritten\n"}, "touch content")
    _git(platform, "update-ref", "refs/remotes/origin/master", "HEAD")
    _write(platform, "agent_rules/platform.allow.txt", "content/\n")
    rc, report = _from_core(project)
    assert rc == 1 and _paths(report) == ["content/intro.md"]


def test_in_clone_audit_of_head(project: dict) -> None:
    """`--agent X` alone is the branch audit of HEAD (art_05's command)."""
    _commit(project["platform"], {"content/intro.md": "rewritten\n"}, "touch content")
    rc, out = _audit(project["platform"], "--agent", "platform")
    assert rc == 1 and "content/intro.md" in out and "owner: content" in out


def test_missing_allow_file_exits_2(project: dict) -> None:
    rc, out = _audit(project["core"], "--audit-branch", "--agent", "data",
                     "--repo", str(project["platform"]))
    assert rc == 2 and "data.allow.txt" in out


def test_notify_alerts_audited_agent_and_owner(project: dict) -> None:
    """--notify (Phase 3): the audited agent and each owner get an alert."""
    _commit(project["platform"], {"content/intro.md": "rewritten\n"}, "touch content")
    rc, out = _audit(project["core"], "--audit-branch", "--agent", "platform",
                     "--repo", str(project["platform"]), "--notify")
    assert rc == 1, out
    shared = project["core"].parent / "shared_state" / "notices"
    for agent in ("platform", "content"):
        (notice,) = [json.loads(p.read_text(encoding="utf-8"))
                     for p in (shared / agent).glob("*.json")]
        assert notice["kind"] == "scope-violation" and notice["severity"] == "alert"
        assert notice["paths"] == ["content/intro.md"] and notice["from"] == "core"
        assert any("touch content" in c for c in notice["commits"])


def test_core_agent_passes(project: dict) -> None:
    rc, out = _audit(project["core"], "--agent", "core")
    assert rc == 0 and "core agent" in out


# --- scope-guard: skipping the commit hooks (P-0135) -------------------------

def _scope_guard():
    spec = importlib.util.spec_from_file_location("scope_guard_p0135", _SCOPE_GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("command,bypass", [
    ("git commit -n -m x", True),
    ("git commit -nm x", True),
    ("git commit -a -n", True),
    ("git commit --no-verify -m x", True),
    ("git -c core.hooksPath=/dev/null commit -m x", True),
    ("git config core.hooksPath .nohooks", True),
    ("git -C ../x commit -n", True),
    ("git commit -am 'use the -n flag'", False),
    ('git commit -m "mention --no-verify and core.hooksPath"', False),
    ('git commit -m "say \\"-n\\" here"', False),
    ("git merge -n origin/master", False),
    ("git commit -m x", False),
])
def test_scope_guard_detects_hook_bypass(command: str, bypass: bool) -> None:
    assert _scope_guard()._bypasses_commit_hooks(command) is bypass
