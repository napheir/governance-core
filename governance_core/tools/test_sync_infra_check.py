"""sync_infra is a read-only wiring check now (P-0137).

The old tool copied files and registered six hooks in every business clone
as absolute paths into core, while `governance-core upgrade` wires every hook
clone-locally; each undid the other. It also built clone paths from config
`install_root`, which in a nested `<root>/<project>/<clone>` layout names the
project's parent, so it skipped every clone there and still exited 0. Now
the installer is the only wiring model, clones are found next to the core
clone, and sync_infra only reports: missing clones, foreign or missing hook
registrations (FAIL), wide allow entries and copy drift (WARN).

Run from repo root:
    python -m pytest tools/test_sync_infra_check.py -q
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_TOOL = Path(__file__).resolve().parent / "sync_infra.py"
HOOKS = ("alpha.py", "beta.py")


def _local(name: str) -> dict:
    return {"type": "command",
            "command": f'python "${{CLAUDE_PROJECT_DIR}}/.claude/hooks/{name}"'}


def _clone(path: Path, cfg: dict, hooks: list | None = None,
           allow: list | None = None) -> Path:
    (path / ".governance").mkdir(parents=True)
    (path / ".governance" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    (path / ".claude" / "hooks").mkdir(parents=True)
    (path / ".claude" / "hooks" / "hooks_manifest.json").write_text(json.dumps(
        {"hooks": {h: {"event": "SessionStart", "matcher": None} for h in HOOKS}}),
        encoding="utf-8")
    entries = hooks if hooks is not None else [_local(h) for h in HOOKS]
    settings = {"hooks": {"SessionStart": [{"_managed": "governance-core", "hooks": entries}]},
                "permissions": {"allow": allow or []}}
    (path / ".claude" / "settings.local.json").write_text(json.dumps(settings),
                                                          encoding="utf-8")
    (path / "constitution").mkdir()
    (path / "constitution" / "total.md").write_bytes(b"# total\nsame\n")
    return path


def _layout(base: Path, nested: bool, agents=("core", "a", "b")) -> dict:
    """Clones under base/proj/ (nested; install_root = base) or base/ (flat)."""
    parent = base / "proj" if nested else base
    cfg = {"project_name": "proj", "install_root": str(base), "core_agent_name": "core",
           "agents": [{"name": n, "branch": "master" if n == "core" else f"feature/{n}",
                       "clone_dir": f"agent-{n}"} for n in agents]}
    return {n: _clone(parent / f"agent-{n}", cfg) for n in agents}


def _rebuild(clones: dict, name: str, **kwargs) -> Path:
    """Recreate clone `name` with other hooks / allow entries."""
    cfg = json.loads((clones["core"] / ".governance" / "config.json").read_text(encoding="utf-8"))
    shutil.rmtree(clones[name])
    return _clone(clones[name], cfg, **kwargs)


def _run(core: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, str(_TOOL), "--project-root", str(core), *args],
                          capture_output=True, encoding="utf-8", env=env, timeout=60)


def _report(core: Path, *args: str) -> tuple:
    res = _run(core, "--json", *args)
    return res.returncode, json.loads(res.stdout)


@pytest.mark.parametrize("nested", [True, False])
def test_clean_clones_pass_in_nested_and_flat_layouts(tmp_path: Path, nested: bool) -> None:
    clones = _layout(tmp_path, nested)
    code, report = _report(clones["core"])
    assert code == 0, report
    assert set(report["clones"]) == {"a", "b"}
    assert all(c["findings"] == [] for c in report["clones"].values())


def test_missing_clone_fails_loudly(tmp_path: Path) -> None:
    clones = _layout(tmp_path, nested=True)
    os.rename(clones["b"], clones["b"].with_name("moved-away"))
    res = _run(clones["core"])
    assert res.returncode == 1
    assert "[FAIL] clone-missing" in res.stdout and "1 FAIL" in res.stdout


def test_central_reference_into_core_fails(tmp_path: Path) -> None:
    clones = _layout(tmp_path, nested=True)
    central = {"type": "command",
               "command": f"python {(clones['core'] / '.claude/hooks/alpha.py').as_posix()}"}
    _rebuild(clones, "a", hooks=[central, _local("beta.py")])
    code, report = _report(clones["core"])
    checks = [(f["check"], f["level"]) for f in report["clones"]["a"]["findings"]]
    assert code == 1
    assert ("foreign-hook-ref", "FAIL") in checks
    assert ("hook-unregistered", "FAIL") in checks  # alpha.py is not clone-local


def test_unregistered_manifest_hook_fails(tmp_path: Path) -> None:
    clones = _layout(tmp_path, nested=False)
    _rebuild(clones, "a", hooks=[_local("alpha.py")])
    code, report = _report(clones["core"], "--agent", "a")
    (f,) = report["clones"]["a"]["findings"]
    assert code == 1 and (f["check"], f["level"]) == ("hook-unregistered", "FAIL")
    assert "beta.py" in f["detail"] and "governance-core upgrade" in f["fix"]


def test_wide_allow_and_drift_only_warn(tmp_path: Path) -> None:
    clones = _layout(tmp_path, nested=True)
    _rebuild(clones, "a", allow=["Bash(rm:*)", "Bash(git status)"])
    (clones["a"] / "constitution" / "total.md").write_bytes(b"# total\nold\n")
    (clones["b"] / "constitution" / "total.md").write_bytes(b"# total\r\nsame\r\n")  # EOL only
    code, report = _report(clones["core"])
    assert code == 0
    checks = sorted((f["check"], f["level"]) for f in report["clones"]["a"]["findings"])
    assert checks == [("copy-drift", "WARN"), ("wide-allow", "WARN")]
    assert report["clones"]["b"]["findings"] == []


def test_execute_is_refused(tmp_path: Path) -> None:
    clones = _layout(tmp_path, nested=True)
    res = _run(clones["core"], "--execute")
    assert res.returncode == 2 and "no longer copies or rewires" in res.stdout


def test_single_agent_is_not_applicable(tmp_path: Path) -> None:
    clones = _layout(tmp_path, nested=False, agents=("core",))
    res = _run(clones["core"])
    assert res.returncode == 0 and "[N/A]" in res.stdout


def test_unknown_agent_and_missing_config_cannot_run(tmp_path: Path) -> None:
    clones = _layout(tmp_path, nested=True)
    assert _run(clones["core"], "--agent", "nobody").returncode == 2
    assert _run(tmp_path / "nowhere").returncode == 2


def test_check_writes_nothing(tmp_path: Path) -> None:
    clones = _layout(tmp_path, nested=True)

    def snapshot() -> dict:
        return {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*") if p.is_file()}

    before = snapshot()
    _run(clones["core"])
    _run(clones["core"], "--execute")
    assert snapshot() == before
