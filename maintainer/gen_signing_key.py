"""Generate the governance-core authorization signing keypair (P-0065 Phase 1).

Run ONCE by the maintainer. Writes:

  - the private signing key to ~/.governance-core/signing_key.json
    (outside the repo tree -- never committed, never packaged; back it up
    offline, it cannot be recovered and signs every authorization code).
  - the public key to governance_core/auth/pubkey.json (committed, shipped
    inside the pip package so consumers can verify codes offline).

Refuses to overwrite an existing private key unless --force, so a key
already in use is not silently destroyed.

This tool lives in the repo-level maintainer/ directory: committed for
auditability, but excluded from the pip package (packages.find matches only
governance_core*).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from governance_core import auth
from governance_core.auth import codec

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("gen_signing_key")

KEY_ID = "gc-2026"
PRIVATE_KEY_PATH = Path.home() / ".governance-core" / "signing_key.json"
PUBLIC_KEY_PATH = Path(auth.__file__).resolve().parent / "pubkey.json"


def main() -> int:
    """Generate the Ed25519 keypair and write the private + public key files."""
    parser = argparse.ArgumentParser(prog="gen_signing_key")
    parser.add_argument("--force", action="store_true",
                        help="overwrite an existing private key")
    args = parser.parse_args()

    if PRIVATE_KEY_PATH.exists() and not args.force:
        logger.error("[FAIL] private key already exists: %s", PRIVATE_KEY_PATH)
        logger.error("       refusing to overwrite; pass --force to replace it")
        return 1

    seed = auth.generate_seed()
    public_key = auth.public_key_from_seed(seed)

    PRIVATE_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_KEY_PATH.write_text(
        json.dumps({"alg": "ed25519", "key_id": KEY_ID,
                    "seed_b64": codec.b64url_encode(seed)}, indent=2) + "\n",
        encoding="utf-8",
    )
    PUBLIC_KEY_PATH.write_text(
        json.dumps({"alg": "ed25519", "key_id": KEY_ID,
                    "key_b64": codec.b64url_encode(public_key)}, indent=2) + "\n",
        encoding="utf-8",
    )
    logger.info("[OK] private key -> %s", PRIVATE_KEY_PATH)
    logger.info("[OK] public  key -> %s", PUBLIC_KEY_PATH)
    logger.info("[WARN] back up the private key offline; it cannot be "
                "recovered and signs every authorization code")
    return 0


if __name__ == "__main__":
    sys.exit(main())
