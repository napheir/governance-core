"""Agent enums come from the project's config, not the upstream roles (P-0130).

Proposal `agent` (contract proposal_frontmatter_schema v1.6.0) and knowledge
`owner` (knowledge_frontmatter_schema v1.3.0) used fixed enums of the
upstream project's roles (core/rules/trade/data/research), so a consumer
with other agents -- deva-vani: core/platform/experience/content -- could
create proposals that audit_proposals then rejected, and could not own
knowledge entries at all. Both now take their values from
.governance/config.json agents[].

Run from repo root:
    python -m pytest tools/test_config_derived_enums.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tools/
import audit_proposals as ap  # noqa: E402

AGENTS = ["core", "platform", "experience", "content"]


def _write_config(root: Path, agents: list, core: str = "core") -> None:
    """Write a complete .governance/config.json for `agents`."""
    gov = root / ".governance"
    gov.mkdir(parents=True, exist_ok=True)
    (gov / "config.json").write_text(json.dumps({
        "project_name": "deva-vani",
        "install_root": str(root.parent),
        "shared_state_root": str(root / "shared_state"),
        "core_agent_name": core,
        "core_branches": ["master"],
        "ritual_phrase": "OK",
        "agents": [{"name": a, "branch": "master" if a == core else f"feature/{a}",
                    "clone_dir": f"agent-{a}"} for a in agents],
    }), encoding="utf-8")


def _proposal(d: Path, nnnn: str, agent: str, status: str = "pending") -> Path:
    """Write a schema-valid proposal owned by `agent`."""
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"p-{nnnn}-x.md"
    path.write_text(
        f"---\nid: P-{nnnn}\nagent: {agent}\nstatus: {status}\n"
        f"created: 2026-11-05\n---\n\n# Proposal P-{nnnn}: x\n\n## Trigger\n\nx\n",
        encoding="utf-8")
    return path


# --- proposals (contract v1.6.0) ---------------------------------------------


def test_proposal_config_agents_read_from_config(tmp_path: Path) -> None:
    _write_config(tmp_path, AGENTS)
    assert ap._config_agents(tmp_path) == set(AGENTS)


def test_proposal_in_flight_business_agent_passes(tmp_path: Path) -> None:
    p = _proposal(tmp_path / "inflight", "0001", "platform")
    errors = ap._validate_one(p.name, p, tmp_path, "in-flight", True, set(AGENTS))
    assert not [e for e in errors if "agent" in e], errors


def test_proposal_in_flight_unknown_agent_fails(tmp_path: Path) -> None:
    p = _proposal(tmp_path / "inflight", "0002", "ghost")
    errors = ap._validate_one(p.name, p, tmp_path, "in-flight", True, set(AGENTS))
    assert any("not in config agents" in e for e in errors), errors


def test_proposal_in_flight_upstream_role_fails_in_other_project(tmp_path: Path) -> None:
    """`trade` is no longer valid by default: it is not deva-vani's agent."""
    p = _proposal(tmp_path / "inflight", "0003", "trade")
    errors = ap._validate_one(p.name, p, tmp_path, "in-flight", True, set(AGENTS))
    assert any("not in config agents" in e for e in errors), errors


def test_proposal_malformed_agent_fails_in_any_region(tmp_path: Path) -> None:
    p = _proposal(tmp_path / "arch", "0004", "Bad Name")
    errors = ap._validate_one(p.name, p, tmp_path, "archive", True, set(AGENTS))
    assert any("not a valid agent name" in e for e in errors), errors


def test_proposal_archived_retired_agent_warns_not_fails(tmp_path: Path) -> None:
    p = _proposal(tmp_path / "arch", "0005", "retired", status="rejected")
    errors = ap._validate_one(p.name, p, tmp_path, "archive", True, set(AGENTS))
    assert not [e for e in errors if "agent" in e], errors
    regions = {"in-flight": [], "archive": [p], "legacy": []}
    warns = ap._check_archived_agents(regions, set(AGENTS))
    assert len(warns) == 1 and "retired" in warns[0]


def test_proposal_archived_current_agent_no_warning(tmp_path: Path) -> None:
    p = _proposal(tmp_path / "arch", "0006", "content", status="rejected")
    regions = {"in-flight": [], "archive": [p], "legacy": []}
    assert ap._check_archived_agents(regions, set(AGENTS)) == []
