"""Claude Code PostToolUseFailure hook: own-write-journal-failure.py

The failure-event twin of own-write-journal.py (P-0138). A Bash command that
fails may still have written some of its targets; this journals them the same
way, from the capture own-write-capture.py stored before the call. For a
failed Edit/Write it only removes the capture (the sha did not change).

- Calls ownership.journal_edit(), the function own-write-journal.py calls.
- An older Claude Code without this event skips the entry with a settings
  warning; the change then surfaces as actor unknown, as before.
- Prints nothing. Fails open: any error exits 0 (registered in
  runtime_import_audit.FAIL_OPEN_GC_IMPORTERS).
"""
import json
import sys
from pathlib import Path


def main() -> None:
    """Journal the captured write of a failed tool call; never affect the session."""
    try:
        raw = sys.stdin.buffer.read().decode("utf-8")
        root = Path(__file__).resolve().parent.parent.parent
        # Fast path, as in own-write-journal.py: no capture waiting means
        # nothing to journal, so skip importing the package.
        pending = root / ".governance" / "pending_writes"
        if not pending.is_dir() or not any(pending.glob("*.json")):
            sys.exit(0)
        payload = json.loads(raw) if raw.strip() else {}
        from governance_core import ownership
        ownership.journal_edit(root, payload)
    except Exception:  # noqa: BLE001 - never break the session
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
