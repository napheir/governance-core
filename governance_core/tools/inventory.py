# -*- coding: utf-8 -*-
"""
tools/inventory.py - Harness capability inventory
--------------------------------------------------
Introspects the live state of all harness components and produces
a human-readable report of what exists, what's active, what's dormant.

Usage:
  python tools/inventory.py            # Full inventory report
  python tools/inventory.py --json     # Machine-readable JSON output

Categories:
  1. Defense Hooks      (PreToolUse / PostToolUse / Notification / git hooks)
  2. Governance Tools   (tools/*.py for auditing, checking, generating)
  3. Slash Commands     (.claude/commands/*.md)
  4. Agent Definitions  (.claude/agents/*.md)
  5. Active Experiments (tools/experiments.json)
  6. Scheduled Tasks    (Windows Task Scheduler entries)
  7. Infrastructure     (dispatcher, startup scripts)
"""
import io
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent
HOOKS_DIR = PROJECT_ROOT / ".claude" / "hooks"
COMMANDS_DIR = PROJECT_ROOT / ".claude" / "commands"
AGENTS_DIR = PROJECT_ROOT / ".claude" / "agents"
TOOLS_DIR = PROJECT_ROOT / "tools"
SETTINGS_FILE = PROJECT_ROOT / ".claude" / "settings.local.json"
REGISTRY_FILE = TOOLS_DIR / "harness_registry.json"
EXPERIMENTS_FILE = TOOLS_DIR / "experiments.json"
GIT_HOOKS_DIR = PROJECT_ROOT / ".git" / "hooks"


def _read_json(path: Path) -> dict:
    """Read a JSON file, return empty dict on failure."""
    if not path.is_file():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _extract_docstring(path: Path) -> str:
    """Extract first line of module docstring from a Python file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read(2000)
        # Match triple-quote docstring
        m = re.search(r'"""(.*?)(?:\n|""")', content, re.DOTALL)
        if m:
            first_line = m.group(1).strip().split("\n")[0]
            return first_line[:80]
        # Match single-line comment
        m = re.search(r'^#\s*(.+)', content, re.MULTILINE)
        if m:
            return m.group(1).strip()[:80]
    except Exception:
        pass
    return ""


def _extract_md_title(path: Path) -> str:
    """Extract title from a markdown file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("# "):
                    return line[2:].strip()[:80]
                if line.startswith("---"):
                    continue
                if line and not line.startswith("#"):
                    return line[:80]
    except Exception:
        pass
    return ""


# ============================================================
# Section Collectors
# ============================================================

def collect_hooks() -> dict:
    """Collect hook status: registered vs orphaned."""
    settings = _read_json(SETTINGS_FILE)
    hooks_config = settings.get("hooks", {})

    # Build set of registered hook files from settings
    registered_files = set()
    registered_details = []

    for stage in ["PreToolUse", "PostToolUse", "Notification"]:
        for entry in hooks_config.get(stage, []):
            matcher = entry.get("matcher", "*")
            for hook in entry.get("hooks", []):
                cmd = hook.get("command", "")
                # Extract hook file path from wrapper pattern
                m = re.search(r'[/\\]\.claude[/\\]hooks[/\\]([\w-]+\.py)', cmd)
                if m:
                    filename = m.group(1)
                    registered_files.add(filename)
                    registered_details.append({
                        "file": filename,
                        "stage": stage,
                        "matcher": matcher,
                        "timeout": hook.get("timeout", "?"),
                    })

    # List all hook files on disk
    all_hook_files = set()
    if HOOKS_DIR.is_dir():
        for f in HOOKS_DIR.iterdir():
            if f.suffix == ".py":
                all_hook_files.add(f.name)

    # Classify
    active = []
    orphaned = []

    for filename in sorted(all_hook_files):
        desc = _extract_docstring(HOOKS_DIR / filename)
        if filename in registered_files:
            stages = [d for d in registered_details if d["file"] == filename]
            stage_str = ", ".join(f"{d['stage']}:{d['matcher']}" for d in stages)
            active.append({"file": filename, "stages": stage_str, "description": desc})
        else:
            orphaned.append({"file": filename, "description": desc})

    # Git hooks
    git_hooks = []
    for name in ["pre-commit", "post-merge"]:
        path = GIT_HOOKS_DIR / name
        if path.is_file():
            git_hooks.append({"file": name, "status": "active"})

    return {"active": active, "orphaned": orphaned, "git_hooks": git_hooks}


def collect_tools() -> list:
    """Collect governance tools inventory."""
    tools = []
    if not TOOLS_DIR.is_dir():
        return tools

    # Categorize tools
    CATEGORIES = {
        "audit": ["audit_hooks", "audit_harness_expiry", "audit_sub_constitutions",
                   "check_scope", "check_agent_roles", "check_constitution_change"],
        "testing": ["run_daily_regression", "run_master_gate", "capture_baseline",
                     "prepare_frozen_dataset", "test_notifier", "report_generator"],
        "generation": ["generate_settings", "hook_runner"],
        "dispatcher": ["task_dispatcher", "install_dispatcher_startup"],
        "analysis": ["analyze_shadow_log", "build_abc_cache", "post_turn_verify",
                      "inventory"],
    }

    # Reverse lookup
    file_to_category = {}
    for cat, files in CATEGORIES.items():
        for f in files:
            file_to_category[f] = cat

    for f in sorted(TOOLS_DIR.iterdir()):
        if f.suffix == ".py":
            stem = f.stem
            desc = _extract_docstring(f)
            category = file_to_category.get(stem, "other")
            tools.append({"file": f.name, "category": category, "description": desc})
        elif f.suffix in (".bat", ".ps1"):
            tools.append({"file": f.name, "category": "scripts", "description": ""})

    return tools


def collect_commands() -> list:
    """Collect slash commands."""
    commands = []
    if not COMMANDS_DIR.is_dir():
        return commands

    for f in sorted(COMMANDS_DIR.iterdir()):
        if f.suffix == ".md":
            title = _extract_md_title(f)
            commands.append({"command": f"/{f.stem}", "description": title})

    return commands


def collect_agents() -> list:
    """Collect agent definitions."""
    agents = []
    if not AGENTS_DIR.is_dir():
        return agents

    for f in sorted(AGENTS_DIR.iterdir()):
        if f.suffix == ".md":
            title = _extract_md_title(f)
            agents.append({"name": f.stem, "description": title})

    return agents


def collect_experiments() -> list:
    """Collect active experiments."""
    data = _read_json(EXPERIMENTS_FILE)
    experiments = []
    today = datetime.now()

    for exp in data.get("experiments", []):
        end_date = datetime.strptime(exp["end_date"], "%Y-%m-%d")
        days_left = (end_date - today).days
        experiments.append({
            "id": exp["id"],
            "status": exp["status"],
            "end_date": exp["end_date"],
            "days_left": days_left,
            "description": exp["description"][:100],
        })

    return experiments


def collect_registry_summary() -> dict:
    """Collect harness component lifecycle summary."""
    data = _read_json(REGISTRY_FILE)
    components = data.get("components", [])

    architectural = sum(1 for c in components if c.get("expiry_likelihood") == "none")
    capability = len(components) - architectural
    overdue = sum(
        1 for c in components
        if (datetime.now() - datetime.strptime(c["last_reviewed"], "%Y-%m-%d")).days > 90
    )

    return {
        "total": len(components),
        "architectural": architectural,
        "capability_dependent": capability,
        "overdue_reviews": overdue,
    }


def collect_permissions() -> dict:
    """Collect permission count summary."""
    settings = _read_json(SETTINGS_FILE)
    perms = settings.get("permissions", {}).get("allow", [])
    return {"count": len(perms)}


# ============================================================
# Report Rendering
# ============================================================

def render_text_report(data: dict) -> str:
    """Render inventory as human-readable text."""
    lines = []
    today = datetime.now().strftime("%Y-%m-%d")
    lines.append(f"=== Harness Capability Inventory ({today}) ===\n")

    # 1. Defense Hooks
    hooks = data["hooks"]
    lines.append(f"## 1. Defense Hooks ({len(hooks['active'])} active, "
                 f"{len(hooks['orphaned'])} orphaned, "
                 f"{len(hooks['git_hooks'])} git)")
    lines.append("")

    lines.append("  Active (registered in settings.local.json):")
    for h in hooks["active"]:
        lines.append(f"    [ON]  {h['file']:30s} {h['stages']}")
    lines.append("")

    if hooks["orphaned"]:
        lines.append("  Orphaned (file exists but not registered):")
        for h in hooks["orphaned"]:
            lines.append(f"    [OFF] {h['file']:30s} {h['description']}")
        lines.append("")

    if hooks["git_hooks"]:
        lines.append("  Git hooks:")
        for h in hooks["git_hooks"]:
            lines.append(f"    [ON]  .git/hooks/{h['file']}")
    lines.append("")

    # 2. Governance Tools
    tools = data["tools"]
    by_cat = {}
    for t in tools:
        by_cat.setdefault(t["category"], []).append(t)

    lines.append(f"## 2. Governance Tools ({len(tools)} total)")
    lines.append("")
    for cat in ["audit", "testing", "generation", "dispatcher", "analysis", "scripts", "other"]:
        items = by_cat.get(cat, [])
        if not items:
            continue
        lines.append(f"  [{cat}]")
        for t in items:
            desc = f" - {t['description']}" if t["description"] else ""
            lines.append(f"    {t['file']:40s}{desc}")
    lines.append("")

    # 3. Slash Commands
    commands = data["commands"]
    lines.append(f"## 3. Slash Commands ({len(commands)})")
    lines.append("")
    for c in commands:
        lines.append(f"    {c['command']:25s} {c['description']}")
    lines.append("")

    # 4. Agent Definitions
    agents = data["agents"]
    lines.append(f"## 4. Agent Definitions ({len(agents)})")
    lines.append("")
    for a in agents:
        lines.append(f"    {a['name']:25s} {a['description']}")
    lines.append("")

    # 5. Experiments
    experiments = data["experiments"]
    lines.append(f"## 5. Active Experiments ({len(experiments)})")
    lines.append("")
    for e in experiments:
        status_marker = "[OVERDUE]" if e["days_left"] < 0 else f"[{e['days_left']}d left]"
        lines.append(f"    {e['id']:35s} {e['status']:10s} {status_marker}")
    if not experiments:
        lines.append("    (none)")
    lines.append("")

    # 6. Component Lifecycle
    registry = data["registry"]
    lines.append(f"## 6. Component Lifecycle ({registry['total']} tracked)")
    lines.append(f"    Architectural (never expire): {registry['architectural']}")
    lines.append(f"    Capability-dependent:         {registry['capability_dependent']}")
    lines.append(f"    Overdue for review:           {registry['overdue_reviews']}")
    lines.append("")

    # 7. Permissions
    perms = data["permissions"]
    lines.append(f"## 7. Permissions ({perms['count']} allow rules)")
    lines.append("")

    # Summary
    total_caps = (len(hooks["active"]) + len(hooks["git_hooks"]) +
                  len(tools) + len(commands) + len(agents))
    dormant = len(hooks["orphaned"])
    lines.append("=" * 50)
    lines.append(f"Total capabilities: {total_caps} active, {dormant} dormant")
    lines.append("=" * 50)

    return "\n".join(lines)


# ============================================================
# Main
# ============================================================

def main() -> None:
    """Collect and display harness inventory."""
    data = {
        "hooks": collect_hooks(),
        "tools": collect_tools(),
        "commands": collect_commands(),
        "agents": collect_agents(),
        "experiments": collect_experiments(),
        "registry": collect_registry_summary(),
        "permissions": collect_permissions(),
        "generated_at": datetime.now().isoformat(),
    }

    if "--json" in sys.argv:
        sys.stdout.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    else:
        sys.stdout.write(render_text_report(data) + "\n")


if __name__ == "__main__":
    main()
