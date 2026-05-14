"""Shared utilities for scope-guard.py and edit-write-guard.py.

Both guards (Bash matcher + Edit/Write matcher) need:
  - branch-to-role mapping (master → core, feature/<x>-* → x)
  - block() helper that prints a uniform banner to stderr + exit 2
  - cross-repo path patterns (other clones)

Extracted on 2026-04-28 per Phase 3 of
proposals/slim_constitution_via_registry_and_router.md to remove ~80 lines
of duplicated logic. Each guard still has its own matcher + tool-specific
checks; only the shared cross-cutting concerns live here.

Sync: this file is in sync_infra.ALWAYS_COPY_FILES, so every clone has
its own copy (each guard resolves _REPO_ROOT relative to its own clone).
"""
import os
import subprocess
import sys

# Cross-repo patterns blocked for non-core agents. shared_state/ is
# intentionally absent — see CLAUDE.md 第四条之一.
CROSS_REPO_PATTERNS = [
    "pythonproject1/agent-rules",
    "pythonproject1/agent-trade",
    "pythonproject1/agent-data",
    "pythonproject1/agent-research",
]

# Branches mapped to "core" (unrestricted)
CORE_BRANCHES = {"master", "main"}

# Branch-prefix → role
ROLE_PREFIX_MAP = {
    "feature/trade": "trade",
    "feature/models": "models",
    "feature/data": "data",
    "feature/simu": "simu",
    "feature/rules": "rules",
    "feature/research": "research",
}


def detect_role(repo_root: str = "") -> str:
    """Detect agent role from current git branch.

    Args:
        repo_root: Optional cwd for git invocation. Empty → use $CWD.

    Fail-open semantics: any error / unknown branch returns "core" so the
    guard does NOT spuriously block during git outage or detached HEAD.
    """
    try:
        kwargs = {"capture_output": True, "text": True, "timeout": 5}
        if repo_root:
            kwargs["cwd"] = repo_root
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], **kwargs
        )
        branch = result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return "core"

    if branch in CORE_BRANCHES:
        return "core"
    for prefix, role in ROLE_PREFIX_MAP.items():
        if branch.startswith(prefix):
            return role
    return "core"


def block(guard_name: str, reason: str, detail: str) -> None:
    """Print a uniform block banner to stderr and sys.exit(2).

    Both guards use the same banner format so user sees a consistent
    diagnostic regardless of which guard fired.
    """
    sys.stderr.write("\n")
    sys.stderr.write("=========================================\n")
    sys.stderr.write(f"[{guard_name}] {reason}\n")
    sys.stderr.write("=========================================\n")
    sys.stderr.write("\n")
    sys.stderr.write(detail + "\n")
    sys.stderr.write("\n")
    sys.exit(2)


def own_repo_pattern(hook_file: str) -> str:
    """Return the cross-repo pattern matching the hook's own repo.

    Used by scope-guard to skip blocking when a Bash command references
    its own clone (which is legitimate; only OTHER clones are off-limits).

    Args:
        hook_file: __file__ of the calling hook script.
    """
    # Hook lives at <repo>/.claude/hooks/<name>.py
    repo_root = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(hook_file)), "..", "..")
    )
    return f"pythonproject1/{os.path.basename(repo_root).lower()}"
