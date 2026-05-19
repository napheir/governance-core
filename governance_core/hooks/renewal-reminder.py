"""Claude Code SessionStart hook: renewal-reminder.py

Surfaces governance-core consumer leases nearing expiry at session start
(P-0074 Phase 2). Unlike candidate-reminder / update-reminder -- which run
consumer-side and stay silent for the hub -- this hook is **hub-side**: it
reads `maintainer/consumer_registry.json` (a file only the governance-core
maintainer repo carries) and reports how many issued authorization leases
fall within the renewal window, so the maintainer re-issues a code before
a consumer's auth-guard freezes that consumer.

A consumer project that merely installed the package has no `maintainer/`
directory -> this hook stays silent. Non-blocking: any error -> silent
exit 0, never breaks a session start.
"""
import datetime
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")


def main() -> None:
    """Report consumer leases within the renewal window at session start."""
    try:
        json.loads(sys.stdin.read())
    except Exception:  # noqa: BLE001
        pass

    # repo root: hook lives at <repo>/.claude/hooks/renewal-reminder.py
    root = Path(__file__).resolve().parent.parent.parent
    registry_path = root / "maintainer" / "consumer_registry.json"

    # Hub gate: only the governance-core maintainer repo has maintainer/.
    # A consumer project that installed the package has no such file --
    # there are no leases for it to track, so this reminder is silent.
    if not registry_path.exists():
        sys.exit(0)

    try:
        from governance_core.candidates import registry
        reg = registry.load_registry(registry_path)
        expiring = registry.expiring_consumers(
            reg, datetime.date.today(), registry.RENEWAL_THRESHOLD_DAYS)
        window = registry.RENEWAL_THRESHOLD_DAYS
    except Exception:  # noqa: BLE001 - never break session start
        sys.exit(0)

    if not expiring:
        sys.exit(0)

    lapsed = sum(1 for r in expiring if r["days_left"] < 0)
    shown = ", ".join(
        f"{r['consumer_id']}"
        f"({'lapsed' if r['days_left'] < 0 else str(r['days_left']) + 'd'})"
        for r in expiring[:8])
    extra = f" (+{len(expiring) - 8} more)" if len(expiring) > 8 else ""
    note = f", {lapsed} already lapsed" if lapsed else ""
    sys.stdout.write(
        f"[Lease renewal] {len(expiring)} consumer lease(s) within the "
        f"{window}-day renewal window{note}: {shown}{extra}\n"
        "  Detail: python maintainer/renewal_status.py -- re-issue with "
        "maintainer/issue_auth_code.py --consumer-id <id>.\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
