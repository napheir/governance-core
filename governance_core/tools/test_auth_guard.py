"""Test harness for auth-guard.py (P-0071).

Two groups, driving the real auth-guard.py as a subprocess inside
throwaway repo trees:

  * verdict cache (P-0071 Phase 1) -- a stale (prior-day) `valid: true`
    verdict must not be honored; a same-day verdict is. Uses an
    unverifiable code: this group is about cache freshness only.

  * revocation gate (P-0071 Phase 3) -- a schema-2 code is checked against
    the signed revocation feed: reachable+clean allows, revoked blocks,
    an unreachable feed within grace allows, and a pre-seeded stale /
    grace-exceeded cache blocks. These need a real-key-signed code (the
    feed and code verify against the bundled public key), so they are
    skipped with a notice when ~/.governance-core/signing_key.json is
    absent -- on a maintainer machine they run.

Run from any clone:
    python tools/test_auth_guard.py
"""
import datetime
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import governance_core
from governance_core.auth import codec, revocation

BAD_CODE = "GC1.eyJzY2hlbWEiOjF9.aaaa"
KEY_PATH = Path.home() / ".governance-core" / "signing_key.json"


def out(line: str) -> None:
    """Write `line` + newline to stdout (constitution Art.7: no print)."""
    sys.stdout.write(line + "\n")


def _pkg_hook() -> Path:
    """Return the package-source auth-guard.py path."""
    return Path(governance_core.__file__).resolve().parent \
        / "hooks" / "auth-guard.py"


def _run_hook(hook: Path) -> int:
    """Run `hook` as a PreToolUse subprocess; return its exit code."""
    return subprocess.run(
        [sys.executable, str(hook)], input="{}",
        capture_output=True, text=True, timeout=30).returncode


def _make_repo(auth_code: str) -> tuple[Path, Path]:
    """Create a throwaway repo with auth-guard + config; return (root, hook)."""
    tmp = Path(tempfile.mkdtemp(prefix="gc_authguard_test_"))
    hook = tmp / ".claude" / "hooks" / "auth-guard.py"
    hook.parent.mkdir(parents=True)
    shutil.copy2(_pkg_hook(), hook)
    # P-0082: auth-guard imports the vendored `_gc_auth` package installed
    # beside it (the installer copies governance_core/auth/ -> _gc_auth/).
    # Replicate that layout so the hook resolves its self-contained deps.
    auth_src = Path(governance_core.__file__).resolve().parent / "auth"
    shutil.copytree(auth_src, hook.parent / "_gc_auth",
                    ignore=shutil.ignore_patterns("__pycache__"))
    cfg = tmp / ".governance" / "config.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(json.dumps({"authorization": {"auth_code": auth_code}}),
                   encoding="utf-8")
    return tmp, hook


def _cleanup(tmp: Path) -> None:
    """Remove a throwaway repo and its temp-dir caches."""
    tag = hashlib.sha256(str(tmp).encode("utf-8")).hexdigest()[:16]
    for cache in (Path(tempfile.gettempdir()) / f"gc_auth_{tag}.json",
                  revocation.feed_cache_path(tmp)):
        try:
            cache.unlink()
        except OSError:
            pass
    shutil.rmtree(tmp, ignore_errors=True)


def _check(label: str, hook: Path, expect: int) -> bool:
    """Run `hook`, compare its exit code to `expect`, report, return pass."""
    rc = _run_hook(hook)
    ok = rc == expect
    out(f"{'[OK]  ' if ok else '[FAIL]'} {label} (exit {rc}, want {expect})")
    return ok


def _cache_cases() -> list[bool]:
    """Phase-1 verdict-cache freshness cases."""
    tmp, hook = _make_repo(BAD_CODE)
    results: list[bool] = []
    try:
        tag = hashlib.sha256(str(tmp).encode("utf-8")).hexdigest()[:16]
        cache = Path(tempfile.gettempdir()) / f"gc_auth_{tag}.json"
        code_sha = hashlib.sha256(BAD_CODE.encode("utf-8")).hexdigest()
        pub_sha = hashlib.sha256(codec.load_bundled_public_key()).hexdigest()
        today = datetime.date.today().isoformat()
        yesterday = (datetime.date.today()
                     - datetime.timedelta(days=1)).isoformat()

        def _seed(verified_on: str, valid: bool) -> None:
            cache.write_text(json.dumps({
                "code_sha256": code_sha, "pubkey_sha256": pub_sha,
                "verified_on": verified_on, "valid": valid}), encoding="utf-8")

        if cache.exists():
            cache.unlink()
        results.append(_check("no cache -> block", hook, 2))
        _seed(yesterday, True)
        results.append(_check("stale valid:true not honored -> block",
                               hook, 2))
        _seed(today, True)
        results.append(_check("same-day valid:true honored -> allow",
                               hook, 0))
        _seed(today, False)
        results.append(_check("same-day valid:false honored -> block",
                               hook, 2))
    finally:
        _cleanup(tmp)
    return results


def _schema2_code(seed: bytes, consumer_id: str, feed_url: str) -> str:
    """Build a real-key-signed schema-2 code for the revocation cases."""
    payload = codec.canonical_payload(
        consumer_id, "2026-05-18", "2027-05-18", schema=2,
        revocation_feed_url=feed_url, max_offline_days=30)
    return codec.make_auth_code(payload, seed)


def _iso_days_ago(days: int) -> str:
    """Return an ISO-8601 'Z' timestamp `days` in the past."""
    return (datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _revocation_cases() -> list[bool]:
    """Phase-3 revocation-gate cases (need the real signing key)."""
    if not KEY_PATH.exists():
        out("[SKIP] revocation cases -- no signing key at "
            f"{KEY_PATH} (run on a maintainer machine to exercise them)")
        return []

    seed = codec.b64url_decode(
        json.loads(KEY_PATH.read_text(encoding="utf-8"))["seed_b64"])
    results: list[bool] = []

    # 1. feed reachable + consumer not listed -> allow
    tmp, hook = _make_repo("placeholder")
    try:
        fp, sp = tmp / "revocation.json", tmp / "revocation.json.sig"
        revocation.write_feed(fp, sp, revocation.new_feed(), seed)
        code = _schema2_code(seed, "acme", fp.as_uri())
        (tmp / ".governance" / "config.json").write_text(
            json.dumps({"authorization": {"auth_code": code}}),
            encoding="utf-8")
        results.append(_check("schema-2, feed reachable + clean -> allow",
                               hook, 0))
    finally:
        _cleanup(tmp)

    # 2. feed reachable + consumer revoked -> block
    tmp, hook = _make_repo("placeholder")
    try:
        fp, sp = tmp / "revocation.json", tmp / "revocation.json.sig"
        feed = revocation.add_revocation(revocation.new_feed(), "acme",
                                         "left org")
        revocation.write_feed(fp, sp, feed, seed)
        code = _schema2_code(seed, "acme", fp.as_uri())
        (tmp / ".governance" / "config.json").write_text(
            json.dumps({"authorization": {"auth_code": code}}),
            encoding="utf-8")
        results.append(_check("schema-2, consumer revoked -> block", hook, 2))
    finally:
        _cleanup(tmp)

    # 3. feed unreachable, fresh install within grace -> allow
    tmp, hook = _make_repo("placeholder")
    try:
        missing = (tmp / "no-such-feed.json").as_uri()
        code = _schema2_code(seed, "acme", missing)
        (tmp / ".governance" / "config.json").write_text(
            json.dumps({"authorization": {"auth_code": code}}),
            encoding="utf-8")
        results.append(_check("schema-2, feed unreachable + grace -> allow",
                               hook, 0))
    finally:
        _cleanup(tmp)

    # 4. pre-seeded cache: no feed ever, grace exceeded -> block
    tmp, hook = _make_repo("placeholder")
    try:
        missing = (tmp / "no-such-feed.json").as_uri()
        code = _schema2_code(seed, "acme", missing)
        (tmp / ".governance" / "config.json").write_text(
            json.dumps({"authorization": {"auth_code": code}}),
            encoding="utf-8")
        revocation.feed_cache_path(tmp).write_text(json.dumps({
            "feed_url": missing, "first_seen": _iso_days_ago(40),
            "last_attempt_at": _iso_days_ago(0), "fetched_at": None,
            "feed": None}), encoding="utf-8")
        results.append(_check("schema-2, no feed past grace -> block",
                               hook, 2))
    finally:
        _cleanup(tmp)

    # 5. pre-seeded cache: stale feed beyond max_offline_days -> block
    tmp, hook = _make_repo("placeholder")
    try:
        missing = (tmp / "no-such-feed.json").as_uri()
        code = _schema2_code(seed, "acme", missing)
        (tmp / ".governance" / "config.json").write_text(
            json.dumps({"authorization": {"auth_code": code}}),
            encoding="utf-8")
        revocation.feed_cache_path(tmp).write_text(json.dumps({
            "feed_url": missing, "first_seen": _iso_days_ago(60),
            "last_attempt_at": _iso_days_ago(0),
            "fetched_at": _iso_days_ago(40),
            "feed": revocation.new_feed()}), encoding="utf-8")
        results.append(_check("schema-2, stale feed past max_offline -> block",
                               hook, 2))
    finally:
        _cleanup(tmp)

    return results


def main() -> int:
    """Run the cache + revocation groups; exit non-zero on any failure."""
    if not _pkg_hook().exists():
        out(f"[FAIL] package hook missing: {_pkg_hook()}")
        return 1
    results = _cache_cases() + _revocation_cases()
    passed, total = sum(results), len(results)
    out(f"\n{passed}/{total} auth-guard cases passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
