"""Multi-clone session-boundary anchor written by install (P-0129 Phase C, F3).

A fresh multi-clone consumer had no `.claude/settings.json` declaring
`projectRoot: "../"`, so session-boundary-guard confined each session to its
clone and proposals in `../shared_state/` were unwritable -- adding the file
itself was classify-gated, a deadlock only CLAUDE_BOUNDARY_OVERRIDE broke.
install now adds the one key idempotently, keeps every other key, and
writes nothing for single-agent or non-standard layouts.

Runs the real installer.install() code path; only the auth-code signature
check is stubbed.

Run from repo root:
    python -m pytest tools/test_installer_topology_anchor.py -q
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from governance_core import installer

_HERE = Path(__file__).resolve().parent
AGENTS = [
    {"name": "core", "branch": "master", "clone_dir": "agent-core"},
    {"name": "platform", "branch": "feature/platform", "clone_dir": "agent-platform"},
]


@pytest.fixture(autouse=True)
def _stub_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub only the auth-code signature check."""
    monkeypatch.setattr(installer.codec, "verify_auth_code",
                        lambda code, key: {"consumer_id": "test-consumer"})


def _clone(tmp_path: Path, name: str = "agent-core") -> Path:
    """Create <tmp>/proj/<name>/ and return it."""
    clone = tmp_path / "proj" / name
    clone.mkdir(parents=True)
    return clone


def _install(clone: Path, agents: list, shared_state_root: Path) -> int:
    """Run a real install into `clone` with the given topology."""
    return installer.install(clone, config_overrides={
        "project_name": "proj", "core_agent_name": "core",
        "agents": agents, "shared_state_root": str(shared_state_root),
    }, auth_code="stub", accept_candidate_uplink=True)


def _settings(clone: Path) -> Path:
    return clone / ".claude" / "settings.json"


def test_multi_clone_gets_anchor(tmp_path: Path) -> None:
    clone = _clone(tmp_path)
    assert _install(clone, AGENTS, tmp_path / "proj" / "shared_state") == 0
    data = json.loads(_settings(clone).read_text(encoding="utf-8"))
    assert data["projectRoot"] == "../"


def test_existing_keys_kept_and_idempotent(tmp_path: Path) -> None:
    clone = _clone(tmp_path)
    _settings(clone).parent.mkdir(parents=True)
    _settings(clone).write_text(json.dumps({"permissions": {"allow": ["Bash(ls:*)"]}}),
                                encoding="utf-8")
    shared = tmp_path / "proj" / "shared_state"
    assert _install(clone, AGENTS, shared) == 0
    first = _settings(clone).read_bytes()
    data = json.loads(first)
    assert data["permissions"] == {"allow": ["Bash(ls:*)"]}
    assert data["projectRoot"] == "../"
    assert _install(clone, AGENTS, shared) == 0
    assert _settings(clone).read_bytes() == first


def test_owner_value_left_alone(tmp_path: Path) -> None:
    clone = _clone(tmp_path)
    _settings(clone).parent.mkdir(parents=True)
    _settings(clone).write_text(json.dumps({"projectRoot": "../../"}), encoding="utf-8")
    assert _install(clone, AGENTS, tmp_path / "proj" / "shared_state") == 0
    assert json.loads(_settings(clone).read_text(encoding="utf-8"))["projectRoot"] == "../../"


def test_single_agent_gets_no_anchor(tmp_path: Path) -> None:
    clone = _clone(tmp_path)
    assert _install(clone, AGENTS[:1], tmp_path / "proj" / "shared_state") == 0
    assert not _settings(clone).exists()


def test_non_sibling_shared_state_gets_no_anchor(tmp_path: Path) -> None:
    clone = _clone(tmp_path)
    assert _install(clone, AGENTS, tmp_path / "elsewhere" / "shared_state") == 0
    assert not _settings(clone).exists()


def test_boundary_resolves_to_project_dir(tmp_path: Path) -> None:
    """End to end: the boundary the guard derives covers the whole project."""
    tool = None
    for candidate in (_HERE / "derive_session_boundary.py",
                      _HERE.parent / "tools" / "derive_session_boundary.py"):
        if candidate.is_file():
            tool = candidate
            break
    if tool is None:
        pytest.skip("derive_session_boundary.py not found")
    spec = importlib.util.spec_from_file_location("_dsb_test", tool)
    dsb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dsb)

    clone = _clone(tmp_path, "agent-platform")
    assert _install(clone, AGENTS, tmp_path / "proj" / "shared_state") == 0
    boundary = dsb.derive_boundary(clone)
    assert boundary.rule == "declarative"
    assert boundary.path == (tmp_path / "proj").resolve()
