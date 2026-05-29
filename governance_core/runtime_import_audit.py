# -*- coding: utf-8 -*-
"""Runtime-import-discipline check (P-0081; issue #3 root-cause).

Invariant
---------
A shipped hook that imports ``governance_core`` at runtime MUST guard the
import and **fail open** (``sys.exit(0)`` -- degrade, never obstruct) if the
import fails. A hook that must **fail closed** (a security gate that denies
the tool call on any error) MUST instead be **self-contained** -- it must NOT
import ``governance_core`` at all. The reason: for a fail-closed per-call gate,
an *import* failure (a broken/uninstalled package -- an infrastructure problem)
is indistinguishable from a real denial, so it would block *every* tool call
and freeze the session. A self-contained gate has no import to fail.

Evidence (0.14.0): every shipped hook that imports ``governance_core`` guards
it and fails open -- ``sensitive-data-guard`` even documents "auth-guard
already fails closed on a broken package" -- EXCEPT ``auth-guard.py`` itself,
which is a PreToolUse ``*`` gate that fails closed. ``auth-guard`` is therefore
the sole violator and is grandfathered here pending its self-containment
refactor (P-0082).

This module is the single source of truth for the classification; ``doctor``
imports it and fails (exit 9) on any *unclassified* importer, so a new
``governance_core``-importing hook cannot ship without an explicit decision.
See ``knowledge_governance/runtime-import-discipline.md``.
"""
from __future__ import annotations

import re
from pathlib import Path

# Hooks that import governance_core but guard the import and fail OPEN
# (sys.exit(0) on failure): a broken package degrades them, never freezes.
# Verified by reading each hook's import-failure path (P-0081).
FAIL_OPEN_GC_IMPORTERS: frozenset[str] = frozenset({
    "sensitive-data-guard.py",
    "candidate-reminder.py",
    "renewal-reminder.py",
    "update-reminder.py",
    "skill-usage-tracker.py",
})

# Fail-CLOSED governance_core importers grandfathered pending a
# self-containment refactor. Empty as of P-0082: auth-guard was vendored
# (it now imports the install-copied `_gc_auth` package, not governance_core),
# so the check enforces full discipline with NO exceptions. A future
# fail-closed importer would be added here only as an explicit, tracked,
# temporary grandfather.
GC_IMPORT_EXEMPT: frozenset[str] = frozenset()

# Matches a top-level or indented `import governance_core` /
# `from governance_core[...] import ...` statement.
_GC_IMPORT_RE = re.compile(r"^[ \t]*(?:from|import)[ \t]+governance_core\b", re.M)


def hook_imports_gc(text: str) -> bool:
    """Return True iff the hook source imports ``governance_core``."""
    return _GC_IMPORT_RE.search(text) is not None


def check_runtime_import_discipline(
    hooks_dir: Path, shipped_hook_names: set[str],
) -> dict[str, list[str]]:
    """Classify each shipped hook by its governance_core-import discipline.

    Only the governance-core-shipped hooks named in ``shipped_hook_names`` are
    inspected -- a consumer's own hooks are out of scope. Returns a dict with
    three sorted lists:

      ``fail_open``   -- importers verified to guard + fail open (allowed)
      ``exempt``      -- fail-closed importers grandfathered pending a fix
      ``violations``  -- importers that are neither: unclassified, must be made
                         self-contained or (after verifying fail-open) added to
                         ``FAIL_OPEN_GC_IMPORTERS`` before shipping

    Args:
        hooks_dir: directory holding the installed hook ``.py`` files.
        shipped_hook_names: hook filenames governance-core ships (manifest keys).

    Returns:
        ``{"fail_open": [...], "exempt": [...], "violations": [...]}``.
    """
    fail_open: list[str] = []
    exempt: list[str] = []
    violations: list[str] = []
    for name in sorted(shipped_hook_names):
        path = hooks_dir / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if not hook_imports_gc(text):
            continue
        if name in FAIL_OPEN_GC_IMPORTERS:
            fail_open.append(name)
        elif name in GC_IMPORT_EXEMPT:
            exempt.append(name)
        else:
            violations.append(name)
    return {"fail_open": fail_open, "exempt": exempt, "violations": violations}
