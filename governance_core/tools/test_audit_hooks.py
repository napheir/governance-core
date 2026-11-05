"""audit_hooks v2: clones from config, expected hooks from the manifest (P-0130 C).

v1 hard-coded the upstream project's five clones and hooks that no longer
ship (sensi-guard.py, pipeline-check.py), so it only produced false reports.
v2 audits every config clone against hooks_manifest.json -- the source the
installer and doctor use -- and must not flag the projectRoot-only
settings.json the installer writes for multi-clone projects (P-0129 F3).

Each clone is produced by the real installer.install() (auth signature
check stubbed), so a clean fixture is exactly what consumers get.

Run from repo root:
    python -m pytest tools/test_audit_hooks.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from governance_core import installer

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tools/
import audit_hooks as ah  # noqa: E402

AGENTS = [
    {"name": "core", "branch": "master", "clone_dir": "agent-core"},
    {"name": "platform", "branch": "feature/platform", "clone_dir": "agent-platform"},
]


@pytest.fixture()
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Two clones installed by the real installer."""
    monkeypatch.setattr(installer.codec, "verify_auth_code",
                        lambda code, key: {"consumer_id": "test-consumer"})
    proj = tmp_path / "proj"
    for agent in AGENTS:
        clone = proj / agent["clone_dir"]
        clone.mkdir(parents=True)
        assert installer.install(clone, config_overrides={
            "project_name": "proj", "core_agent_name": "core", "agents": AGENTS,
            "shared_state_root": str(proj / "shared_state"),
        }, auth_code="stub", accept_candidate_uplink=True) == 0
    return proj


def _issues(project: Path, agent: str) -> list:
    """All v2 issues for one clone of the fixture."""
    clones = ah.load_clones(project / "agent-core")
    repo, is_core = clones[agent]
    core = clones["core"][0]
    expected = ah.manifest_hook_files()
    issues = (ah._check_hook_files(agent, repo, expected)
              + ah._check_registrations(agent, repo, expected)
              + ah._check_legacy_settings_json(agent, repo))
    if not is_core:
        issues += ah._check_hook_versions(agent, repo, core, expected)
    return issues


def test_fresh_install_is_clean(project: Path) -> None:
    """Includes the installer's projectRoot-only settings.json: not flagged."""
    assert (project / "agent-platform" / ".claude" / "settings.json").exists()
    assert ah.main(project / "agent-core", []) == 0


def test_clones_and_manifest_come_from_config(project: Path) -> None:
    clones = ah.load_clones(project / "agent-core")
    assert set(clones) == {"core", "platform"}
    assert clones["core"][1] is True and clones["platform"][1] is False
    assert "edit-write-guard.py" in ah.manifest_hook_files()
    assert "sensi-guard.py" not in ah.manifest_hook_files()


def test_missing_hook_reported(project: Path) -> None:
    (project / "agent-platform" / ".claude" / "hooks" / "scope-guard.py").unlink()
    assert any("Missing hook: scope-guard.py" in i for i in _issues(project, "platform"))


def test_unregistered_hook_reported(project: Path) -> None:
    path = project / "agent-platform" / ".claude" / "settings.local.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for groups in data["hooks"].values():
        for group in groups:
            group["hooks"] = [h for h in group["hooks"]
                              if "edit-write-guard.py" not in h["command"]]
    path.write_text(json.dumps(data), encoding="utf-8")
    assert any("not registered" in i and "edit-write-guard.py" in i
               for i in _issues(project, "platform"))


def test_hook_differing_from_core_reported(project: Path) -> None:
    hook = project / "agent-platform" / ".claude" / "hooks" / "command-guard.py"
    hook.write_text(hook.read_text(encoding="utf-8") + "\n# local edit\n",
                    encoding="utf-8")
    assert any("command-guard.py differs from core" in i
               for i in _issues(project, "platform"))


def test_settings_json_with_hooks_reported(project: Path) -> None:
    path = project / "agent-platform" / ".claude" / "settings.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["hooks"] = {"PreToolUse": []}
    path.write_text(json.dumps(data), encoding="utf-8")
    assert any("settings.json (non-local) declares hooks" in i
               for i in _issues(project, "platform"))


def test_fix_copies_differing_hook_from_core(project: Path) -> None:
    hook = project / "agent-platform" / ".claude" / "hooks" / "command-guard.py"
    hook.write_text("# broken\n", encoding="utf-8")
    assert ah.main(project / "agent-core", ["--fix"]) == 1  # reported this run
    assert ah.main(project / "agent-core", []) == 0        # clean after the fix
