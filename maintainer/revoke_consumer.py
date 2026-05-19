"""Revoke (or list) governance-core consumers (P-0071 Phase 2).

Maintainer-only. Adds a `consumer_id` to the signed revocation feed
(`revocation.json` + `revocation.json.sig` at the repo root), re-signs it
with the private key, and marks the consumer revoked in
`consumer_registry.json`.

A `consumer_id` in the published feed is frozen at runtime by every
consumer's `auth-guard` (P-0071 Phase 3) -- this is how the maintainer
actively ejects a project that has left the organization, without the
consumer having to cooperate or upgrade.

Usage:
    python maintainer/revoke_consumer.py --init
    python maintainer/revoke_consumer.py --consumer-id acme --reason "left org"
    python maintainer/revoke_consumer.py --unrevoke acme   # correct a mistake
    python maintainer/revoke_consumer.py --list

Like the other maintainer tools this lives in maintainer/: committed for
auditability, excluded from the pip package.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import sys
from pathlib import Path

from governance_core.auth import codec, revocation
from governance_core.candidates import registry

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("revoke_consumer")

REPO_ROOT = Path(__file__).resolve().parent.parent
FEED_PATH = REPO_ROOT / "revocation.json"
SIG_PATH = REPO_ROOT / "revocation.json.sig"
REGISTRY_PATH = Path(__file__).resolve().parent / "consumer_registry.json"
PRIVATE_KEY_PATH = Path.home() / ".governance-core" / "signing_key.json"


def _load_seed() -> bytes | None:
    """Return the private signing seed, or None if the key is missing."""
    if not PRIVATE_KEY_PATH.exists():
        logger.error("[FAIL] no signing key at %s", PRIVATE_KEY_PATH)
        logger.error("       run maintainer/gen_signing_key.py first")
        return None
    key_data = json.loads(PRIVATE_KEY_PATH.read_text(encoding="utf-8"))
    return codec.b64url_decode(key_data["seed_b64"])


def _load_existing_feed() -> dict | None:
    """Load + verify the on-disk feed; return None if it is absent.

    Refuses a feed whose signature does not verify -- re-signing a tampered
    feed would launder the tampering.
    """
    if not FEED_PATH.exists():
        return None
    return revocation.load_feed(FEED_PATH, SIG_PATH,
                                codec.load_bundled_public_key())


def _cmd_init(force: bool) -> int:
    """Write a fresh, empty signed revocation feed."""
    if FEED_PATH.exists() and not force:
        logger.error("[FAIL] %s already exists -- use --force to overwrite",
                     FEED_PATH.name)
        return 1
    seed = _load_seed()
    if seed is None:
        return 1
    revocation.write_feed(FEED_PATH, SIG_PATH, revocation.new_feed(), seed)
    logger.info("[OK] wrote empty signed feed: %s + %s",
                FEED_PATH.name, SIG_PATH.name)
    return 0


def _cmd_list() -> int:
    """Verify and print the current revocation feed."""
    try:
        feed = revocation.load_feed(FEED_PATH, SIG_PATH,
                                    codec.load_bundled_public_key())
    except revocation.RevocationFeedError as exc:
        logger.error("[FAIL] %s", exc)
        return 1
    revoked = feed["revoked"]
    logger.info("[OK] revocation feed verified (updated %s, %d revoked)",
                feed["updated"], len(revoked))
    for entry in revoked:
        sys.stdout.write(
            f"  {entry['consumer_id']}  revoked_on={entry['revoked_on']}  "
            f"reason={entry.get('reason') or '(none)'}\n")
    return 0


def _cmd_revoke(consumer_id: str, reason: str) -> int:
    """Add `consumer_id` to the feed, re-sign, and mark the registry."""
    seed = _load_seed()
    if seed is None:
        return 1
    try:
        feed = _load_existing_feed() or revocation.new_feed()
    except revocation.RevocationFeedError as exc:
        logger.error("[FAIL] existing feed rejected: %s", exc)
        logger.error("       refusing to re-sign a feed that does not verify")
        return 1

    if revocation.is_revoked(feed, consumer_id):
        logger.info("[WARN] %r is already revoked -- refreshing its entry",
                    consumer_id)

    revoked_on = datetime.date.today().isoformat()
    feed = revocation.add_revocation(feed, consumer_id, reason, revoked_on)
    revocation.write_feed(FEED_PATH, SIG_PATH, feed, seed)
    logger.info("[OK] %r added to revocation feed (revoked_on=%s)",
                consumer_id, revoked_on)

    if registry.mark_revoked(REGISTRY_PATH, consumer_id, revoked_on, reason):
        logger.info("[OK] consumer marked revoked in %s", REGISTRY_PATH.name)
    else:
        logger.info("[WARN] %r not found in %s -- feed updated, registry "
                    "unchanged", consumer_id, REGISTRY_PATH.name)

    logger.info("[OK] commit %s + %s and push so consumers' auth-guard "
                "picks up the revocation", FEED_PATH.name, SIG_PATH.name)
    return 0


def _cmd_unrevoke(consumer_id: str) -> int:
    """Remove `consumer_id` from the feed, re-sign, mark the registry active.

    Corrects a mistaken revocation (P-0074 Phase 1). Per-consumer -- other
    revoked entries in the feed are untouched.
    """
    seed = _load_seed()
    if seed is None:
        return 1
    try:
        feed = _load_existing_feed()
    except revocation.RevocationFeedError as exc:
        logger.error("[FAIL] existing feed rejected: %s", exc)
        logger.error("       refusing to re-sign a feed that does not verify")
        return 1
    if feed is None:
        logger.info("[WARN] no revocation feed exists -- nothing to un-revoke")
        return 0
    if not revocation.is_revoked(feed, consumer_id):
        logger.info("[WARN] %r is not on the revocation feed -- no-op",
                    consumer_id)
        return 0

    feed = revocation.remove_revocation(feed, consumer_id)
    revocation.write_feed(FEED_PATH, SIG_PATH, feed, seed)
    logger.info("[OK] %r removed from the revocation feed", consumer_id)

    if registry.mark_active(REGISTRY_PATH, consumer_id):
        logger.info("[OK] consumer marked active in %s", REGISTRY_PATH.name)
    else:
        logger.info("[WARN] %r not found in %s -- feed updated, registry "
                    "unchanged", consumer_id, REGISTRY_PATH.name)

    logger.info("[OK] commit %s + %s and push so consumers' auth-guard "
                "picks up the un-revocation", FEED_PATH.name, SIG_PATH.name)
    return 0


def main() -> int:
    """Dispatch one of: --init, --list, --unrevoke, or revoke a consumer."""
    parser = argparse.ArgumentParser(prog="revoke_consumer")
    parser.add_argument("--consumer-id", default=None,
                        help="consumer to revoke")
    parser.add_argument("--reason", default="",
                        help="why the consumer is being revoked")
    parser.add_argument("--init", action="store_true",
                        help="write a fresh empty signed revocation feed")
    parser.add_argument("--force", action="store_true",
                        help="with --init, overwrite an existing feed")
    parser.add_argument("--list", action="store_true",
                        help="verify and print the current feed")
    parser.add_argument("--unrevoke", default=None,
                        help="consumer to un-revoke -- remove from the feed; "
                             "corrects a mistaken revocation")
    args = parser.parse_args()

    actions = sum([args.init, args.list, args.consumer_id is not None,
                   args.unrevoke is not None])
    if actions != 1:
        parser.error("choose exactly one of --init / --list / "
                     "--consumer-id / --unrevoke")

    if args.init:
        return _cmd_init(args.force)
    if args.list:
        return _cmd_list()
    if args.unrevoke is not None:
        return _cmd_unrevoke(args.unrevoke)
    if not args.reason:
        parser.error("--reason is required when revoking a consumer")
    return _cmd_revoke(args.consumer_id, args.reason)


if __name__ == "__main__":
    sys.exit(main())
