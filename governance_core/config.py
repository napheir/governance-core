"""governance-core configuration loader.

Reads the downstream project's `.governance/config.json` and exposes typed
accessors for hooks and audit tools. **All hardcoded paths / agent names /
business keywords in generic resources must be sourced from here, never
inline.**

Phase 1.2+ will implement the full loader; this stub establishes the API
contract.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CONFIG_FILENAME = ".governance/config.json"


@dataclass(frozen=True)
class AgentSpec:
    name: str
    branch: str
    clone_dir: str


@dataclass(frozen=True)
class GovernanceConfig:
    project_name: str
    install_root: Path
    shared_state_root: Path
    claude_dir: str
    core_agent_name: str
    core_branches: tuple[str, ...]
    ritual_phrase: str
    agents: tuple[AgentSpec, ...]
    upstream_branch: str
    raw: dict[str, Any]


def load_config(project_root: str | Path | None = None) -> GovernanceConfig:
    """Load .governance/config.json from project root.

    project_root defaults to env var GOVERNANCE_CORE_PROJECT_ROOT or cwd.
    """
    if project_root is None:
        project_root = os.environ.get("GOVERNANCE_CORE_PROJECT_ROOT") or os.getcwd()
    root = Path(project_root).resolve()
    cfg_path = root / CONFIG_FILENAME
    if not cfg_path.exists():
        raise FileNotFoundError(
            f"governance-core config not found: {cfg_path}. "
            f"Run `governance-core install` first."
        )
    raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    agents = tuple(
        AgentSpec(name=a["name"], branch=a["branch"], clone_dir=a["clone_dir"])
        for a in raw["agents"]
    )
    return GovernanceConfig(
        project_name=raw["project_name"],
        install_root=Path(raw["install_root"]),
        shared_state_root=Path(raw["shared_state_root"]),
        claude_dir=raw.get("claude_dir", ".claude"),
        core_agent_name=raw["core_agent_name"],
        core_branches=tuple(raw["core_branches"]),
        ritual_phrase=raw["ritual_phrase"],
        agents=agents,
        upstream_branch=raw.get("upstream_branch", "origin/master"),
        raw=raw,
    )


# Proposal-pipeline storage layout — derived by convention from
# .governance/config.json (P-0066 Phase 1). Replaces the legacy project-root
# `config/proposals_config.json` that the P-0059 extraction never carried over.
PROPOSAL_LOCK_TIMEOUT_SEC = 10


def load_proposals_config(project_root: str | Path | None = None) -> dict[str, Any]:
    """Derive the proposal-pipeline config consumed by tools/proposal_lib.py.

    Historically tools/proposal_lib.py imported `load_proposals_config` from a
    project-root `config/` module backed by `config/proposals_config.json`.
    That module was never extracted into the governance-core package (P-0059
    gap), so `/proposal` crashed on import in every consumer project. P-0066
    Phase 1 replaces it with this loader: every path is derived by convention
    from `.governance/config.json`'s `shared_state_root` + project root +
    `agents` enum — no separate proposals_config.json, no project-root
    `config` module.

    project_root defaults to env var GOVERNANCE_CORE_PROJECT_ROOT or cwd.

    Returns a dict of absolute-path strings (plus `agents` list and
    `lock_timeout_sec` int):
      shared_state_proposals_dir  <shared_state_root>/proposals
      id_ledger_path              <shared_state_root>/proposals/_id_ledger.json
      lock_path                   <shared_state_root>/proposals/_id_ledger.json.lock
      archive_dir                 <project_root>/proposals/_archive
      snapshot_dir                <project_root>/audit/proposal_snapshots
      lock_timeout_sec            PROPOSAL_LOCK_TIMEOUT_SEC
      agents                      [agent.name, ...]
    """
    if project_root is None:
        project_root = os.environ.get("GOVERNANCE_CORE_PROJECT_ROOT") or os.getcwd()
    root = Path(project_root).resolve()
    cfg = load_config(root)
    proposals_dir = cfg.shared_state_root / "proposals"
    return {
        "shared_state_proposals_dir": str(proposals_dir),
        "id_ledger_path": str(proposals_dir / "_id_ledger.json"),
        "lock_path": str(proposals_dir / "_id_ledger.json.lock"),
        "archive_dir": str(root / "proposals" / "_archive"),
        "snapshot_dir": str(root / "audit" / "proposal_snapshots"),
        "lock_timeout_sec": PROPOSAL_LOCK_TIMEOUT_SEC,
        "agents": [a.name for a in cfg.agents],
    }
