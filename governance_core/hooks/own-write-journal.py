"""Claude Code PostToolUse hook: own-write-journal.py

Journals an Edit/Write of a shared_state partition file, attributed to this
clone's agent (P-0136, contracts/shared_state_ownership.md §4 "Edit/Write
journal").

- Reads the capture own-write-capture.py stored before the tool ran, then
  calls ownership.record_write(op="edit:<Tool>", via="edit").
- An agent's own edit then moves its last-seen manifest silently, unless the
  file had changed beforehand in a way no journal run explains: that still
  becomes an alert. An edit of another agent's partition notifies its owner.
- No capture (the Pre hook failed) means nothing is journaled; the change
  then surfaces as actor unknown.
- Prints nothing. Fails open: any error exits 0 (registered in
  runtime_import_audit.FAIL_OPEN_GC_IMPORTERS).
"""
import json
import sys
from pathlib import Path


def main() -> None:
    """Journal the captured edit; never affect the session."""
    try:
        raw = sys.stdin.buffer.read().decode("utf-8")
        root = Path(__file__).resolve().parent.parent.parent
        # Fast path: no capture waiting (ownership.PENDING_REL) means there is
        # nothing to journal, so skip importing the package after every edit.
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
