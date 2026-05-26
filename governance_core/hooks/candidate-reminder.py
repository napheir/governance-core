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
        from governance_core.candidates import ledger, rejected
        pending = ledger.pending_candidate_skills(root)
        # P-0076 Phase 2: cross-check pending against the rejected registry
        # so an owner notices "this skill is still tagged candidate-common
        # but hub already rejected it" at session start, not only after a
        # wrap-up sweep.
        reg = rejected.load_rejected_registry()
        already_rejected: list[Path] = []
        for skill_path in pending:
            digest = ledger.skill_digest(skill_path)
            for candidate_name in (skill_path.stem, skill_path.name):
                r = rejected.is_rejected(candidate_name, digest, reg)
                if r is not None and rejected.should_block(r):
                    already_rejected.append(skill_path)
                    break
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
    if already_rejected:
        names = ", ".join(p.stem for p in already_rejected[:8])
        sys.stdout.write(
            f"  WARNING: {len(already_rejected)} of these were previously "
            f"REJECTED by the hub ({names}). Remove `layer: candidate-common` "
            f"from their frontmatter or delete them to stop sweep retries -- "
            f"see the rejection's advice for context.\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
