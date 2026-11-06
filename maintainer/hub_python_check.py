"""SessionStart check: is this hub session running on the repo source?

The hub develops governance_core in place. Its tools, tests and hooks run
`python`, so they test this repo only when that interpreter imports
governance_core from <repo>/governance_core -- the editable install in the
hub's .venv. The machine-wide Python carries the released package for the
local consumers; a hub session started without the venv on PATH would
silently run that released copy instead of the code being edited (P-0133).

Registered for the hub only, in .claude/settings.json; not shipped (lives in
maintainer/). Stdlib only, never raises, always exits 0: it warns, it does
not block.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EXPECTED = REPO / "governance_core"


def imported_from() -> Path | None:
    """Return the directory `python` would import governance_core from."""
    try:
        spec = importlib.util.find_spec("governance_core")
    except (ImportError, ValueError):
        return None
    if spec is None or spec.origin is None:
        return None
    return Path(spec.origin).resolve().parent


def warning(found: Path | None) -> str | None:
    """Return the warning text, or None when the repo source is in use."""
    if found is not None and found == EXPECTED.resolve():
        return None
    where = str(found) if found is not None else "nowhere (not installed)"
    return ("[WARN] hub session is not on the repo source: python is "
            f"{sys.executable} and imports governance_core from {where}. "
            "Tools, tests and hooks here would run that copy, not the code "
            "being edited. Restart the session with the hub venv first on "
            "PATH (the gchub alias; see docs/core-manual.md, hub dev "
            "environment).")


def main() -> int:
    """Emit the warning as SessionStart hook JSON when it applies."""
    try:
        text = warning(imported_from())
    except Exception as exc:  # noqa: BLE001 -- a check must never break startup
        text = f"[WARN] hub_python_check failed: {type(exc).__name__}: {exc}"
    if text is not None:
        sys.stdout.write(json.dumps({
            "systemMessage": text,
            "hookSpecificOutput": {"hookEventName": "SessionStart",
                                   "additionalContext": text},
        }) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
