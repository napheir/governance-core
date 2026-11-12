"""Claude Code SessionStart hook: foreign-change-notice.py

Tells an agent, and its owner, about changes others made to the agent's
shared_state content since its last session (P-0135,
contracts/shared_state_ownership.md §5).

- Every change to the agent's partitions that it did not make itself becomes
  a notice before the last-seen manifest moves, so nothing drops out of sight.
- Output is SessionStart hook JSON: `systemMessage` reaches the owner's UI
  without depending on the agent, and `additionalContext` tells the agent to
  report first.
- Every clone also shows the project-wide count of un-acked notices, so the
  owner sees it in whichever session they open.
- Alerts repeat until acked (python tools/notices.py ack <id>, only on the
  owner's word); notice-gate.py also holds the first prompt of a session
  once while any are un-acked. Info notices -- attributed lib writes by the
  core agent -- are acked automatically once two distinct sessions
  (`session_id` from the hook input) have shown them (P-0136); a resume
  keeps the id and does not count twice.

Single-agent projects: silent. Fails open: any error exits 0 without output
(registered in runtime_import_audit.FAIL_OPEN_GC_IMPORTERS).
"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")


def _render(result: dict) -> tuple:
    """(owner text, agent text) for a scan result; ("", "") if nothing to say."""
    me = result["agent"]
    lines = []
    for n in result["notices"]:
        paths = ", ".join(n["paths"][:3]) + (" ..." if len(n["paths"]) > 3 else "")
        tag = "ALERT" if n["severity"] == "alert" else "info"
        lines.append(f"  [{tag}] {n['id']}: {n['kind']} from {n['from']} -- {paths}"
                     + (f" ({n['detail']})" if n["detail"] else ""))
    if not result["chain_ok"]:
        lines.append(f"  [ALERT] the shared_state journal chain is broken "
                     f"({result['chain_detail']}): someone edited or truncated it")
    others = {a: c for a, c in result["counts"].items() if a != me}
    if not lines and not others:
        return "", ""
    head = []
    if lines:
        head.append(f"[Changed by others] {me}: {len(result['notices'])} "
                    f"notice(s) about your shared_state content:")
    owner = "\n".join(head + lines)
    if others:
        owner += ("\n" if owner else "") + "[Notices pending] " + ", ".join(
            f"{a}: {c}" for a, c in sorted(others.items())) + " (un-acked, project-wide)"
    agent = owner
    if lines:
        agent += ("\nReport these to the owner at the start of your first reply. "
                  "Ack an ALERT only when the owner says so in that turn: "
                  "python tools/notices.py ack <id>.")
    return owner, agent


def main() -> None:
    """Scan, persist, report; never break session start."""
    session_id = ""
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
        if isinstance(payload, dict) and isinstance(payload.get("session_id"), str):
            session_id = payload["session_id"]
    except Exception:  # noqa: BLE001 - no id: show, mark nothing
        pass
    root = Path(__file__).resolve().parent.parent.parent
    try:
        from governance_core import ownership
        result = ownership.scan(root)
        owner_text, agent_text = _render(result)
        if owner_text:
            sys.stdout.write(json.dumps({
                "systemMessage": owner_text,
                "hookSpecificOutput": {"hookEventName": "SessionStart",
                                       "additionalContext": agent_text},
            }, ensure_ascii=False) + "\n")
        shared = ownership.shared_root(root)
        if owner_text and session_id:
            for n in result["notices"]:
                if n["severity"] == "info":
                    ownership.mark_shown(shared, result["agent"], n["id"], session_id)
    except Exception:  # noqa: BLE001 - never break session start
        sys.exit(0)
    sys.exit(0)


if __name__ == "__main__":
    main()
