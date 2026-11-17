"""Claude Code PreToolUse hook: own-write-capture.py

Remembers the sha of each shared_state partition file a tool call may write,
just before it runs, so the PostToolUse hook own-write-journal.py can journal
the write with its real `sha_before` (P-0136, P-0138;
contracts/shared_state_ownership.md §4 "Edit/Write and shell journal").

- Edit/Write/MultiEdit/NotebookEdit: the one target file.
- Bash: the write targets that scope-guard's parser finds
  (_guard_common.shell_write_targets). Fast path: when no target lies under
  shared_state, exit before importing the package.
- Writes `<clone>/.governance/pending_writes/<key>.json`; prunes captures
  older than 24 hours. Only partition files, only in a multi-agent project.
- Never blocks and prints nothing: the allow/deny decision is the guards'.
  Fails open: any error exits 0 (registered in
  runtime_import_audit.FAIL_OPEN_GC_IMPORTERS).
"""
import json
import sys
from pathlib import Path


def _names_shared_state(hooks_dir: Path, root: Path, payload: dict) -> bool:
    """True when a Bash call's parsed write targets include a shared_state path."""
    tool_input = payload["tool_input"] if "tool_input" in payload else None
    if not isinstance(tool_input, dict) or "command" not in tool_input:
        return False
    command = tool_input["command"]
    if not isinstance(command, str) or not command.strip():
        return False
    cwd = payload["cwd"] if "cwd" in payload else None
    if not isinstance(cwd, str) or not cwd:
        cwd = str(root)
    sys.path.insert(0, str(hooks_dir))
    import _guard_common
    return any(_guard_common.shared_state_access(t, "", str(root))[0] != "outside"
               for t in _guard_common.shell_write_targets(command, cwd))


def main() -> None:
    """Capture the targets' shas; never affect the tool call."""
    try:
        raw = sys.stdin.buffer.read().decode("utf-8")
        payload = json.loads(raw) if raw.strip() else {}
        hooks_dir = Path(__file__).resolve().parent
        root = hooks_dir.parent.parent
        if isinstance(payload, dict) and "tool_name" in payload \
                and payload["tool_name"] == "Bash" \
                and not _names_shared_state(hooks_dir, root, payload):
            sys.exit(0)
        from governance_core import ownership
        ownership.capture_before(root, payload)
    except Exception:  # noqa: BLE001 - never block a tool call
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
