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


# --- per-code revocation (P-0132), pytest-style ---------------------------

_FP_A = "a" * 64
_FP_B = "b" * 64


def test_per_code_entry_revokes_only_that_code() -> None:
    feed = revocation.add_revocation(revocation.new_feed(), "acme", "leaked",
                                     code_sha256=_FP_A)
    assert revocation.is_revoked(feed, "acme", _FP_A)
    assert not revocation.is_revoked(feed, "acme", _FP_B)
    assert not revocation.is_revoked(feed, "acme")  # consumer itself not revoked
    assert not revocation.is_revoked(feed, "other", _FP_A)


def test_per_code_consumer_wide_entry_still_revokes_every_code() -> None:
    feed = revocation.add_revocation(revocation.new_feed(), "acme", "left")
    assert revocation.is_revoked(feed, "acme")
    assert revocation.is_revoked(feed, "acme", _FP_B)


def test_per_code_entries_are_idempotent_and_independent() -> None:
    feed = revocation.new_feed()
    feed = revocation.add_revocation(feed, "acme", "x", code_sha256=_FP_A)
    feed = revocation.add_revocation(feed, "acme", "y", code_sha256=_FP_A)
    feed = revocation.add_revocation(feed, "acme", "left")
    assert len(feed["revoked"]) == 2
    restored = revocation.remove_revocation(feed, "acme")  # consumer-wide only
    assert revocation.is_revoked(restored, "acme", _FP_A)
    assert not revocation.is_revoked(restored, "acme", _FP_B)
    cleared = revocation.remove_code_revocation(restored, _FP_A)
    assert cleared["revoked"] == []


def test_per_code_feed_validation_rejects_bad_fingerprint() -> None:
    feed = revocation.new_feed()
    feed["revoked"] = [{"consumer_id": "acme", "revoked_on": "2026-11-05",
                        "reason": "", "code_sha256": "NOT-HEX"}]
    try:
        revocation.validate_feed(feed)
    except revocation.RevocationFeedError:
        pass
    else:
        raise AssertionError("bad code_sha256 accepted")
    try:
        revocation.add_revocation(revocation.new_feed(), "acme", "", code_sha256="x")
    except revocation.RevocationFeedError:
        pass
    else:
        raise AssertionError("add_revocation accepted a bad fingerprint")


def test_per_code_evaluate_blocks_the_revoked_code() -> None:
    now = datetime.datetime.now(datetime.timezone.utc)
    feed = revocation.add_revocation(revocation.new_feed(), "acme", "leaked",
                                     code_sha256=_FP_A)
    blocked = revocation.evaluate(feed, "acme", 30, now, now, now,
                                  code_sha256=_FP_A)
    allowed = revocation.evaluate(feed, "acme", 30, now, now, now,
                                  code_sha256=_FP_B)
    assert blocked[:2] == (False, "revoked")
    assert allowed[:2] == (True, "current")


def _v0484_accepts(feed_bytes: bytes) -> dict:
    """Feed parsing of clients before 0.49.0, frozen from v0.48.4's
    revocation.validate_feed (shipped tests cannot reach the hub's history).
    Signature checking is unchanged and covered above."""
    feed = json.loads(feed_bytes.decode("utf-8"))
    assert isinstance(feed, dict) and feed.get("schema") == 1
    assert feed.get("updated")
    revoked = feed.get("revoked")
    assert isinstance(revoked, list)
    for entry in revoked:
        if not isinstance(entry, dict) or not entry.get("consumer_id"):
            raise revocation.RevocationFeedError(
                "every revoked entry needs a non-empty consumer_id")
    return feed


def _v0484_is_revoked(feed: dict, consumer_id: str) -> bool:
    """v0.48.4's revocation.is_revoked: consumer_id match only."""
    return any(e.get("consumer_id") == consumer_id for e in feed["revoked"])


def test_per_code_feed_still_valid_for_clients_before_0_49() -> None:
    """Old clients require consumer_id in every entry and match on it alone:
    a per-code entry keeps the feed valid for them and reads as revoking the
    whole consumer -- never invalidates the feed (which would freeze every
    consumer after max_offline_days)."""
    feed = revocation.add_revocation(revocation.new_feed(), "governance-core",
                                     "leaked", code_sha256=_FP_A)
    parsed = _v0484_accepts(revocation.serialize_feed(feed))
    assert _v0484_is_revoked(parsed, "governance-core")
    assert not _v0484_is_revoked(parsed, "deva-vani")


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

    # --- remove_revocation (un-revoke, P-0074) ------------------------
    results.append(_case(
        "remove_revocation drops the consumer",
        lambda: not revocation.is_revoked(
            revocation.remove_revocation(feed, "acme"), "acme")))
    results.append(_case(
        "remove_revocation of an absent consumer is a no-op",
        lambda: revocation.remove_revocation(
            revocation.new_feed(), "ghost")["revoked"] == []))

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
        # mark_active -- the registry side of un-revoke (P-0074)
        results.append(_case(
            "mark_active clears revoked status back to active",
            lambda: registry.mark_active(reg, "acme") is True
            and registry.load_registry(reg)["consumers"][0]["status"]
            == "active"))
        results.append(_case(
            "mark_active drops revoked_on / revocation_reason",
            lambda: "revoked_on" not in
            registry.load_registry(reg)["consumers"][0]))
        results.append(_case(
            "mark_active returns False for an unregistered consumer",
            lambda: registry.mark_active(reg, "ghost") is False))
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
