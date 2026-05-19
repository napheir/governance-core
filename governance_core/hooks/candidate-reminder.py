"""Claude Code SessionStart hook: candidate-reminder.py

Surfaces candidate-common learned skills not yet uplinked to
governance-core (P-0072 Phase 2). Even if `/wrap-up` is skipped entirely,
the count stays visible at every session start -- so an un-uplinked
candidate is a loud, recurring state, not a silent default.

The hub project (governance-core itself) has no uplink concept and stays
silent. Non-blocking: any error -> silent exit 0, never breaks a session.
"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")


def main() -> None:
    """Report not-yet-uplinked candidate-common skills at session start."""
    try:
        json.loads(sys.stdin.read())
    except Exception:  # noqa: BLE001
        pass

    # repo root: hook lives at <repo>/.claude/hooks/candidate-reminder.py
    root = Path(__file__).resolve().parent.parent.parent
    cfg_path = root / ".governance" / "config.json"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - no/unreadable config -> nothing to say
        sys.exit(0)

    # Hub gate: governance-core itself curates via review/promote and never
    # uplinks to itself -- the reminder is meaningless for the hub.
    auth = cfg["authorization"] if "authorization" in cfg else {}
    if isinstance(auth, dict) and "consumer_id" in auth \
            and auth["consumer_id"] == "governance-core":
        sys.exit(0)

    try:
        from governance_core.candidates import ledger
        pending = ledger.pending_candidate_skills(root)
    except Exception:  # noqa: BLE001 - never break session start
        sys.exit(0)

    if not pending:
        sys.exit(0)

    shown = ", ".join(p.stem for p in pending[:8])
    extra = f" (+{len(pending) - 8} more)" if len(pending) > 8 else ""
    sys.stdout.write(
        f"[Candidate uplink] {len(pending)} candidate-common skill(s) not "
        f"yet uplinked to governance-core: {shown}{extra}\n"
        "  The next /wrap-up (step 4d) will uplink them; or run "
        "/submit-candidate now.\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
