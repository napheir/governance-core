# -*- coding: utf-8 -*-
"""
merge-audit.py - PostToolUse Bash hook for automatic audit on merge/pull
------------------------------------------------------------------------
Detects completed git merge or git pull operations and automatically runs
scope audit to verify no cross-scope violations were introduced.

Non-blocking (always exit 0). Outputs audit results as informational
feedback to the agent.

Hypothesis: Merge operations may introduce cross-scope violations that
go undetected without immediate audit.
Created: 2026-04-05
Review schedule: Quarterly (next: 2026-07-05)
"""
import io
import json
import os
import re
import subprocess
import sys

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Patterns that indicate a merge/pull operation
MERGE_PATTERNS = [
    r"\bgit\s+merge\b",
    r"\bgit\s+pull\b",
    r"\bgit\s+rebase\b",
]

# Tools directory (relative to project root)
SCOPE_CHECK = "tools/check_scope.py"

# Agent role detection from branch name
BRANCH_ROLE_MAP = {
    "master": "core",
    "main": "core",
    "feature/rules": "rules",
    "feature/trade": "trade",
    "feature/data": "data",
    "feature/research": "research",
}


def is_merge_command(command: str) -> bool:
    """Check if the Bash command is a merge/pull operation."""
    for pattern in MERGE_PATTERNS:
        if re.search(pattern, command):
            return True
    return False


def detect_role() -> str:
    """Detect current agent role from git branch."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        branch = result.stdout.strip()
    except Exception:
        return "core"

    for prefix, role in BRANCH_ROLE_MAP.items():
        if branch.startswith(prefix) or branch == prefix:
            return role
    return "core"


def run_scope_audit(role: str) -> str:
    """Run scope check for the detected role."""
    if not os.path.isfile(SCOPE_CHECK):
        return "[merge-audit] Scope checker not found, skipping."

    try:
        result = subprocess.run(
            [sys.executable, SCOPE_CHECK, "--agent", role],
            capture_output=True, text=True, timeout=15,
        )
        output = result.stdout.strip()
        if result.returncode == 0:
            return f"[merge-audit] Post-merge scope audit PASSED for '{role}'."
        else:
            return (
                f"[merge-audit] Post-merge scope audit FAILED for '{role}'!\n"
                f"{output}\n"
                "-> Review the merge for scope violations before continuing."
            )
    except subprocess.TimeoutExpired:
        return "[merge-audit] Scope audit timed out (15s)."
    except Exception as e:
        return f"[merge-audit] Scope audit error: {e}"


def count_changed_files() -> int:
    """Count files changed in the most recent merge commit."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1..HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        files = [f for f in result.stdout.strip().split("\n") if f]
        return len(files)
    except Exception:
        return 0


def main() -> None:
    """Detect merge commands and trigger audit."""
    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except (json.JSONDecodeError, Exception):
        sys.exit(0)

    tool_name = event.get("tool_name", "")
    if tool_name != "Bash":
        sys.exit(0)

    # Check if this was a merge/pull command
    tool_input = event.get("tool_input", {})
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    if not command:
        # PostToolUse may have command in different location
        command = event.get("input", {}).get("command", "") if isinstance(event.get("input"), dict) else ""

    if not is_merge_command(command):
        sys.exit(0)

    # This was a merge/pull - run audit
    role = detect_role()
    changed = count_changed_files()

    sys.stdout.write(f"[merge-audit] Detected merge operation ({changed} files changed).\n")

    audit_result = run_scope_audit(role)
    sys.stdout.write(audit_result + "\n")

    sys.exit(0)


if __name__ == "__main__":
    main()
