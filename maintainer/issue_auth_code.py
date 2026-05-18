"""Issue a governance-core authorization code (P-0065 Phase 1).

Maintainer-only. Reads the private signing key from
~/.governance-core/signing_key.json and prints a signed authorization code
for one consumer. Hand the printed code to the project owner out-of-band;
they pass it to `governance-core install --auth-code <CODE>`.

Usage:
    python maintainer/issue_auth_code.py --consumer-id <project-or-org>
    python maintainer/issue_auth_code.py --consumer-id acme --expiry 2027-01-01

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


def main() -> int:
    """Sign and emit an authorization code for the given consumer."""
    parser = argparse.ArgumentParser(prog="issue_auth_code")
    parser.add_argument("--consumer-id", required=True,
                        help="stable identity of the consuming project/org")
    parser.add_argument("--expiry", default=None,
                        help="optional expiry date YYYY-MM-DD (default: none)")
    args = parser.parse_args()

    if not PRIVATE_KEY_PATH.exists():
        logger.error("[FAIL] no signing key at %s", PRIVATE_KEY_PATH)
        logger.error("       run maintainer/gen_signing_key.py first")
        return 1

    key_data = json.loads(PRIVATE_KEY_PATH.read_text(encoding="utf-8"))
    seed = codec.b64url_decode(key_data["seed_b64"])

    issued = datetime.date.today().isoformat()
    payload = codec.canonical_payload(args.consumer_id, issued, args.expiry)
    code = codec.make_auth_code(payload, seed)

    # Record the issuance in the consumer registry (P-0065 Phase 5).
    registry.record_consumer(REGISTRY_PATH, args.consumer_id, issued,
                             expiry=args.expiry)

    logger.info("[OK] authorization code for consumer_id=%r issued=%s expiry=%s",
                args.consumer_id, issued, args.expiry or "(perpetual)")
    logger.info("[OK] consumer recorded in %s", REGISTRY_PATH.name)
    sys.stdout.write(code + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
