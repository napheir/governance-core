"""Claude Code UserPromptSubmit hook: notice-gate.py

Makes sure the owner sees un-acked ownership alerts (P-0136,
contracts/shared_state_ownership.md §5 "How the owner sees it").

How SessionStart output is displayed is not specified by Claude Code, and
one owner missed it. Blocking a prompt is the documented way to put text in
front of the user. So while this agent has un-acked alerts, the first prompt
of each session is blocked once (`decision: "block"`); the `reason` lists
the alerts and asks the owner to resend. The session id is remembered in
`<clone>/.governance/notice_gate_seen.json`, so a session is held at most
once; a resumed or compacted session keeps its id. An unattended run
(`claude -p`) stops here by design.

Single-agent projects: silent (checked from config before importing the
package). Fails open: any error lets the prompt through (registered in
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
    """Block the session's first prompt once while alerts are un-acked."""
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
        root = Path(__file__).resolve().parent.parent.parent
        if not _multi_agent(root):
            sys.exit(0)
        session_id = payload["session_id"] if isinstance(payload, dict) \
            and isinstance(payload.get("session_id"), str) else ""
        from governance_core import ownership
        reason = ownership.alert_gate(root, session_id)
        if reason:
            sys.stdout.write(json.dumps({"decision": "block", "reason": reason},
                                        ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 - never trap the owner's prompt
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
