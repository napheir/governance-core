"""Revocation feed: format, signing, verification (P-0071 Phase 2).

A revocation feed is a signed JSON document the maintainer publishes and
every consumer's `auth-guard` polls (P-0071 Phase 3). A `consumer_id`
present in the feed is frozen at runtime -- this is how the maintainer
actively ejects a project that has left the organization, without needing
the consumer to cooperate or upgrade.

The feed and its detached signature are two files:

    revocation.json       the feed document
    revocation.json.sig   b64url Ed25519 signature over the feed bytes

The signature is computed over the *exact* serialized bytes of
revocation.json, so a verifier checks the bytes it received (or fetched)
without re-canonicalizing. The feed is signed by the same maintainer key
that signs authorization codes; consumers verify it with the bundled
public key (`governance_core/auth/pubkey.json`).

Feed shape:

    {"schema": 1, "updated": "<ISO-8601 Z>",
     "revoked": [{"consumer_id": str, "revoked_on": "YYYY-MM-DD",
                  "reason": str}, ...]}
"""

from __future__ import annotations

import datetime
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from . import codec, sign, verify

FEED_SCHEMA = 1


class RevocationFeedError(Exception):
    """Raised when a revocation feed is malformed or its signature is bad."""


def _now() -> str:
    """Return the current UTC time as an ISO-8601 'Z' string."""
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _revoked_list(feed: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the feed's revoked entries, tolerating an absent key."""
    revoked = feed.get("revoked")
    return revoked if isinstance(revoked, list) else []


def new_feed() -> dict[str, Any]:
    """Return a fresh, empty revocation feed."""
    return {"schema": FEED_SCHEMA, "updated": _now(), "revoked": []}


def serialize_feed(feed: dict[str, Any]) -> bytes:
    """Return the canonical bytes of `feed` -- the exact signed payload."""
    return (json.dumps(feed, sort_keys=True, indent=2, ensure_ascii=False)
            + "\n").encode("utf-8")


def validate_feed(feed: Any) -> None:
    """Raise RevocationFeedError if `feed` is not a well-formed feed."""
    if not isinstance(feed, dict):
        raise RevocationFeedError("revocation feed is not a JSON object")
    if feed.get("schema") != FEED_SCHEMA:
        raise RevocationFeedError(
            f"unsupported revocation feed schema: {feed.get('schema')!r}")
    if not feed.get("updated"):
        raise RevocationFeedError("revocation feed missing 'updated'")
    revoked = feed.get("revoked")
    if not isinstance(revoked, list):
        raise RevocationFeedError("revocation feed 'revoked' must be a list")
    for entry in revoked:
        if not isinstance(entry, dict) or not entry.get("consumer_id"):
            raise RevocationFeedError(
                "every revoked entry needs a non-empty consumer_id")


def is_revoked(feed: dict[str, Any], consumer_id: str) -> bool:
    """Return True iff `consumer_id` appears in the feed's revoked list."""
    return any(e.get("consumer_id") == consumer_id
               for e in _revoked_list(feed))


def add_revocation(feed: dict[str, Any], consumer_id: str, reason: str,
                   revoked_on: str | None = None) -> dict[str, Any]:
    """Return a new feed with `consumer_id` revoked (idempotent).

    Re-revoking an already-listed consumer refreshes its entry rather than
    duplicating it. `updated` is bumped to now; entries stay sorted by id.
    """
    if not consumer_id:
        raise RevocationFeedError("consumer_id must be non-empty")
    revoked_on = revoked_on or datetime.date.today().isoformat()
    kept = [e for e in _revoked_list(feed)
            if e.get("consumer_id") != consumer_id]
    kept.append({"consumer_id": consumer_id, "revoked_on": revoked_on,
                 "reason": reason})
    kept.sort(key=lambda e: e["consumer_id"])
    return {"schema": FEED_SCHEMA, "updated": _now(), "revoked": kept}


def remove_revocation(feed: dict[str, Any],
                      consumer_id: str) -> dict[str, Any]:
    """Return a new feed with `consumer_id` removed from the revoked list.

    The mirror of `add_revocation` -- the per-consumer un-revoke (P-0074).
    Idempotent: removing a consumer that is not listed simply yields a feed
    without it (only `updated` is bumped). `updated` is bumped to now.
    """
    if not consumer_id:
        raise RevocationFeedError("consumer_id must be non-empty")
    kept = [e for e in _revoked_list(feed)
            if e.get("consumer_id") != consumer_id]
    kept.sort(key=lambda e: e["consumer_id"])
    return {"schema": FEED_SCHEMA, "updated": _now(), "revoked": kept}


def sign_feed(feed_bytes: bytes, seed: bytes) -> str:
    """Return the b64url Ed25519 signature over `feed_bytes`."""
    return codec.b64url_encode(sign(feed_bytes, seed))


def verify_feed(feed_bytes: bytes, signature_b64: str,
                public_key: bytes) -> dict[str, Any]:
    """Verify the detached signature over `feed_bytes`; return the feed.

    Raises RevocationFeedError if the signature does not verify, the bytes
    are not JSON, or the parsed feed shape is invalid.
    """
    try:
        sig = codec.b64url_decode(signature_b64.strip())
    except (ValueError, TypeError) as exc:
        raise RevocationFeedError(f"signature is not valid base64url: {exc}")
    if not verify(feed_bytes, sig, public_key):
        raise RevocationFeedError("revocation feed signature does not verify")
    try:
        feed = json.loads(feed_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RevocationFeedError(f"revocation feed is not valid JSON: {exc}")
    validate_feed(feed)
    return feed


def write_feed(feed_path: Path, sig_path: Path, feed: dict[str, Any],
               seed: bytes) -> bytes:
    """Serialize, sign, and write the feed + detached signature.

    Returns the exact feed bytes that were written and signed.
    """
    feed_bytes = serialize_feed(feed)
    feed_path.write_bytes(feed_bytes)
    sig_path.write_text(sign_feed(feed_bytes, seed) + "\n", encoding="utf-8")
    return feed_bytes


def load_feed(feed_path: Path, sig_path: Path,
              public_key: bytes) -> dict[str, Any]:
    """Read and verify a feed + detached signature from disk; return it."""
    if not feed_path.exists():
        raise RevocationFeedError(f"revocation feed missing: {feed_path}")
    if not sig_path.exists():
        raise RevocationFeedError(f"revocation signature missing: {sig_path}")
    return verify_feed(feed_path.read_bytes(),
                       sig_path.read_text(encoding="utf-8"), public_key)


def sig_url_for(feed_url: str) -> str:
    """Return the detached-signature URL for a revocation feed URL."""
    return feed_url + ".sig"


def feed_cache_path(project_root: Path) -> Path:
    """Return the temp-dir path of the revocation-feed cache for a repo.

    The cache holds the last successfully fetched+verified feed, the times
    of the last fetch and last fetch attempt, and the first-seen time -- so
    `auth-guard` polls at most once per TTL and `doctor` can report status.
    Keyed by the repo path so distinct repos never share a cache.
    """
    tag = hashlib.sha256(str(project_root).encode("utf-8")).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"gc_revfeed_{tag}.json"


def evaluate(feed: dict[str, Any] | None, consumer_id: str,
             max_offline_days: int, fetched_at: datetime.datetime | None,
             first_seen: datetime.datetime,
             now: datetime.datetime) -> tuple[bool, str, str]:
    """Decide whether `consumer_id` may proceed, given the revocation feed.

    `feed` is the last successfully verified feed, or None if one has never
    been fetched. `fetched_at` is when that feed was fetched; `first_seen`
    is when `auth-guard` first ran for this consumer; `now` is the current
    time. Returns (allowed, category, reason) where category is one of:

      - "current"  feed present and recently fetched     -> allowed
      - "grace"    no feed yet, within the grace window   -> allowed
      - "revoked"  consumer_id is on the feed             -> blocked
      - "offline"  feed too stale, or grace exceeded      -> blocked
        (cannot confirm the consumer was not revoked since the last fetch)
    """
    if feed is not None:
        if is_revoked(feed, consumer_id):
            return (False, "revoked",
                    f"consumer {consumer_id!r} is on the revocation feed")
        if fetched_at is not None:
            offline = (now - fetched_at).days
            if offline > max_offline_days:
                return (False, "offline",
                        f"revocation feed not refreshed for {offline} days "
                        f"(max_offline_days={max_offline_days})")
        return (True, "current", "revocation feed current")
    grace = (now - first_seen).days
    if grace > max_offline_days:
        return (False, "offline",
                f"revocation feed never reached in {grace} days "
                f"(max_offline_days={max_offline_days})")
    return (True, "grace", f"revocation feed not yet reached "
            f"(grace {grace}/{max_offline_days} days)")
