"""Report governance-core consumer lease-renewal status (P-0074 Phase 2).

Maintainer-only. Scans consumer_registry.json and lists every active
consumer ordered by how soon its authorization lease expires, flagging
those within the renewal threshold (default 30 days) -- so the maintainer
can re-issue a code before a consumer's auth-guard freezes it.

This is visibility only: it never re-signs or re-issues anything. Renewal
stays a deliberate maintainer act -- run issue_auth_code.py for the
consumer. The signed auto-renewal feed is explicitly out of scope for
P-0074 (see the proposal); P-0074 only makes "who is due" visible.

Usage:
    python maintainer/renewal_status.py
    python maintainer/renewal_status.py --threshold-days 45

Like the other maintainer tools this lives in maintainer/: committed for
auditability, excluded from the pip package.
"""

from __future__ import annotations

import argparse
import datetime
import logging
import sys
from pathlib import Path

from governance_core.candidates import registry

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("renewal_status")

REGISTRY_PATH = Path(__file__).resolve().parent / "consumer_registry.json"


def main() -> int:
    """Print every active consumer's lease status, flagging expiring ones."""
    parser = argparse.ArgumentParser(prog="renewal_status")
    parser.add_argument(
        "--threshold-days", type=int,
        default=registry.RENEWAL_THRESHOLD_DAYS,
        help="flag consumers expiring within this many days "
             f"(default {registry.RENEWAL_THRESHOLD_DAYS})")
    args = parser.parse_args()

    reg = registry.load_registry(REGISTRY_PATH)
    today = datetime.date.today()
    rows = registry.lease_status(reg, today)
    if not rows:
        logger.info("[OK] no active consumers in %s", REGISTRY_PATH.name)
        return 0

    expiring = [r for r in rows if r["days_left"] is not None
                and r["days_left"] <= args.threshold_days]
    logger.info("[OK] %d active consumer(s); %d within the %d-day renewal "
                "window (today %s)", len(rows), len(expiring),
                args.threshold_days, today.isoformat())
    for r in rows:
        if r["days_left"] is None:
            mark, detail = "[ -- ]", "no expiry recorded (perpetual code)"
        elif r["days_left"] < 0:
            mark = "[LAPSED]"
            detail = f"expired {-r['days_left']}d ago (expiry {r['expiry']})"
        elif r["days_left"] <= args.threshold_days:
            mark = "[RENEW]"
            detail = f"{r['days_left']}d left (expiry {r['expiry']})"
        else:
            mark = "[OK]"
            detail = f"{r['days_left']}d left (expiry {r['expiry']})"
        sys.stdout.write(f"  {mark:9s} {r['consumer_id']}  {detail}\n")

    if expiring:
        logger.info("[WARN] re-issue a code for each flagged consumer: "
                    "python maintainer/issue_auth_code.py "
                    "--consumer-id <id>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
