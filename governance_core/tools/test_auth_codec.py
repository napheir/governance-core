"""Test harness for governance_core.auth.codec (P-0071 Phase 1).

Covers the authorization-code codec (schema 2 only since P-0132):
  - schema 1 (retired perpetual) refused
  - schema 2 (leased + revocable) round-trip + required-field enforcement
  - expiry checking
  - malformed / tampered / unknown-schema rejection

Uses a throwaway keypair generated per run -- never the real signing key.

Run from any clone:
    python tools/test_auth_codec.py
"""
import json
import sys

from governance_core import auth
from governance_core.auth import codec

_FEED = "https://example.invalid/revocation.json"


def out(line: str) -> None:
    """Write `line` + newline to stdout (constitution Art.7: no print)."""
    sys.stdout.write(line + "\n")


def _case(label: str, fn) -> bool:
    """Run `fn`; return True iff it returns True without raising."""
    try:
        ok = fn()
    except Exception as exc:  # noqa: BLE001 - a raising case is a failure
        out(f"[FAIL] {label}: unexpected {type(exc).__name__}: {exc}")
        return False
    if ok:
        out(f"[OK]   {label}")
        return True
    out(f"[FAIL] {label}")
    return False


def _raises(label: str, fn, exc_type=codec.AuthCodeError) -> bool:
    """Run `fn`; return True iff it raises `exc_type`."""
    try:
        fn()
    except exc_type:
        out(f"[OK]   {label}")
        return True
    except Exception as exc:  # noqa: BLE001
        out(f"[FAIL] {label}: raised {type(exc).__name__}, want "
            f"{exc_type.__name__}")
        return False
    out(f"[FAIL] {label}: did not raise")
    return False


def _sign(payload: bytes, seed: bytes) -> str:
    """Build a GC1 code from raw `payload` bytes signed with `seed`."""
    return codec.make_auth_code(payload, seed)


def _schema1_payload() -> bytes:
    """A retired schema-1 payload (no expiry, no feed), built by hand."""
    return json.dumps({"consumer_id": "acme", "issued": "2026-05-18",
                       "schema": 1},
                      sort_keys=True, separators=(",", ":")).encode("utf-8")


def test_schema1_refused_by_codec() -> None:
    """P-0132: a correctly signed schema-1 (perpetual) code no longer verifies."""
    seed = auth.generate_seed()
    code = _sign(_schema1_payload(), seed)
    try:
        codec.verify_auth_code(code, auth.public_key_from_seed(seed))
    except codec.AuthCodeError as exc:
        assert "schema" in str(exc)
    else:
        raise AssertionError("schema-1 code verified")


def test_per_code_fingerprint_is_sha256_of_stripped_code() -> None:
    """The fingerprint identifies one code; surrounding whitespace is ignored."""
    import hashlib
    code = "GC1.payload.sig"
    assert codec.code_fingerprint(code) == codec.code_fingerprint(f"  {code}\n")
    assert codec.code_fingerprint(code) == hashlib.sha256(code.encode()).hexdigest()


def main() -> int:
    """Run every codec case; exit non-zero on any failure."""
    seed = auth.generate_seed()
    pub = auth.public_key_from_seed(seed)
    results: list[bool] = []

    # --- schema 1: retired (P-0132) ------------------------------------
    code_s1 = _sign(_schema1_payload(), seed)
    results.append(_raises(
        "schema-1 perpetual code refused",
        lambda: codec.verify_auth_code(code_s1, pub)))
    results.append(_raises(
        "canonical_payload refuses to build schema 1",
        lambda: codec.canonical_payload("acme", "2026-05-18", schema=1),
        exc_type=ValueError))

    # --- schema 2 -----------------------------------------------------
    s2 = codec.canonical_payload(
        "acme", "2026-05-18", "2027-05-18", schema=2,
        revocation_feed_url=_FEED, max_offline_days=30)
    code_s2 = _sign(s2, seed)

    def _s2_fields() -> bool:
        p = codec.verify_auth_code(code_s2, pub, today="2026-06-01")
        return (p["schema"] == 2 and p["revocation_feed_url"] == _FEED
                and p["max_offline_days"] == 30)

    results.append(_case("schema-2 round-trip carries feed + bound",
                          _s2_fields))
    results.append(_raises(
        "schema-2 past expiry rejected",
        lambda: codec.verify_auth_code(code_s2, pub, today="2027-06-01")))

    # schema-2 payload missing a required field (hand-built, then signed)
    bad = json.dumps(
        {"consumer_id": "acme", "issued": "2026-05-18", "schema": 2,
         "expiry": "2027-05-18"},
        sort_keys=True, separators=(",", ":")).encode("utf-8")
    code_bad = _sign(bad, seed)
    results.append(_raises(
        "schema-2 missing revocation_feed_url rejected",
        lambda: codec.verify_auth_code(code_bad, pub, today="2026-06-01")))

    # schema-2 with non-positive max_offline_days
    bad2 = json.dumps(
        {"consumer_id": "acme", "issued": "2026-05-18", "schema": 2,
         "expiry": "2027-05-18", "revocation_feed_url": _FEED,
         "max_offline_days": 0},
        sort_keys=True, separators=(",", ":")).encode("utf-8")
    code_bad2 = _sign(bad2, seed)
    results.append(_raises(
        "schema-2 max_offline_days=0 rejected",
        lambda: codec.verify_auth_code(code_bad2, pub, today="2026-06-01")))

    # canonical_payload itself rejects an incomplete schema-2 build
    results.append(_raises(
        "canonical_payload schema-2 missing fields raises ValueError",
        lambda: codec.canonical_payload("acme", "2026-05-18", schema=2),
        exc_type=ValueError))

    # --- malformed / tampered / unknown schema ------------------------
    results.append(_raises(
        "malformed code (no GC1 prefix) rejected",
        lambda: codec.verify_auth_code("not.a.code", pub)))

    tampered = code_s2[:-4] + ("AAAA" if code_s2[-4:] != "AAAA" else "BBBB")
    results.append(_raises(
        "tampered signature rejected",
        lambda: codec.verify_auth_code(tampered, pub, today="2026-06-01")))

    unknown = json.dumps(
        {"consumer_id": "acme", "issued": "2026-05-18", "schema": 99},
        sort_keys=True, separators=(",", ":")).encode("utf-8")
    code_unknown = _sign(unknown, seed)
    results.append(_raises(
        "unknown schema rejected",
        lambda: codec.verify_auth_code(code_unknown, pub)))

    passed = sum(results)
    total = len(results)
    out(f"\n{passed}/{total} codec cases passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
