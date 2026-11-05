# -*- coding: utf-8 -*-
"""
check_agent_roles.py
--------------------
Validate that each agent's .claude/agents/ directory follows the role
definition rules of the project-architecture clause (art_01 角色定义规范).

Agents and their clone directories come from .governance/config.json
(P-0130 -- the upstream agents, clone paths and role-prefix vocabularies were
hard-coded here before, so the tool rejected every other project's agents).

Checks:
1. Each agent has at least one core role file named after it (<agent>-*.md)
2. No cross-scope role files: a role file whose name prefix is ANOTHER
   agent's name (shared roles such as design-system-owner.md are fine)
3. Role files have YAML frontmatter with name / description / tools

Clone roots: a single-agent project checks this repo; a multi-clone project
checks <this clone's parent>/<clone_dir> for every agent.

Usage:
    python tools/check_agent_roles.py
    python tools/check_agent_roles.py --agent platform
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_agent_roots(root: Path) -> dict:
    """Return {agent name: clone root Path} from root's config (fail loud)."""
    from governance_core.config import load_config
    cfg = load_config(root)
    if len(cfg.agents) == 1:
        return {cfg.agents[0].name: root}
    return {a.name: root.parent / a.clone_dir for a in cfg.agents}


def check_agent(name: str, clone_root: Path, agent_names: set) -> list:
    """Check one agent's role definitions. Returns list of issue strings."""
    issues = []
    roles_dir = clone_root / ".claude" / "agents"

    if not clone_root.exists():
        issues.append(f"[WARN] {name}: clone directory not found: {clone_root}")
        return issues

    if not roles_dir.exists():
        issues.append(f"[HIGH] {name}: .claude/agents/ directory missing")
        return issues

    role_files = sorted(roles_dir.glob("*.md"))
    if not role_files:
        issues.append(f"[HIGH] {name}: no role definition files found")
        return issues

    # Check 1: a core role named after the agent
    if not any(rf.stem == name or rf.stem.startswith(f"{name}-")
               for rf in role_files):
        issues.append(
            f"[HIGH] {name}: missing core role file named after the agent "
            f"({name}-<role>.md)"
        )

    # Check 2: no role file claimed by another agent's name
    others = agent_names - {name}
    for rf in role_files:
        prefix = rf.stem.split("-")[0]
        if prefix in others:
            issues.append(
                f"[HIGH] {name}: cross-scope role file: {rf.name} "
                f"(prefix '{prefix}' is agent '{prefix}')"
            )

    # Check 3: YAML frontmatter exists with the required fields
    for rf in role_files:
        try:
            content = rf.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            issues.append(f"[WARN] {name}: cannot read {rf.name}: {exc}")
            continue
        if not content.startswith("---"):
            issues.append(f"[WARN] {name}: {rf.name} missing YAML frontmatter")
            continue
        end_idx = content.find("---", 3)
        if end_idx == -1:
            issues.append(f"[WARN] {name}: {rf.name} incomplete YAML frontmatter")
            continue
        frontmatter = content[3:end_idx]
        for field in ("name:", "description:", "tools:"):
            if field not in frontmatter:
                issues.append(
                    f"[WARN] {name}: {rf.name} missing frontmatter field: {field}"
                )

    return issues


def main(root: Path = ROOT, argv: list | None = None) -> int:
    """Run role definition compliance checks; return the exit code."""
    parser = argparse.ArgumentParser(description="Check agent role definitions")
    parser.add_argument("--agent", help="Check specific agent only")
    args = parser.parse_args(argv)

    agent_roots = load_agent_roots(root)
    agent_names = set(agent_roots)
    if args.agent:
        if args.agent not in agent_roots:
            print(f"Unknown agent: {args.agent}")
            print(f"Available (from config): {', '.join(sorted(agent_names))}")
            return 1
        to_check = {args.agent: agent_roots[args.agent]}
    else:
        to_check = agent_roots

    all_issues = []
    for name, clone_root in to_check.items():
        print(f"Checking {name}...")
        issues = check_agent(name, clone_root, agent_names)
        all_issues.extend(issues)
        if not issues:
            print(f"  [OK] {name}: all checks passed")
        else:
            for issue in issues:
                print(f"  {issue}")

    print()
    high_count = sum(1 for i in all_issues if i.startswith("[HIGH]"))
    warn_count = sum(1 for i in all_issues if i.startswith("[WARN]"))
    if high_count > 0:
        print(f"Result: {high_count} HIGH, {warn_count} WARN issues found")
        return 1
    if warn_count > 0:
        print(f"Result: {warn_count} WARN issues (no HIGH)")
        return 0
    print("Result: All agents compliant")
    return 0


if __name__ == "__main__":
    sys.exit(main())
