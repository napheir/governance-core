"""
Claude Code PreToolUse hook: scope-guard.py

Intercepts Bash tool calls and blocks commands that target paths
outside the current agent's scope. Auto-detects current repo from
hook file location to avoid false-positive blocking of own-repo paths.

Three enforcement layers (for non-core agents):
  1. Cross-repo blocking: commands referencing other agent repos
  2. --no-verify blocking: prevents bypassing pre-commit scope checks
  3. Python write blocking: detects file write operations in python -c
     commands, forces agents to use Edit/Write tools (which are guarded
     by edit-write-guard.py)

Branch-based role detection:
  master / main       -> core   (governance authority, no restrictions)
  feature/trade-*     -> trade  (blocked from other agent repos)
  feature/rules-*     -> rules  (blocked from other agent repos)
  feature/data-*      -> data   (blocked from other agent repos)
  feature/research-*  -> research (blocked from other agent repos)
  feature/models-*    -> models (blocked from other agent repos)
  feature/simu-*      -> simu   (blocked from other agent repos)
  unknown             -> core   (fail-open to most permissive)

Exit codes:
  0 = allow command
  2 = block command (Claude Code will not execute it)

Receives JSON on stdin with the tool call details.
"""
import os
import re
import sys
import json

# Shared cross-cutting logic (role detection, block(), repo patterns) lives
# in _guard_common.py — same dir, must add to sys.path before import.
# FAIL-CLOSED: if _guard_common is missing (sync hiccup, bad clone state),
# we MUST exit 2 to block the tool — silently exit 0 would leave non-core
# agents able to write any path. Better to break loud than fail open.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from _guard_common import (  # noqa: E402
        CROSS_REPO_PATTERNS as BLOCKED_PATTERNS,
        detect_role as _detect_role_shared,
        block as _block_shared,
        own_repo_pattern,
    )
except ImportError as exc:
    sys.stderr.write(
        "\n[SCOPE GUARD FATAL] Cannot import _guard_common.py "
        f"(error: {exc}).\n"
        "This indicates a broken clone state. Run from agent-core:\n"
        "  python tools/sync_infra.py --execute\n"
        "to restore .claude/hooks/_guard_common.py in this clone.\n"
        "Blocking tool call until resolved.\n"
    )
    sys.exit(2)

# Patterns that indicate file write operations in Python commands.
# Non-core agents should use Edit/Write tools instead (properly guarded).
PYTHON_WRITE_PATTERNS = [
    r'open\s*\([^)]*["\'][wa]',       # open("file", "w") or "a"
    r'\.write\s*\(',                   # .write(...)
    r'\.write_text\s*\(',              # Path.write_text(...)
    r'\.write_bytes\s*\(',             # Path.write_bytes(...)
    r'\.mkdir\s*\(',                   # Path.mkdir(...)
    r'\.rename\s*\(',                  # Path.rename(...)
    r'\.replace\s*\(',                 # Path.replace(...)
    r'\.unlink\s*\(',                  # Path.unlink(...)
    r'\.rmdir\s*\(',                   # Path.rmdir(...)
    r'shutil\.(copy|move|rmtree)',     # shutil operations
    r'os\.(remove|unlink|rename|makedirs)',  # os file operations
]

# Auto-detect current repo to exclude from blocked patterns.
_OWN_PATTERN = own_repo_pattern(__file__)


def _detect_role() -> str:
    return _detect_role_shared()


def _block(role, reason, detail):
    """Block with role-tagged banner."""
    _block_shared("SCOPE GUARD", f"{reason} (role={role})", detail)


def _check_no_verify(command, role):
    """Block --no-verify for non-core agents."""
    if "--no-verify" in command:
        _block(role, "Bash command BLOCKED",
               "--no-verify bypasses pre-commit scope checks.\n"
               "Non-core agents may not skip scope enforcement.\n"
               "If this change is authorized, ask core agent to commit it.")


def _check_python_writes(command, role):
    """Block Python file write operations for non-core agents.

    Forces agents to use Edit/Write tools for file modifications,
    which are guarded by edit-write-guard.py with proper scope checks.
    """
    if not re.search(r'python[3]?\s+-c\s', command):
        return

    for pattern in PYTHON_WRITE_PATTERNS:
        if re.search(pattern, command):
            _block(role, "Bash command BLOCKED",
                   f"Python command contains file write operation "
                   f"(matched: '{pattern}').\n"
                   "Non-core agents must use Edit/Write tools for file "
                   "modifications\n"
                   "(these are guarded by edit-write-guard.py with scope "
                   "checks).")


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")
    if not command:
        sys.exit(0)

    role = _detect_role()
    if role == "core":
        sys.exit(0)

    # --- Layer 1: Cross-repo blocking ---
    cmd_norm = command.lower().replace("\\", "/")

    for pattern in BLOCKED_PATTERNS:
        if pattern == _OWN_PATTERN:
            continue
        if pattern in cmd_norm:
            repo_name = pattern.split("/")[-1]
            _block(role, "Bash command BLOCKED",
                   f"Command references {repo_name} which is outside "
                   f"your scope.\n"
                   f"Current branch role: {role} (only core can access "
                   f"other repos)\n\n"
                   "For READ access: use Read/Grep/Glob tools (not Bash).\n"
                   "For WRITE access: request explicit user authorization.")

    # --- Layer 2: --no-verify blocking ---
    _check_no_verify(command, role)

    # --- Layer 3: Python file write blocking ---
    _check_python_writes(command, role)

    sys.exit(0)


if __name__ == "__main__":
    main()
