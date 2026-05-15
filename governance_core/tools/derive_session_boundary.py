"""Session-boundary discovery for session-boundary-guard.py.

Per proposals/project_boundary_guard_for_extra_project_writes.md sec.2.1,
boundary is determined by walking up from cwd via three rules:

  1. Declarative override -- nearest ancestor with .claude/settings.json
     (or settings.local.json) containing a `projectRoot` field. The field
     is resolved as a path RELATIVE to the directory containing the
     settings file. First hit wins (closest to cwd).
  2. Git toplevel -- if no declarative, the first ancestor with a .git
     directory. Records as candidate; we keep walking for declarative
     in case it exists higher up.
  3. cwd itself -- if no declarative AND no git ancestor.

The walk is cwd -> root, so closer override wins over farther one.

Example: trade-agent project layout

    <install-root>/
      agent-core/                 <- core's clone
        .claude/settings.json     <- contains "projectRoot": "../"
      agent-rules/                <- rules' clone
        .claude/settings.local.json   <- contains "projectRoot": "../"
      ...

cwd=agent-core/      -> boundary = <install-root>/  (declarative)
cwd=~/projects/foo/  -> boundary = foo/             (git toplevel, if .git there)
cwd=~/scratch/       -> boundary = ~/scratch/       (cwd fallback)

Self-contained (no third-party deps); the bootstrap installer can deploy
this together with session-boundary-guard.py to ~/.claude/hooks/ as
peer files.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import NamedTuple


SETTINGS_FILES = (
    ".claude/settings.json",
    ".claude/settings.local.json",
)
PROJECT_ROOT_KEY = "projectRoot"


class Boundary(NamedTuple):
    """Resolved session boundary.

    Attributes:
        path: absolute resolved path; all writes must be inside this tree.
        rule: 'declarative' | 'git-toplevel' | 'cwd' -- which rule fired.
        source: path to the settings file that declared projectRoot
            (declarative only); else the directory matched (git
            toplevel) or None (cwd).
    """
    path: Path
    rule: str
    source: Path | None


def _read_project_root(settings_path: Path) -> str | None:
    """Return the projectRoot value (raw string) from a settings file, or None.

    Returns None on any read/parse error -- discovery falls through to next
    layer rather than failing loudly. (The hook's failure mode is "deny";
    bad settings shouldn't accidentally widen the boundary.)
    """
    try:
        text = settings_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    val = data.get(PROJECT_ROOT_KEY)
    if isinstance(val, str) and val.strip():
        return val.strip()
    return None


def derive_boundary(cwd: str | Path) -> Boundary:
    """Compute the session boundary for the given cwd.

    Args:
        cwd: starting directory. Will be resolved to an absolute canonical
            path before walking.

    Returns:
        Boundary with the resolved boundary path, the discovery rule that
        fired, and the source location (settings file or marker dir).
    """
    cwd_path = Path(cwd).resolve()

    git_top: Path | None = None
    cur = cwd_path
    while True:
        # Rule 1: declarative override (closest to cwd wins)
        for rel in SETTINGS_FILES:
            settings_path = cur / rel
            if not settings_path.is_file():
                continue
            raw = _read_project_root(settings_path)
            if raw is None:
                continue
            # Resolve projectRoot relative to <cur>
            resolved = (cur / raw).resolve()
            return Boundary(
                path=resolved,
                rule="declarative",
                source=settings_path,
            )

        # Rule 2: record first git toplevel encountered, keep walking
        # for a declarative override that may live higher up.
        if git_top is None and (cur / ".git").exists():
            git_top = cur

        parent = cur.parent
        if parent == cur:
            break
        cur = parent

    # Rule 3: fallbacks
    if git_top is not None:
        return Boundary(path=git_top, rule="git-toplevel", source=git_top)
    return Boundary(path=cwd_path, rule="cwd", source=None)


_GIT_BASH_DRIVE_RE = re.compile(r"^/([a-zA-Z])(/|$)")


def _translate_git_bash_path(p: str) -> str:
    """Translate Git Bash `/c/Users/...` to Windows `C:/Users/...`.

    Git Bash on Windows exposes drive letters as `/<letter>/...`, but
    Python's Path.resolve() on Windows treats `/c/...` as a path
    relative to the current drive (-> `C:\\c\\Users\\...`). Translate
    before resolve() so downstream comparison works.
    """
    m = _GIT_BASH_DRIVE_RE.match(p)
    if m:
        drive = m.group(1).upper()
        rest = p[m.end():]
        return f"{drive}:/{rest}"
    return p


def is_inside_boundary(target: str | Path, boundary: Path) -> bool:
    """Check whether a target path is inside the boundary tree.

    Resolves both to absolute canonical form (follows symlinks) before
    comparing, so symlinks cannot escape the boundary. Translates
    Git Bash drive paths (`/c/Users/...`) to Windows form before
    resolving.
    """
    raw = os.path.expanduser(str(target))
    raw = _translate_git_bash_path(raw)
    target_resolved = Path(raw).resolve()
    boundary_resolved = Path(boundary).resolve()
    try:
        target_resolved.relative_to(boundary_resolved)
        return True
    except ValueError:
        return False


# CLI mode for ad-hoc inspection.
if __name__ == "__main__":  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser(
        description="Derive Claude session boundary from a cwd."
    )
    parser.add_argument(
        "--cwd",
        default=None,
        help="Directory to derive boundary from (default: current cwd).",
    )
    parser.add_argument(
        "--check",
        default=None,
        help="Optional target path; reports whether it is inside the boundary.",
    )
    args = parser.parse_args()

    import os
    start = args.cwd or os.getcwd()
    b = derive_boundary(start)
    print(f"cwd:      {Path(start).resolve()}")
    print(f"boundary: {b.path}")
    print(f"rule:     {b.rule}")
    if b.source is not None:
        print(f"source:   {b.source}")
    if args.check:
        inside = is_inside_boundary(args.check, b.path)
        print(f"check:    {args.check} -> {'INSIDE' if inside else 'OUTSIDE'}")
