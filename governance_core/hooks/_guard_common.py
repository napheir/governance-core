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
import json
import os
import subprocess
import sys
from pathlib import Path


def _load_cross_repo_patterns():
    """Derive cross-repo block patterns from .governance/config.json.

    Pattern format: '<install-root-basename>/<clone-dir>' lowercased, matched
    as a substring against paths. Returns [] on any error — fail-open, the
    same posture as detect_role(): a config outage must not spuriously block.
    """
    try:
        repo_root = Path(__file__).resolve().parent.parent.parent
        cfg_path = repo_root / ".governance" / "config.json"
        if not cfg_path.exists():
            return []
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        root_name = Path(cfg.get("install_root", "")).name.lower()
        if not root_name:
            return []
        core_name = cfg.get("core_agent_name", "core")
        return [
            f"{root_name}/{a['clone_dir'].lower()}"
            for a in cfg.get("agents", [])
            if a.get("name") != core_name and a.get("clone_dir")
        ]
    except Exception:
        return []


# Cross-repo patterns blocked for non-core agents. shared_state/ is
# intentionally absent — see the shared-runtime-state clause. Derived from
# .governance/config.json; empty (fail-open) when config is missing.
CROSS_REPO_PATTERNS = _load_cross_repo_patterns()

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
    install_root_name = os.path.basename(os.path.dirname(repo_root)).lower()
    return f"{install_root_name}/{os.path.basename(repo_root).lower()}"
