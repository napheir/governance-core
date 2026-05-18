"""Test harness for governance_core.auth.revocation (P-0071 Phase 2).

Covers the signed revocation feed:
  - new / serialize / validate feed shape
  - add_revocation (idempotent) + is_revoked membership
  - detached signature: sign -> verify round-trip
  - rejection of a tampered feed, a wrong signature, malformed bytes
  - write_feed / load_feed round-trip on disk

Uses a throwaway keypair generated per run -- never the real signing key.

Run from any clone:
    python tools/test_revocation.py
"""
import datetime
import json
import shutil
import sys
import tempfile
from pathlib import Path

from governance_core import auth
from governance_core.auth import revocation
from governance_core.candidates import registry


def out(line: str) -> None:
    """Write `line` + newline to stdout (constitution Art.7: no print)."""
    sys.stdout.write(line + "\n")


def _case(label: str, fn) -> bool:
    """Run `fn`; return True iff it returns True without raising."""
    try:
        ok = fn()
    except Exception as exc:  # noqa: BLE001
        out(f"[FAIL] {label}: unexpected {type(exc).__name__}: {exc}")
        return False
    out((f"[OK]   {label}") if ok else f"[FAIL] {label}")
    return bool(ok)


def _raises(label: str, fn) -> bool:
    """Run `fn`; return True iff it raises RevocationFeedError."""
    try:
        fn()
    except revocation.RevocationFeedError:
        out(f"[OK]   {label}")
        return True
    except Exception as exc:  # noqa: BLE001
        out(f"[FAIL] {label}: raised {type(exc).__name__}, want "
            f"RevocationFeedError")
        return False
    out(f"[FAIL] {label}: did not raise")
    return False


def main() -> int:
    """Run every revocation-feed case; exit non-zero on any failure."""
    seed = auth.generate_seed()
    pub = auth.public_key_from_seed(seed)
    other_pub = auth.public_key_from_seed(auth.generate_seed())
    results: list[bool] = []

    # --- feed shape ---------------------------------------------------
    empty = revocation.new_feed()
    results.append(_case(
        "new_feed is empty schema-1",
        lambda: empty["schema"] == 1 and empty["revoked"] == []
        and bool(empty["updated"])))

    # --- add_revocation / is_revoked ----------------------------------
    feed = revocation.add_revocation(empty, "acme", "left org",
                                     revoked_on="2026-05-18")
    results.append(_case("is_revoked false before, true after",
                          lambda: (not revocation.is_revoked(empty, "acme"))
                          and revocation.is_revoked(feed, "acme")))

    twice = revocation.add_revocation(feed, "acme", "refresh")
    results.append(_case(
        "add_revocation idempotent (no duplicate)",
        lambda: sum(e["consumer_id"] == "acme"
                    for e in twice["revoked"]) == 1))

    # --- sign / verify round-trip -------------------------------------
    feed_bytes = revocation.serialize_feed(feed)
    sig = revocation.sign_feed(feed_bytes, seed)
    results.append(_case(
        "sign -> verify round-trip returns feed",
        lambda: revocation.verify_feed(feed_bytes, sig, pub)["revoked"][0]
        ["consumer_id"] == "acme"))

    # --- rejection cases ----------------------------------------------
    tampered = feed_bytes.replace(b"left org", b"LEFT ORG")
    results.append(_raises(
        "tampered feed bytes rejected",
        lambda: revocation.verify_feed(tampered, sig, pub)))
    results.append(_raises(
        "feed verified against wrong key rejected",
        lambda: revocation.verify_feed(feed_bytes, sig, other_pub)))
    results.append(_raises(
        "non-JSON feed bytes rejected",
        lambda: revocation.verify_feed(
            b"not json", revocation.sign_feed(b"not json", seed), pub)))

    bad_schema = revocation.serialize_feed(
        {"schema": 99, "updated": "x", "revoked": []})
    results.append(_raises(
        "unknown feed schema rejected",
        lambda: revocation.verify_feed(
            bad_schema, revocation.sign_feed(bad_schema, seed), pub)))

    bad_entry = revocation.serialize_feed(
        {"schema": 1, "updated": "x", "revoked": [{"reason": "no id"}]})
    results.append(_raises(
        "revoked entry without consumer_id rejected",
        lambda: revocation.verify_feed(
            bad_entry, revocation.sign_feed(bad_entry, seed), pub)))

    # --- write_feed / load_feed on disk -------------------------------
    tmp = Path(tempfile.mkdtemp(prefix="gc_revocation_test_"))
    try:
        fp, sp = tmp / "revocation.json", tmp / "revocation.json.sig"
        revocation.write_feed(fp, sp, feed, seed)
        results.append(_case(
            "write_feed -> load_feed round-trip",
            lambda: revocation.is_revoked(
                revocation.load_feed(fp, sp, pub), "acme")))
        # corrupt the on-disk feed -> load must reject
        fp.write_bytes(fp.read_bytes().replace(b"acme", b"evil"))
        results.append(_raises(
            "load_feed rejects a feed edited after signing",
            lambda: revocation.load_feed(fp, sp, pub)))

        # registry mark_revoked -- the consumer-registry side of revocation
        reg = tmp / "registry.json"
        registry.record_consumer(reg, "acme", "2026-05-18")
        results.append(_case(
            "mark_revoked returns True for a registered consumer",
            lambda: registry.mark_revoked(
                reg, "acme", "2026-05-18", "left org") is True))
        results.append(_case(
            "revoked consumer entry carries status=revoked",
            lambda: registry.load_registry(reg)["consumers"][0]["status"]
            == "revoked"))
        results.append(_case(
            "mark_revoked returns False for an unregistered consumer",
            lambda: registry.mark_revoked(reg, "ghost", "2026-05-18")
            is False))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # --- evaluate(): the auth-guard revocation decision ---------------
    now = datetime.datetime.now(datetime.timezone.utc)
    recent = now - datetime.timedelta(days=2)
    old = now - datetime.timedelta(days=40)
    clean = revocation.new_feed()
    revoked_feed = revocation.add_revocation(clean, "acme", "left org")

    def _ev_is(feed, fetched, first, allowed, category) -> bool:
        a, c, _ = revocation.evaluate(feed, "acme", 30, fetched, first, now)
        return a is allowed and c == category

    results.append(_case(
        "evaluate: revoked consumer -> blocked/revoked",
        lambda: _ev_is(revoked_feed, recent, recent, False, "revoked")))
    results.append(_case(
        "evaluate: clean feed freshly fetched -> allowed/current",
        lambda: _ev_is(clean, recent, recent, True, "current")))
    results.append(_case(
        "evaluate: clean feed stale beyond max_offline -> blocked/offline",
        lambda: _ev_is(clean, old, old, False, "offline")))
    results.append(_case(
        "evaluate: no feed within grace -> allowed/grace",
        lambda: _ev_is(None, None, recent, True, "grace")))
    results.append(_case(
        "evaluate: no feed past grace -> blocked/offline",
        lambda: _ev_is(None, None, old, False, "offline")))

    passed, total = sum(results), len(results)
    out(f"\n{passed}/{total} revocation cases passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
