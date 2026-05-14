# -*- coding: utf-8 -*-
"""
check_agent_roles.py
--------------------
Validate that each agent's .claude/agents/ directory follows the role
definition standards defined in AGENTS.md.

Checks:
1. Each agent has at least one core role file (<agent>-specialist.md)
2. No cross-scope role files (e.g. trade-specialist.md in data-agent)
3. Role files have valid YAML frontmatter

Usage:
    python tools/check_agent_roles.py
    python tools/check_agent_roles.py --agent data
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent

# Agent definitions: name -> (clone directory, allowed role prefixes)
AGENT_DEFS = {
    "rules": {
        "dir": "agent-rules",
        "allowed_prefixes": ["rules", "algorithm", "finance", "model", "signal"],
        "core_role": "rules-specialist.md",
    },
    "trade": {
        "dir": "agent-trade",
        "allowed_prefixes": ["trade", "execution", "risk", "order"],
        "core_role": "trade-specialist.md",
    },
    "data": {
        "dir": "agent-data",
        "allowed_prefixes": ["data", "design", "dashboard", "collector", "analysis"],
        "core_role": "data-specialist.md",
    },
    "research": {
        "dir": "agent-research",
        "allowed_prefixes": ["research", "evaluation", "prototype", "survey"],
        "core_role": "research-specialist.md",
    },
}


def check_agent(name: str, defn: dict) -> list:
    """Check a single agent's role definitions. Returns list of issues."""
    issues = []
    agent_dir = PROJECT_ROOT / defn["dir"]
    roles_dir = agent_dir / ".claude" / "agents"

    if not agent_dir.exists():
        issues.append(f"[WARN] {name}: clone directory not found: {agent_dir}")
        return issues

    if not roles_dir.exists():
        issues.append(f"[HIGH] {name}: .claude/agents/ directory missing")
        return issues

    role_files = list(roles_dir.glob("*.md"))
    if not role_files:
        issues.append(f"[HIGH] {name}: no role definition files found")
        return issues

    # Check 1: core role exists
    core_role = defn["core_role"]
    if not (roles_dir / core_role).exists():
        issues.append(
            f"[HIGH] {name}: missing core role file: {core_role}"
        )

    # Check 2: no cross-scope roles
    allowed = defn["allowed_prefixes"]
    for rf in role_files:
        stem = rf.stem  # e.g. "trade-specialist"
        first_part = stem.split("-")[0]  # e.g. "trade"
        if first_part not in allowed:
            issues.append(
                f"[HIGH] {name}: cross-scope role file: {rf.name} "
                f"(prefix '{first_part}' not in allowed: {allowed})"
            )

    # Check 3: YAML frontmatter exists
    for rf in role_files:
        try:
            content = rf.read_text(encoding="utf-8")
        except Exception as e:
            issues.append(f"[WARN] {name}: cannot read {rf.name}: {e}")
            continue

        if not content.startswith("---"):
            issues.append(
                f"[WARN] {name}: {rf.name} missing YAML frontmatter"
            )
            continue

        # Check for required frontmatter fields
        end_idx = content.find("---", 3)
        if end_idx == -1:
            issues.append(
                f"[WARN] {name}: {rf.name} incomplete YAML frontmatter"
            )
            continue

        frontmatter = content[3:end_idx]
        for field in ["name:", "description:", "tools:"]:
            if field not in frontmatter:
                issues.append(
                    f"[WARN] {name}: {rf.name} missing frontmatter field: {field}"
                )

    return issues


def main():
    """Run role definition compliance checks."""
    parser = argparse.ArgumentParser(description="Check agent role definitions")
    parser.add_argument("--agent", help="Check specific agent only")
    args = parser.parse_args()

    agents_to_check = {}
    if args.agent:
        if args.agent not in AGENT_DEFS:
            print(f"Unknown agent: {args.agent}")
            print(f"Available: {', '.join(AGENT_DEFS.keys())}")
            sys.exit(1)
        agents_to_check[args.agent] = AGENT_DEFS[args.agent]
    else:
        agents_to_check = AGENT_DEFS

    all_issues = []
    for name, defn in agents_to_check.items():
        print(f"Checking {name}...")
        issues = check_agent(name, defn)
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
        sys.exit(1)
    elif warn_count > 0:
        print(f"Result: {warn_count} WARN issues (no HIGH)")
        sys.exit(0)
    else:
        print("Result: All agents compliant")
        sys.exit(0)


if __name__ == "__main__":
    main()
