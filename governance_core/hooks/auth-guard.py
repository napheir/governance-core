"""Claude Code PreToolUse hook: auth-guard.py

Runtime authorization enforcement (P-0065 Phase 1, P-0071). Fires before
EVERY tool call and blocks it unless the project's governance-core
authorization is valid. Two gates run in order:

  1. Code verification -- the stored authorization code must verify against
     the bundled public key and must not be expired. The verdict is cached
     per (repo, code, public key, date): re-checked once per day so an
     expired code is never served a stale `valid`.

  2. Revocation (schema-2 codes only) -- the code's consumer_id must not
     appear on the maintainer's signed revocation feed. `auth-guard` polls
     the feed URL carried in the code, at most once per TTL, caching the
     last verified feed. If the feed cannot be reached, the last cached
     feed is used; once no successful fetch has happened for the code's
     `max_offline_days`, the consumer is frozen. A schema-1 (legacy
     perpetual) code carries no feed and skips this gate.

Together with the install-time gate this makes "invalid or revoked
authorization -> no capabilities" hold continuously. The freeze affects
the agent's tool calls only; the human's own shell is unaffected, so
recovery is always possible.

Fail-closed for verification: any error -- missing config, broken package,
unreadable key -- blocks. Fetch failures are NOT fail-open: they fall back
to the cached feed and, past max_offline_days, to a freeze.

Exit codes:
  0 = authorized (allow)
  2 = unauthorized (block)
"""
import datetime
import hashlib
import json
import sys
import tempfile
import urllib.request
from pathlib import Path

# P-0082: auth-guard is self-contained -- it imports the auth primitives from
# the vendored `_gc_auth` package installed beside this hook, NOT from
# `governance_core`. A fail-closed per-call gate must never depend on the
# package being importable, or a broken/uninstalled package would freeze every
# tool call (issue #3 / runtime-import-discipline). `_gc_auth` is a copy of
# governance_core/auth/ written by the installer; same code, no namespace dep.
_HOOK_DIR = Path(__file__).resolve().parent
if str(_HOOK_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOK_DIR))

_BLOCK_HEADER = (
    "[AUTH GUARD] BLOCKED: governance-core authorization is invalid, "
    "missing, or revoked -- all capabilities are disabled."
)
_RECOVER_INSTALL = (
    "  Recover: run  governance-core install --auth-code <CODE>  in a "
    "terminal (capabilities are gated on a valid maintainer-issued code; "
    "see README 'Authorization')."
)
_RECOVER_REVOKED = (
    "  This consumer_id is on the maintainer's revocation feed. "
    "Re-installing will not help -- contact the governance-core maintainer."
)
_RECOVER_OFFLINE = (
    "  The signed revocation feed could not be reached within the code's "
    "max_offline_days. Restore network access so auth-guard can refresh it."
)

# Poll the revocation feed at most once per this window (and retry a failed
# fetch no more often than this) -- keeps the hook off the network on the
# vast majority of tool calls.
_FEED_TTL = datetime.timedelta(hours=6)
_FETCH_TIMEOUT_SECONDS = 8


def _block(detail: str, recover: str) -> None:
    """Emit the block message with `detail` and exit 2 (deny the tool call)."""
    sys.stderr.write(f"{_BLOCK_HEADER}\n  Reason: {detail}\n{recover}\n")
    sys.exit(2)


def _now() -> datetime.datetime:
    """Return the current time as an aware UTC datetime."""
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(dt: datetime.datetime) -> str:
    """Format `dt` as an ISO-8601 'Z' string."""
    return dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(text: str) -> datetime.datetime:
    """Parse an ISO-8601 'Z' string into an aware UTC datetime."""
    return datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))


def _verify_code(auth_code: str, public_key: bytes) -> bool:
    """Verify `auth_code` (signature + expiry); return True iff valid."""
    from _gc_auth import codec
    try:
        codec.verify_auth_code(auth_code, public_key)
        return True
    except codec.AuthCodeError:
        return False


def _fetch_feed(feed_url: str, public_key: bytes):
    """Fetch + verify the revocation feed; return the feed dict or None.

    Any failure -- network error, HTTP error, or a signature that does not
    verify -- yields None. A forged feed is therefore treated as no feed,
    never as a trusted empty one.
    """
    from _gc_auth import revocation
    try:
        with urllib.request.urlopen(
                feed_url, timeout=_FETCH_TIMEOUT_SECONDS) as resp:
            feed_bytes = resp.read()
        with urllib.request.urlopen(
                revocation.sig_url_for(feed_url),
                timeout=_FETCH_TIMEOUT_SECONDS) as resp:
            sig_text = resp.read().decode("utf-8")
        return revocation.verify_feed(feed_bytes, sig_text, public_key)
    except Exception:  # noqa: BLE001 - any failure -> treat as no feed
        return None


def _revocation_gate(root: Path, consumer_id: str, feed_url: str,
                     max_offline_days: int, public_key: bytes):
    """Evaluate the revocation feed for `consumer_id`; return (allowed, reason).

    Maintains a temp-dir feed cache so the network is touched at most once
    per `_FEED_TTL`. The cache holds the last verified feed, the last
    successful-fetch and last-attempt times, and the first-seen time.
    """
    from _gc_auth import revocation
    cache_path = revocation.feed_cache_path(root)
    now = _now()

    fresh = {"feed_url": feed_url, "first_seen": _iso(now),
             "last_attempt_at": None, "fetched_at": None, "feed": None}
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        if cache.get("feed_url") != feed_url:
            cache = fresh  # code re-issued with a different feed -> reset
            dirty = True
        else:
            dirty = False
    except Exception:  # noqa: BLE001 - no/unreadable cache -> start fresh
        cache, dirty = fresh, True

    first_seen = _parse_iso(cache["first_seen"])
    fetched_at = (_parse_iso(cache["fetched_at"])
                  if cache.get("fetched_at") else None)
    last_attempt = (_parse_iso(cache["last_attempt_at"])
                    if cache.get("last_attempt_at") else None)
    feed = cache.get("feed")

    feed_fresh = fetched_at is not None and (now - fetched_at) < _FEED_TTL
    attempt_due = last_attempt is None or (now - last_attempt) >= _FEED_TTL
    if not feed_fresh and attempt_due:
        cache["last_attempt_at"] = _iso(now)
        dirty = True
        fetched = _fetch_feed(feed_url, public_key)
        if fetched is not None:
            feed = fetched
            fetched_at = now
            cache["feed"] = feed
            cache["fetched_at"] = _iso(now)

    if dirty:
        try:
            cache_path.write_text(json.dumps(cache), encoding="utf-8")
        except Exception:  # noqa: BLE001 - cache is best-effort
            pass

    return revocation.evaluate(feed, consumer_id, max_offline_days,
                               fetched_at, first_seen, now)


def main() -> None:
    """Block the pending tool call unless governance-core is authorized."""
    # Consume the hook payload to keep the stdin protocol clean (unused).
    try:
        json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        pass

    # repo root: hook lives at <repo>/.claude/hooks/auth-guard.py
    root = Path(__file__).resolve().parent.parent.parent
    cfg_path = root / ".governance" / "config.json"

    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        _block(f"cannot read .governance/config.json ({exc})",
               _RECOVER_INSTALL)

    if "authorization" not in cfg or "auth_code" not in cfg["authorization"]:
        _block("no authorization recorded in config.json", _RECOVER_INSTALL)
    auth_code = cfg["authorization"]["auth_code"]

    try:
        from _gc_auth import codec
        public_key = codec.load_bundled_public_key()
    except Exception as exc:  # noqa: BLE001
        _block(f"governance-core package public key unavailable ({exc})",
               _RECOVER_INSTALL)

    # --- Gate 1: code verification (signature + expiry), date-keyed cache --
    code_sha = hashlib.sha256(auth_code.encode("utf-8")).hexdigest()
    pub_sha = hashlib.sha256(public_key).hexdigest()
    root_tag = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:16]
    cache_path = Path(tempfile.gettempdir()) / f"gc_auth_{root_tag}.json"
    today = datetime.date.today().isoformat()

    valid = None
    try:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if (cached["code_sha256"] == code_sha
                and cached["pubkey_sha256"] == pub_sha
                and cached.get("verified_on") == today):
            valid = cached["valid"]
    except Exception:  # noqa: BLE001 - no/stale/unreadable cache -> verify
        pass

    if valid is None:
        valid = _verify_code(auth_code, public_key)
        try:
            cache_path.write_text(
                json.dumps({"code_sha256": code_sha, "pubkey_sha256": pub_sha,
                            "verified_on": today, "valid": valid}),
                encoding="utf-8")
        except Exception:  # noqa: BLE001 - cache is best-effort
            pass

    if not valid:
        _block("authorization code does not verify", _RECOVER_INSTALL)

    # --- Gate 2: revocation (schema-2 codes only) -------------------------
    try:
        from _gc_auth import codec
        payload = codec.decode_payload(auth_code)
    except Exception as exc:  # noqa: BLE001
        _block(f"cannot read authorization payload ({exc})", _RECOVER_INSTALL)

    if payload.get("schema") != 2:
        sys.exit(0)  # schema-1 legacy perpetual code: no revocation gate

    try:
        consumer_id = payload["consumer_id"]
        feed_url = payload["revocation_feed_url"]
        max_offline_days = payload["max_offline_days"]
    except KeyError as exc:
        _block(f"schema-2 payload missing {exc}", _RECOVER_INSTALL)

    allowed, category, reason = _revocation_gate(
        root, consumer_id, feed_url, max_offline_days, public_key)
    if allowed:
        sys.exit(0)
    recover = _RECOVER_REVOKED if category == "revoked" else _RECOVER_OFFLINE
    _block(reason, recover)


if __name__ == "__main__":
    main()
