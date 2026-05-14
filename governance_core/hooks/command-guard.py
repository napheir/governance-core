"""Claude Code PreToolUse hook: command-guard.py

Command-level deny/allow guard for Bash tool calls.
Runs BEFORE scope-guard.py to provide fast-path blocking/allowing.

Layers:
  0.   Evasion detection: block base64 decode, pipe-to-shell, eval, etc.
  0.5. Allow-prefix early-pass (rm into safe whitelisted paths bypass deny)
       — promoted from former Layer 2 so the wide rm regex in 1.5 has a
         configurable escape hatch via shared.allow_commands.txt prefix list.
  1.   Literal deny list: command contains any deny substring -> exit 2 (block)
  1.5. Regex deny list: command matches any destructive regex -> exit 2 (block)
       — handles case variance + path variants the substring layer can't catch.
       Bad regex in deny file = fail-closed (block all, surface error).
  2.   Delegate: exit 0 (hand off to scope-guard for path-level checks)

Inspired by Claude Code src/utils/permissions/permissions.ts Layer 2/3.

Exit codes:
  0 = allow (or delegate to next hook)
  2 = block

History:
  - Layer 0.5 + Layer 1.5 added per
    proposals/harden_destructive_command_guard.md (2026-05-01).
"""
import json
import re
import sys
from pathlib import Path


# -- Evasion pattern detection --
# These catch attempts to bypass deny-list substring matching via encoding,
# indirection, or pipe-to-interpreter patterns.
EVASION_PATTERNS = [
    (r"base64\s+(-d|--decode)", "base64 decode execution"),
    (r"\|\s*bash\b", "pipe to bash"),
    (r"\|\s*sh\b", "pipe to sh"),
    (r"\|\s*zsh\b", "pipe to zsh"),
    (r"bash\s+<<<", "bash herestring"),
    (r"sh\s+<<<", "sh herestring"),
    (r"\beval\s+\$", "eval with variable expansion"),
    (r"\bsource\s+/dev/stdin", "source from stdin"),
    (r"curl\s.*\|\s*(bash|sh|python)", "curl pipe to interpreter"),
    (r"wget\s.*\|\s*(bash|sh|python)", "wget pipe to interpreter"),
    (r"\bexec\s*\(.*fromhex", "Python hex decode exec"),
    (r"\b__import__\s*\(", "Python dynamic import"),
]


def load_patterns(filepath: str) -> list:
    """Load patterns from a text file, ignoring blanks and comments."""
    path = Path(filepath)
    if not path.exists():
        return []
    patterns = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def main():
    """Check Bash commands against deny/allow lists."""
    try:
        hook_input = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool_name = hook_input.get("tool_name", "")
    if tool_name != "Bash":
        sys.exit(0)

    command = hook_input.get("tool_input", {}).get("command", "")
    if not command:
        sys.exit(0)

    # Project root: hook lives at <repo>/.claude/hooks/command-guard.py
    root = Path(__file__).resolve().parent.parent.parent
    deny_path = root / "agent_rules" / "shared.deny_commands.txt"
    deny_regex_path = root / "agent_rules" / "shared.deny_commands_regex.txt"
    allow_path = root / "agent_rules" / "shared.allow_commands.txt"

    # 0. Evasion detection (regex, case-insensitive)
    for regex, label in EVASION_PATTERNS:
        if re.search(regex, command, re.IGNORECASE):
            print(
                f"[COMMAND GUARD] BLOCKED: evasion pattern detected "
                f"({label})",
                file=sys.stderr,
            )
            sys.exit(2)

    # 0.5. Allow-prefix early-pass.
    # An explicit allow prefix (e.g. "prefix:rm /tmp/") wins over the
    # subsequent deny layers — this is the configured escape hatch for
    # the wide rm regex in 1.5.
    for pattern in load_patterns(str(allow_path)):
        if pattern.startswith("prefix:"):
            prefix = pattern[len("prefix:"):]
            if command.startswith(prefix):
                sys.exit(0)  # explicit allow; skip remaining deny layers

    # 1. Literal deny check (substring match, case-sensitive)
    for pattern in load_patterns(str(deny_path)):
        if pattern in command:
            print(
                f"[COMMAND GUARD] BLOCKED: command contains "
                f"denied pattern '{pattern}'",
                file=sys.stderr,
            )
            sys.exit(2)

    # 1.5. Regex deny check (handles case variance + path variants).
    # Bad regex = fail-closed (block all, surface error) — same philosophy
    # as _guard_common import failure in edit-write-guard.py.
    for pattern in load_patterns(str(deny_regex_path)):
        try:
            if re.search(pattern, command):
                print(
                    f"[COMMAND GUARD] BLOCKED: command matches "
                    f"destructive regex /{pattern}/",
                    file=sys.stderr,
                )
                sys.exit(2)
        except re.error as exc:
            print(
                f"[COMMAND GUARD] FATAL: regex syntax error in "
                f"shared.deny_commands_regex.txt -- pattern={pattern!r} "
                f"err={exc}. Blocking until fixed.",
                file=sys.stderr,
            )
            sys.exit(2)

    # 2. Delegate to subsequent hooks (scope-guard etc.)
    sys.exit(0)


if __name__ == "__main__":
    main()
