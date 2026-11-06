"""hub_python_check: warn when the hub session is not on the repo source (P-0133).

Run from repo root:
    python -m pytest maintainer/test_hub_python_check.py -q
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from governance_core import installer

_SCRIPT = Path(__file__).resolve().parent / "hub_python_check.py"
_spec = importlib.util.spec_from_file_location("hub_python_check", _SCRIPT)
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)

HOOK = {"hooks": {"SessionStart": [{"hooks": [{
    "type": "command",
    "command": "python \"${CLAUDE_PROJECT_DIR}/maintainer/hub_python_check.py\""}]}]}}


def _run(extra_env: dict[str, str]) -> subprocess.CompletedProcess:
    """Run the check as Claude Code does: a script under `python`."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8", **extra_env)
    return subprocess.run([sys.executable, str(_SCRIPT)], capture_output=True,
                          encoding="utf-8", timeout=60, env=env)


def test_repo_source_is_silent() -> None:
    assert check.warning(check.EXPECTED) is None


def test_other_copy_warns() -> None:
    text = check.warning(Path("C:/Python311/Lib/site-packages/governance_core"))
    assert text is not None and text.startswith("[WARN]")
    assert "site-packages" in text and "gchub" in text
    assert text.isascii()


def test_not_installed_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check.importlib.util, "find_spec", lambda name: None)
    text = check.warning(check.imported_from())
    assert text is not None and "not installed" in text


def test_shadowing_copy_emits_session_start_json(tmp_path: Path) -> None:
    """A governance_core found ahead of the repo -> hook JSON, exit 0."""
    fake = tmp_path / "governance_core"
    fake.mkdir()
    (fake / "__init__.py").write_text("", encoding="utf-8")
    res = _run({"PYTHONPATH": str(tmp_path)})
    assert res.returncode == 0, res.stderr
    payload = json.loads(res.stdout)
    assert str(fake) in payload["systemMessage"]
    assert payload["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert payload["hookSpecificOutput"]["additionalContext"] == payload["systemMessage"]


def test_upgrade_keeps_project_settings_hook(tmp_path: Path,
                                             monkeypatch: pytest.MonkeyPatch) -> None:
    """A single-agent project's .claude/settings.json hook survives install."""
    monkeypatch.setattr(installer.codec, "verify_auth_code",
                        lambda code, key: {"consumer_id": "test-consumer"})
    root = tmp_path / "proj"
    settings = root / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps(HOOK, indent=2) + "\n", encoding="utf-8")
    before = settings.read_bytes()
    for _ in range(2):  # install, then upgrade
        assert installer.install(
            root, config_overrides={"project_name": "proj", "ritual_phrase": "OK"},
            auth_code="stub", accept_candidate_uplink=True) == 0
    assert settings.read_bytes() == before
