# -*- coding: utf-8 -*-
"""Skill discovery and progressive loading subsystem.

Inspired by Hermes Agent's skill learning loop.

Architecture (P-0069): the machinery (tracker / extractor / registry) ships
inside the governance-core package and is imported as
``governance_core.discovery``. Per-project state (.usage.json, learned/*.md)
lives in the consuming project, resolved at runtime via
``resolve_project_root()`` — so state is never written across project
boundaries and is not confused with the package's code location.
"""
import os
import subprocess
from pathlib import Path
from typing import Optional

_ROOT_CACHE: Optional[Path] = None


def resolve_project_root(module_file: Optional[str] = None) -> Path:
    """Resolve the consuming project's root for skill-learning state.

    Resolution order:
      1. ``CLAUDE_AGENT_ROOT`` env var (explicit override)
      2. ``git rev-parse --show-toplevel`` from current working directory
      3. Module-file parent (last-resort fallback when git is unavailable)

    Cached on first call to avoid repeated subprocess overhead.

    Args:
        module_file: ``__file__`` of the caller, used as fallback when
            git resolution fails.

    Returns:
        Path to the project root where skill-learning state files live.
    """
    global _ROOT_CACHE
    if _ROOT_CACHE is not None:
        return _ROOT_CACHE

    env = os.environ.get("CLAUDE_AGENT_ROOT")
    if env:
        _ROOT_CACHE = Path(env).resolve()
        return _ROOT_CACHE

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            _ROOT_CACHE = Path(result.stdout.strip()).resolve()
            return _ROOT_CACHE
    except (OSError, subprocess.TimeoutExpired):
        pass

    if module_file:
        _ROOT_CACHE = Path(module_file).resolve().parent.parent.parent
        return _ROOT_CACHE

    _ROOT_CACHE = Path.cwd().resolve()
    return _ROOT_CACHE


def _reset_root_cache() -> None:
    """Clear the resolver cache (test-only helper)."""
    global _ROOT_CACHE
    _ROOT_CACHE = None
