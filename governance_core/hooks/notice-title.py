"""Claude Code UserPromptSubmit hook: notice-title.py

Keeps the session title in step with this agent's un-acked ownership alerts
(P-0136, contracts/shared_state_ownership.md §5 "How the owner sees it").

- While there are N un-acked alerts the title reads `[ALERT N] <agent>`;
  once they are acked it goes back to `<agent>`
  (hookSpecificOutput.sessionTitle, shown as a chip on the prompt border).
- The title is set only when the count differs from what this session's
  title last showed, so a session that never had alerts keeps its own
  title. foreign-change-notice.py sets it at SessionStart.
- Never blocks a prompt and never adds context: a prompt, including a
  peer's cross-session message, always goes through unchanged.

Single-agent projects: silent (checked from config before importing the
package). Fails open: any error exits 0 without output (registered in
runtime_import_audit.FAIL_OPEN_GC_IMPORTERS).
"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")


def _multi_agent(root: Path) -> bool:
    """True when config lists two or more agents (cheap pre-check)."""
    cfg_path = root / ".governance" / "config.json"
    if not cfg_path.is_file():
        return False
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    return isinstance(cfg, dict) and "agents" in cfg and len(cfg["agents"]) >= 2


def main() -> None:
    """Emit a sessionTitle when the alert count changed; nothing else."""
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
        root = Path(__file__).resolve().parent.parent.parent
        if not _multi_agent(root):
            sys.exit(0)
        session_id = payload["session_id"] if isinstance(payload, dict) \
            and isinstance(payload.get("session_id"), str) else ""
        from governance_core import ownership
        title = ownership.title_update(root, session_id)
        if title is not None:
            sys.stdout.write(json.dumps({"hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit", "sessionTitle": title}},
                ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 - never touch the prompt
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
