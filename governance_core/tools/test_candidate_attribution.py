"""Test harness for candidate attribution + registry schema (P-0071 Phase 4).

Covers:
  - consumer registry schema 2: record_consumer entry shape, first_issued
    preserved across re-issue, is_consumer_revoked, schema-1 -> 2 migration
  - uplink origin binding: a candidate's `origin` must match the verified
    authorization code's consumer_id, else uplink_envelope aborts

The uplink cases need a real-key-signed code (codes verify against the
bundled public key), so they are skipped with a notice when
~/.governance-core/signing_key.json is absent.

Run from any clone:
    python tools/test_candidate_attribution.py
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

from governance_core.auth import codec
from governance_core.candidates import envelope, registry, uplink

KEY_PATH = Path.home() / ".governance-core" / "signing_key.json"


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
    """Run `fn`; return True iff it raises UplinkError."""
    try:
        fn()
    except uplink.UplinkError:
        out(f"[OK]   {label}")
        return True
    except Exception as exc:  # noqa: BLE001
        out(f"[FAIL] {label}: raised {type(exc).__name__}, want UplinkError")
        return False
    out(f"[FAIL] {label}: did not raise")
    return False


def _registry_cases() -> list[bool]:
    """Consumer-registry schema-2 cases (no key needed)."""
    results: list[bool] = []
    tmp = Path(tempfile.mkdtemp(prefix="gc_cand_attr_test_"))
    try:
        reg = tmp / "consumer_registry.json"
        registry.record_consumer(reg, "acme", "2026-05-18",
                                 expiry="2027-05-18")
        entry = registry.load_registry(reg)["consumers"][0]
        results.append(_case(
            "record_consumer writes schema-2 entry (active + dates)",
            lambda: entry["status"] == "active"
            and entry["first_issued"] == "2026-05-18"
            and entry["last_issued"] == "2026-05-18"))

        registry.record_consumer(reg, "acme", "2026-08-01",
                                 expiry="2027-08-01")
        reissued = registry.load_registry(reg)["consumers"][0]
        results.append(_case(
            "re-issue preserves first_issued, advances last_issued",
            lambda: reissued["first_issued"] == "2026-05-18"
            and reissued["last_issued"] == "2026-08-01"))

        results.append(_case(
            "is_consumer_revoked False for an active consumer",
            lambda: registry.is_consumer_revoked(reg, "acme") is False))
        results.append(_case(
            "is_consumer_revoked False for an unknown consumer",
            lambda: registry.is_consumer_revoked(reg, "ghost") is False))
        registry.mark_revoked(reg, "acme", "2026-09-01", "left org")
        results.append(_case(
            "is_consumer_revoked True after mark_revoked",
            lambda: registry.is_consumer_revoked(reg, "acme") is True))

        # schema-1 registry -> migrated on load
        legacy = tmp / "legacy_registry.json"
        legacy.write_text(json.dumps({
            "schema": 1, "consumers": [
                {"consumer_id": "old", "issued": "2026-01-01",
                 "expiry": None, "note": "", "recorded_at": "2026-01-01T0Z"}],
            "candidates": []}), encoding="utf-8")
        migrated = registry.load_registry(legacy)
        results.append(_case(
            "schema-1 registry migrates to schema 2 on load",
            lambda: migrated["schema"] == 2
            and migrated["consumers"][0]["status"] == "active"
            and migrated["consumers"][0]["first_issued"] == "2026-01-01"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return results


def _uplink_origin_cases() -> list[bool]:
    """Uplink origin-binding cases (need the real signing key)."""
    if not KEY_PATH.exists():
        out(f"[SKIP] uplink origin cases -- no signing key at {KEY_PATH}")
        return []

    seed = codec.b64url_decode(
        json.loads(KEY_PATH.read_text(encoding="utf-8"))["seed_b64"])

    def _code(consumer_id: str) -> str:
        payload = codec.canonical_payload(
            consumer_id, "2026-05-18", "2027-05-18", schema=2,
            revocation_feed_url="https://example.invalid/revocation.json",
            max_offline_days=30)
        return codec.make_auth_code(payload, seed)

    results: list[bool] = []
    tmp = Path(tempfile.mkdtemp(prefix="gc_cand_uplink_test_"))
    try:
        payload_file = tmp / "sample-skill.md"
        payload_file.write_text("# sample\n\nInnocuous candidate body.\n",
                                encoding="utf-8")
        env_dir = envelope.build_envelope(
            tmp / "outbox", kind="skill", origin="acme",
            title="sample skill", rationale="a common-layer candidate",
            payload_files=[payload_file])

        results.append(_case(
            "uplink dry-run allowed when origin matches code consumer_id",
            lambda: bool(uplink.uplink_envelope(
                env_dir, _code("acme"), dry_run=True))))
        results.append(_raises(
            "uplink aborts when origin != code consumer_id",
            lambda: uplink.uplink_envelope(
                env_dir, _code("other-org"), dry_run=True)))
        results.append(_raises(
            "uplink aborts on an unverifiable auth code",
            lambda: uplink.uplink_envelope(
                env_dir, "GC1.bad.code", dry_run=True)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return results


def main() -> int:
    """Run registry + uplink-origin groups; exit non-zero on any failure."""
    results = _registry_cases() + _uplink_origin_cases()
    passed, total = sum(results), len(results)
    out(f"\n{passed}/{total} candidate-attribution cases passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
