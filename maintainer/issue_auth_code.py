"""Issue a governance-core authorization code (P-0065 Phase 1, P-0071).

Maintainer-only. Reads the private signing key from
~/.governance-core/signing_key.json and prints a signed authorization code
for one consumer, followed by a ready-to-paste install block (on stderr)
the maintainer hands the project owner out-of-band.

Codes are issued at schema 2 (P-0071): a leased, revocable code carrying an
`expiry` (default: issued + 365 days), the signed revocation-feed URL the
consumer's `auth-guard` polls, and `max_offline_days` (the offline grace
bound). `--schema 1` issues a legacy perpetual code instead.

Usage:
    python maintainer/issue_auth_code.py --consumer-id <project-or-org>
    python maintainer/issue_auth_code.py --consumer-id acme --expiry 2027-01-01
    python maintainer/issue_auth_code.py --consumer-id legacy --schema 1

This tool lives in the repo-level maintainer/ directory: committed for
auditability, but excluded from the pip package.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import sys
from pathlib import Path

from governance_core.auth import codec
from governance_core.candidates import registry

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("issue_auth_code")

PRIVATE_KEY_PATH = Path.home() / ".governance-core" / "signing_key.json"
# Consumer registry: committed, maintainer-side, alongside this tool.
REGISTRY_PATH = Path(__file__).resolve().parent / "consumer_registry.json"

# Schema-2 issuance policy (P-0071). The lease window and offline bound were
# fixed by the 2026-05-18 design discussion; the feed URL is this repo's
# committed revocation.json served raw by GitHub.
DEFAULT_LEASE_DAYS = 365
DEFAULT_MAX_OFFLINE_DAYS = 30
DEFAULT_REVOCATION_FEED_URL = (
    "https://raw.githubusercontent.com/napheir/governance-core/master/"
    "revocation.json"
)


def main() -> int:
    """Sign and emit an authorization code for the given consumer."""
    parser = argparse.ArgumentParser(prog="issue_auth_code")
    parser.add_argument("--consumer-id", required=True,
                        help="stable identity of the consuming project/org")
    parser.add_argument("--schema", type=int, default=codec.CURRENT_SCHEMA,
                        choices=codec.SUPPORTED_SCHEMAS,
                        help="payload schema (default: 2, leased + revocable)")
    parser.add_argument("--expiry", default=None,
                        help="expiry date YYYY-MM-DD (schema 2 default: "
                             f"issued + {DEFAULT_LEASE_DAYS} days; "
                             "schema 1 default: none/perpetual)")
    parser.add_argument("--revocation-feed-url",
                        default=DEFAULT_REVOCATION_FEED_URL,
                        help="signed revocation feed URL (schema 2 only)")
    parser.add_argument("--max-offline-days", type=int,
                        default=DEFAULT_MAX_OFFLINE_DAYS,
                        help="offline grace bound in days (schema 2 only)")
    args = parser.parse_args()

    if not PRIVATE_KEY_PATH.exists():
        logger.error("[FAIL] no signing key at %s", PRIVATE_KEY_PATH)
        logger.error("       run maintainer/gen_signing_key.py first")
        return 1

    key_data = json.loads(PRIVATE_KEY_PATH.read_text(encoding="utf-8"))
    seed = codec.b64url_decode(key_data["seed_b64"])

    issued = datetime.date.today().isoformat()

    # Resolve the expiry: schema 2 leases by default; schema 1 is perpetual
    # unless an explicit --expiry is given.
    expiry = args.expiry
    if args.schema == 2 and expiry is None:
        expiry = (datetime.date.today()
                  + datetime.timedelta(days=DEFAULT_LEASE_DAYS)).isoformat()

    if args.schema == 2:
        payload = codec.canonical_payload(
            args.consumer_id, issued, expiry, schema=2,
            revocation_feed_url=args.revocation_feed_url,
            max_offline_days=args.max_offline_days)
    else:
        payload = codec.canonical_payload(args.consumer_id, issued, expiry,
                                          schema=1)
    code = codec.make_auth_code(payload, seed)

    # Record the issuance in the consumer registry (P-0065 Phase 5).
    registry.record_consumer(REGISTRY_PATH, args.consumer_id, issued,
                             expiry=expiry)

    logger.info("[OK] authorization code for consumer_id=%r schema=%d "
                "issued=%s expiry=%s", args.consumer_id, args.schema, issued,
                expiry or "(perpetual)")
    if args.schema == 2:
        logger.info("[OK] revocation_feed_url=%s max_offline_days=%d",
                    args.revocation_feed_url, args.max_offline_days)
    logger.info("[OK] consumer recorded in %s", REGISTRY_PATH.name)
    sys.stdout.write(code + "\n")

    # Ready-to-paste install block for the maintainer to hand the consumer
    # out-of-band. The code is set as a shell variable first: it has no
    # internal spaces, so it survives copy-paste line wrapping intact, and
    # the install command then stays short. stdout above is kept as the bare
    # code so the tool stays scriptable; this block goes to stderr.
    install_block = "\n".join([
        "",
        "--- install block: hand to the consumer owner out-of-band; they run",
        "    it in their project directory (ideally in a fresh venv) ---",
        "pip install governance-core",
        f"CODE='{code}'",
        'governance-core install --auth-code "$CODE" '
        "--accept-candidate-uplink --project-root .",
        "governance-core doctor",
        "",
    ])
    sys.stderr.write(install_block)
    return 0


if __name__ == "__main__":
    sys.exit(main())
