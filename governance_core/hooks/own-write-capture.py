"""Claude Code PreToolUse hook: own-write-capture.py

Remembers a shared_state partition file's sha just before an Edit/Write, so
the PostToolUse hook own-write-journal.py can journal the write with its
real `sha_before` (P-0136, contracts/shared_state_ownership.md §4
"Edit/Write journal").

- Writes `<clone>/.governance/pending_writes/<key>.json`; prunes captures
  older than 24 hours.
- Only files in some agent's partition, only in a multi-agent project.
- Never blocks and prints nothing: the allow/deny decision is
  edit-write-guard's. Fails open: any error exits 0 (registered in
  runtime_import_audit.FAIL_OPEN_GC_IMPORTERS).
"""
import json
import sys
from pathlib import Path


def main() -> None:
    """Capture the target's sha; never affect the tool call."""
    try:
        raw = sys.stdin.buffer.read().decode("utf-8")
        payload = json.loads(raw) if raw.strip() else {}
        root = Path(__file__).resolve().parent.parent.parent
        from governance_core import ownership
        ownership.capture_before(root, payload)
    except Exception:  # noqa: BLE001 - never block a tool call
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
