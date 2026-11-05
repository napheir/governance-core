"""check_agent_roles v2: agents and clones come from config (P-0130 Phase C).

v1 hard-coded the upstream agents (rules/trade/data/research), their clone
paths and role-prefix vocabularies, so every other project's agents were
"Unknown agent". v2 checks, per config agent: a core role named after the
agent (<agent>-*.md), no role file named after ANOTHER agent, frontmatter.

Run from repo root:
    python -m pytest tools/test_check_agent_roles.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tools/
import check_agent_roles as car  # noqa: E402

AGENTS = ["core", "platform", "experience", "content"]
ROLE = "---\nname: {n}\ndescription: d\ntools: Read\n---\n\nBody.\n"


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """4-clone layout, each clone with config + its own core role file."""
    proj = tmp_path / "deva-vani"
    for agent in AGENTS:
        clone = proj / f"agent-{agent}"
        (clone / ".governance").mkdir(parents=True)
        (clone / ".governance" / "config.json").write_text(json.dumps({
            "project_name": "deva-vani", "install_root": str(tmp_path),
            "shared_state_root": str(proj / "shared_state"),
            "core_agent_name": "core", "core_branches": ["master"],
            "ritual_phrase": "OK",
            "agents": [{"name": a, "branch": "master", "clone_dir": f"agent-{a}"}
                       for a in AGENTS],
        }), encoding="utf-8")
        roles = clone / ".claude" / "agents"
        roles.mkdir(parents=True)
        (roles / f"{agent}-specialist.md").write_text(
            ROLE.format(n=f"{agent}-specialist"), encoding="utf-8")
    return proj


def test_all_config_agents_checked_and_compliant(project: Path, capsys) -> None:
    assert car.main(project / "agent-core", []) == 0
    out = capsys.readouterr().out
    for agent in AGENTS:
        assert f"Checking {agent}" in out


def test_business_agent_accepted_by_name(project: Path) -> None:
    assert car.main(project / "agent-core", ["--agent", "platform"]) == 0


def test_unknown_agent_lists_config_agents(project: Path, capsys) -> None:
    assert car.main(project / "agent-core", ["--agent", "trade"]) == 1
    assert "platform" in capsys.readouterr().out


def test_missing_core_role_is_high(project: Path) -> None:
    (project / "agent-content" / ".claude" / "agents" / "content-specialist.md").unlink()
    roles = project / "agent-content" / ".claude" / "agents"
    (roles / "writer.md").write_text(ROLE.format(n="writer"), encoding="utf-8")
    issues = car.check_agent("content", project / "agent-content", set(AGENTS))
    assert any("missing core role" in i for i in issues), issues


def test_role_named_after_other_agent_is_cross_scope(project: Path) -> None:
    roles = project / "agent-platform" / ".claude" / "agents"
    (roles / "content-writer.md").write_text(ROLE.format(n="content-writer"),
                                             encoding="utf-8")
    issues = car.check_agent("platform", project / "agent-platform", set(AGENTS))
    assert any("cross-scope" in i and "content-writer.md" in i for i in issues), issues


def test_shared_role_is_not_cross_scope(project: Path) -> None:
    roles = project / "agent-core" / ".claude" / "agents"
    (roles / "design-system-owner.md").write_text(
        ROLE.format(n="design-system-owner"), encoding="utf-8")
    issues = car.check_agent("core", project / "agent-core", set(AGENTS))
    assert not issues, issues


def test_single_agent_checks_this_repo(tmp_path: Path) -> None:
    repo = tmp_path / "governance-core"
    (repo / ".governance").mkdir(parents=True)
    (repo / ".governance" / "config.json").write_text(json.dumps({
        "project_name": "gc", "install_root": str(tmp_path),
        "shared_state_root": str(repo / "shared_state"), "core_agent_name": "core",
        "core_branches": ["master"], "ritual_phrase": "OK",
        "agents": [{"name": "core", "branch": "master", "clone_dir": "governance-core"}],
    }), encoding="utf-8")
    (repo / ".claude" / "agents").mkdir(parents=True)
    (repo / ".claude" / "agents" / "core-auditor.md").write_text(
        ROLE.format(n="core-auditor"), encoding="utf-8")
    assert car.load_agent_roots(repo) == {"core": repo}
    assert car.main(repo, []) == 0
